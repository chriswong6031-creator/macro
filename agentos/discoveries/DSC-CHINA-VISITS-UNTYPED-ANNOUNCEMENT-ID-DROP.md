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

## REPAIRED BY P1-R2 (2026-08-22)

Both boundaries named above are now typed, counted exclusions —
DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION. `collectors/china_filings.py` gained
`key_anomaly()` / `normalize_announcement_id()` / `partition_by_key_integrity()`
(pure, owned by the natural-key module) and `write_filings()` now partitions
`new_rows` on that predicate BEFORE the `drop_duplicates(subset=["announcementId"])`
this claim describes — malformed rows are excluded and counted
(`LAST_KEY_INTEGRITY`, folded into `LAST_RUN_OUTCOME`), never silently
collapsed, and a pre-existing malformed row already in the accrued store is
split off and written back verbatim rather than risk being swept into the
keyed dedup. `collectors/china_visits.py`'s bare comprehension is replaced by
`account_candidates()`, an explicit typed split using the SAME predicate
(imported from china_filings, never re-derived), and `refresh()` now
mechanically verifies `represented + typed_exclusions == eligible` as an
explicit branch before trusting its own derivation — an accounting that does
not add up refuses to write anything and degrades to `source_failure`
instead. Any run with typed exclusions is typed `upstream_degraded` (the
EXISTING health state, not a new fifth one — `engine/china_intel_hub.py`'s
`_visit_block()` keys off that literal string, and the hub was read but not
edited per the commission). The `collectors.china_filings` import that
supplies the predicate is now itself fail-closed: an import failure degrades
to `source_failure` rather than the pre-repair behavior of proceeding to
derive blind. Reconciliation is now auditable directly from the collector's
own receipts (`health.json`'s additive `candidate_accounting` field, written
on both the clean and degraded paths) rather than only by cross-referencing
the two stores at a specific commit, which was this claim's `so_what`.
Verified via `tests/test_china_filings_collector.py::TestKeyIntegrityMutationGuard`
and `tests/test_china_visits_collector.py::TestAccountingMutationGuard`
(mutation guards proving the exclusion depends on the real predicate/
accounting, not on the test's own logic). This closes the hole this record
describes; the falsifier and `verified_at` above remain an accurate record
of what was true when this discovery was first verified.

Sequel: repairing this mechanism without designing its lifecycle introduced two
new lifecycle defects — [[DSC:CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS]]
— closed by P1-R3 (DEC:CHINA-COVERAGE-EXCEPTION-LEDGER). This record's own claim
and falsifier are unaffected: the bare-comprehension drop it describes was real
and #6229 did remove it.
