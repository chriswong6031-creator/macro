# VEND-0 Institutional Estimates Vendor Bake-Off

**Status:** `SAMPLE_REQUIRED`

**Recommendation:** `PROBE_FURTHER` — no winner and no procurement decision

**Access date:** 2026-08-23
**Scope:** records-only research under `VENDOR_BAKEOFF_PROTOCOL.md` and `handoffs/VEND_0.md`; no adapter, ingestion, schema/store, runtime, authority, vendor contact, trial, purchase, or credential use.

## Immutable pickup and method receipt

| item | receipt |
|---|---|
| Macro pickup / recovery base | `origin/main` `383aeba386a651b8f9cda65efc804f12df38e67b` (2026-08-23) |
| protected Mastermind source | `origin/master` `5d752c4c28d63207849247bd608cf9993e2f58bb` |
| loaded Sol Skillpack | `mastermind.sol_skillpack.v1`, version `1.0.0`, minimum bootstrap major `1`; `INDEX`, `BOOTSTRAP_KERNEL`, `COLD_START`, `COMMISSION_WAVE`, `RECONCILE_STATE`, `REVIEW_RETURN`, and `CLOSEOUT` all read from the same protected SHA |
| governing program state | K3E-0 is a derived records-only freeze: it is not canonical K3-E, a new truth store, a provider selection, or runtime permission (`DEC:K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE`) |
| current-estate probe | No provider-specific runtime client, configured capability, or authorized sample found by a tracked `engine/`, `scripts/`, `config/` search and an environment-name-only check. This is **not** a claim that the company has no subscription elsewhere. |
| evidence classes | `PRIMARY_PRODUCT_PAGE`, `PRIMARY_DEVELOPER_DOCUMENTATION`, `PRIMARY_VENDOR_BROCHURE`, and `PRIMARY_MARKETPLACE_QUERY_LIBRARY` are public vendor-origin claims. `SAMPLED_RECORD` and `RIGHTS_SCHEDULE` were unavailable. |

The accompanying machine-readable ledger is
[`VEND_0_EVIDENCE_LEDGER_2026-08-23.json`](VEND_0_EVIDENCE_LEDGER_2026-08-23.json).
It is intentionally a claim ledger, not a substitute for data records.

## Decision answer

There is enough primary-source evidence to admit four **evaluation candidates**:

1. LSEG I/B/E/S Estimates, including its Point-in-Time/Historical products;
2. FactSet Estimates, including Point-in-Time Consensus;
3. S&P Capital IQ Estimates; and
4. Visible Alpha Estimates as a separately entitled S&P dataset, not assumed to be included with Capital IQ Estimates.

There is not enough evidence to shortlist a procurement winner. All four remain
`CLAIMED_NOT_SAMPLED` for field-level semantics and `RIGHTS_UNVERIFIED` for the
rights that determine whether any observed record is lawful to store, derive from,
display, redistribute, or use for model training. The bounded VEND-0 verdict is
therefore **`SAMPLE_REQUIRED / PROBE_FURTHER`**.

This does not downgrade the candidate vendors. It prevents a product page, a
demo ticker, or a pre-existing adapter from becoming architecture or authority.

## Current estate and lawful comparison boundary

The current K3E contract requires provider-issued, source-available,
collector-observed, system-known, and superseded clocks to remain distinct where
the source supplies them. `known_at` is mandatory for historical replay.
Corrections append or supersede; they never rewrite an as-known record in place.
`UNLICENSED`, `UNAVAILABLE`, `STALE`, `LOW_COVERAGE`, and `RIGHTS_BLOCKED` are
lawful outputs, not conditions to synthesize away.

The estate has partial revision assets but no admitted multi-horizon institutional
PIT expectation history. Its usable baseline is therefore **current-state and
forward-accrual only**. A current provider snapshot cannot be spread backwards to
create analyst history, dispersion, or revision chronology.

## Candidate evidence matrix

