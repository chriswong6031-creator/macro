---
key: APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE
question: >
  Two overlapping `daily.yml` collect jobs can each build the USAspending append-only
  artifacts from the base each checked out, and `git pull --rebase -X theirs origin main`
  then REPLACES the earlier run's appended rows with the later run's. Where does the guard
  belong: a push-path check against `origin/main`, a collector-side base binding recorded
  at collection time, or a CI fence asserting the committed artifacts extend their
  predecessor?
answer: >
  A PUSH-PATH check, and only that. `scripts/ci/append_only_base_fence.py` reads
  `config/append_only_artifacts.json`, and for each declared artifact THIS run's local
  commits actually changed, compares the version at `origin/main` against the version
  about to be pushed — byte-prefix for JSONL ledgers, identity-set containment for the
  parquet spine. When main carries rows the push would drop, it WITHHOLDS the family:
  every path in `withhold_paths` is restored from `origin/main` and committed, so the
  rebase has nothing to resolve. It is called from inside each publishing lane's retry
  loop, after the fetch and before the rebase — `push_append_only_fence` in
  `scripts/ci/push_retry.sh` — in `daily.yml` (collect push + cancel-window salvage push),
  `government-revenue-live.yml`, and `backfill.yml`.
rationale: >
  Three properties decided it. (1) THE PUSH IS WHERE THE INFORMATION IS. The corruption is
  not a collector defect: every write-path guard in `collectors/usaspending_awards.py` —
  the torn-generation refusal (:3956-3972), the staged-replay generation binding
  (:4030-4044) — compares the run's state to the ledgers on the run's OWN disk, and a run
  whose entire base is stale is perfectly self-consistent and passes all of them. The
  first moment the two generations are both observable is after `git fetch origin main`,
  which is exactly where this runs. (2) SCOPING TO WHAT THIS RUN CHANGED IS LOAD-BEARING,
  not an optimization: `-X theirs` only resolves CONFLICTING hunks, so a member this run
  did not write cannot be clobbered — and flagging it anyway would fire every single
  night, because the 30-minute `government-revenue-live` lane appends
  `candidate_ledger.jsonl` rows while the nightly collect job is still running. A fence
  that withholds the night's collection nightly is worse than the defect. (3) WITHHOLDING
  IS THE ONLY SAFE REMEDY. Re-merging is not available: the artifacts are entangled
  through `award_event_projection_state.json`'s generation binding, and the DSC measured
  that no partial revert restores coherence (spine alone -> 0 candidates, + projection
  state -> 0, + receipts -> 0, all 25 changed artifacts -> 26 still unaccounted). Dropping
  this run's rows costs one cycle — the collector re-fetches an 1826-day window every
  night — while publishing a lost update costs evidence permanently and is not repairable
  by a session.
