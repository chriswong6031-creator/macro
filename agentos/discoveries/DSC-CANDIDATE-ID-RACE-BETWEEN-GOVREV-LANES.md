---
key: CANDIDATE-ID-RACE-BETWEEN-GOVREV-LANES
claim: >
  `tests/test_government_revenue_candidates.py::test_reviewed_historical_cohort_rebuilds_byte_exact_and_nothing_escapes_review`
  rebuilds candidate observations LIVE from `data/government_revenue/*` and asserts every
  rebuilt `candidate_id` appears in the append-only `candidate_ledger.jsonl` or the
  reviewed-quarantine manifest — but the ledger is advanced by a DIFFERENT lane
  (`government-revenue-live.yml`) than the one that restates the award-event spine
  (`daily.yml` collection). `candidate_id` is
  `_digest("grc1", {candidate_family, issuer_company_id, event_id})`
  (`engine/government_revenue/candidates.py:1665`), and `event_id` is derived from the
  spine's `projection_generation_id`. So whenever a collection restates the spine AFTER
  the ledger's last fold, every affected id changes and the assertion fails on DATA alone,
  with no code change and neither lane at fault. Measured on `origin/main` 2026-08-18:
  the 04:21Z collection (`93ab221b81dd`) moved `projection_generation_id`
  `award-event-36437ac025d26210ea4b5b89` -> `award-event-9f19640ea565ca3387dd95bf`, six
  minutes after the 04:15Z ledger append (`5214d0b20a17`), producing a clean 26-for-26 id
  swap — same tickers (HII/HII/RTX/GD...), same `effective_at 2026-05-15`, 56 rebuilt rows
  vs 56 ledger rows, 26 in each direction. This reds `ci-pack-6`, and because `ci-gate`
  requires every pack green it blocks EVERY pull request in the repo.
falsifier: >
  Roll `data/government_revenue/` back to the ledger-issuance commit with the code
  untouched and re-run the test — it passes; restore and it fails:
  `git checkout 5214d0b20a17 -- data/government_revenue &&
   python3 -m pytest "tests/test_government_revenue_candidates.py::test_reviewed_historical_cohort_rebuilds_byte_exact_and_nothing_escapes_review" -q`
  (1 passed, 122s) then `git checkout HEAD -- data/government_revenue` (1 failed, 95s).
  Two data states, same code, two deterministic outcomes. The claim is refuted if that
  rollback does NOT flip the outcome, or if the 26 unaccounted ids are found to be
  genuinely new economic events rather than re-digested existing ones — check by
  intersecting the ledger rows added at 04:15Z against the unaccounted set (`comm -12`
  returned 0 overlap, i.e. a pure id swap, not new awards).
so_what: >
  A session diagnosing this red will read "first-seen candidates with neither a ledger
  issuance nor a reviewed historical suppression" and hunt for 26 escaped awards or a
  review-process defect. There is none — do not open a govrev data or compliance
  investigation, and do not hand-advance `candidate_ledger.jsonl` (nightly is the sole
  advancer of forward ledgers). The break self-heals on one more
  `government-revenue-live` fold and needs no repo change. It is also RECURRENT by
  construction: any future collection that restates the spine between the ledger fold and
  the next CI run reds the whole fleet again. Closing it structurally means scoping the
  `unaccounted` set to the generation the ledger was built from (the spine's
  `projection_generation_id` / `last_observed_at`), so a restatement NEWER than the ledger
  is not read as "escaped review" — that preserves the review property for the generation
  under review rather than weakening it. That is a Government Revenue program decision,
  not a drive-by heal. Generalization worth carrying beyond this test: an assertion that
  compares a LIVE REBUILD against an artifact advanced by a DIFFERENT LANE is a standing
  race, not a test — it is green only while the two lanes' commits happen to agree.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  `engine/government_revenue/candidates.py:1665` (candidate_id digest inputs);
  `tests/test_government_revenue_candidates.py:392` (the `unaccounted` assertion);
  `.github/ci/legacy-jobs.yml:7643` (step "award-event spine, candidates, entity +
  workspace contracts", job `unrun-government-revenue`, confirmed in ci-pack-6 via
  `python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 6
  --pack-count 12 --validate-only`);
  main baseline run 32100795267 (2026-08-18 04:53Z) red on ci-pack-6 + ci-gate, while run
  32091085776 (02:13Z) was green on ci-pack-6 — bracketing the introducing commit;
  `git show 93ab221b81dd -- data/government_revenue/ingest_status.json` (the
  projection_generation_id restatement); local reproduction at main `29619e3b9d07`
  (1 failed, 352 passed) and the rollback experiment in `falsifier`.
scope: [macro, government_revenue, tests/test_government_revenue_candidates.py]
confidence: verified
---

## Detail

### Why it is not "26 awards escaped review"

The 26 ids are not new events. Probing the same imports the test uses:

```
rebuilt rows: 56   ledger ids: 56
rebuilt-not-in-ledger: 26
ledger-not-in-rebuild: 26
 NEW grc1-08282b1d9f0d3e2b367f62e8 HII govws-e44decb10b5c3b53edc16e7c 2026-05-15 known_at 2026-08-18T01:55:22.848864+00:00
```

`known_at` on every unaccounted row is the NEW generation's stamp. The set intersection of
the 26 rows the ledger gained at 04:15Z with the 26 unaccounted ids is empty — a pure
re-digest, one-for-one.

### Lane ordering that produced it

```
93ab221b81dd  04:21Z  data: daily collection 2026-08-18     <- restates the spine
5214d0b20a17  04:15Z  govrev: SAM opportunity evidence      <- last ledger append
```

`data/` on main is therefore self-inconsistent across two lanes: the ledger advancer ran
before the collector's final restatement, and no lane has folded since.

### Why it did not self-heal quickly on 2026-08-18

`government-revenue-live.yml` declares `concurrency: {group: government-revenue-live,
cancel-in-progress: false}` and `daily.yml` calls it as a reusable workflow
(`.github/workflows/daily.yml:1344`), so they share one group. GitHub keeps at most ONE
pending run per group, so each newly queued tick cancels the previously pending one —
three consecutive ticks died that way (`32100336749`, `32103699468` cancelled;
`32109312184` pending).

The holder was NOT an orphaned run. Both `daily.yml` runs had jobs actively `in_progress`
with `total_count` 8 and 9 — **not 0**, which is the tell that separates ordinary
congestion from the unschedulable-runner-label deadlock where a run never concludes at
all. Read true execution time from the jobs API (`started_at` per job), never from
`gh run list`, whose duration is queue+exec lifetime. The congestion itself traced to a
`workflow_dispatch` of `daily.yml` at 00:29Z fired on top of a still-running scheduled run
from 22:52Z, oversubscribing the `macstudio` pool — the same "never dispatch over a live
run" discipline that governs `ci.yml` main baselines.

Related: [[DSC-SEALED-PIN-ON-A-NIGHTLY-OWNED-PATH]] — the sibling ci-pack-3 red on the same
night, also caused by a nightly lane rewriting an artifact another component treats as
stable.
