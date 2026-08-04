# Capital Structure — authenticated observed share-count truth plane

Status: the original v1 pure kernel remains a lab/compatibility contract; the
separately authenticated materializer is implemented as a pre-production path.
Its daily R2 step remains hard-gated off. The retention planner exists, but its
production command is independently hard-disabled before credentials or remote
I/O until the deletion/fencing/capability release gates pass. No issuer or market coverage
is claimed until that gate is deliberately enabled and the lane publishes its
first externally witnessed receipt from retained Company Facts bytes.

Wave 5 adds the single signed write-ahead journal beneath the Wave 4 external
head fence. New writers no longer emit the legacy marker/capsule pair; legacy
readers remain only for drainage. The reader still accepts authenticated v2 and
scope-bound v3 heads at the same key, and only a default-off same-selection v2
to v3 migration exists. This wave does not add v3 genesis or successor
publication, retention authority, coverage, UI, or Prophet use.

Wave 6 adds the closed v4 witness contract, the v2/v3/v4 Synapse catalog union,
native v4 signing/authentication and test seam, exact v2-or-v3-to-v4 structural
migration, and v1/v2 journal recovery at that existing key. Production native
v4 genesis/successor publication remains unavailable: the production wrapper
does not enable the injected native-publish seam and no workflow schedules it.
Both migration flags remain strict, mutually exclusive, and default false. This
wave adds no activation, retention, coverage, UI/API, or Prophet authority.

The next wave adds a manual-only isolated R2 conditional create/CAS/readback
harness and one closed local review-receipt contract. Adversarial hardening now
requires exact botocore HTTP 412 `PreconditionFailed` refusals, preserves closed
stage/category/completed-prefix evidence, closes every owned response body, and
binds the exact reviewed source archive and dependency lock in the receipt. Its
protected Environment, dedicated bucket, and credentials are not provisioned;
the workflow has never run; no receipt exists; and no R2 provider behavior is
claimed. The reviewed harness invokes no List, Delete, HMAC, production
publication, retention, UI/API, or Prophet operation; its same-process adapter
is a reviewed-code target guard, not a security sandbox. Operator details live in
`research/CAPITAL_STRUCTURE_SHARE_COUNT_R2_CONFORMANCE_HANDOFF.md`.

## 0. Acceptance boundary

This wave is a deterministic, point-in-time evidence plane for three SEC Company
Facts concepts only:

- `us-gaap:CommonStockSharesOutstanding`;
- `dei:EntityCommonStockSharesOutstanding`; and
- `dei:EntityPublicFloat`.

It is explicitly **not** a current-share-count selector, fully diluted share
calculation, stock-price/market-cap join, warrant/option/convertible model,
authorized-share or shelf/ATM capacity model, cash-runway calculation, dilution
severity/probability score, alert, Prophet input, ranker, sizing rule, or trade
authority. A public-float *dollar fact* is not converted into float shares.

The v1 compatibility implementation files are:

- `contracts/capital_structure_share_count_observation.schema.json`
- `contracts/capital_structure_companyfacts_source_receipt.schema.json`
- `contracts/capital_structure_companyfacts_source_snapshot.schema.json`
- `contracts/capital_structure_share_count_snapshot_fact_observation.schema.json`
- `engine/capital_structure/share_count_truth.py`
- `scripts/compile_capital_structure_share_counts.py`
- `tests/test_capital_structure_share_count_truth.py`

The operational v2 implementation files are:

