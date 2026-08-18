---
key: OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS
claim: >
  Two `daily.yml` runs whose `collect` jobs OVERLAP each compute the USAspending
  append-only artifacts from the base each checked out, and the later push replaces
  the earlier one's rows wholesale — a lost update, not a merge. Measured 2026-08-18:
  the EDT cron run 32077948964 collected 01:07:12Z→04:08:26Z and committed 59ccb9c774c8
  at 04:01:49Z; the workflow_dispatch run 32084697588 collected 01:27:00Z→04:28:57Z off
  a base ~2.5h older than that commit and committed 93ab221b81dd at 04:21:53Z. Run B's
  push dropped run A's 16 newly appended `award_event_snapshots.parquet` rows and
  substituted its own 16 with the same `event_state_sha256` but its own `known_at`
  (01:37:55.262200Z → 01:55:22.848864Z) and `source_receipt_id`, and dropped run A's
  376 `collection_receipts.jsonl` lines for its own 376 — so `collection_receipts.jsonl`
  on main is no longer a prefix-extension of its predecessor, which is a contract the
  repo's own test asserts (tests/test_usaspending_awards.py:1817
  `assert second_bytes.startswith(first_bytes)`). The two runs cannot supersede each
  other by design: `.github/workflows/daily.yml:65` puts each cron and each manual
  dispatch in its OWN concurrency group, deliberately, so the DST pair cannot kill each
  other's slot.
falsifier: >
  Exhibit a single collector run emitting BOTH receipt run-ids
  `usaspending-97b25ea228b65919c41eab1a` and `usaspending-643af6aaa406bdd6db068f65`, or
  a code path that mutates `known_at` on an existing snapshot row (there is none:
  `_append_event_versions` SKIPS a re-observation whose state hash is unchanged,
  collectors/usaspending_awards.py:1916-1917, and retains prior rows verbatim at
  :1888-1899). Or show the two `collect` jobs did not overlap:
  `gh run view 32077948964 --json jobs --jq '[.jobs[]|select(.name=="collect")]'` and
  the same for 32084697588. Or show `collection_receipts.jsonl` at 93ab221b81dd still
  starts with its 59ccb9c774c8 bytes.
so_what: >
  A hand `gh workflow run daily.yml` while another daily run is queued or in progress
  does not merely waste a runner — it can CORRUPT append-only evidence, silently.
  The existing rule ("never dispatch while a daily.yml run is queued or in progress",
  CLAUDE.md §Recovery etiquette) now has a measured corruption receipt, not just a
  compute-waste rationale. Preflight
  `gh run list --workflow daily.yml --json status --jq '[.[]|select(.status!="completed")]'`
  and do not dispatch over a live run. Second: when a govrev candidate red reports
  "first-seen candidates with neither a ledger issuance nor a reviewed historical
  suppression", check whether the SAME (candidate_family, issuer_company_id, award-ref,
  effective_at) tuples also appear as ORPHANED ledger rows before believing new award
  records arrived — 26 unaccounted paired 1:1 with 26 orphans over 18 tuples here, which
  means re-identification, not discovery. Third: every write-path check in
  collectors/usaspending_awards.py (torn-generation refusal :3956-3972, staged-replay
  binding :4030-4044) compares the run's state to the ledgers on the run's OWN disk, so a
  run whose entire base is stale is internally consistent and passes all of them; the
  missing check is base-freshness against origin/main at push time.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  origin/main @66e260d1610d. Reproduced the red locally on a full-`data/` worktree:
  `python3 -m pytest tests/test_government_revenue_candidates.py -q` → 1 failed / 38
  passed, `tests/test_government_revenue_candidates.py:392` listing the same 26 `grc1-`
  ids as the CI job (run 32100795267, job 95601375488, ci-pack-6). Rebuilt
  `build_candidate_observations` against the committed tree: 56 rebuilt rows vs 56 ledger
  rows, 26 unaccounted and 26 orphaned, with the two sets covering an identical 18-tuple
  key set. Positional diff of `award_event_snapshots.parquet` between 59ccb9c774c8 and
  93ab221b81dd: 210→210 rows, exactly two columns changed (`known_at`,
  `source_receipt_id`) on exactly 16 rows at positions 194-209 — the 16 rows run A
  appended over the 194-row 08-14 base — with `event_state_sha256`, `first_seen_at` and
  `source_response_sha256` identical on all of them. Per-commit walk of the previous 8
  transitions of that file (08-07 through 08-14): 0 rewritten rows in every one.
  `git diff --stat 59ccb9c774c8 93ab221b81dd -- data/government_revenue/` →
  `collection_receipts.jsonl | 752 +++---` (376 removed, 376 added). Chain into the
  failure: `_event_id` folds `known_at` (engine/government_revenue/award_events.py:1409-1419,
  called :1473-1480) → `candidate_id = _digest("grc1", {family, issuer_company_id,
  event_id})` (engine/government_revenue/candidates.py:1665-1669).
