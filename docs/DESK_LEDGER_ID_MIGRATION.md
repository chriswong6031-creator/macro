# Desk thesis-ledger id migration (2026-08)

## The defect (2026-08-03 experiments audit)

Desk thesis ids were minted from the **data date**, not run identity — `{asof}-{i}`
(ai_desk), `{asof}-{ticker}-{i}` (stock_desk), `{region}-{asof}-{i}` (thematic_desk),
`mb-{asof}-{i}` (master_brain), `{asof}-{HHMMSS}-{i}` (policy_intent). A stale detector
state re-briefed on a later run day reuses the same `state_asof`, so re-runs collided
with the prior run's ids (2026-06-15 was used on three different run days):

- **ai_desk** — `data/ai_desk/theses.jsonl`: 124 appended rows under 51 unique ids.
  `engine/desk_scorer.py` `dedupe_by_id` is last-wins, so 73 rows (58.9%) were silently
  discarded — 68 of them past-due and never graded. Graded coverage of the desk's real
  output: 28%.
- **stock_desk** — 606 rows under 259 ids (347 dropped), and worse: 35 of the 72 graded
  ids were re-appended with **mutated** `lean` / `check_by` under the same id (e.g.
  `2026-06-18-HWM-3` check_by moved 07-30→07-16 across 5 appends; `2026-06-22-YETI-6`
  lean cautious→constructive). A falsifier whose direction/horizon is rewritten after
  logging is not pre-registered — this is the direct cause of desk_placebo's pairing
  failure ("reconstructed 24 graded predicates but the track record has 72"), which caps
  Stock Desk's placebo coverage at 0.33 and makes it unpromotable.
- **thematic_desk** — avoided corruption via first-wins-at-append, but dropped every
  re-run invisibly.

## The fix (forward-looking; shipped with `engine/desk_ledger.py`)

1. **Run-scoped ids.** Every id now carries `run_token(generated_at)` — the run's full
   UTC second, `YYYYMMDDHHMMSS` — e.g. `2026-06-15-20260803043611-1`. Two runs over the
   same `state_asof` mint disjoint ids. (policy_intent's earlier HHMMSS-only token was
   upgraded too: it still collided when two different run *days* shared a stale asof and
   fired at the same wall-clock second.)
2. **Immutable rows.** Every desk's `_append_ledger` now refuses to append a row whose
   id already exists in the ledger — loudly (a `::warning` GitHub annotation + log
   line). First write wins; a live row's `lean`/`check_by` can never be rewritten by a
   later append. With run-scoped ids a rejection means id minting regressed — a real
   defect signal, not noise.

## Migration story for the already-collided ledgers

**History is NOT rewritten.** The ledgers are append-only and the graded outcomes in
`scored.jsonl` are final; rewriting either would destroy the very pre-registration
integrity this fix restores. Concretely:

- Existing `theses.jsonl` rows keep their colliding ids. The scorers keep **last-wins
  dedupe on read** — for the legacy window this reproduces exactly the rows that were
  actually graded and published; nothing already scored changes retroactively.
- The 68 ai_desk past-due-but-never-graded shadowed rows (and stock_desk's 347) stay
  ungraded. They are **not recoverable**: their entry snapshots were overwritten by the
  colliding append, and grading them now would be a post-hoc reconstruction, not a
  pre-registered test.
- The legacy collided window is therefore **permanently under-covered**, and that is
  disclosed rather than patched: `desk_placebo.null_baseline`'s pairing check already
  refuses to promote a desk whose reconstructed predicates cannot be paired 1:1 with
  its track record (stock_desk's coverage cap is that disclosure). Coverage heals
  forward from the deploy date as new, collision-free ids accrue.
- Do **not** "fix" old ids in place, and do not rebuild `scored.jsonl` from a re-keyed
  ledger. Any future promotion read over the legacy window must treat pre-migration
  graded coverage as the measured artifact it is.

Tests pinning the contract: `tests/test_desk_thesis_ids.py` (disjoint ids across runs on
the same `state_asof`; mutation-by-append rejected loudly; ledger row preserved).
