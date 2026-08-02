# Capital Structure Company Facts Intake Docket

Canonical implementation note for the dedicated SEC Company Facts source lane.

## What landed

`collectors/sec_capital_structure_companyfacts.py` is a bounded, serial-SEC-host
collector that admits only unique CIKs anchored by a verified, retained,
parser-clean `complete_submission` row in
`data/capital_structure/source_manifest.parquet`. It never modifies or extends
`capital_structure.source_manifest/v1`.

It retains current SEC Company Facts JSON only after all of these gates pass:

1. canonical `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` request;
2. streamed response under the declared and actual byte caps;
3. UTF-8 JSON with a CIK exactly equal to the requested CIK;
4. SHA-256 content-addressed source-store write and exact read-back; and
5. closed-contract manifest and append-only coverage-row validation; and
6. an immutable generation, chained receipt, and atomic selector publish.

The queue is deterministic and hard capped at 24 CIKs/run (64 maximum). A
2:1:1 rotating retry/new/refresh schedule, ordered by due clock then CIK within
each lane, prevents any continually non-empty lane from starving while retaining
retry weight. It is serial inside `scripts.collect`'s shared `sec` host group and
preserves a local 100ms request floor. Delayed retry/defer work and fresh captures
are separately counted; a deferred request never becomes a negative issuer fact.

## Contracts and artifacts

| Artifact | Contract | Purpose |
| --- | --- | --- |
| `data/capital_structure/companyfacts/generations/<sha256>/source_manifest.parquet` | `capital_structure.companyfacts_source_manifest/v1` | Immutable, byte-verified Company Facts source evidence. |
| `data/capital_structure/companyfacts/generations/<sha256>/coverage.parquet` | `capital_structure.companyfacts_coverage_row/v1` | Immutable generation containing the append-only queue/retrieval history. |
| `data/capital_structure/companyfacts/receipts/<sha256>.json` | `capital_structure.companyfacts_coverage_receipt/v1` | Immutable sequence/predecessor receipt that commits both ordered prefixes and exact generation files. |
| `data/capital_structure/companyfacts/coverage_receipt.json` | `capital_structure.companyfacts_current_pointer/v1` | Tiny atomically replaced pointer to the selected immutable receipt/generation. |

The collector stages and read-backs both Parquet ledgers under an identity-named
generation directory, seals an immutable receipt under `receipts/`, then advances
only the tiny pointer. It never overwrites a ledger or receipt. On startup it
authenticates the complete predecessor chain, every required generation, and the
selected generation's exact bytes and ordered prefixes. A fault before pointer
advance leaves the prior authenticated generation selected; an orphaned staged
generation or receipt is unreachable evidence, not a source claim.

All three artifacts are registered in `config/synapse.yml`. The daily collection
step runs the adapter immediately after `sec_capital_structure`; this dependency
is recorded in `.github/workflows/daily.yml` and `config/dag.yml`.

## Scope and hard nonclaims

This lane is source acquisition only. It does **not**:

- normalize or interpret any Company Facts value;
- write, amend, or consume the capital-structure share-count truth ledger;
- infer outstanding, float, fully diluted, capacity, cash runway, risk, or
  financing state;
- create instruments or classifications; or
- affect risk, ranking, sizing, entry, alerting, or Prophet.

The current Company Facts endpoint is not historical availability evidence. Its
receipt records Mastermind acquisition/retention clocks only; future PIT use must
respect that limitation and preserve raw source references.

## Next-wave boundary: share-count consumption

The next wave may add a separate offline consumer that reads **only** verified
Company Facts manifests plus a valid coverage receipt, fetches no network bytes,
and feeds the parked share-count truth plane through an explicit versioned input
contract. That consumer must retain the Company Facts manifest ID, content hash,
object-store namespace, anchor manifest ID, acquisition clock, concept/unit, and
all ambiguity/defer outcomes. It must not use filing date as a public-availability
substitute, must not coerce current-source data into historical values, and must
not grant any authority beyond the existing share-count truth-plane boundary.

## Validation performed

`python3 -m pytest -q tests/test_sec_capital_structure_companyfacts.py`

The focused suite covers canonical request/CIK validation, declared and streamed
byte caps, unique verified-anchor selection, deterministic starvation-free queue
progress, source-store failure, honest `ok`/`partial`/`degraded`/`blocked` status,
force-refresh history preservation, body/semantic/cross-ledger identity checks,
full-chain startup authentication, retry-after global cooldown, total run budgets,
and last-good survival across generation/receipt/pointer publish faults.
