# Capital Structure W2A queue census — 2026-08-21

This is the small frozen input receipt for W2A scheduling and horizon-health
choices. It records committed ledger facts, not a claim that the W2 scheduler is
already live.

## Exact bases

- `main_at_task_start`: `182102a8810fb40e9b509fc5aecd524809c2f088`
- `implementation_and_refreshed_census_base`:
  `33d70f5ce4b36329e8acfb285557f4c9d3c72589`
- Repository: `mastermindx-market-intelligence/macro`
- Current global retrieval cap: 200 filings per collector run

The base advanced during context loading because a natural production chain
landed new Capital Structure ledgers on `origin/main`. The refreshed census
below is therefore the quota evidence; the earlier snapshot is not used to size
the implementation.

## Refreshed committed facts

At `33d70f5ce4b3`:

| Fact | Value |
| --- | ---: |
| In-policy discovery rows | 20,053 |
| Post-run retryable candidates | 18,652 |
| Parked accessions | 403 |
| Latest discovered filing date | 2026-08-20 |
| Latest eligible-retained filing date | 2026-07-31 |
| Latest compiled filing date | 2026-07-31 |
| Latest completed daily index | 2026-08-20 |
| Newest daily index state | 2026-08-21 `retry` (attempt 2, HTTP 403) |

The latest five completed SEC index sessions are 2026-08-14, 08-17, 08-18,
08-19, and 08-20. They contain 1,320 post-run pending candidates:

| Retrieval lane | Pending in live horizon |
| --- | ---: |
| issuer_current_report | 604 |
| issuer_periodic | 250 |
| issuer_proxy | 20 |
| prospectus | 267 |
| reg_a | 29 |
| registration | 77 |
| state | 73 |

Across the eight latest completed sessions, all-policy daily arrivals were p50
281.5, p90 457.7, p95 471.4, and max 485. No static class split inside the
unchanged 200 cap can honestly promise full current-tail clearance while also
reserving recovery and historical work.

The newly landed natural run also proves the current daily-index path can recover:
2026-08-20 moved from retry to complete and delivered 199 in-policy rows. W2A
therefore does not add a second source. The still-retrying 2026-08-21 index must
surface as `degraded_discovery` until the existing path succeeds.

## Frozen W2A policy

| Work class | Reserved slots | Boundary |
| --- | ---: | --- |
| `LIVE_TAIL` | 160 | Latest five policy-current `complete` SEC index sessions, after recovery precedence |
| `RECOVERY` | 20 | Latest queue-open state in `storage_deferred`, `transient_error`, or `stored_parser_deferred` and filing date inside the latest 20 policy-current completed sessions |
| `HISTORICAL_BACKFILL` | 20 | Remaining unparked eligible candidates |

Parking and ordinary queue eligibility run before classification. Unused
reservations spill in donor order `LIVE_TAIL`, `RECOVERY`,
`HISTORICAL_BACKFILL`; each donor offers slots to that same recipient order
with itself omitted. The existing weighted lane rotation runs once inside each
final class allocation. Within each lane, LIVE_TAIL serves newest filing
sessions first and uses exact current-run arrival as the same-session tie-break,
while RECOVERY and HISTORICAL_BACKFILL retain the prior oldest-first debt order. This newest-first
law is required by the production-shaped ledger: oldest-first selected zero
2026-08-20 rows before correction even though 2026-08-20 was the discovery
horizon.

The partition is a fairness and
observability policy. `degraded_capacity` is expected whenever measured arrivals
or the live horizon exceed effective selected capacity; historical backlog alone
does not make the current horizon degraded.

The discovered watermark date and observation clock are bound to the same
newest filing-date cohort. Eligible retention means a durably retained,
parser-eligible, clean complete-submission root; W1 roots remain retained even
before the operational file-number-provenance backfill closes their queue item.
The retained clock is likewise selected only from roots at the retained filing
date. A persisted federal-closure `not_published` row closes discovery coverage;
an aged weekday HTTP 404 using the same storage status does not.

Public projection freshness is downstream of one generation-bound health
calculation over discovery, eligible retention, and compiled events. Compiler
age remains visible as generation freshness but cannot authorize a `fresh`
information-horizon claim.

## Reproduction boundaries

The census was read-only against committed Parquet/JSONL/JSON ledgers and
reimplemented the current collector eligibility, queue-closing, and parking
predicates. No network request was used. A future production proof must use the
first natural scheduled collector to Capital Structure chain after the W2A merge;
do not dispatch a duplicate daily run.
