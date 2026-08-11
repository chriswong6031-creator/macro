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
2. **Vintage-pinned inputs, receipted.** The replay reads the BAKE-TIME
   board — the exact `us_standouts.json` the refused 2026-08-09 bake read
   (blob `f9ce1f3044` @ commit `b3d3c38bdce5`, `as_of=2026-08-07`,
   `rank_by=us_prophet_v1`) — with exactly ONE field changed:
   `staleness.inputs.panel.mixed_vintage` healed `true→false`, and that heal
   VERIFIED by recomputation (run the #5241-fixed `_panel_price_reach`
   against the board's members with price reads date-clamped ≤2026-08-09;
   assert it yields `false`; refuse to mint if it does not). Post-heal
   re-renders of the board are FORBIDDEN as input: the 2026-08-10 evening
   re-render was adjudicated contaminated in review — it swapped the ranker
   (`us_prophet_v1→v2`), refreshed options snapshots, and admitted three
   tickers (ASTS, CRC, SVM) via a wall-clock earnings-blackout hole (a
   +08:00 render host past local midnight saw their 2026-08-10 earnings as
   past — one-sided lookahead). The script hard-refuses: board
   `as_of != 2026-08-07`, board sha256 != the pinned constant, ranker
   != us_prophet_v1, or either input commit not an ancestor of origin/main.
   PIT geometry inputs (regime/leash state, stage-tilt, option store) are
   pinned to their bake-time-commit vintage via git; any input that cannot
   be vintage-pinned is disclosed PER FIELD in the disclosure artifact with
   the vintage actually used. No input is "whatever is on disk".
3. **Provenance on every minted row.** Each backfilled plan carries
   `origination_mode: "outage_backfill_2026_08_09"` plus
   `backfill_executed_at` (real wall date) alongside the normal era stamps
   (`selection_era` unchanged — same engine). A plan without the stamp minted
   by this lane = defect.
4. **Collision rule: live wins — window closes at MERGE, not execution.**
   Any ticker originated by the 2026-08-10 nightly or any later live bake
   landing before the backfill MERGES is NOT double-minted. Its weekend
   counterfactual is recorded display-only in the disclosure artifact
   instead. One active plan per candidate episode, guarded by a test
   asserting at-most-one-open-plan per ticker+direction; the collision set
   is re-verified against fresh origin/main immediately before merge
   (script `--verify-collisions` mode) and the merge aborts on any new
   collision until re-reconciled.
5. **Disclosure artifact + schema amendment ride the same PR.**
   `data/prophet/backfill_disclosures.json` (modeled on
   `data/us_board_ledger/disclosed_gaps.json`): window, authority
   ("operator force-majeure 2026-08-11"), full counterfactual set (minted +
   collided + still-refused with reasons), input SHAs, executing commit.
   `research/PROPHET_LEDGER_SCHEMA.md` gains a dated force-majeure addendum
   scoping the exception to this one event; the standing no-backfill law stays
   in force for all other dates.
6. **Segregation is test-pinned — through the LEDGER and every live
   aggregate, not just the index render.** (a) every plan with
   `origination_mode` startswith `outage_backfill` appears in the disclosure
   artifact and vice versa; (b) no backfilled plan has `recorded_at` outside
   the disclosed window; (c) `origination_mode` is CARRIED INTO the ledger
   row at close (`build_prophet` ledger-row constructor) and
   `record_summary` — the published `index["record"]` win-rate — splits or
   excludes backfilled rows, pinned by a test that closes a backfilled plan
   and asserts the published record excludes/splits it; (d) marketing
   surfaces (`engine/marketing/receipt_source`, `allies`, `content_studio`)
   HARD-EXCLUDE `origination_mode != live` plans — a reconstructed pick may
   never be presented as a live historical call, under any framing; (e)
   `prophet_stage_shadow` cohort stats that feed live plan geometry
   (`plan_horizon_days`) exclude backfilled rows; (f) the brain gateway plan
   projection whitelist includes `origination_mode` so the chat layer can
   see and caveat it.
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

- The 2026-08-09 22:59Z bake ACTUALLY RAN the current intake end-to-end:
  79 buys → 54 admitted → 30 eligible → 30 refused, all at
  `clock_provenance` on `panel.mixed_vintage=true` — receipted
  (`data/prophet/origination_receipts/31292839484-*.json`, intake receipt
  rows_in_part=30). The counterfactual "fix present" flips exactly one
  poisoned input; everything else is the receipted live path.
- The board it read survives in git history (blob `f9ce1f3044` @ commit
  `b3d3c38bdce5`, `as_of=2026-08-07`, `mixed_vintage=true` baked in). THAT
  board — not any later re-render — is the replay input, with the one
  poisoned flag healed by verified recomputation (§0.2). Review adjudication
  2026-08-11: the 2026-08-10 evening re-render of the same `as_of` board is
  CONTAMINATED as a replay input (v1→v2 ranker swap, refreshed options
  snapshot, and a wall-clock earnings-blackout hole that admitted ASTS/CRC/
  SVM on lookahead — board membership measurably flapped 78↔81 rows by
  render-host timezone on identical `as_of`). The wall-clock defect in
  `build_stock_library`'s blackout gate is tracked as its own fix lane,
  separate from this backfill.
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
   - `--plans-baseline <sha>`: commit on main AFTER the 2026-08-10 nightly
     checkpoint (for the collision set = plans originated live since 08-09).
2. Extract the pinned board to a temp path; run the intake through
   `originate_plans(asof="2026-08-09", standouts_path=<pinned board>, ...)`
   — via a thin wrapper, NOT by editing build_prophet's constants; plans
   baseline = `_load_existing_plans` on the checkout (post-bake main).
3. Post-process originated plans: inject `origination_mode`,
   `backfill_executed_at`; drop collisions per §0.4 into the disclosure's
   `collided` list; write surviving plans to `site/prophet/plans/` +
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