alternatives:
  - option: (b) Collector-side base binding — record the base commit/generation the run
      read, refuse at commit time if origin/main's artifact generation is newer
    why_not: >
      Strictly weaker than (a) for more coupling. A commit id answers "did main move",
      not "did main move UNDER MY ARTIFACT" — to tell those apart it would still have to
      compare artifact content, which is (a). It would also make the collector a git
      client, which it deliberately is not: `UsaspendingAwardsCollector` runs in tests,
      locally, and under `--root` sandboxes where git is not an oracle at all, and a
      base binding recorded at collection time is stale by the hours of collection that
      follow it (the measured run collected for 3h01m before pushing).
  - option: (c) CI fence asserting the committed append-only artifacts extend their
      predecessor, baselined from a named commit forward
    why_not: >
      It cannot PREVENT — it reports after the bytes are on main — and when it does fire
      it wedges the fleet with a red that no session can heal. That is not hypothetical:
      this exact corruption redded ci-pack-6 through ci-gate for every armed PR, and the
      DSC's measured conclusion is that neither existing reviewed manifest expresses a
      disposition for it, so clearing it is an operator call. A guard whose only failure
      mode is "block the whole fleet until an operator re-baselines" is a worse trade
      than the same check run one step earlier, where it can act. The DETECTION role it
      would have played is served instead by the fence's own `::error` annotations plus
      `--check-only`, which an operator can run against any pair of refs.
  - option: Merge the DST cron and workflow_dispatch concurrency groups so collect jobs
      cannot overlap
    why_not: >
      Explicitly forbidden by the thing it would undo. `.github/workflows/daily.yml:45-66`
      gives each DST cron and each manual dispatch its OWN group precisely so the DST pair
      cannot cancel each other's slot — GitHub cancels a PENDING run in a group even with
      `cancel-in-progress: false`, which killed the queued EDT run on 2026-08-14/15 and
      left a survivor that skipped every real job. The overlap is by design; the fix
      belongs at the artifact layer.
  - option: Add `data/government_revenue/*.jsonl merge=union` to `.gitattributes`, the
      idiom the repo already uses for 20 other append-only ledgers
    why_not: >
      The right instinct, and it CANNOT be applied to this directory. Three blockers, in
      increasing severity. (1) It cannot cover the parquet spine at all — a union merge of
      two binary frames produces garbage — so the exposure that moved `candidate_id` and
      caused this incident survives untouched. (2) It is actively WRONG for
      `candidate_ledger.jsonl`, whose `candidate_projection_state.json` binds the ledger by
      `prior_sha256` over an exact byte prefix (scripts/build_government_revenue_candidates.py
      :540-542): a union-merged tail no longer reproduces that hash, converting a silent
      lost update into a hard projection-lane failure. (3) Even where union WOULD work —
      the three receipt ledgers — applying it there while the parquets stay unmerged is the
      worst outcome available: receipts from both runs against a spine from one, i.e. the
      mixed generation the collector's own torn-generation refusal exists to prevent. The
      twenty existing `merge=union` entries are all standalone ledgers with no
      cross-artifact hash binding; this directory is one hash-bound generation, and the
      unit of correctness is the family, not the file. Raised by the #5882 lane and
      declined here for those reasons, not for scope.
  - option: Re-merge the two generations at push time instead of withholding one
    why_not: >
      A union is well-defined for the receipt ledgers (dedup by `receipt_id`) and NOT for
      the parquet spine, whose merged pair is bound by hash into
      `award_event_projection_state.json`. Unioning the halves we can and withholding the
      halves we cannot produces exactly the mixed generation the collector's own
      torn-generation refusal exists to prevent. If a re-merge is ever wanted it belongs
      in the collector, re-run over a fresh base — the shape `government-revenue-live.yml`
      already uses for its published twins.
evidence: >
  Replayed the real incident through the shipped bash wiring against blobs from the actual
  commits: base c52b647d499f, run A 59ccb9c774c8, run B 93ab221b81dd. Unfenced, the
  published tree is run B's on all five affected artifacts; fenced, it is run A's on all
  five. The fence's verdicts over the real history — 2026-08-18 (59ccb9c774c8 ->
  93ab221b81dd): `collection_receipts.jsonl` 376 lines dropped,
  `subaward_collection_receipts.jsonl` 192, `idv_collection_receipts.jsonl` 26,
  `award_event_snapshots.parquet` 16 of 210 identities, `award_action_versions.parquet`
  18 of 35257 — a blast radius the DSC had measured at 2 artifacts, not 5. A SECOND,
  PREVIOUSLY UNRECORDED occurrence on 2026-08-07 (1fc6d1181e4c -> 08ad4d836d6a): 360 of
  720 receipt ids swapped for the same byte count, plus 192 subaward and 26 idv. Control
  (c52b647d499f -> 59ccb9c774c8, a legitimate nightly transition): all 8 members ok.
  `tests/test_append_only_base_fence.py` — 20 tests, including an end-to-end git
  reproduction of the lost update and its fenced counterfactual.
affects:
  - .github/workflows/daily.yml
  - .github/workflows/government-revenue-live.yml
  - .github/workflows/backfill.yml
  - scripts/ci/append_only_base_fence.py
  - scripts/ci/push_retry.sh
  - config/append_only_artifacts.json
  - data/government_revenue/