- `engine/capital_structure/companyfacts_authenticated_read.py`
- `engine/capital_structure/share_count_materializer.py`
- `engine/capital_structure/share_count_publication.py`
- `engine/capital_structure/share_count_retention.py` (planner only; production deletion blocked)
- `scripts/materialize_capital_structure_share_counts.py`
- `scripts/retain_capital_structure_share_counts.py` (hard-disabled release shell)
- `contracts/capital_structure_companyfacts_bridge_receipt.schema.json`
- `contracts/capital_structure_share_count_observation_v2.schema.json`
- `contracts/capital_structure_companyfacts_source_snapshot_v2.schema.json`
- `contracts/capital_structure_share_count_snapshot_fact_observation_v2.schema.json`
- `contracts/capital_structure_share_count_ledger_receipt_v2.schema.json`
- `contracts/capital_structure_share_count_ledger_v2.schema.json`
- `contracts/capital_structure_share_count_materialization_receipt.schema.json`
- `contracts/capital_structure_share_count_current_pointer.schema.json`
- `contracts/capital_structure_share_count_head_witness.schema.json`
- `contracts/capital_structure_share_count_head_guard_scope.schema.json`
- `contracts/capital_structure_share_count_head_witness_v3.schema.json`
- `contracts/capital_structure_share_count_head_witness_v4.schema.json`
- `contracts/capital_structure_share_count_external_head.schema.json`
- `contracts/capital_structure_share_count_publish_journal.schema.json`
- `contracts/capital_structure_share_count_publish_journal_v2.schema.json`
- `contracts/capital_structure_share_count_retention_receipt.schema.json`
- `contracts/capital_structure_share_count_r2_conformance_receipt.schema.json`
- `engine/capital_structure/share_count_r2_conformance.py`
- `scripts/probe_capital_structure_share_count_r2.py`
- `.github/workflows/capital-share-count-r2-conformance.yml`
- `requirements/capital-share-r2-conformance-macos-arm64-py312.lock`
- `tests/test_capital_structure_companyfacts_authenticated_read.py`
- `tests/test_capital_structure_share_count_materializer_model.py`
- `tests/test_capital_structure_share_count_publication.py`
- `tests/test_capital_structure_share_count_retention.py`
- `tests/test_capital_structure_share_count_materializer.py`
- `tests/test_capital_structure_share_count_r2_conformance.py`
- `tests/test_capital_structure_share_count_r2_operator.py`

## 1. What one observation means

Each immutable row represents one fact slot:

`issuer + metric kind + XBRL namespace/name + source unit + period end + accession + form + filed date`.

`fact_revision_id` identifies the direct fact revision only. It is computed from
fact-slot semantics and in-scope raw fact-entry hashes, deliberately excluding
whole-payload metadata/hash, retained-object locator, receipt ID and receipt
clocks. Those identify a source snapshot, not a corrected share fact.

The row retains:

- the direct SEC XBRL namespace/name, source unit and `scale="1"` (Company
  Facts values are supplied in actual units, not rendered/Inline-XBRL display
  scale);
- reported and normalized decimal strings, without float rounding;
- period end, fiscal year/period/frame where Company Facts supplies them;
- accession, form and filed date; `accepted_at` stays null because Company
  Facts does not provide it;
- an exact retained-payload SHA-256, SEC Company Facts endpoint, content-
  addressed raw-object locator, durable manifest locator, JSON-pointer path and
  SHA-256 of every raw fact entry used;
- an upstream source-receipt clock and `system_available_at`, which is the only
  `available_at` exposed by this plane;
- an append-only `source_snapshots` ledger that links every supplied receipt to
  receipt-bound snapshot-fact observations, each of which holds its own state,
  reported/normalized values, exact entry hashes and PIT clocks, without
  advancing a fact correction chain;
- concept-semantic security classification (`common_stock`) for both share
  concepts, while public float is honestly marked `not_security_specific`;
- closed state (`observed`, `deferred`, `ambiguous`) and immutable correction
  lineage; and
- context-only authority flags, all rank/sizing/entry/trade/Prophet flags false.

The two common-share concepts deliberately remain separate.  One is a
`us-gaap` balance-sheet concept and the other is a DEI cover-page/entity fact;
the kernel never chooses one as “the” current count or assumes they reconcile.

## 2. Source and PIT contract

### v1 compatibility kernel

`compile_share_count_observations(source_bytes, source_receipt, ...)` requires
the exact JSON bytes plus a receipt naming their SHA-256. The receipt is strict:

- it validates against the closed
  `capital_structure.companyfacts_source_receipt.v1` schema, including
  `version=1`, `source_system=sec_companyfacts`,
  `acquisition_state=provided_snapshot`, a content-addressed durable raw-object
  locator and a durable manifest locator;
- issuer CIK and SEC endpoint must match exactly;
- source receipt is an externally provided snapshot, not a collector result;
- source retrieval and system-availability timestamps must be timezone-aware;
- system availability cannot precede retrieval; and
- a fact with a filed date after the system-availability date is retained as a
  temporal defer, never backdated into a historical view.

