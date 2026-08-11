# Prophet US — Outage Backfill (force-majeure, operator-ordered 2026-08-11)

Operator order (2026-08-11 ~00:05Z, force-majeure override of the forward-ledger
no-backfill law): backfill picks that would have originated during the outage /
stale window, include them in the forward ledger, using the current state of the
engine (including the #5241 session-clamp patch). Companion order: investigate a
lower candidate pool with graduation (separate doc/PR; not this file).

This document is the design of record for the backfill PR. §0 gates are the
"not done unless" list.

## §0 ACCEPTANCE GATES (not done unless)

1. **Scope is exactly the receipted refusal set.** The backfill replays ONE
   origination event: `recorded_at=2026-08-09` (the Sunday bake that actually
   executed and refused 30 eligible candidates on the poisoned
   `panel.mixed_vintage` flag). No other date is minted. 2026-08-03→08-06 are
   NOT reconstructed (see §2 refusal). 2026-08-10 forward belongs to the live
   nightly.
2. **Vintage-pinned inputs, receipted.** The replay reads the genuine
   `as_of=2026-08-07` board (post-heal staleness block), plus the event-time
   plans baseline, each pinned by commit SHA. A separately pinned current
   plans baseline supplies collision authority. All three SHAs are recorded in
   the backfill receipt; no input is "whatever is on disk".
3. **Provenance on every minted row.** Each backfilled plan carries
   `origination_mode: "outage_backfill_2026_08_09"` plus
   `backfill_executed_at` (real wall date) alongside the normal era stamps
   (`selection_era` unchanged — same engine). A plan without the stamp minted
   by this lane = defect.
4. **Collision rule: live wins.** Any ticker originated by the 2026-08-10
   nightly (or any later live bake landing before the backfill executes) is NOT
   double-minted. Its weekend counterfactual is recorded display-only in the
   disclosure artifact instead. One active plan per candidate episode.
5. **Disclosure artifact + schema amendment ride the same PR.**
   `data/prophet/backfill_disclosures.json` (modeled on
   `data/us_board_ledger/disclosed_gaps.json`): window, authority
   ("operator force-majeure 2026-08-11"), full counterfactual set (minted +
   collided + still-refused with reasons), input SHAs, executing commit.
   `research/PROPHET_LEDGER_SCHEMA.md` gains a dated force-majeure addendum
   scoping the exception to this one event; the standing no-backfill law stays
   in force for all other dates.
6. **Segregation is test-pinned.** New test (pattern:
   `tests/test_grade_us_board.py::test_no_graded_rows_were_backfilled_into_a_disclosed_null_era`)
   asserting: (a) every plan with `origination_mode` startswith
   `outage_backfill` appears in the disclosure artifact and vice versa; (b) no
   backfilled plan has `recorded_at` outside the disclosed window; (c) any
   track-record/calibration aggregate that reads the ledger splits or excludes
   `origination_mode != live` rows (at minimum: pins that the field survives
   the index render so readers CAN split).
7. **Nightly passthrough proven.** A test loads a backfilled plan fixture
   through `_load_existing_plans` + the management path and shows the nightly
   neither drops, rewrites, nor chokes on the extra fields, and renders its
   state into index.json (the forward ledger then advances it organically —
   the backfill itself NEVER writes `data/prophet/ledger.jsonl`).
8. **Gates untouched.** `_resolve_origination_clocks`, `select_candidates`,
   and the #5071 integrity layer are not modified. The replay passes them on
   their own terms (recorded_at=2026-08-09 against the healed 08-07 board) —
   if any gate refuses at execution time, the refusal is recorded in the
   disclosure, not overridden in code. The 5 chronology-refused candidates
   from the R6 audit STAY refused.
9. **Merge window respected.** The backfill PR merges only while no nightly
   engine job is between checkout and its prophet checkpoint (else the
   PROTECTED_PROPHET_PATHS race guard discards that night's prophet outputs).
   Execute + verify live after the next nightly renders.
10. **User-facing disclosure is plain-word and bilingual.** Board/Tier-2
    surface for backfilled rows says, in EN and ZH, that the pick was
    reconstructed after an outage from that weekend's data — no internal
    jargon ("backfill", "mixed vintage", era slugs are banned front-facing).
    Copy routes through the design-doctrine banned-vocab check.

## §1 Why recorded_at=2026-08-09 is the honest reconstruction

- The 2026-08-09 22:59Z scheduled bake (run `31340764145`, engine job
  `93332847126`) ACTUALLY RAN the current intake end-to-end: 79 buys → 54
  admitted → 30 eligible → 30 refused, all at `clock_provenance` on
  `panel.mixed_vintage=true`. The durable checkpoint
  `8421e4783f141248656c850bfd61d1e15a6aeb97` receipts the exact 30 identities
  and errors in `site/prophet/index.json:intake.validation_failures`, with
  `intake.legacy_shadow.rows_in_part=30`. (The similarly dated
  `data/prophet/origination_receipts/31292839484-*.json` belongs to an earlier
  workflow-dispatch run that originated two plans; it is NOT this refusal
  receipt.) The counterfactual "fix present" flips exactly one poisoned input;
  everything else is the receipted live path.
- The board it read is still on main (`site/factordata/us_standouts.json`,
  `as_of=2026-08-07`), and the 2026-08-10 closing-bell render re-derived its
  staleness block through the healed `_panel_price_reach`:
  `mixed_vintage: false`, `off_majority_tickers: [CTRA, CWEN-A, TPH]` (real
  strays, not weekend riders). The replay input already exists at the right
  vintage on main — pin its SHA.
- All origination clock gates are relative to the `asof` parameter
  (`engine/prophet_bridge.py:585-671`; `scripts/build_prophet.py --date`,
  `:1384-1391`): `price_basis_date(2026-08-07) ==
  last_session_on_or_before(2026-08-09)` holds, so checks 1-4 pass on their
  own terms; check 5 (mixed_vintage) passes on the healed block; check 6
  (source_basis) unchanged. No gate is bypassed.
- Saturday (recorded_at=2026-08-08) is NOT also minted: same Friday board,
  near-identical set, double-minting would twin every plan ID. One event, the
  one with receipts.

## §2 Refused scope: 2026-08-03→08-06 (and why)

Standing operator ruling `data/us_board_ledger/disclosed_gaps.json`
(`us-board-frozen-alpha-2026-08`, dated 2026-08-07, CI-enforced by
`tests/test_grade_us_board.py:1101`): the 08-01→08-06 boards were computed on
a frozen stale alpha panel (GHA cache regression, healed by #4798);
`gradeable: false, backfillable: false`; "Backfilling with corrected dates
fixes the dates and leaves the rankings wrong." A vintage-correct replay of
those dates would require the point-in-time board harness that the ruling
itself notes does not exist (`build_stock_library.py` has no as-of capability
— as_of derives from the panel on disk). Reconstructing from the frozen
boards would mint picks a correct engine would never have picked.

The force-majeure order is therefore executed on the dates where an honest
reconstruction exists (the weekend refusal event) and REFUSED for
08-03→08-06, where only a fabricated one does. If the operator wants those
dates too, that is a separate commission: build the PIT board replay harness
first (heavy; new-authority-adjacent; needs its own prereg + a fresh
adjudication superseding the 2026-08-07 ruling).

Note the twist discovered in recon: 08-06's board froth was ALSO within the
frozen-alpha window — so the "outage" the operator sees on the grid
(nothing after Aug 5) is two back-to-back incidents (frozen alpha through
08-06, then cancelled nights + the mixed-vintage wedge 08-07→08-10), only
the second of which is honestly replayable.

## §3 Mechanism (builder spec)

New one-off script `scripts/backfill_prophet_outage.py` (era-stamped, refuses
to run twice — idempotence via the disclosure artifact):

1. Inputs (all pinned, passed as SHAs on the CLI, recorded in the receipt):
   - `--board-commit <sha>`: commit on main whose
     `site/factordata/us_standouts.json` is the healed 08-07 board.
   - `--event-baseline-commit <sha>`: the plan set at the scheduled event's
     checkout (`5d06ee689...`), used for duplicate/open-plan suppression so the
     replay can reproduce the receipted 30-row refusal population.
   - `--collision-baseline-commit <sha>`: main AFTER the 2026-08-10 nightly
     checkpoint (the plans originated live since the event).
2. Extract the pinned board to a temp path; run the intake through
   `originate_plans(asof="2026-08-09", standouts_path=<pinned board>, ...)`
   — via a thin wrapper, NOT by editing build_prophet's constants. Its
   `existing_ids` and `active_keys` MUST come from the pinned event baseline,
   not the executing checkout or collision baseline: `originate_plans`
   suppresses those rows before returning them, which would erase the full
   weekend counterfactual set from disclosure.
3. Compare the replay output with the separately loaded collision baseline;
   inject `origination_mode` and `backfill_executed_at` into survivors, and
   put collisions per §0.4 into the disclosure's `collided` list. Write
   surviving plans to `site/prophet/plans/` +
   origination receipt to `data/prophet/origination_receipts/` (same format
   as the nightly's) + `data/prophet/backfill_disclosures.json`.
4. NEVER write: `data/prophet/ledger.jsonl` (nightly advances it),
   `site/prophet/index.json`/`states/` (nightly renders them),
   `site/factordata/*` (not ours).
5. Commit artifacts + script + tests + docs in ONE PR. Execute the script
   IN the PR branch (artifacts are committed outputs, house pattern), so CI
   sees the final state and the disclosure test runs against real rows.
6. After merge + next nightly: verify index.json carries the backfilled
   plans with states, board renders them with the disclosure chip, ledger
   begins advancing them. Then update the masterplan §6.9 execution record.

## §4 Sequencing / status

- [x] #5241 merged (10:33Z 08-10); healed board staleness live on main.
- [ ] 2026-08-10 nightly (run 31440972065, in-flight) verified: board
      advances to as_of=2026-08-10, forward origination resumes (~25 clean
      expected). Backfill branches off THIS post-bake main.
- [ ] Builder implements §3 (opus `builder`, this doc §0 gates inline in the
      spawn prompt).
- [ ] Opus `reviewer` red-team pass on the epistemics + collision handling
      BEFORE merge (adjudication coverage gate).
- [ ] Merge in the clear window (no engine job mid-flight), verify live
      after the next nightly.
- Companion investigation (lower pool / graduation) tracked separately;
  recon in flight.
