# Prophet US — Outage Backfill (force-majeure, operator-ordered 2026-08-11)

> **SUPERSEDED AS STANDING POLICY (2026-08-18) — `DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT`.**
> This document remains the dated record of the 2026-08-11 backfill as executed, and
> nothing in it is retracted. But it is NO LONGER the governing rule: a session lost to an
> infrastructure outage is now backfilled by DEFAULT, with no fresh per-case charter, and
> "no origination event executed" is no longer grounds to refuse. §2's refusal of
> 2026-08-03→08-06 stands on its own separate footing — those boards' RANKINGS are wrong
> (frozen stale alpha panel), which is a data defect to disclose, not an outage to recover.


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

## §5 SECOND EVENT — 2026-08-11 (operator force-majeure, 2026-08-13)

A separate operator order, chartered separately on purpose. §0's gates transfer; the
INPUTS do not, and §5.1 is the whole reason this is a different kind of artifact.
Producer: `scripts/backfill_prophet_outage_20260811.py`. Reader-facing record:
`research/PROPHET_LEDGER_SCHEMA.md` § Addendum 2026-08-13.

### §5.1 There is nothing to replay

`daily.yml` was stranded for the 2026-08-11 session by the #5362 workflow-size cap
(postmortem: `tests/test_workflow_file_size.py`) and its recovery dispatches were
force-cancelled. The night produced NO collect, NO board, NO intake receipt, NO refusal
set. The 2026-08-12 session recovered live — run 31649984834 collected BOTH stranded
days' bars and originated 25 plans at `recorded_at=2026-08-12` — so the board artifact
went from `as_of=2026-08-10` (2026-08-11T03:36Z) straight to `as_of=2026-08-12`.
**No `as_of=2026-08-11` board has ever existed in this repository's history**, verified
across all 40 revisions of `site/factordata/us_standouts.json` spanning the window.

So where §0.2 pinned a bake-time blob by sha256, this event has no blob to pin. The
board is RECONSTRUCTED, and every property §0.2 got for free has to be built:

| §0.2 property | 2026-08-09 (replay) | 2026-08-11 (reconstruction) |
|---|---|---|
| board provenance | pinned blob `f9ce1f3044` @ `b3d3c38bdce5`, sha256-fenced | **built** on `7ba57221ddec`; synthetic, never published |
| price vintage | inherited from the pinned blob | **structural** — vintage tree + only the missing sessions, fenced |
| code vintage | current tree (same engine) | **pre-#5370 tree** — #5370 edits the origination module and merged 82 min after the bake slot |
| justification of the one change | heal verified by recomputation | **harness scored** against the 2026-08-10 board the vintage already ships |
| refusal set | receipted, replayed verbatim | engine gates at execution + an added chronology refusal |

### §5.2 Mechanism

1. **Vintage worktree** at `7ba57221ddec` — newest main at or before the 22:30Z cron.
   Its committed price store ends 2026-08-10 *because the stranded collect never wrote
   08-11*, which is what makes truncation structural rather than a read-time clamp.
2. **Price overlay**: for every file on the plan-price ladder
   (`data/baskets/ohlcv` → `data/stocks` → the four wide close panels, plus
   `data/yahoo` and `data/baskets/extras.parquet`), append ONLY the sessions in
   `(vintage_last, 2026-08-11]` taken from the store the 2026-08-12 collect wrote. Rows
   the vintage already carries keep the vintage's own bytes, so a later restatement
   cannot leak backwards.
   `data/russell_breadth/_closes_cache.parquet` is gitignored and must be supplied from
   a lane checkout — without it `universe()` silently drops ~1,300 small caps and the
   board is ranked over a third less universe.
   `data/baskets/extras.parquet` is `universe()`'s LAST rung (curated searchable names no
   index cache carries) and belongs in the surface for the opposite reason to lookahead:
   left behind it stays a session back while every other panel advances, which is a
   within-panel vintage TEAR of exactly the shape that made the 2026-08-09 bake refuse
   all 30 eligible candidates on `panel.mixed_vintage`.
3. **Fence** every price parquet in the tree before the builder starts. A bar past the
   ceiling is a refusal, not a warning.
4. **Rebuild `site/factordata/alpha.json`** from the truncated panel. This is what makes
   the board say 2026-08-11: `build_stock_library` does not derive its own `as_of` — it
   publishes alpha's stamp verbatim (`wide["as_of"] = alpha_asof`, build_stock_library.py:4839)
   and anchors the W1.5 earnings-blackout gate to the same value. Reusing the vintage's
   committed alpha would have produced a board labelled 2026-08-10 whose blackout gate
   was also anchored to 2026-08-10, and the origination clock contract would refuse it.
