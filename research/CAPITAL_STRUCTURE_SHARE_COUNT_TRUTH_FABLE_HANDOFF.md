# Capital Structure — observed share-count truth plane

## 0. Acceptance boundary

This wave is a deterministic, point-in-time evidence plane for two SEC Company
Facts concepts only:

- `us-gaap:CommonStockSharesOutstanding`;
- `dei:EntityCommonStockSharesOutstanding`; and
- `dei:EntityPublicFloat`.

It is explicitly **not** a current-share-count selector, fully diluted share
calculation, stock-price/market-cap join, warrant/option/convertible model,
authorized-share or shelf/ATM capacity model, cash-runway calculation, dilution
severity/probability score, alert, Prophet input, ranker, sizing rule, or trade
authority. A public-float *dollar fact* is not converted into float shares.

The canonical implementation files are:

- `contracts/capital_structure_share_count_observation.schema.json`
- `contracts/capital_structure_companyfacts_source_receipt.schema.json`
- `contracts/capital_structure_companyfacts_source_snapshot.schema.json`
- `contracts/capital_structure_share_count_snapshot_fact_observation.schema.json`
- `engine/capital_structure/share_count_truth.py`
- `scripts/compile_capital_structure_share_counts.py`
- `tests/test_capital_structure_share_count_truth.py`

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

The current acquisition limitation is real: this wave supplies the kernel and
contract only. A future intake lane must retain raw Company Facts bytes and its
receipt before this can claim issuer or market coverage.

The manifest locator is deliberately constrained to the raw-payload SHA-256 in
this pure kernel. It is a hash-bound handle, **not** evidence that this kernel
has resolved or read a manifest. The future external collector/readback and
reconciliation lane is the authority for manifest resolution and retention
verification.

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

## 4. Integration sequence (do not skip)

1. Build an intake writer that stores exact Company Facts response bytes in a
   manifest-addressed immutable source store and emits this receipt. Do not bolt
   a network fetch into the pure compiler.
2. Add a bounded universe/coverage ledger: CIK list, attempted/succeeded source
   receipts, timestamp, source failure reason and retention verification. Until
   that exists, UI/API must say source acquisition is unavailable, not “0
   coverage” or “no dilution.”
3. Register the schema/compiler/source ledger in Synapse, the build DAG and
   CI only after it is reconciled with the document-terms and SEC intake waves.
   This wave intentionally avoids shared config/workflow edits to prevent a
   false deployment claim before a source path exists.
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