reversibility: easy
reversibility_detail: >
  Deleting the `push_append_only_fence` calls restores the prior behaviour exactly; the
  fence writes nothing unless it has proven a loss. The registry is additive — a family
  with no members touched by a push is invisible to it.
supersedes: []
scope: [macro]
confidence: high
pr: "#5885"
decided_at: 2026-08-18
decided_by: fable main loop
workstream: ""
---

## Detail

### Failure directions, chosen deliberately

The fence has three exits and they do not all point the same way.

* A member this run CHANGED that cannot be read, or whose declared identity columns are
  absent, is `indeterminate` and **withholds**. We changed a file we cannot prove extends
  main; that is precisely the case the fence exists for.
* An INFRASTRUCTURE fault — `git rev-list` failing, or the local range spanning more than
  `MAX_LOCAL_COMMITS`, which means the graph is truncated and the changed set would be a
  SUPERSET of this run's own work — does **not** withhold. Without a trustworthy changed
  set a withhold can discard a legitimate generation, and declining to act merely leaves
  the pre-fence behaviour in place. It prints `::error` and exits 0.
* A withhold that itself FAILS fails CLOSED — the one exception. It exits
  `WITHHOLD_FAILED` (2), which `push_append_only_fence` turns into a non-zero return so the
  caller SKIPS that push attempt. The fence has PROVEN the tree drops evidence and then
  could not undo it; "the remedy broke" is not a reason to publish. Pinned in a real
  `bash -eo pipefail` shell, in the `if !` shape the lanes use, because a bare call under
  `-e` would abort the step instead of skipping the attempt.
* Otherwise the fence never fails the step. The market plane must publish, and the
  annotation is the signal.

That asymmetry is the whole design: fail-closed on a DATA question the fence can answer —
including "can I still act on my own verdict" — and fail-open-and-loud on an
INFRASTRUCTURE question it cannot.

### Why the merge-base is avoided

`changed_paths()` uses `git rev-list <onto>..<head>` plus a per-commit `diff-tree`, not
`git diff <onto>...<head>`. Three-dot needs a merge-base, `actions/checkout` clones at
depth 1, and on a truncated graph the merge-base may not exist on the runner at all. The
`MAX_LOCAL_COMMITS` cap is the guard for the residual case where `rev-list` answers with a
superset instead of failing.

### What this does not touch

The corruption already on main. The fence compares a run's build against `origin/main`;
it never walks history, so it neither inherits nor reports the 2026-08-07 and 2026-08-18
transitions. (For the record: PR #5870 restored run A's generation, so `origin/main`'s
`collection_receipts.jsonl` is byte-identical to 59ccb9c774c8 again — but nothing in the
fence depends on that being true.) The 26 orphaned `candidate_ledger.jsonl` rows remain an
operator disposition, exactly as the DSC states.

### Relationship to DSC:CANDIDATE-ID-RACE-BETWEEN-GOVREV-LANES (#5876)

That record, filed while this was being built, diagnoses the same ci-pack-6 red and gets
the observations right — 26 ids swapped one-for-one, no new awards, the rollback
experiment, and the correct prescription not to hand-advance the ledger. Its mechanism
claim that `event_id` derives from the spine's `projection_generation_id` is not right:
`engine/government_revenue/award_events.py:1407-1419` seeds the digest with per-row
`known_at`, and `projection_generation_id` appears nowhere in that module. The generation
id moved because the rows moved, not the other way round.

It matters because it flips the conclusion. The generation id changes on EVERY collection
(`13eb126c` -> `36437ac0` on the legitimate 08-14 -> run A append, `36437ac0` -> `9f19640e`
on the lost update), so if that were the cause the test would red every night. It does not,
because an append preserves every prior row: 194 -> 210 identities with all 194 intact over
the legitimate transition, and zero rewritten rows across the previous eight. The red
therefore is NOT "recurrent by construction" under normal operation and does NOT self-heal
on the next fold — it recurs exactly when an append-only artifact is published over a moved
base, which is what this fence prevents. A correction is appended to that record.