5. **Build the board**, verify `as_of == price_through == 2026-08-11` and
   `rank_by == us_prophet_v2`.
6. **Originate** in the same tree so plan geometry re-reads the same fenced prices.
7. **Collide** (live wins, cutoff 2026-08-12), **chronology-refuse**, stamp, disclose.

Between passes, every tracked file the builder writes is restored from the vintage —
`data/name_score/us_calls.parquet` is a keep-FIRST PIT stamp, the shadow ledgers accrue,
and `us_standouts.json` is read back as the previous board — so the control rehearsal
cannot become the reconstruction's input.

### §5.3 The control — what it establishes, and what it does not

Running the harness one session earlier rebuilds a board that ALREADY EXISTS (the
vintage's own `as_of=2026-08-10`, sha256 `3e86c1088f…`, 69 buy rows). The agreement
between the rebuild and the real artifact is this window's error bar; it rides in the
disclosure as `harness_fidelity` and a run below the floor refuses.

**Be precise about what it measures, because the number is easy to over-read.** The
vintage's committed price store already ends 2026-08-10, so on the control pass the
overlay appends nothing to any tracked file — the only file it writes is the gitignored
Russell panel. The control therefore establishes:

* that supplying the Russell close panel from a lane checkout reproduces the board built
  with the runner's own copy of it,
* that the alpha rebuild lands on the tree's own session, and
* that `build_stock_library` is deterministic over unchanged inputs.

It does **not** exercise the truncation (computed, then discarded unwritten), the
append, or the minted set (`originate_plans` is not called on the control pass). Those
are covered by the fence, the overlay manifest and the unit suite instead. The
disclosure row carries this split verbatim as `measures` / `does_not_measure` rather
than a sentence that implies all of it.

**Measured.** 0.875 (floor 0.85), identical across two independent runs — the harness is
deterministic. Residual: 6 of 69 reference names missing (ALB, BKSY, JOBY, SMR, UEC,
UUUU), 3 extra (BLDR, KALU, RDW); ranking-boundary differences, not price-coverage gaps —
all six missing names are present in the panel with 2026-08-10 data. An earlier
measurement of **0.822**, taken before the Russell panel was supplied, is what pointed at
that cache: `build_stock_library.py:753` predicts exactly this shortfall when it is
absent, which is why supplying it is part of the mechanism rather than a nicety.

The 2026-08-11 board it then produced carries **3,041 panel members** — the same panel
size the real 2026-08-10 bake recorded — and 69 buy rows.

### §5.3b Result — and why "only 3" is the right answer

`buy_rows=69 → admitted=46 → duplicate_id 36 → eligible 10 → minted 3, chronology-refused
7, collided 0, still-refused 0`. Both funnel identities close. Minted: **HCC, LNG,
NXPI**. Chronology-refused by the engine's own contract: ARR, MP, MTDR, ORA, SPHR, SSD,
TREX.

The number is small because **the live 2026-08-12 nightly had already re-originated most
of that night's episodes**, and the disclosure proves it by name rather than asserting
it. A plan id is `(ticker, direction, formation ANCHOR)` and the anchor is a SIGNAL date,
so a name the 08-12 bake minted off an 08-10 or 08-05 anchor yields the SAME id from the
08-11 board. 36 of the 46 admitted candidates are that case, and 11 of those 36 are names
the live lane won inside the collision window (ALB, AMR, ASTS, BKSY, CRC, CVCO, DXYZ,
FANG, HEI, KEYS, URG — all `recorded_at=2026-08-12`).

This nearly went unrecorded. The engine checks the id BEFORE the open-plan check, so
these candidates never reach the `collided` path the lane maps, and without the #5305
`already_published_ids` machinery they would have survived only as the integer `dup=36`
inside a document whose stated purpose is "every candidate the reconstruction did NOT
mint". The re-walk now reconciles exactly (36 enumerated = 36 the engine counted).

So the honest summary of this window is not "the reconstruction found little". It is:
**the live path had already covered most of the outage, and three names are what it never
re-originated.** §0.4 working as designed, with the whole overlap on the record.

### §5.4 What this event does NOT authorise

2026-08-03 → 2026-08-06 stay refused under `us-board-frozen-alpha-2026-08` — and this
window does not weaken that ruling, which turns on a factor panel frozen at 2026-07-31,
not on a missing session. 2026-08-12 forward is the live nightly's. There is still no
generic backfill lane and no `--asof` flag; a third window needs its own order, its own
producer, its own disclosure row and its own dated addendum.