`PROVEN` below means a primary vendor source explicitly states the narrow public
claim; it does **not** mean this repository has validated a licensed delivered
record. `CLAIMED_NOT_SAMPLED` means credible public capability language exists
but the specified sample assertion remains untested. `UNESTIMABLE` means public
materials do not establish the property. `RIGHTS_UNVERIFIED` means no applicable
contract/data-rights schedule was available.

| criterion | LSEG I/B/E/S | FactSet Estimates | S&P Capital IQ Estimates | Visible Alpha Estimates |
|---|---|---|---|---|
| comparable institutional-estimates basis | **PROVEN (product claim):** LSEG calls out analyst detail, consensus, aggregates, guidance and KPIs. | **PROVEN (product/API claim):** consensus, detail, actuals, guidance, segments and ratings. | **PROVEN (product claim):** consensus, detailed estimates, broker/analyst coverage and revisions. | **PROVEN (product claim):** S&P presents a distinct contributor-model and KPI dataset. |
| PIT / as-of reconstructability | **CLAIMED_NOT_SAMPLED:** LSEG quant brochure describes daily PIT snapshots and date/time arrays; exact export schema and replay behavior not seen. | **CLAIMED_NOT_SAMPLED:** daily local-midnight consensus snapshots, history from Dec-2009, and a no-later-entry rule are documented. Record replay has not been performed. | **CLAIMED_NOT_SAMPLED:** Snapshot every two hours since Aug-2016; public page names `spEffectiveDate` and `spToDate`. A record-level replay is still required. | **CLAIMED_NOT_SAMPLED:** S&P states intraday updates with broker timestamps but does not publish a record schema here. |
| analyst / broker / contributor detail | **CLAIMED_NOT_SAMPLED:** product page claims 950+ firms and 19,000+ analysts. | **CLAIMED_NOT_SAMPLED:** detail API and broker/analyst linkage are documented; broker content needs entitlement. | **CLAIMED_NOT_SAMPLED:** page claims broker and analyst coverage and notes contributor entitlements may restrict visibility. | **CLAIMED_NOT_SAMPLED:** S&P claims 250+ model contributors; identity/visibility and export rights are not proven. |
| EPS, revenue, horizon, fiscal mapping | **CLAIMED_NOT_SAMPLED:** EPS and broad measures/KPIs are claimed; fiscal-period mapping must be sampled across non-calendar issuers. | **CLAIMED_NOT_SAMPLED:** API supports metrics and fixed/rolling fiscal periods; report-builder warns fiscal-year-end changes can remove prior schema rows. | **CLAIMED_NOT_SAMPLED:** page claims 3–5-year horizon and general/industry metrics; quarterly/year mapping must be tested. | **CLAIMED_NOT_SAMPLED:** S&P claims 5–10 years (up to 15) and line/KPI depth; each horizon and period mapping needs an export test. |
| source-effective / published / provider-observed clocks | **UNESTIMABLE:** public materials establish PIT/date-time language, not all five clocks. | **PARTIAL CLAIMED_NOT_SAMPLED:** API documentation names `inputDateTime` (source availability) and `lastModifiedDate`; publication, provider-observed and withdrawal clocks unverified. | **PARTIAL CLAIMED_NOT_SAMPLED:** `spEffectiveDate` and `spToDate` are named; source publication and provider-observed clocks unverified. | **PARTIAL CLAIMED_NOT_SAMPLED:** broker timestamp claimed; no public mapping to K3E clock vocabulary. |
| revisions, corrections, withdrawals / restatements | **CLAIMED_NOT_SAMPLED:** historical/PIT products exist, but correction lineage semantics were not published in examined sources. | **PARTIAL CLAIMED_NOT_SAMPLED:** PIT methodology says snapshots are not adjusted for later QA corrections, dilution, default-currency changes, or unavailable broker estimates. Withdrawal/reissue behavior remains untested. | **CLAIMED_NOT_SAMPLED:** revisions and snapshots are claimed; correction, restatement and withdrawal lineage requires samples. | **UNESTIMABLE:** no public correction-lineage schema examined. |
| identifiers / corporate actions | **UNESTIMABLE:** no verified delivered identifier or corporate-action record. | **UNESTIMABLE:** FactSet Symbology linkage is claimed, but cross-listing, successor and adjustment behavior require records. | **UNESTIMABLE:** no delivered identifier/corporate-action sample examined. | **UNESTIMABLE:** no delivered identifier/corporate-action sample examined. |
| history and universe | **CLAIMED_NOT_SAMPLED:** product page claims US from 1976 and non-US from 1987; field/region survival needs sample coverage output. | **CLAIMED_NOT_SAMPLED:** PIT consensus public history starts Dec-2009 while non-PIT estimates claims are deeper; the distinction is material. | **CLAIMED_NOT_SAMPLED:** public claims give 1996 international/1999 North American history, varying by metric. | **CLAIMED_NOT_SAMPLED:** S&P claims history since 2019 non-US / 2017 US, distinct from CIQ Estimates. |
| operability / limits | **PARTIAL CLAIMED_NOT_SAMPLED:** documented API, FTP, cloud and feed delivery, but no entitlement or production limit proof. | **PROVEN (public API doc):** 10 requests/sec and 10 concurrent requests/user for the API; real account/product throughput remains untested. | **UNESTIMABLE:** delivery channels are claimed but public rate-limit evidence was not found in examined materials. | **UNESTIMABLE:** same. |
| storage, derived data, redistribution, display, model-training rights | **RIGHTS_UNVERIFIED** | **RIGHTS_UNVERIFIED** — public documentation also shows broker entitlements constrain visibility. | **RIGHTS_UNVERIFIED** — contributor entitlements constrain visibility. | **RIGHTS_UNVERIFIED** |
| authoritative public cost | **UNESTIMABLE** | **UNESTIMABLE** | **UNESTIMABLE** | **UNESTIMABLE** |

