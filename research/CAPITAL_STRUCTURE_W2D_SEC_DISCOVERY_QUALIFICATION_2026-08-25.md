# Capital Structure V2 W2D — SEC discovery-clock qualification

Date: 2026-08-25
Owner: Capital Structure Intelligence V2
State: qualified implementation, held for Sol; not merged and not proven live
Protected Skillpack: `mastermindx-market-intelligence/Mastermind@51f9942733b86e550bb9169d2a43462bd28e774f`

## Executive finding

Natural run `32786919396` did not prove that SEC was unavailable. It exposed a
calendar/readiness defect in our discovery contract: at
`2026-08-25T00:04:02Z` (August 24 at 20:04 ET), the collector treated both the
August 24 and August 25 daily indexes as due. The August 24 index had not yet
entered its documented nightly construction window, and August 25 was still a
future SEC filing day in New York.

A later read-only canary using the production SEC identity, headers, timeout,
and pacing retrieved the August 24 index successfully. Its `Last-Modified` was
`2026-08-25T02:01:43Z` (22:01:43 ET on August 24), while the still-unpublished
August 25 object returned an XML `AccessDenied` response. The quarterly archive
listing contained August 24 and did not contain August 25. The original 403 is
therefore classified primarily as object publication/readiness timing, not an
SEC rate-limit or general access-policy failure.

The repair keeps one discovery ledger and one evidence plane:

- Latest Filings Atom is the provisional same-day accession-discovery surface.
- The daily EDGAR form index is authoritative end-of-day reconciliation and
  bounded backfill.
- SEC Archives complete-submission bytes remain the only filing evidence that
  may enter source-manifest, evidence-ID, closed-bundle, event, and projection
  law.

No queue, store, source-of-truth, job, cadence, timeout, capacity envelope, or
authority plane is added.

## Production falsifier receipt

Run `32786919396`, collect job `97620633216`, and Capital Structure job
`97654020902` produced generation
`a6ff3b6b47db58ec549ff4508399312311f549a1`.

The committed discovery state said:

- horizon: `degraded_discovery`
- reason: `latest_expected_index_not_complete`
- latest expected daily index: `2026-08-25`, status `retry`
- latest completed/discovered/retained/compiled filing date: `2026-08-21`
- August 24 daily-index error: HTTP 403
- August 25 daily-index error: HTTP 403

At the collection instant, UTC had crossed midnight but New York had not. The
old caller passed `now.date()` in UTC to `due_index_dates`, so the horizon asked
for an SEC day that did not yet exist and asked for the current New York day's
daily reconciliation before the SEC's documented nightly build.

## Official-source law

The qualification uses the following primary SEC sources:

