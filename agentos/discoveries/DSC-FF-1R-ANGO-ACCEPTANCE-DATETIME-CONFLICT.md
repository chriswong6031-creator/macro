---
key: FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT
claim: >
  FF-1R corrective tranche-A run 32708350406 successfully read ANGO's lawful
  20,779-byte legacy manifest, then detected conflicting acceptance_datetime
  assertions for accession 0001628280-26-048138 in the merged prior-manifest
  and current-Submissions evidence set before any issuer, pointer, or recovery
  cursor progress; no historical shard was fetched.
falsifier: >
  Run `gh run view 32708350406 --log`, read the exact
  run_56830b4a74bd82a33d19 receipt and bounded ANGO/source objects, then replay
  `engine/fundamental_forensics/broad_sec_store.py:1919`
  `_assert_no_duplicate_filing_conflicts`. This claim is disproved if the
  receipt does not name historical_submissions_conflict for accession
  0001628280-26-048138, if the manifest transport itself failed, if a
  historical shard was fetched, or if the conflicting field is not
  acceptance_datetime.
so_what: >
  Keep the frozen plan at cursor 0 and preserve every source assertion. Do not
  normalize or choose an acceptance timestamp, skip ANGO, weaken the conflict
  guard, or retry recovery until a separately commissioned source comparison
  establishes whether the disagreement is representational or substantive and
  Sol adjudicates the governing rule.
kind: runtime
verified_at: 2026-08-24
verified_by: >
  GitHub Actions run 32708350406 / job 97374223159; bounded Research R2 read of
  fundamental_forensics/broad-sec/v1/runs/run_56830b4a74bd82a33d19/receipt.json
  at sha256 60d39e7e6ca96d8d570d2c9af88365e7e1ad643330f90023444178df7c3e0194;
  engine/fundamental_forensics/broad_sec_store.py conflict and recovery stop path.
scope:
  - macro
  - fundamental-forensics
  - engine/fundamental_forensics/broad_sec_store.py
confidence: verified
---

The operation selected the exact frozen first 64-CIK slice, fetched one current
Submissions object for ANGO, and fetched zero historical Submissions or Company
Facts objects. Its one typed failure stopped the loop with completed total 0 and
backlog 2,571. ANGO's pointer and legacy manifest, the continuation, and
latest-complete remained byte-identical; the failed immutable receipt and
observation evidence were retained. This is a source-adjudication blocker, not
a recurrence of the manifest transport defect and not an accepted recovery
checkpoint.