There is no HTTP fallback and no use of `collectors/edgar_facts.py` cache. That
cache remains useful for its existing financial-statement surface, but it is a
fetch-time materialization and lacks an immutable source receipt / system clock
needed for historical share-count truth. The CLI invoked without both source and
receipt emits an explicit `status="unavailable"` result with
`collector_state="not_implemented_in_share_count_truth_wave"`.

That limitation remains true for the v1 CLI itself: it does not acquire or
authenticate production source state and must not be wired around the v2 lane.

The manifest locator is deliberately constrained to the raw-payload SHA-256 in
this pure kernel. It is a hash-bound handle, **not** evidence that this kernel
has resolved or read a manifest. The future external collector/readback and
reconciliation lane is the authority for manifest resolution and retention
verification.

The existing `collectors.fundamental_forensics_companyfacts` manifest is **not
yet a direct receipt adapter**. It has a distinct `ffseccfm_` identity, archive
paths and capture/readback contract, and deliberately declares
`point_in_time_eligible=false`. A future adapter must verify that manifest and
its capture through `read_verified_companyfacts`, retain the exact response
bytes in the capital-structure source store, and then emit this wave's closed
receipt. It must carry forward that current-snapshot / no-coverage limitation;
it cannot promote the existing manifest into point-in-time coverage by relabeling
its clocks.

### v2 authenticated production bridge

The v2 path closes the previously missing source seam without weakening it:

1. `load_authenticated_companyfacts_snapshot()` authenticates the external
   Company Facts HMAC head, exact selected receipt, complete predecessor chain,
   immutable generation files, ordered manifest/coverage prefixes, and a stable
   local pointer while holding a bounded nonblocking read lease.
2. The production command recovers the independently witnessed share-count head
   **before** opening upstream metadata or a retained raw object.
3. Only the next contiguous batch of at most 24 unconsumed manifests is opened.
   Every object is selected by its signed `store_id`, backend, digest-derived
   key, SHA-256, and exact length, with 32 MiB/object and 256 MiB/run caps. There
   is no SEC request, legacy cache read, or preferred-bucket fallback.
4. The pure v2 model re-authenticates the exact Company Facts receipt bytes and
   binds every source snapshot through a bridge receipt to that receipt,
   generation, ordered prefixes, source object, filing anchor, and acquisition
   clock. Each fact row retains the exact decoded raw fact entry so its value,
   unit, period, filing fields, semantic class, and entry hash can be re-derived
   rather than trusted as opaque compiler output. `public_available_at` remains
   null rather than borrowing filing time.
5. Publication validates the canonical ledger and ledger-tail-derived input
   binding, seals immutable ledger and signed receipt bytes externally, then
   advances a separate HMAC R2 head by exact-predecessor compare-and-swap before
   replacing the local pointer. A clean runner authenticates and reconstructs
   the selected state from the signed head plus exactly one receipt and ledger.
   A runner retaining an authenticated local high-water accepts a later head
   only after a logarithmic binary-lifting proof lands on that exact receipt.
   Local pointer/receipt selection and external selected-receipt authentication
   complete before any ledger opens. Rejected rollback/fork/ancestry paths read
   no ledger; a valid convergence reads only logarithmic proof receipts followed
   by one selected external ledger fetch and an exact local install readback.
   Publication uses one absent-only, signed
   `.share_count_publish_journal.json`, durably linked from a fully fsynced
   temporary file before CAS and dispatched by its exact schema. Legacy
   `capital_structure.share_count_publish_journal/v1` contains only exact v2
   `E`/`C` witnesses and their canonical pointer bytes and remains drainable.
   Native-v4 `capital_structure.share_count_publish_journal/v2` uses a distinct
   HMAC domain and permits only null-to-v4 genesis or exact v4-to-v4 successor;
   structural migration does not write it. Neither schema has phase, token,
   timestamp, transaction ID, or redundant receipt digest, and mixed/unknown
   journal shapes fail closed.
   Candidate external receipt and ledger bytes are exact-read before intent and
   re-authenticated before recovery CAS. Restart uses a fresh token, bounds
   conditional conflict replay at two, and accepts `C` or any proven descendant
   of `E`, including a direct sibling winner; genesis accepts any authenticated
   external winner. Rollback/fork evidence stays exact and no selected ledger is
   opened before the proof. An entry journal makes the publisher recovery-only,
   so a recovered result returns before migration or caller-candidate validation.
   Scope-valid v3 migrations and v4 migration/genesis/successor outcomes are
   drainable only under the exact v1-compatibility matrix below; wrong scope,
   virtual-v2 anchor, or authenticated receipt ancestry fails before external
   artifact or ledger I/O.
   Native v3 publication remains blocked. Capsule-only legacy recovery follows
   its historical strict matrix: `H==E` validates E and
   clears; `H==C` or an authenticated descendant of C proves C before converging
   and clearing; every sibling, equal-sequence fork, rollback, malformed proof,
   or missing proof rejects and retains the exact capsule/pointer before any
   ledger read. A v3 or v4 head plus any legacy marker/capsule bytes rejects
   unchanged, even when those legacy bytes are malformed. Legacy readers remain for
   drainage only: normal publication never writes marker/capsule state. Journal
   plus either legacy name is terminal ambiguity before remote I/O, and any
   recovery bytes seen at entry defer migration to a second clean invocation.
