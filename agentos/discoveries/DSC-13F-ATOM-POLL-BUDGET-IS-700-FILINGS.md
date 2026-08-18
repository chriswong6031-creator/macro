---
key: 13F-ATOM-POLL-BUDGET-IS-700-FILINGS
claim: >
  The institutional 13F census fast lane is bounded by FILINGS BETWEEN COMPLETED POLLS,
  not by wall clock. One atom poll reaches min(--max-accessions 750,
  ATOM_EPHEMERAL_ENTRY_LIMIT 930) = 750 entries, and the healthy `known_overlap` exit
  requires a FULL 100-entry page already checkpointed, so the real budget is 700 new
  13F-family filings; at 701 the scan exits `ephemeral_limit`, discovery.atom.complete
  goes False and the run FAILS. The feed is form-filtered server-side
  (action=getcurrent&type=13F, re-forced per page) plus a client-side FORM_TYPES
  filter, so those 700 are 13F filings, not filings of all types. Measured peak arrival
  is under ~200/hour even on a deadline day, so an hourly poll spends under a third of
  the budget. Separately, most of the `discovery:` block of config/institutional_13f.yml
  is DEAD CONFIG with no consumers repo-wide - latest_filings_page_size,
  latest_filings_max_pages, max_accessions_per_run, daily_index_lookback_days,
  full_index_reconcile_days and index_not_published_grace_days are all unread, so the
  apparent 1,200-entry reach (100 x 12) does not exist.
falsifier: >
  Raising --max-accessions in .github/workflows/smart-money-13f-census.yml above 930
  (making ATOM_EPHEMERAL_ENTRY_LIMIT the binding term instead), changing the
  `known_overlap` exit in engine/institutional_census/sec_sources.py so completeness no
  longer requires a fully-known page, or wiring the dead `discovery:` config keys to
  real consumers. Any of these moves the budget off 700.
so_what: >
  Size this lane's cron by filing arrival rate, never by "it feels stale". Hourly holds
  2x margin against a ~2h crush ceiling; ~4h is the ordinary-day ceiling. Overrun is the
  GOOD failure - LOUD (red run) - and the daily/full index lanes recover the accessions,
  so widening the interval cannot silently drop filings. That is what made it safe to
  cut the lane from 24 firings/day to 9 (PR #5850) to stop it starving the shared
  two-host macstudio pool and the authoritative nightly. Do NOT reason from
  config/institutional_13f.yml's discovery block - it is decorative.
kind: constraint
verified_at: 2026-08-17
verified_by: >
  engine/institutional_census/sec_sources.py:49 (ATOM_EPHEMERAL_ENTRY_LIMIT = 930),
  :41-44 + :1072-1086 (type=13F in the base URL and re-forced per page), :39 + :984
  (FORM_TYPES client filter), :1114-1145 (page walk; short_page/known_overlap return
  complete=True, stalled/ephemeral_limit return False);
  engine/institutional_census/rolling.py:1172 (entry_limit=min(max_accessions, 930)),
  :1397-1404 (atom_complete -> has_coverage_gap -> status);
  scripts/run_institutional_13f_rolling.py:264 (non-zero exit outside {ok,no_changes});
  .github/workflows/smart-money-13f-census.yml (--max-accessions 750).
  Arrival-rate bound MEASURED on 2026-08-14, the Q2 13F deadline and heaviest day of
  the quarter: executed polls 31836198835 (job 23:24:14Z->00:12:01Z) and 31851720444
  (00:57:14Z->00:58:31Z) were 3h46m apart spanning the 17:30 ET cutoff and BOTH
  succeeded; success requires complete is True, so each window delivered <=700.
  Dead config confirmed by repo-wide grep of the six key names: the only hit outside
  config/institutional_13f.yml is scripts/build_institutional_13f_census.py:819, which
  reads only the public_summary / research_bench blocks.
scope: [macro]
confidence: verified
---

## Detail

Two independent facts get conflated when sessions size this lane, and both mislead
toward a denser cron than correctness needs.

First, the reach looks like 1,200 (`latest_filings_page_size: 100` x
`latest_filings_max_pages: 12`) if you read the config. Those keys have no consumers;
the live path takes its bound from `--max-accessions 750` on the command line and the
930 constant in code, and the `known_overlap` full-page requirement costs a further 100.
700 is the number that matters.

Second, `gh run list` makes the lane look far more expensive than it is, because its
`startedAt` equals `createdAt` - so any duration computed from it is queue+execution
lifetime, not execution. This lane's lifetime p90 was 124.7 min against true execution
of 7-15 min. Sizing either the cron or `timeout-minutes` off the run list argues for
keeping headroom the job never uses. True cost is only in
`gh api /repos/OWNER/REPO/actions/runs/<id>/jobs`.

The failure mode is the reassuring part. Every way of exceeding the budget routes to
`complete=False`, which reds the run, rather than to a quiet short read. The one known
exception is a latent bug, chipped separately: the `short_page` exit at
sec_sources.py:1129-1130 compares `len(page)` - the FORM-FILTERED list - against the raw
`count` requested, so a single out-of-set 13F variant on a page would declare
completeness early and truncate the scan while staying green. Exposure scales with pages
walked per poll.
