---
key: CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP
claim: >
  collectors/china_visits.py silently discards any institutional_visit candidate
  whose announcementId is falsy, and that drop is invisible to every instrument
  the plane owns. The guard is a bare comprehension filter —
  `rows = [_derive_row(f, ts) for f in candidates if f.get("announcementId")]` —
  so a dropped candidate leaves no typed exclusion, no counter, no log line and
  no health note, while `n_candidates` (reported in health.json's detail and in
  the collect log) keeps counting the PRE-filter list. A run that dropped k
  candidates therefore prints exactly the same shape as a run that dropped none:
  "N candidate row(s) this run", status ok. The reconciling arithmetic
  `represented_downstream + named_typed_exclusions == n_candidates` can only be
  checked from the stores at the collection commit, never from the receipts the
  collector emits. Measured on the first natural post-P1-R1 Asia-close run
  (32460910383 -> collection commit 324c9ca7ab98): the path fired ZERO times —
  145 of 145 candidates carried a non-empty, distinct announcementId and all 145
  were persisted in the same invocation — so P1's falsifier passed on positive
  evidence, not on the absence of this hole.
falsifier: >
  Read data/china_filings/filings.parquet at any collection commit, filter
  category == "institutional_visit", and count rows whose announcementId is
  empty/None/NaN. If that count is 0 for every commit the store has ever carried,
  the drop path is unreachable in practice and this is bookkeeping, not a
  landmine. If it is ever > 0 while health.json for the same commit reads status
  ok with detail "N candidate row(s) this run" and visits.parquet holds fewer
  than N of that run's candidates, the silent drop is confirmed live.
so_what: >
  Do not accept china_visits' own receipts (n_candidates, health status,
  workflow conclusion, or the aggregate visits.parquet row count) as proof that
  every eligible filing was represented — they are all consistent with a silent
  drop. Any future candidate->visit acceptance must reconcile per announcementId
  from the two stores at the immutable collection commit, exactly as the
  2026-08-21 P1 receipt does (research/china_alpha_intelligence/receipts/
  P1_NATURAL_RUN_RECEIPT_2026-08-21.md). Repairing the hole — turning the drop
  into a typed, counted exclusion surfaced in health.json — is a bounded change
  that was deliberately NOT made in the proof session: Sol's 2026-08-21 P1
  adjudication says "Do not independently widen the implementation", so the
  repair needs its own commission. Note the same shape guards nothing else in
  this plane: every other exclusion china_visits can make is already typed
  (no_coverage, source_failure, upstream_degraded).
kind: landmine
verified_at: 2026-08-21
verified_by: >
  P1 natural-run falsifier session 2026-08-21: git cat-file -p
  324c9ca7ab98:data/china_filings/filings.parquet and
  324c9ca7ab98:data/china_visits/visits.parquet read into pandas; candidate
  filter reproduced exactly (category == "institutional_visit") -> 145 rows, 145
  distinct non-falsy announcementIds, 0 falsy; visit plane 145 rows all stamped
  system_recorded_at 2026-08-21T09:29:55.173073+00:00; source read at
  collectors/china_visits.py refresh() (the comprehension guard quoted above).
scope: [macro, collectors/china_visits.py]
confidence: verified
---

Why the hole is narrow but not theoretical: `announcementId` comes straight from
CNInfo's list payload and `china_filings` dedups on it, so a missing value means
an upstream payload anomaly rather than a house bug — exactly the class of event
that arrives without warning and that a plane built to make honest absence
claims must not absorb quietly. The plane's whole product promise is that "no
visit filing for this name" is a *measured* null; a silently dropped candidate
converts a real filing into that null for one company, with every health
instrument still reading `ok`.

Related: [[DSC:CHINA-VISITS-FIRST-CYCLE-ZERO-IS-BOOTSTRAP-NOT-QUIET]] — same
plane, same lesson from the other direction (a zero that instruments reported as
healthy was structural, not real).
