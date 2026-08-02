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
- `engine/capital_structure/share_count_truth.py`
- `scripts/compile_capital_structure_share_counts.py`
- `tests/test_capital_structure_share_count_truth.py`

## 1. What one observation means

Each immutable row represents one fact slot:

`issuer + metric kind + XBRL namespace/name + source unit + period end + accession + form + filed date`.

The row retains:

- the direct SEC XBRL namespace/name, source unit and `scale="1"` (Company
  Facts values are supplied in actual units, not rendered/Inline-XBRL display
  scale);
- reported and normalized decimal strings, without float rounding;
- period end, fiscal year/period/frame where Company Facts supplies them;
- accession, form and filed date; `accepted_at` stays null because Company
  Facts does not provide it;
- an exact retained-payload SHA-256, SEC Company Facts endpoint, JSON-pointer
  path and SHA-256 of every raw fact entry used;
- an upstream source-receipt clock and `system_available_at`, which is the only
  `available_at` exposed by this plane;
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

- strict Draft 2020-12 schema validation and all authority fences;
- separate `us-gaap` shares, DEI shares and DEI public-float rows;
- unexpected-unit defer without silent reinterpretation;
- duplicate fact values becoming ambiguous rather than “latest wins”;
- hash-bound source bytes and receipt-clock failures;
- filing-date versus system-availability PIT refusal; and
- contiguous, non-branching correction lineage.

This is a solid substrate for parity work, but not parity itself: it adds a
truthful denominator evidence layer rather than cosmetic “dilution risk” cards.