scope:
  - macro
  - .github/workflows/daily.yml
  - collectors/usaspending_awards.py
  - data/government_revenue/
confidence: verified
---

## Detail

Three plausible stories were tested and two are wrong.

**Not "a nightly advanced the candidate set without the review/issuance step".** The
issuance step ran: 5214d0b20a17 (`govrev: SAM opportunity evidence 2026-08-18T04:15Z`)
appended 26 rows to `candidate_ledger.jsonl` with `candidate_projection_status`
`status: ok`. Those 26 are precisely the rows that are now orphaned.

**Not "26 new award records arrived".** No award records arrived at all between the two
collection commits: `award_event_snapshots.parquet` stayed at 210 rows and every
semantic column — including `event_state_sha256` — is byte-identical. Only the
observation stamps moved. `agentos/discoveries/DSC-NIGHTLY-LANE-ORDER-DECIDES-LEDGER-COMPLETENESS.md`
(PR #5869, open at the time of writing) attributes the red to "new award records" and to
a five-minute lane-ordering overlap. The ordering observation is real and its
operational prescription — do not hand-issue the missing ledger rows — is correct and
is followed here. The causal attribution is not: a lane-ordering race between a
projection and a *legitimate* collection would leave the earlier ledger rows valid,
because `candidate_id` would not move. What moved `candidate_id` was a second collector
run overwriting the first's rows.

**Not a `known_at` semantics defect.** `known_at` means "the instant of the poll that
first recorded THIS state version" — it is excluded from `AWARD_EVENT_SNAPSHOT_STATE_FIELDS`
(collectors/usaspending_awards.py:302-320), the state hash docstring reads "Hash only
semantic direct-source state, never a receipt or retrieval clock"
(collectors/usaspending_awards.py:857-860), and an identical re-observation is skipped
rather than re-stamped (:1916-1917). Pinning `known_at` per `(award_key, state_hash)` to
first-observation would be actively wrong: for `A→B→A→B`, the fourth row's event carries
an award_key, source_rail, state_hash, event_type and changed_fields tuple identical to
the second row's, so the two would collide into one `event_id` and `_merge`
(engine/government_revenue/award_events.py:1789) would collapse a real transition out of
existence. `known_at` in the `_event_id` seed is load-bearing and must stay.

### Why every existing guard passed

The collector's write path is careful and all of it is scoped to one process's disk: the
torn-generation refusal (:3956-3972) compares the on-disk state binding to the on-disk
ledgers, and the staged-replay check (:4030-4044) proves the bytes a reader will load
reproduce the generation this run computed. Both are satisfied by a run whose base is
stale, because such a run is perfectly self-consistent — it simply does not know that a
newer generation exists. Nothing in the write path, and nothing in the push retry, asks
whether `origin/main` moved under an append-only artifact between checkout and push.

### What clears the CI red

`test_reviewed_historical_cohort_rebuilds_byte_exact_and_nothing_escapes_review` goes
green when the govrev projection lane issues the 26 re-identified candidates forward,
which is the disposition it already takes for any first-seen candidate. That lane —
`government-revenue-live.yml`, "the sole SAM ledger and canonical Government Revenue
projection owner" — is invoked by `daily.yml` at :1341-1346 and its
`government_revenue_projection / refresh` job was queued behind the runner pool from
2026-08-18T04:28:58Z. The scheduled 30-minute ticks of the same workflow cannot overtake
it: they share `concurrency: group: government-revenue-live` with `cancel-in-progress: false`
(:109-113), so run 32103699468 sat `pending` with zero jobs.

Do NOT hand-write the missing ledger rows, allowlist the ids, or repair the parquet by
hand. The ledger's sole legitimate advancer is the nightly. Restoring run A's
`award_event_snapshots.parquet` alone does not work and correctly fails closed: the
committed `award_event_projection_state.json` binds the *current* pair's semantic
digests, so a rebuild against the restored file yields `status != ready` and ZERO
candidates rather than the old 26 (measured).

### Residue this leaves on main

The 26 ledger rows issued at 04:10:06Z are permanently orphaned — real issuances whose
`candidate_id`s no longer rebuild from source, so `/candidate/{id}/history` for them is
stranded. Run A's 376 collection receipts are gone. `collection_receipts.jsonl` on main
is not a prefix-extension of its own predecessor. None of that is repairable by a
session and none of it is what the failing test is reporting; the test is reporting the
26 replacements, and issuing those forward is the correct disposition.
