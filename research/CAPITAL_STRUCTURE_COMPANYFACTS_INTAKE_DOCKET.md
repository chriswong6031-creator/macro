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
5. closed-contract manifest and append-only coverage-row validation.

The queue is deterministic, hard capped at 24 CIKs/run (64 maximum), prioritizes
due retry/defer rows, then new anchors, then stale seven-day refreshes. It is
serial inside `scripts.collect`'s shared `sec` host group and preserves a local
100ms request floor. Delayed retry/defer work and fresh captures are separately
counted; a deferred request never becomes a negative issuer fact.

## Contracts and artifacts

| Artifact | Contract | Purpose |
| --- | --- | --- |
| `data/capital_structure/companyfacts/source_manifest.parquet` | `capital_structure.companyfacts_source_manifest/v1` | Immutable, byte-verified Company Facts source evidence. |
| `data/capital_structure/companyfacts/coverage.parquet` | `capital_structure.companyfacts_coverage_row/v1` | Append-only queue/retrieval outcome ledger. |
| `data/capital_structure/companyfacts/coverage_receipt.json` | `capital_structure.companyfacts_coverage_receipt/v1` | Telemetry-last receipt that hash-binds anchor, source, and coverage prefixes. |

The collector stages and read-backs both Parquet ledgers, removes any prior
receipt before the pair is published, and writes the receipt only after their
hashes match. Consumers must require that receipt; raw objects written before a
failed ledger publish are unreachable evidence, not source claims.

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
byte caps, unique verified-anchor selection, deterministic retry-first bounded
queueing, source-store failure, no-anchor no-network behavior, append-only ledger
receipts, and telemetry-last failure behavior.
