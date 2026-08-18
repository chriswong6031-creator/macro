---
key: GOVREV-DOUBLE-COLLECT-PUBLISHED-NOTHING-X-THEIRS-DROPPED-IT
claim: >
  USAspending published NOTHING between the two 2026-08-18 collection passes — all 376
  receipt pages that differ between 59ccb9c774c8 and 93ab221b81dd carry byte-identical
  `request_sha256` AND `response_sha256`, differing only in `run_id`, `observed_at` and
  the `receipt_id` derived from them — so every re-identified candidate, including the
  rail reclassifications that flip `usaspending_award_snapshot` <-> `usaspending_award_action`,
  is pure re-derivation on our side and not a source event. The row loss that caused it is
  resolved BY NAME by `git pull --rebase --autostash -X theirs origin main`
  (.github/workflows/daily.yml:702, :751, :772, :1313): the later run's append and the
  earlier run's append are a conflicting tail hunk in an append-only JSONL/parquet, and
  `-X theirs` resolves that conflict to the run being replayed, discarding the rows already
  on main rather than unioning them.
falsifier: >
  Exhibit any receipt key `(subject.award_key, subject.ticker, rail, page)` whose
  `response_sha256` differs between the two commits — reproduce with:
  `git show 59ccb9c774c8:data/government_revenue/collection_receipts.jsonl` and
  `git show 93ab221b81dd:data/government_revenue/collection_receipts.jsonl`, take the
  multiset difference of canonical-JSON lines (376 rows each side), index both by that
  4-tuple and compare `response_sha256`. Measured: 376 of 376 identical, 0 differing.
  Or show a `-X theirs` rebase that PRESERVES both sides' appended tail lines in a
  conflicting hunk of an append-only file — the 12-line reproduction in the Detail section
  below settles that one in isolation, outside this repo.
