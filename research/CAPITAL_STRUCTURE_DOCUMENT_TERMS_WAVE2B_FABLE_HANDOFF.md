# Capital Structure Intelligence — Wave 2B Direct Terms Ledger

Status: implemented as an uncommitted precision-first build slice  
Owner: `capital-structure-intelligence`  
Canonical artifact: `data/capital_structure/document_term_observations.parquet`

## Ruling

Wave 2B is deliberately a **document-row transcription ledger**, not a dilution
engine. It makes five directly displayed SEC registration-fee-table fields
available as immutable, point-in-time observations:

| Direct field | Type | What it means here |
|---|---|---|
| `amount_to_be_registered` | row-dependent quantity | Direct shares, debt principal, units, or securities; never a generic share default |
| `proposed_maximum_offering_price_per_unit` | row-dependent price | Direct per-share, per-unit, or per-security price only when the row establishes the basis |
| `proposed_maximum_aggregate_offering_price` | amount | A single displayed fee-table cell, never summed across rows |
| `registration_fee` | amount | A single displayed filing/registration fee cell |
| `filing_fee_rate` | dimensional rate | A direct scalar rate or explicit numerator-plus-denominator pair |

All numbers are canonical decimal **strings**. There are no binary floating
point values, currency conversions, scale guesses, price-times-shares checks,
or inferred aggregate values.

For `USD_per_USD`, `value` is the exact displayed numerator and `scale` is the
exact displayed denominator. Thus `$147.60 per $1,000,000` remains
`value=147.6, scale=1000000`; it is not silently converted to either `147.6` as
a scalar rate or `0.0001476` as a normalized ratio.

## Actual source representation and parser path

The inspected retained corpus contains 714 source-manifest rows for 200
accessions: 200 `complete_submission`, 200 primary, and 314 generic exhibit
rows. The generic exhibit allowlist currently retains EX-3/4/10/99 material;
there is no selected `EX-FILING FEES` class. Therefore this lane must not make
an imaginary exhibit dependency its source of truth.

The parser uses only the immutable `complete_submission` manifest object while
retaining the exact primary or `EX-FILING FEES` child provenance:

```text
source_manifest.parquet
  -> exact storage.store_id + content-addressed object_key + sha256 readback
  -> complete SGML submission bytes
  -> matching primary and EX-FILING FEES <DOCUMENT>/<TEXT> segments
  -> one named fee table
  -> explicit security row + direct cell + exact table/row/cell byte spans
  -> document_term_observations.parquet
```

The source store namespace is checked before every read. A configured default
bucket cannot silently satisfy an `r2_research` or `r2_shared` manifest from a
different namespace. A missing object or hash mismatch fails the whole term
generation; it cannot become an empty/zero result.

## State and ambiguity law

Every in-scope retained complete submission receives one row per named field.
The only outcomes are:

- `observed`: one direct displayed decimal value with an explicit security row
  and safe unit/principal/price basis.
- `unavailable`: parser/source structure did not expose a direct value; this is
  not a negative fact, zero, or capacity estimate.
- `ambiguous`: competing tables, unknown unit basis, or unsupported/multiple
  numeric dimensions. The compiler leaves the value null.

Evidence is never prose-only. Each row carries its complete-submission manifest
identity, child-document coordinates, document SHA-256, source rights/privacy
attributes, and stable table, row, security-cell, and term-cell byte ranges/hashes
(or the verified document root when no table exists). Every locator is rebound to
the retained bytes before publication.

## PIT and correction law

`source_available_at` records when the source bytes first became durable.
`available_at` records when Mastermind actually produced the term extraction or
correction. A historical source backfilled today is not visible in yesterday's
canonical replay. A parser improvement emits correction version N+1 that points
to the old observation; it is never backdated. The engine function
`current_document_terms_as_of(...)` selects only the latest visible immutable
version per document-term slot.

Normal nightly work reads only new manifests or documents produced by an older
parser version. `--rebuild` deliberately re-reads every retained in-scope
submission and is the controlled route for parser upgrades/corrections.

## What Fable must not build on top of this yet

This ledger is **not** any of the following:

- an active shelf/ATM/PIPE/convertible/warrant instrument;
- remaining or active capacity, an offering amount, or an issuance count;
- fully diluted shares, float, cash runway, overhang, or reverse-split logic;
- a dilution score, financing probability, risk severity, rank, entry, sizing,
  veto, or Prophet feature/authority.

Even an observed `proposed_maximum_aggregate_offering_price` is a historical
registration-fee-table field. It cannot be relabelled “available shelf
capacity” without a later issuer/instrument reconciliation receipt that proves
the registration family, amendments, EFFECT/withdrawal state, take-downs, and
time validity.

## Next build gates

1. Add a wider adjudicated real-filing corpus covering multi-row fee tables,
   ASR deferral language, older fee-table formats, and Reg-A variants.
2. Promote a separate instrument-linkage candidate ledger only after it can
   keep an explicit registration family and refusal/ambiguity state.
3. Reconcile registration/amendment/EFFECT/withdrawal/take-down evidence before
   calculating any capacity. Direct fee-table fields alone do not satisfy this.
4. Build issuer-state receipt(s), cash evidence, and dilution outcomes as
   separate versioned ledgers before even proposing a probability model.
5. Route only a later validated context projection into Neural Web, Mastermind,
   or Prophet; those systems must not read raw terms as a backdoor signal.

## Implementation surfaces

- Contract: `contracts/capital_structure_document_term_observation.schema.json`
- Parser/history primitives: `engine/capital_structure/document_terms.py`
- Offline compiler: `scripts/compile_capital_structure_document_terms.py`
- Fixture test: `tests/test_capital_structure_document_terms.py`
- Nightly step: `.github/workflows/daily.yml`
- Registry/DAG: `config/synapse.yml`, `config/dag.yml`

The frontend deliberately receives no new term payload in Wave 2B. This keeps
the product honest until a separate authorization decision approves an
evidence-safe, context-only display surface.
