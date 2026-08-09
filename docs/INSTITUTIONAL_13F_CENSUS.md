# Institutional 13F Census

## Purpose

The Institutional 13F Census is the market-wide evidence plane behind the
Smart Money page.  It answers broad ownership questions across every SEC 13F
filer without pretending that every filer is an active, skilled stock picker.
The curated Smart Money desk remains a separate, versioned cohort.

The system has four explicit layers:

1. **SEC evidence** — immutable bytes, accession manifests, discovery coverage,
   and all original/amended/notice forms.
2. **Normalized census** — as-filed holding rows, manager relationships, and
   point-in-time effective filing views.
3. **Research bench** — screened candidates with transparent readiness fields;
   no performance or skill claim is implied.
4. **Featured desk** — the bounded, manually governed cohort already rendered
   on `smart_money.html`.

Only bounded aggregate census context reaches the public page.  The evidence
and research layers are not Neural Web or Prophet authority.

## Source and clock contract

Rolling discovery is deliberately redundant:

- EDGAR Latest Filings Atom is the fast, provisional lane.
- EDGAR daily indexes close missed-page and transient-poll gaps nightly.
- A full-index pass repairs weekly coverage and removals/corrections.
- SEC quarterly Form 13F bulk packages reconcile the completed filing window.

Every observation keeps three clocks:

- `report_period`: what portfolio date the filing describes;
- `accepted_at`: when the filing became public; and
- `first_seen_at`: when this system retained it.

Filing date is not a substitute for acceptance time.  The accession, source
URL, original-byte SHA-256, and parser version travel with every normalized
generation.

## Filing semantics

- `13F-HR` begins an as-filed lineage.
- A restatement `13F-HR/A` replaces that lineage's effective holdings.
- A new-holdings amendment appends disclosed holdings to the lineage.
- `13F-NT` is a notice/manager relationship, never a zero portfolio.
- Confidential omissions make a report incomplete rather than empty.
- Pending filers are absent from an incoming-quarter cohort, never sellers.
- `OTHERMANAGER` and `OTHERMANAGER2` remain distinct directed relationships.
- Raw rows are keyed by accession plus source ordinal; malformed or duplicate
  SEC sequence values are retained rather than silently collapsed.

## Publication protocol

Raw objects are addressed by content hash.  Immutable accession and
normalization manifests are written and read back before any catalog pointer
advances.  Quarter generations are immutable.  `current.json` advances with an
exact-predecessor compare-and-swap and may not rewind.  Canonical JSON is the
authority; deterministic Parquet is a query projection.  Version 1 has no
deletion or retention job.

The object layout begins at `smart-money/13f/evidence/v1/`:

```text
objects/sha256/<prefix>/<digest>.<bin|json|parquet>
filings/<cik10>/<accession>/<raw-receipt-id>.json
bulk/windows/<start>_<end>/revisions/<source-sha>/<revision-id>.json
rolling/checkpoint/current.json
quarters/report_period=YYYY-MM-DD/generations/<generation-id>/manifest.json
quarters/report_period=YYYY-MM-DD/current.json
```

Normalized tables are immutable content-addressed objects bound by the quarter
generation manifest; there is no parallel mutable catalog tree.

The writer accepts only the explicit `INSTITUTIONAL_13F_R2_*` runtime namespace
(or a local store for tests).  It never discovers or falls back to another
namespace.  During bootstrap, the workflow explicitly binds the repository's
existing public-evidence R2 secrets into those names; rotating that binding to a
least-privilege key requires no storage-code or object-layout change.

## Transition-period behavior

The completed-quarter census is frozen while the next 45-day filing window is
open.  Incoming filings appear in the early-reporter surface only.  An
incoming-quarter comparison is computed on the paired reporting cohort, with
`n_reporting`, `n_expected`, and coverage shown; it is never compared against a
full prior-quarter denominator.

The canonical boards promote atomically only after their configured cohort
gate.  The broader census promotes after the SEC bulk reconciliation for the
completed window.  Main boards therefore never combine different report
periods, even when some managers report weeks early.

## Public aggregate semantics

The bounded public payload reports filer counts, paired-report coverage,
mapping coverage, and at most six broadening, narrowing, and sector rows.  The
security action board:

- compares the same filer in two completed periods;
- uses share-count changes, with a disclosed materiality threshold;
- excludes put/call rows from the long-equity action view;
- restricts the ranked board to US-traded common equity, ADRs, REITs, and
  partnership shares (funds, warrants, debt, preferreds, and units stay in evidence);
- ranks transparent net unique-filer breadth, not dollar activity; and
- labels the population as SEC filers, because it includes passive, quant,
  custody, bank, insurance, pension, and active managers.

A disclosed `holder_discontinuity_v1` rank fence withholds security rows whose
one-quarter holder jump is both extreme and dominated by new/exit identities.
Those rows usually reflect a merger, spin-off, take-private, or identifier
change rather than discretionary buying.  They remain in evidence and in the
quality count; the public “buying/selling” leaders omit them until a corporate-
action lineage can reconcile the old and new security.

Unknown identifiers remain unresolved and contribute to coverage disclosure.
They are not guessed from issuer names.  A missing identifier map or mapping
coverage below the configured floor is a failed compilation, not an empty
"complete" board.

The raw `value` field is also retained without guessing its unit.  Although the
current form specification uses dollars, accepted filings still contain both
dollar-style and legacy thousand-dollar-style values.  Broadening/narrowing is
therefore share-count based.  AUM, portfolio weights, and value-based rankings
stay excluded until a provenance-aware per-accession unit resolver marks a row
`reported_dollars` or `apparent_thousands`; unresolved rows never receive an
invented `value_usd`.

## Research-bench governance

Version 1 screens a current-map candidate bench using only structural
readiness: retained-quarter count, identifier coverage, material-decision
density, and interpretable position count.  It explicitly emits
`point_in_time: false`; the first two-quarter screen is discovery, not a
historical performance ranking.  Manager type is a provenance-bearing
classification, and uncertain managers remain `unknown`.

The roster is `screened_not_promoted`, with zero research-eligible managers
until at least eight immutable quarters have been retained.  Promotion into the
featured desk requires a separate, look-ahead-free performance study,
point-in-time identifiers and classifications, survivorship controls, human
review, and a new versioned roster receipt.  Census size alone is not a skill
signal.

## Operations and alarms

A healthy lane distinguishes a quiet poll from an outage.  It records discovery
coverage even when no 13F forms were found and alarms on:

- an uncovered published index day;
- retained backlog age or parked acquisitions;
- a discovered accession with no hash-bound evidence object;
- a catalog pointer older than its complete generation;
- a completed filing window without bulk reconciliation; or
- a public summary that exceeds 16 KiB or contains filer-level records.

The rolling and bulk workflows run off the site-render critical path.  A failed
run publishes nothing, leaving the last complete generation and page summary in
place.