6. One inner ledger receipt covers the entire bounded source batch and carries
   only appended IDs plus four domain-separated rolling prefix commitments. The
   outer signed receipt repeats that constant-size tail binding; neither layer
   recopies the complete ID prefix on every append.
7. The R2 `capital_structure/share_counts/v2/current_head.json`, immutable
   `v2/receipts/`, and immutable `v2/generations/` namespace is authoritative.
   The local `data/capital_structure/share_counts/v2/` workspace is an ignored
   crash-recovery mirror, so the nightly broad data checkpoint cannot commit
   cumulative ledgers to Git. A propagated 15-minute budget plus a process-level
   workflow timeout bounds the production command.
   The head key now validates closed v2/v3/v4 witnesses. A one-time v2-to-v3
   migration keeps the exact
   v2 selection and sequence, adds signed scope
   `{backend:r2, account_id, bucket, head_key}`, binds the exact canonical v2
   bytes including their newline, and signs through a distinct v3 HMAC method
   and domain. The CAS uses the exact v2 token at the same key, then requires a
   fresh byte-identical v3 readback; an identical concurrent winner is accepted,
   while every newer or different head aborts. An old v2-only binary rejects v3
   before PUT. The strict migration variable defaults false and gates only the
   rewrite: v3 clean recovery and exact no-op remain available when false, but
   genesis and every v3 successor publication remain blocked.
8. Wave 6 implements native v4 authentication/signing, structural migration,
   recovery, and an injected native-publication test seam at the same mutable
   key. The schema keeps the exact eleven v2/v3 selection fields, adds the exact
   R2 guard scope, and closes `transition` to `genesis`, `migration`, or
   `successor`. The only permitted state shapes are:

   | Transition | Required state and proof | v1 journal interaction |
   | --- | --- | --- |
   | `genesis` | `sequence=1` and `previous_receipt=null`; the publish attempt's expected remote pointer must be null. | v1 recovery may converge only when its expected witness is null and the selected v4 artifacts authenticate; any non-null expected state fails closed. |
   | `migration` from v2 | `from_witness_sha256` commits to exact v2 bytes and `v2_anchor_sha256` is that virtual-v2 anchor. | Drainable only if it proves the exact virtual-v2 anchor of the journal's v2 `E` or `C`. |
   | `migration` from v3 | `from_witness_sha256` authenticates v3 and `v2_anchor_sha256` authenticates the v3-bound virtual-v2 anchor. | The v3 wrapper is not v1 evidence; the same exact virtual-v2-anchor rule is mandatory. |
   | `successor` | `sequence>=2`, non-null `previous_receipt`, and `previous_witness_sha256`; authenticated signed exact-scope v4 receipt ancestry, not sequence arithmetic, must prove the preceding v4 state. | v1 recovery may converge only when that ancestry proves its v2 `E` or `C` outcome; otherwise exact evidence is retained and recovery fails closed. |

   These v4 validation, migration, and recovery paths are executable, but native
   genesis/successor publication is unavailable from the production wrapper and
   has no scheduled workflow. The contract makes no global rollback claim: a
   clean runner still cannot identify credential-
   level restoration of a prior valid head without a separately durable
   monotonic witness or signer domain. It grants no activation, retention,
   coverage, UI/API, fact, risk, rank, sizing, entry, trade, or Prophet
   authority.

   The one local journal filename uses exact schema dispatch:

   | Journal schema | Permitted intent | Release state |
   | --- | --- | --- |
   | `capital_structure.share_count_publish_journal/v1` | Exact v2 `E -> C`, including drainage through the compatibility matrix above | Implemented legacy path; remains drainable |
   | `capital_structure.share_count_publish_journal/v2` | Null `E` to v4 `genesis`, or exact v4 `E` to v4 `successor`; never a structural migration | Implemented engine/test seam; production native publication unavailable |

   `CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED` and
   `CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V4_MIGRATION_ENABLED` are strict
   lowercase booleans, default false, and mutually exclusive. V4 structural
   migration and native publication also require separate invocations.