so_what: >
  First: when a govrev (or any append-only collector) red reports rail reclassification,
  changed `event_type`, or shifted `effective_at`, do NOT reason from the derived artifacts
  about what the source published — go to `collection_receipts.jsonl` and compare
  `response_sha256` per page. Identical response hashes prove the source published nothing
  and the change is ours, which turns "the source moved" into "we lost rows", a completely
  different repair. Here that check took one pass over two blobs and answered a question the
  parquet-level diff could not.
  Second: `-X theirs` is not a safe conflict strategy for append-only artifacts. It is
  correct for a re-derivable snapshot (take the newest computation) and silently lossy for a
  ledger (drop the other run's evidence). This is the same shape as
  `rebase-splices-two-renders-into-a-paywall-leak` on the render lane — `-X theirs` has now
  cost this repo evidence twice, in two different lanes.
  Third, and this is a DECLINED remedy rather than a missing one: do NOT reach for
  `merge=union` here. An earlier revision of this record recommended it, on the observation
  that `.gitattributes` carries 20 `merge=union` entries and none for
  `data/government_revenue/`. The observation is true and the inference is WRONG, refuted by
  PR #5885 and verified here. `candidate_ledger.jsonl` is bound by an exact BYTE PREFIX
  hash — `prefix = ledger.raw[:prior_byte_count]`, then
  `if sha256(prefix).hexdigest() != state_ledger["prior_sha256"]: raise
  CandidateProjectionError` (scripts/build_government_revenue_candidates.py:540-542) — and a
  union-merged tail cannot reproduce that hash, so union converts a SILENT lost update into a
  HARD projection-lane failure. Union also cannot cover the parquet spine at all (binary),
  and the parquets are what actually moved `candidate_id` (16 of 210, 18 of 35,257), so the
  exposure that caused the red would survive untouched. Partial application is worse still:
  union on the receipt ledgers with the parquets unmerged yields receipts from BOTH runs
  against a spine from ONE — precisely the mixed generation the collector's torn-generation
  refusal (collectors/usaspending_awards.py:3956-3972) exists to prevent.
  The distinction to carry: all 20 existing `merge=union` entries are STANDALONE ledgers with
  no cross-artifact hash binding, whereas `data/government_revenue/` is ONE hash-bound
  generation. **The unit of correctness is the family, not the file.** That is why #5870's
  repair had to revert every moved file across both trees, and why the right remedy withholds
  the whole coherence family (the base fence) rather than merging any single artifact.
  Third: the collector's own dedupe is NOT the defect and must not be "fixed" — see
  DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  origin/main @87cce5e2d4e1, worktree branch claude/govrev-event-identity-adjudication.
  Receipts: multiset diff of `collection_receipts.jsonl` between 59ccb9c774c8 and
  93ab221b81dd → 376 rows only-in-pass-1, 376 only-in-pass-2, 376 common 4-tuple keys;
  fields differing on all 376 = {`run_id`, `observed_at`, `receipt_id`}; fields identical on
  all 376 = {`endpoint`, `has_next`, `page`, `rail`, `record_count`, `request_sha256`,
  `response_sha256`, `schema_version`, `subject`}. Pass 1 run_id
  `usaspending-97b25ea228b65919c41eab1a` observed 2026-08-18T01:37:55.262200Z; pass 2 run_id
  `usaspending-643af6aaa406bdd6db068f65` observed 2026-08-18T01:55:22.848864Z. 168 distinct
  award keys across 21 tickers (AVAV BA BWXT CW GD GE HEI HII HWM IRDM KTOS LDOS LHX LMT NOC
  PLTR RTX TDG TDY TXT VSAT).
  Spine (null-aware column diff, pandas): `award_event_snapshots.parquet` 210 rows both
  sides, only `known_at` + `source_receipt_id` differ and only on positions 194-209 (the 16
  rows pass 1 appended), `event_state_sha256` identical on all 16;
  `award_action_versions.parquet` 35,257 rows both sides, only `known_at`, `first_seen_at`,
  `award_recipient_known_at`, `source_receipt_id` differ and only on positions 35,239-35,256
  (18 rows), `event_state_sha256` identical on all 18. 194/210 and 35,239/35,257 rows
  untouched proves the re-observation dedupe
  (collectors/usaspending_awards.py:1915-1916) works and is not re-stamping.
  Resolver: `.github/workflows/daily.yml:702` `git pull --rebase --autostash -X theirs
  origin main`, same idiom at :751, :772, :1313, :1786; concurrency at :65 puts each cron
  and each `workflow_dispatch` in its own group with `cancel-in-progress: false`, so
  overlapping collect jobs are by design.
scope:
  - macro
  - .github/workflows/daily.yml
  - collectors/usaspending_awards.py
  - data/government_revenue/
confidence: verified
---

## Detail

### What the receipt check settles that the parquet diff could not

`DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS` established the lost update from
the parquet side and is correct. It did not compare the receipts' `response_sha256`, so it
could not close the remaining question: when the re-derived candidates changed
`source_rail` between `usaspending_award_snapshot` and `usaspending_award_action`, was that
a real USAspending publication in the 17.5-minute window, or our own re-derivation?

It is entirely ours. Both passes hit the same endpoints with the same request bodies
(`request_sha256` identical on all 376 pages) and received byte-identical bodies back
(`response_sha256` identical on all 376), with identical `record_count` and `has_next`. The
only things that moved are the three fields that encode *when we fetched* and *which run
fetched*. There is no source event anywhere in this incident.

This matters for disposition: a rail reclassification driven by a genuine upstream
publication would be a legitimate new observation deserving forward issuance. A rail
reclassification with an identical response body is an artifact of recomputing from a base
that had lost rows, and issuing it forward would mint a second identity for a fact the
ledger already holds.

### The resolver that discards the rows

The push path retries `git pull --rebase --autostash -X theirs origin main`. During a
`pull --rebase`, the local commit is the side being replayed, so `-X theirs` resolves every
conflicting hunk in favour of the local run and against what is already on main.

For a re-derivable snapshot that is the right call — the newest computation wins. For an
append-only artifact it is a silent lost update: run A appended 376 receipt lines to the
tail, run B (computing from a base ~2.5h older) appended its own 376 to the tail of the old
file, the two tails conflict, and `-X theirs` keeps only run B's. The measured diff is
exactly that shape — 376 removed, 376 added, same keys, same content hashes.

The same mechanism drops run A's 16 `award_event_snapshots` rows and 18
`award_action_versions` rows, which run B then re-derives under its own `known_at`, which
re-mints `event_id` and therefore `candidate_id`.

### Standalone reproduction (no repo state needed)

```sh
mkdir -p xt/up && cd xt/up && git init -q .
printf 'base1\nbase2\n' > log.jsonl && git add -A && git commit -qm base
cd .. && git clone -q up work
cd up   && printf 'base1\nbase2\nRUN_A_row\n' > log.jsonl && git commit -qam "run A append"
cd ../work && printf 'base1\nbase2\nRUN_B_row\n' > log.jsonl && git commit -qam "run B append"
git pull --rebase --autostash -X theirs origin master
cat log.jsonl
```

Output:

```
base1
base2
RUN_B_row
```

`RUN_A_row` is gone. No conflict was reported, no retry fired, and the push that follows
publishes a file that is not a prefix-extension of its own predecessor. That is the whole
incident in twelve lines: two runs, two appends, one survivor.


### What is NOT the defect

The re-observation dedupe works. 194 of 210 snapshot rows and 35,239 of 35,257 action
version rows are byte-identical across the two passes; only the rows run B could not see
were re-derived. A second pass over content the run CAN see re-stamps nothing. Do not
"fix" `known_at` re-stamping — there is none to fix.