- [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data): EDGAR accepts filings on business days from 06:00 to 22:00 ET; current-day indexes begin updating around 22:00 ET and usually complete within a few hours; automated access is capped at 10 requests per second.
- [Submit Filings](https://www.sec.gov/submit-filings): EDGAR filing hours and federal-holiday closure are New York/ET rules.
- [Determine the Status of My Filing](https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing): most post-17:30 ET filings receive the next business day's filing date, with named form exceptions.
- [Developer Resources](https://www.sec.gov/about/developer-resources): Latest Filings RSS and daily/quarterly indexes are official EDGAR data surfaces.
- [RSS Feeds](https://www.sec.gov/about/rss-feeds): Latest Filings search results are available as RSS/Atom.
- [Latest Filings](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent): current official filing-date filings are exposed before nightly index reconciliation.
- [EDGAR Calendar](https://www.sec.gov/submit-filings/filer-support-resources/edgar-calendar): EDGAR does not accept filings on listed federal holidays.

W2D adopts a conservative daily-index readiness boundary of 06:00 ET on the
following calendar day. That is later than “within a few hours” after the
documented 22:00 ET start and prevents a partly built index from being called
overdue. The boundary is a health expectation, not a scheduler, retry, or SEC
request-rate change.

## Read-only canaries

The canaries used the configured production User-Agent (redacted in this
record), `Accept-Encoding: gzip, deflate`, a 30-second timeout, and unchanged
`PACE_SECONDS=0.12`. They did not write any discovery, coverage, retrieval,
source-manifest, or event ledger.

### Daily-index canary

At `2026-08-25T20:08Z`:

| Object | Result | Evidence |
|---|---:|---|
| `form.20260824.idx` | 200 | `Last-Modified=2026-08-25T02:01:43Z`; 1,022,564 bytes; 5,251 filing rows; SHA-256 `40b557e6e6782c79084c6d7256d81dff8a498ebf8040d9b65f05cdcaeea7f649` |
| `form.20260825.idx` | 403 | XML `AccessDenied`; the object was not yet in the QTR3 archive listing and the canary preceded the August 25 nightly build |
| QTR3 `index.json` | 200 | contained `form.20260824.idx`; did not contain `form.20260825.idx` |

This result does not mean every SEC 403 is a readiness response. The collector
persists the exact response as retryable; only clock and archive evidence allow
this specific incident to be classified.

### Latest Filings canary

A bounded 30-page traversal read 3,000 Atom entry rows and 2,031 unique
accessions. Every page was full, page 14 was the first to include an August 24
filing, and page 29 still mixed August 24 and August 25 rows. Duplicate listing
rows were common because one accession can appear under multiple filing roles.
The feed exposed no trustworthy `next` link or total count.

Therefore one page is not an exhaustive market-wide discovery claim. Production
traversal must page from offset zero until it crosses the prior durable update
watermark (including equal-time ties), or reaches an actual short/empty end. It
must fail closed if the fixed page cap is exhausted or if a final page-zero
read proves the leading anchor moved beyond the bounded window.

## Implemented source law

### Two explicit clocks

`capital-structure-sec-discovery-clock/1.0.0` publishes two separate facts:

1. `latest_expected_realtime_filing_date`: the latest open SEC filing day whose
   Latest Filings stream must have been observed.
2. `latest_expected_sec_index_date`: the latest SEC filing day whose daily
   index should be complete after the conservative readiness boundary.

All calculations use `America/New_York`. Weekends and observed US federal
holidays roll back to the latest open filing day. A naive datetime is rejected.

### Provisional overlay and authoritative reconciliation

Latest Filings rows:

- are parsed strictly from Atom accession ID, form category, title CIK/company/
  role, summary filing date/accession, entry update time, and archive link law;
- prefer the `Filer`/`Issuer` role when one accession is listed multiple times;
- preserve the unchanged form allowlist and issuer-scoped reconciliation rule;
- are deduplicated by canonical accession into `discovery.parquet`;
- are marked `discovery_channel=latest_filings` and remain provisional.

Daily-index rows reconcile the same accession in place. They replace provisional
issuer/form/path metadata, preserve the original `_first_seen`, retain the
Latest Filings observation fields, and stamp `reconciled_at`. They do not append
a second discovery row and cannot rewrite a previously published source
manifest, evidence ID, bundle, or event.

### Fail-closed traversal

The traversal cap is 200 pages of 100 rows (20,000 listing rows) at the existing
0.12-second pacing. A scan is accepted only when it proves one of:

- an update strictly older than the prior durable watermark was crossed, while
  equal-time rows were retained; or
- the official feed returned a short or empty page.

After reaching the boundary, page zero is fetched once more. The original
leading entry must remain inside the final first page; otherwise the entire
overlay attempt is discarded and coverage is recorded `retry`. No partial rows
enter discovery.

### Health truth

Health filters daily reconciliation and real-time overlay coverage separately.
Before the daily-index readiness boundary, the current New York filing day's
daily index is not overdue. After readiness, a missing/non-complete expected
daily index degrades discovery. Independently, a missing, retrying, invalid, or
stale Latest Filings observation degrades discovery even if yesterday's daily
index is complete.

The queue receipt binds the clock policy version. Legacy receipts without that
field preserve the previous health interpretation for historical artifact
compatibility.

## Hostile fixtures

The attributable fixtures prove:

- Monday 18:30 ET uses Friday as the latest expected daily index but requires a
  Monday Latest Filings observation.
- Monday 22:00 ET still does not declare Monday's in-progress daily index
  overdue.
- Tuesday after 06:00 ET requires Monday's completed daily reconciliation.
- Weekend and federal-holiday clocks use the last open filing day.
- UTC midnight while New York remains on the prior day does not advance the SEC
  filing date.
- a multi-page traversal crosses the durable watermark and retains equal-time
  ties.
- exhausting the 20,000-row bound publishes no partial discovery.
- a source movement that ejects the leading anchor fails closed.
- overlay unavailability records a retry with no partial discovery.
- one accession observed through Latest Filings and then the daily index remains
  one discovery row, one immutable evidence ledger, and one compiled event.
- daily reconciliation corrects provisional metadata without changing the
  historical evidence bytes.
- a missing daily index after its actual readiness time degrades discovery.

## Frozen boundaries

W2D does not change:

- `LIVE_TAIL=500`, `RECOVERY=20`, `HISTORICAL_BACKFILL=20`, derived global 540;
- class precedence, lane fairness, newest-session ordering, spill, parking, or
  retrieval pacing;
- the daily workflow carrier, job graph, 240-minute collector cap, 90-minute
  Capital Structure cap, or 76.5-minute warning;
- source/evidence/event identity, closed-bundle atomicity, append-only fence,
  compiler/projection binding, public twin, #5792, or W1 publication law;
- archive complete-submission bytes as the sole filing evidence;
- `prophet_authority=false`.

W2D is qualified locally but is not accepted, merged, or proven live. It must
remain a draft `[HOLD-FOR-SOL]` carrier. It may not merge before W2C adjudication.
After both held waves are accepted and merged, only the first natural scheduled
chain containing both may prove W2 closure.