9. The publisher never deletes. A bounded retention planner can identify only
   old, quarantined, unselected full ledger generations and emit an all-false
   operational receipt in injected tests. Its production command is hard-blocked:
   R2 conditional-delete semantics are not yet proven, no shared external
   publisher/compactor fence exists, and a same-bucket delete credential plus
   symmetric head HMAC would collapse the intended privilege boundary. No
   production generation is currently deleted by this lane.
10. The manual R2 conformance harness is a separate, unprovisioned operator
    plane. An explicit main-only dispatch with `run_conformance=true` would use
    only five dedicated `R2_SHARE_COUNT_CONFORMANCE_*` Environment secrets and
    one fresh disposable key under
    `capital_structure/share_counts/conformance/v1/`. The reviewed path guards
    an exact target and calls only HEAD, GET, and conditional PUT; the adapter is
    not a same-process security sandbox, so dedicated isolated credentials and
    source review are load-bearing. The target passing contract requires
    absent-only A creation, exact HEAD/ranged-readback, exact HTTP 412
    `PreconditionFailed` duplicate-create conflict plus
    preservation, exact-ETag update to B, stale GET/PUT conflicts, and final
    exact B readback. Only a botocore `ClientError` with HTTP 412 and exact
    `Error.Code=PreconditionFailed` proves each deliberate refusal; every 409,
    transport ambiguity, malformed result, or cleanup failure is non-passing.
    Non-pass receipts preserve the failed stage/category and the exact ordered
    completed-step prefix, and every returned body is closed even on expired or
    malformed paths. The canonical receipt is a
    90-day GitHub Actions review artifact only; it is never an R2/Git/public
    artifact or production selector. No Environment/bucket/credential is
    configured and the workflow has not run, so R2 CAS remains unproven.
    The receipt is deliberately not registered in Synapse because no existing
    storage locus truthfully represents an expiring GitHub review artifact and
    it has no consumer.
    This is a sequential trace, not a concurrent linearizability proof, and it
    says nothing about the separately configured production publisher's hidden
    SDK retries. Activation also requires either a single-attempt production CAS
    client or exact candidate reconciliation for every ambiguous/retried result,
    plus an independent concurrent-writer race proof.

Outer publication v2 removes the former 512-receipt full-chain recovery cliff.
It does not remove the upstream dependency: Company Facts source selection still
authenticates its v1 receipt chain and blocks before receipt 513. Until that
source lane receives its own authenticated checkpoint migration, the end-to-end
materializer is bounded by the upstream 512-source-publication checkpoint.

The production trust domains are intentionally separate:
`CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY` authorizes the source selection;
`CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY` authorizes only the distinct
v2/v3/v4 selector and v1/v2 journal HMAC domains.
`SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID` completes
the exact signed R2 scope; the bucket and fixed head key are also authenticated.
It remains optional for migration-false v2 operation, but is mandatory before
migration and whenever a v3 or v4 head is authenticated. If configured, it must match
the exact resolved Cloudflare R2 global/EU/FedRAMP endpoint before client
construction; the endpoint is deliberately not part of signed scope.
Neither key grants fact, instrument, capacity, risk,
ranking, sizing, entry, trade, or Prophet authority.

### Existing-ledger trust boundary

Every update of an existing share-count ledger requires a caller-held,
externally pinned `ledger_head_receipt_id`. The CLI therefore requires
`--expected-existing-ledger-head-receipt-id` together with
`--existing-ledger-json`. The compiler checks the supplied witness before
extending a ledger; replaying a snapshot already present in that ledger returns
the exact existing output rather than rewinding the current view.