### Primary-source ledger

| candidate | primary source accessed 2026-08-23 | admissible claim only |
|---|---|---|
| LSEG I/B/E/S | [I/B/E/S Estimates product page](https://www.lseg.com/en/data-analytics/financial-data/company-data/ibes-estimates); [LSEG Quant Research brochure](https://www.lseg.com/content/dam/data-analytics/en_us/documents/brochures/data-for-quant-research.pdf); [LSEG developer catalogue](https://developers.lseg.com/en/api-catalog/refinitiv-data-platform/rdp-data-exploration/quickstart/company) | detail/consensus/KPI/history product family, PIT product claim, delivery options and catalogue-level sample/rate-limit claim. |
| FactSet | [FactSet Estimates API](https://developer.factset.com/api-catalog/factset-estimates-api); [PIT Consensus overview](https://insight.factset.com/resources/at-a-glance-factset-estimates-point-in-time-consensus); [Estimates DataFeed overview](https://insight.factset.com/resources/factset-consensus-estimates-datafeed) | broker-detail/fiscal APIs; source-availability and last-modified fields; PIT methodology; historical detail/guidance and analyst linkage claims. |
| S&P Capital IQ Estimates | [Capital IQ Estimates](https://www.spglobal.com/market-intelligence/en/solutions/capital-iq-estimates); [Fundamental Data](https://www.spglobal.com/market-intelligence/en/solutions/products/fundamental-data); [specific-observation-date query](https://www.marketplace.spglobal.com/en/support/query-library/query-%281008%29) | two-hour snapshot and effective/to-date field claims; current/historical/revision product claims; specific observation-date query is an available product query, not a reproduced result. |
| Visible Alpha | [S&P Estimates offering](https://www.spglobal.com/market-intelligence/en/solutions/products/estimates) | separate dataset, contributor/KPI/horizon/history/broker-timestamp product claims only. |

No non-vendor commentary, comparison blog, price estimate, or unlicensed payload was used as positive evidence. Cost was not reported because no authoritative public price schedule for a comparable entitlement was found in the examined primary sources.

## Frozen representative sample design

The sample must test data semantics, not whether a single mega-cap ticker renders.
It should be frozen before access and reused byte-for-byte across every candidate.

| component | frozen requirement | discriminator |
|---|---|---|
| issuer panel | 30 issuers: 12 US, 8 Europe, 6 APAC, 4 Canada/other; large/mid/small capitalization; at least 8 non-calendar fiscal years; at least 3 ADR/cross-listing or share-class cases; at least 3 mergers/spin-offs/renames; at least 4 formerly covered/inactive names | universe marketing and identifier claims versus actual survivorship, identity and fiscal mapping behavior |
| periods / metrics | EPS and revenue for annual + quarterly horizons; one industry KPI where offered; two completed periods, two current/future periods, and one long-horizon request | horizon breadth and fiscal-period mapping rather than an aggregate screen |
| as-of replay | request the same issuer/metric/period as of 10 pre-fixed historical dates around earnings and revision windows; repeat extraction on a second authorized client/day | whether a reproducible as-known value, effective interval, and provider cutoff actually exist |
| revision and correction probe | select 10 documented estimate revisions; select at least 3 issuer corporate/fiscal changes and 3 late actual/correction cases; request the pre-change, post-change and current views | append/supersede lineage versus hindsight overwrite, disappearance, or silent restatement |
| contributor probe | request broker/analyst/provider identity, status, exclusion, coverage count and native record ID wherever license permits | distinguishes visible aggregate consensus from legally usable detail history |
| clock probe | capture every delivered source timestamp, effective interval, publication/availability marker, collection time and system receipt time; label any absent clock `UNAVAILABLE`, not inferred | clock collapse and look-ahead risk |
| null probe | deliberately request uncovered issuer, unsupported metric, out-of-history as-of date, missing fiscal period, excluded broker, and post-corporate-action predecessor ID | whether missingness is distinguishable from zero, empty consensus, entitlement failure, or an unavailable request |
| rights probe | obtain the relevant order form/data dictionary/licence schedule for raw retention, derived features, model training, internal display, external display, redistribution, deletion/retention and analyst/broker attribution | determines whether an otherwise excellent record is lawful for K3E use |
| reproducibility receipt | retain only permitted sample identifiers, request parameters, response schema version, field-presence matrix, content hash, timestamp and access/entitlement label — never confidential payload in git | independently auditable without retaining vendor data |

### Pass / fail criteria before any winner claim

A candidate may be considered for a later procurement decision only if the authorized
sample proves all of the following at record level:

1. a stable vendor identifier and fiscal-period identity for EPS and revenue;
2. a usable as-of mechanism that returns an historically contemporaneous record,
   with no undetected look-ahead;
3. distinct source/provider and local observation clocks, or explicit typed absence;
4. a revision/correction/withdrawal lineage that can preserve the prior as-known value;
5. null and entitlement states distinguishable from legitimate zero/empty values;
6. a documented corporate-action and fiscal-calendar treatment for the frozen edge cases;
7. applicable written rights for the contemplated raw/derived/storage/display/training uses; and
8. a repeatable extraction within the contracted rate/operability envelope.

Failure of any condition is not a reason to backfill or normalize it away. The
candidate is marked `PARTIAL`, `RIGHTS_BLOCKED`, or `UNESTIMABLE` for that use.

## Exact remaining external gate

The next lawful action is one procurement-neutral request for a **time-limited
evaluation entitlement or vendor-supplied, rights-permitted redacted export** for
the frozen sample above, accompanied by the applicable data dictionary and rights
schedule. It must specify whether broker/analyst detail is entitled and which
uses are allowed. This VEND-0 packet does not authorize the request to be sent,
a trial to be started, terms to be accepted, a purchase to be made, confidential
data to be uploaded, or a sample to be committed to this repository.

Until that gate is satisfied, the only truthful answer is:

> Credible institutional candidates exist, but no vendor is selected and no
> historical consensus capability is proven for K3E.

## Negative proof / non-goals

- No credential value, private contract, sample payload, vendor contact, trial,
  purchase, term acceptance, or external persistent change occurred.
- No provider adapter, ingestion job, storage schema, model, ranker, fair-value,
  trade/gate/size, Prophet, event, identity, lifecycle, publication, or control
  plane was added or modified.
- No claim of production proof, data-rights clearance, exact price, or vendor
  winner is made.
