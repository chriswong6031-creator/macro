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

## Claim-keyed ledgers — the audited boundary (2026-08 follow-up)

The migration above covers the ORDINAL-id desks, where `{asof}-{i}` made the id an
accident of enumeration order. A second family keys the id to the CLAIM itself —
`{asof}-<subject>` — deliberately stable across re-registration of the same logical
claim (engine/qledger.py documents the intent: "stable across re-registration...so
adapters are idempotent"). Stable ids are only safe when the append path enforces
FIRST-WINS: if duplicates can enter the file, the scorers' last-wins dedupe turns a
re-append into a rewrite of the logged predicate — the same mutation class as
stock_desk above. Audit result per module (2026-08-03, code + measured ledgers):

| module · id shape | append gate | ledger measured |
|---|---|---|
| narrative_brain · `{asof}-nb-{basket}` | first-wins (`seen` id set) | never accrued a row (lane degraded) |
| altdata_brain · `{asof}-{tk}-brain` | first-wins + active-window skip | never accrued a row (lane degraded) |
| altdata_ledger · `{asof}-{tk}-altconv` | first-wins + active/cooldown skip | 422 rows / 422 unique ids — clean |
| risk_brain · `{asof}-rb-state` | first-wins (`seen` id set) | never accrued a row (lane degraded; no scorer consumes it yet) |
| qledger · sha1 of desk·asof·scope·horizon·direction·salt | keep-FIRST dedupe in register()/register_batch() | 29,719 rows / 29,719 unique ids — clean |
| demand_ledger · `{asof}-{chain}-{tkr}` | was VINTAGE-only → **id gate added 2026-08** | 45 rows / 45 unique ids — clean |

* **The first five are sound.** A same-asof re-run that produces different content
  (LLM-authored or state-dependent) is silently dropped at append: first write
  stays the pre-registered predicate, so no post-hoc mutation is possible. The
  SILENT skip is intentional in this family — re-registration of the same logical
  claim is the normal idempotent path, unlike the ordinal desks where any id
  collision means minting regressed and is announced loudly. qledger is stronger
  still: direction and horizon are inside the id hash, so a flipped claim mints a
  NEW id by construction, and `backfill_regime_stamps()` rewrites are
  fill-null-only (stamp fields, never predicate fields).
* **demand_ledger was the gap.** `emit()` deduped by vintage
  (`chain:ticker:fy:divergence`) while the id omits fy + divergence, so a same-day
  re-run after a divergence flip (or fy roll) passed the vintage filter and would
  have appended a FLIPPED lean/op/threshold under a live id — silently shadowing
  the logged predicate under `dedupe_by_id`'s last-wins. Never observed in the
  data (45/45 unique ids) but open by construction; now closed with
  `desk_ledger.reject_existing_ids` at append. Run-scoped ids are NOT appropriate
  here — the stable claim key is the design. A same-day flip is refused loudly
  and re-logs under the next day's id (one nightly cycle of latency, no lost
  pre-registration).

Tests pinning the claim-keyed contract: `tests/test_demand_ledger.py`
(same-day divergence flip refused loudly + original row preserved; next-day flip
mints a disjoint id).