The internal receipt chain is still useful for structural integrity, but it is
not itself an external witness. A writer able to replace the entire JSON file
can recompute local hashes. Persist the pinned head in a durable commit/witness
record outside the mutable ledger before trusting a prior history or invoking
an update.

For v2, that external witness is implemented rather than left to the caller.
The current ignored local pointer is only a cache of the HMAC-authenticated
external head. Exact replay is a no-op; a valid lagging pointer converges only
after an authenticated O(log delta) ancestry proof; a divergent, tampered,
missing, oversized, or indeterminate state fails closed. A clean workspace can
authenticate the selected state but cannot detect credential-level restoration
of an older otherwise valid mutable head; global rollback detection needs a
separate monotonic witness or signer domain. The output receipt repeats the exact
inner ledger head, compiler version, materializer clock, and rolling
source/observation commitments and retains all decision-authority flags as false.

### Snapshot refreshes versus fact corrections

A source snapshot may change because SEC refreshed root metadata, another
uninvolved concept changed, the whole-payload hash changed, or Mastermind
received it later. The compiler retains that receipt in an append-only
`source_snapshots` ledger. Each source snapshot has a canonical
`source_snapshot_id` over its full normalized body, a unique link per logical
slot, and a closed snapshot-fact observation keyed by receipt + fact revision +
snapshot-local state/PIT. Links target the snapshot-fact observation—not the
possibly deferred state of a canonical fact row. It does **not** create
`correction_version + 1`. Only a change in a direct in-scope fact revision may
advance a correction chain.

The CLI emits and accepts a self-contained
`capital_structure.share_count_ledger.v1` envelope with immutable
`observations` and append-only `source_snapshots`. Re-ingesting that envelope
with the same raw bytes/receipt is idempotent. It retains the existing history,
does not append a duplicate snapshot, and reports disposition counts only for
the current source snapshot. Future as-of selection must consume these
receipt-bound snapshot facts and clocks, never invent a synthetic correction.

## 3. Failure behavior

The compiler does not “latest wins.” It behaves as follows:

| Condition | Row state |
| --- | --- |
| Direct valid fact in the expected unit | `observed` |
| Wrong unit, missing value/period/accession/form/filed date, negative value, malformed entry, or impossible availability clock | `deferred` |
| Same fact slot has multiple distinct values | `ambiguous` |

In `deferred` or `ambiguous`, normalized values/units/scales are null. Raw
source evidence remains attached so a future review or source correction can
explain the refusal. A new retained snapshot that changes the fact slot creates
a contiguous immutable correction version; it cannot overwrite history or fork
the correction chain.

## 4. Integration sequence (current state; do not skip)

1. **Landed:** bounded Company Facts intake, exact retained objects, coverage
   ledger, authenticated generation/receipt chain, and external source head.
2. **Implemented, pre-production:** metadata-only authenticated reader, strict
   contiguous raw-object bridge, pure v2 model, independently signed
   crash-recoverable publication, a bounded retention planner/receipt contract,
   selector/receipt-first high-water proof before any ledger load, default-off
   daily execution, DAG/Synapse declarations, CI coverage, and
   explicit zero-source unavailability. The v2/v3/v4 authenticated reader,
   exact selection-preserving v3/v4 structural migrations, old-writer rejection,
   schema-dispatched v1/v2 single-file journal recovery, native-v4 publication
   test seam, recovery-only entry fence, and legacy capsule-only drainage matrix
   are also implemented. Production native v4 genesis/successor publication is
   unavailable. The retention production shell is a
   deliberate fail-closed release block, not an operational compactor.
3. **Still required before activation:** the complete v4 and schema-dispatched
   journal implementation has received independent adversarial review, but the
   new isolated-provider harness is only locally tested code. Provision a
   protected Environment plus dedicated disposable bucket/credential, obtain
   and review a real `passed` receipt, and make an explicit operator activation
   decision. The
   selector/receipt-versus-ledger
   split, journal crash protocol, and v3/v4 old-writer fences are adversarially
   pinned, but none enables the lane. Keep
   both migration flags false until every intended publisher has v4 support and
   the operator schedules exactly one mutually exclusive migration with the
   exact account/bucket scope provisioned. Native v4 genesis/successor remains
   unavailable from production and unscheduled regardless of those migration
   flags.
   A passed create/CAS/readback receipt closes only that exact scoped provider
   sequential trace; it does not establish concurrent linearizability or safe
   production retry behavior and does not activate publication. Separately
   prove R2 atomic
   conditional delete on an isolated object, add a shared external publish/delete
   fence and exact race test, mint a verifier-only capability that cannot write
   the signed head/receipts, add an end-to-end retention deadline, and re-audit
   the complete lane. Then provision distinct production credentials and
   deliberately enable the publication variable.
   The current reviewed conformance path never calls Delete, so it cannot release
   retention. Retention additionally requires its own visibility and apply variables. Only
   afterward may the team observe the first
   successful daily receipt and report
   actual retained-source coverage/freshness. Code deployment alone is not
   corpus coverage, and UI/API must never render absence as zero shares or no
   dilution.
4. Only after normalizing capital events, source intake, and corporate actions
   should a consumer attempt a clearly labelled observed “share-count history”
   view. It must preserve the concept/fact basis and show unavailable/ambiguous
   states, not an unlabeled single line.
5. Fully diluted shares, headroom/capacity, inferred float shares, runway and
   offering probability each require their own contract, data sources, temporal
   tests and authority ruling. None may be derived inside this plane.

## 5. Test evidence

`tests/test_capital_structure_share_count_truth.py` pins:

- strict Draft 2020-12 observation and closed receipt-schema validation,
  durable raw-object/manifest locators, and all authority fences;
- separate `us-gaap` shares, DEI shares and DEI public-float rows;
- unexpected-unit defer without silent reinterpretation;
- duplicate fact values becoming ambiguous rather than “latest wins”;
- hash-bound source bytes and receipt-clock failures;
- filing-date versus system-availability PIT refusal; and
- contiguous, non-branching correction lineage; and
- root-metadata/payload-hash/receipt-clock refreshes that remain receipt-linked
  but create zero false fact corrections;
- deferred-then-later-observed snapshot transitions without false corrections;
- self-contained CLI envelope re-ingestion/idempotence; and
- cross-ledger tamper refusal for IDs, receipt/PIT bindings, exact entry hashes
  and one-link/one-snapshot-fact-per-logical-slot invariants.

This is a solid substrate for parity work, but not parity itself: it adds a
truthful denominator evidence layer rather than cosmetic “dilution risk” cards.

The operational suites additionally pin authenticated selection and read deadlines,
exact receipt/source/anchor binding, bounded append and replay, semantic
re-derivation, all-false authority, strict store identity, separate HMAC/R2
publication, concurrent CAS conflict, pre/post-CAS crash recovery, lagging
runner convergence, exact-schema dispatch for the single-filename absent-only
signed v1/v2 journals, exact
candidate artifact reread, two-conflict replay bound, recovery-only entry,
direct-sibling/genesis convergence, mixed-protocol refusal, capsule-only drainage,
scope-bound v3 and v4 authentication/migration, exact virtual-v2 anchors,
distinct v3/v4 head and v1/v2 journal signature domains, null-to-v4 genesis and
v4-to-v4 successor test-seam publication/recovery, corrected v1/v4 compatibility,
both old-v2-writer race orders, concurrent identical migration, mutually exclusive
strict-default-false migration flags, strict legacy capsule sibling rejection, and
legacy/v3/v4 coexistence refusal,
logarithmic high-water ancestry proof before ledger access, zero ledger reads on
rollback/fork/divergent-proof rejection, exactly one selected external ledger
fetch after a successful proof, bounded local install readback, clean-run
rollback nonclaim, rolling-prefix
tamper refusal, descriptor-relative symlink/root-swap/lock
refusal, bounded retention planning and production hard-blocking, deadline
enforcement, Git-plane
exclusion, and explicit empty-source unavailability. They do not substitute for
a live R2 publication probe or the first daily coverage receipt. The dedicated
conformance suites additionally pin the closed `passed|failed|inconclusive`
receipt, redacted scope and GitHub provenance, exact fresh-key target guard,
absent-only create, duplicate/stale conflict preservation, exact ETag update,
bounded ranged readbacks, non-pass ambiguity handling, 90-second deadline,
manual/main-only protected workflow, isolated-secret no-fallback rule, no
List/Delete/HMAC/publication calls, and best-effort review-only receipt upload. These are
local tests: no dedicated provider environment is provisioned and no live
conformance receipt exists.
