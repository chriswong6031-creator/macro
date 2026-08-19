# Prophet PIT Replay Harness V1 — general point-in-time session reconstruction

**Authority:** `DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT` (chairman, 2026-08-18,
PR #5878). Backfilling an infrastructure-outage-lost Prophet session is the DEFAULT; no
per-case charter; reconstructed rows enter the forward ledger UNMARKED (the operator
explicitly declined an `origination_disclosure` flag — the accepted cost is recorded in
the DEC rationale and is not re-litigated here). That DEC names the blocker this build
removes: `scripts/backfill_prophet_outage.py` is hard-pinned to the 2026-08-09 event,
`scripts/backfill_prophet_outage_20260811.py` to 2026-08-11, and
`build_stock_library.py` has no as-of capability. This harness is the commissioned
general producer: parameterized by **(market, session date)** over US/CN/HK/CA/Intl.

**Design ancestors (read before touching anything):**
`research/PROPHET_OUTAGE_BACKFILL_2026_08.md` (§0 gates, §5 reconstruction mechanism —
the PIT discipline transfers verbatim), `scripts/backfill_prophet_outage_20260811.py`
(the reference implementation of every primitive named below), and
`research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md` (the freeze that produced the
immediate candidates: US 2026-08-14, CN and HK 2026-08-17).

**What changed vs the ancestors, and why it is now safe to generalize:**
1. The DEC removes the per-event charter and the row marking, so the disclosure
   document, `DISCLOSURE_COPY` chips, `origination_mode` stamps and bidirectional
   segregation tests DO NOT transfer. Receipts (operational audit trail) DO.
2. Every event-pinned constant becomes derived: vintage SHA from the bake slot,
   control reference from the vintage's own committed board, required ranker read
   from that board, fidelity floor and price surface from a per-market registry.
3. The mandatory control pass is the safety net that makes generalization honest:
   a market whose declared price surface is incomplete FAILS its control fidelity
   floor and refuses to mint. Surfaces are enumerated by archaeology and then
   MEASURED, never trusted.

## §0 ACCEPTANCE GATES (not done unless)

1. **One command, any supported session.**
   `python3 -m scripts.prophet_pit_replay --market us --session 2026-08-14`
   (dry-run default; `--execute` writes; `--control` implied — see gate 3). Markets
   `us`, `cn`, `hk` fully implemented. `ca` and `intl` ship as DECLARED registry
   entries that refuse with the exact missing pieces named (bake lane, price surface,
   capture stores) — fail-closed generality, never a wrong replay. No other
   market string is accepted.
2. **PIT discipline is structural, never a read-time clamp.**
   Vintage worktree at the newest `origin/main` commit at or before the market's bake
   slot on the session date — resolved with `git rev-list -1 --first-parent
   --before=<slot> origin/main` (**`--first-parent` is load-bearing**: a merged
   branch's interior commits carry pre-merge timestamps, and without it the resolver
   can select a commit whose CONTENT only landed on main after the slot), then
   `merge-base --is-ancestor` proven against `origin/main`, shallow-repo refusal with
   the `--deepen` remediation (lift `assert_ancestor_of_main`). Price overlay appends
   ONLY sessions in `(vintage_last, session]` from `--live-price-ref` (default
   `origin/main`); vintage rows keep vintage bytes; columns aligned to the vintage
   frame; atomic writes (`truncate_frame` / `overlay_sessions` / `_atomic_parquet`
   lifted intact). `fence_no_bar_after` proves no bar past the session ceiling over
   the market's ENTIRE declared surface before any builder runs, with `unscannable`
   reported and the control-pass `ahead_of_pass` subtlety preserved. An overlay that
   writes past its own ceiling refuses (`BackfillRefused`), and the
   `_needs_write` truncation-without-append case stays covered.
3. **Control pass mandatory for mint.** Before reconstructing the lost session, the
   same harness rebuilds the vintage tree's OWN committed board (its `as_of` = the
   control session) and scores buy-set Jaccard against the committed artifact
   (`board_fidelity` lifted). Below the registry floor (default 0.85) → refuse;
   `--allow-low-fidelity` proceeds but records the waiver + measured number in the
   receipt. The receipt carries the control's `measures` / `does_not_measure` split
   verbatim from the ancestor design (§5.3 of the charter). Builder state is restored
   between passes (`reset_builder_state` generalized: every tracked non-price write
   reverted, untracked leftovers counted and sampled).
4. **Rows enter the forward ledger UNMARKED, via stage-and-absorb — the nightly
   stays the sole advancer.** The harness NEVER writes `data/prophet/ledger.jsonl`,
   `data/china_standout_track/board.parquet`, `data/us_board_ledger/snapshots*.jsonl`
   / `retro_grades*.parquet`, any `data/hk_pick_lab/` graded store,
   `site/prophet/index.json`, `site/prophet/states/*`, or ANY `site/factordata/*`
   artifact (reconstructed boards are never published). Instead:
   - **US plans (precedent-native staging):** surviving minted plans →
     `site/prophet/plans/<ID>.json` in the normal live shape — NO `origination_mode`,
     no disclosure row, no user-facing chip — plus a normal-format origination
     receipt `data/prophet/origination_receipts/replay-<session>-<hash>.json` with
     explicit `price_through` / `source_asof` (the chronology audit requires
     explicit stamps; run `scripts/audit_prophet_plan_chronology.py` over the result
     as a gate). The nightly advances the plan ledger organically (§0.7 of the
     charter: passthrough, not backfill-written).
   - **Ledger rows (new stage-and-absorb):** pending-entry files
     `data/us_board_ledger/pending_replay/<session>.json`,
     `data/china_standout_track/pending_replay/<session>.json`,
     `data/board_ledger/pending_replay/<session>.json` (HK board-order ledger —
     census 2026-08-18: `engine/board_ledger.append_board` writes
     `data/board_ledger/hk_board.parquet`, dedupe `(date, ticker)` keep-first, a
     second HK forward ledger this list originally missed),
     `data/hk_pick_lab/pending_replay/<session>.json`. Each market's own nightly
     pass absorbs its pending dir through its OWN append + dedupe machinery
     (`grade_us_board` nightly path; `engine/china_standout_track.append_board`'s
     dedupe on `(date, ticker, board_definition)` keep-first — five call-site
     cohorts per session, all captured; `engine/board_ledger`'s `(date, ticker)`;
     `build_hk_pick_lab`'s fire/grade passes keyed
     `(engine_id, ticker, fire_date[, horizon, kind])`) and deletes the pending
     file in the same run. Absent/empty pending dir = exact no-op (zero risk to a
     normal nightly). Absorption is idempotent: dedupe keys + file removal; a
     crashed absorb re-runs next night. `data/board_ledger/*` joins the
     never-write-directly list above.
5. **Ledger rows are produced by the VINTAGE lane's own code — the harness never
   synthesizes a row.** After the vintage tree's board build, the harness runs the
   market's own ledger pass INSIDE the vintage tree (grade_us_board snapshot for US,
   the `china_standout_track` append pass for CN, the hk_pick_lab fire pass for HK —
   each via a thin subprocess runner in the vintage tree, ancestors' pattern) and
   captures the session-dated DELTA of the declared capture stores as the
   pending-entry payload. Rolling/stateful stores (e.g. `entry_latch.parquet`,
   `ripening.parquet`) are NEVER captured or absorbed — they resume organically from
   the next live pass, and the receipt names them as such. If a market's ledger pass
   cannot run cleanly in the vintage tree, that half refuses with the reason named
   in the receipt — a partial entry is disclosed, never silent.
6. **Disclosed-gap guard, fail-closed.** A (market, session) inside any
   `disclosed_gaps.json` window with `backfillable: false` refuses, citing the gap
   id and the DEC's data-defect carve-out. `us-board-frozen-alpha-2026-08`
   (2026-08-01→08-06) stays exactly as it is — `tests/test_grade_us_board.py`'s
   enforcement is untouched and the refusal is unit-tested. Markets without a gaps
   file check an empty set (the registry names the path; absence is not an error).
7. **Idempotent and collision-safe.** A harness receipt already existing for
   (market, session) — on `origin/main` or in the working tree — refuses re-execution.
   US collision law: live wins, cutoff = session + 1 day (any live plan recorded
   after the lost session owns its episode; the generalization of
   `LIVE_WINS_FROM`), duplicate-id enumeration via the `already_published_ids`
   re-walk (#5305 machinery — enumerated ids, never a bare count), funnel
   reconciliation identities must close, and `--verify-collisions` re-derives the
   set against fresh `origin/main` for the pre-merge check. CN/HK: the lost session
   has no live rows by construction; dedupe keys protect absorb idempotence.
8. **Engine gates untouched.** `originate_plans`, `select_candidates`,
   `_resolve_origination_clocks`, the integrity layer and the chronology audit are
   imported/called on their own terms, never modified. A gate that refuses at
   execution time has its refusal recorded in the receipt, not overridden.
9. **Every claim receipted.** Harness receipt
   `data/pit_replay/<market>-<session>-<hash>.json`: DEC citation, market, session,
   bake slot, vintage SHA + committed time + resolution proof, live-price-ref SHA,
   overlay manifest totals + per-file provenance (`overlay_files`, including
   wholesale-substituted gitignored panels named as substitutions WITH their
   column diff vs the vintage constituents — the survivorship direction, §2b(2)),
   `skipped_identical`, fence digest + `ahead_of_pass` + `unscannable`, control
   fidelity block, stamp verifications (board `as_of` == session; `price_through`
   == session where the market stamps it; ranker == the vintage's own board's
   ranker — READ from the vintage board, asserted on the rebuild), funnel counts +
   reconciliation, residual wall-clock exposures (TZ=UTC pinned; the measured
   `earnings_blackout_delta` pattern for US), `env_pins` as applied (including the
   dead-proxy keys, §2b(3)), `residual_network`, `pinned_stores` + their
   post-build byte-assertion results, `aux_panel_source`, executed_at, executing
   commit. Dry-run writes the receipt to the work dir ONLY and touches nothing in
   the checkout.
10. **Tests green, including the ancestors'.** New units: vintage resolution
    (first-parent + before-slot monotonicity), overlay/fence/truncate on synthetic
    frames, gap-guard refusal, registry validation (unimplemented market → named
    refusal), pending-entry schema, absorb hooks (absorb → rows present via the
    lane's own dedupe → file removed → re-run no-op → empty dir no-op), receipt
    idempotence refusal, US collision cutoff. Existing suites — the two old
    backfill scripts' tests, `test_grade_us_board.py`, chronology audit — stay
    green and UNTOUCHED. Full-checkout-dependent tests carry `needs_full_checkout`.
11. **This PR ships tooling + proof, zero ledger bytes.** Committed: the harness,
    absorb hooks, tests, this masterplan, and the DRY-RUN receipt of US 2026-08-14
    (`research/PROPHET_PIT_REPLAY_DRYRUN_US_2026_08_14.md` + receipt JSON) as the
    proof artifact. NO `--execute` artifacts, no pending entries, no plans. The
    three candidate executions (US 08-14, CN 08-17, HK 08-17) are post-merge
    follow-ups under the DEC default. The two old event scripts are dated records
    and are not modified.

## §1 Market registry (the whole difference between markets, in one place)

Python dict in `scripts/prophet_pit_replay.py` (entries carry hooks, so code, not
YAML). Fields per market:

| field | us | cn | hk | ca / intl |
|---|---|---|---|---|
| `bake_slot_utc` | 18:30 America/New_York on session date (daily.yml `30 22/23 * * *`) | 08:30Z (asia-close on-time slot) | 08:30Z (same lane) | DECLARED-UNRESOLVED → refuse |
| `board_relpath` | `site/factordata/us_standouts.json` | `site/factordata/china_standouts.json` | `site/factordata/hk_standouts.json` | `site/factordata/canada_standouts.json` / TBD |
| `build` | `python -m scripts.build_stock_library` (+ alpha rebuild pre-step, §2) | `python -m scripts.build_china` | `python -m scripts.build_hk` | TBD |
| `price_surface` | `PRICE_TICKER_STORES` + `PRICE_WIDE_PANELS` from the 08-11 script, verbatim | `data/china` + `data/china_stocks` ticker stores; `data/china_search/closes.parquet` + gitignored `data/china_breadth/_closes_cache.parquet` panels | `data/hk` + `data/hk_stocks`; `data/hk_search/closes_deep.parquet` + gitignored `data/hk_breadth/_closes_cache.parquet` + `data/china_search/closes.parquet` (A/H signal reads it — `engine/hk_ah.py`) | TBD |
| `aux_sources` | gitignored `data/russell_breadth/*` from a lane checkout (`--aux-panel-source`) | `china_breadth` close cache (NOT present on this host's lane checkouts, measured 2026-08-18 — control pass will price the gap) | `hk_breadth` close cache (same host finding) | TBD |
| `env_pins` | `TZ=UTC`, `RENDER_NO_DRIP=1` + dead-proxy | `TZ=UTC`, `RENDER_NO_DRIP=1`, `CN_LANE=asia` (the fail-closed lane gate every CN/HK ledger write checks) + dead-proxy + `pinned_stores` assertion — see §2b(3): the review PROVED one drip store (`data/china_st`) reaches board admission, so "none touch the board path" was false and the drip set is now pinned, not merely named | `TZ=UTC`, `RENDER_NO_DRIP=1`, `CN_LANE=asia` + dead-proxy; no live fetch found on the HK board path (census) | TBD |
| `ledger_pass` | grade_us_board snapshot (vintage runner) + `originate_plans` (vintage runner) | china_standout_track append pass (vintage runner, in-process in library rebuild) | `board_ledger.append_board` (in `compute_hk_standouts`) + hk_pick_lab fire pass (vintage runners) | TBD |
| `capture_stores` | snapshot row for `as_of`==session | `board.parquet` rows `date`==session, all board_definition cohorts | `data/board_ledger/hk_board.parquet` rows `date`==session + fire-pass rows for session | TBD |
| `pending_dir` | `data/us_board_ledger/pending_replay/` | `data/china_standout_track/pending_replay/` | `data/board_ledger/pending_replay/` + `data/hk_pick_lab/pending_replay/` | TBD |
| `session_valid` | prophet_bridge session helpers | `china_standout_track.session_status` | HK calendar (census) | TBD |
| `gaps_file` | `data/us_board_ledger/disclosed_gaps.json` | none | none | none |
| `fidelity_floor` | 0.85 | 0.85 | 0.85 | — |

A registry entry missing any required field is DECLARED-UNRESOLVED and the CLI
refuses that market, printing the missing fields. That refusal is unit-tested.

## §2 US specifics (all inherited from the 08-11 event, now derived not pinned)

- The board's `as_of` is `alpha.json`'s stamp verbatim (`build_stock_library.py`
  `wide["as_of"] = alpha_asof`; alpha stamps `R.index.max()` off the breadth close
  panel — `engine/residual_alpha.py`). So the harness rebuilds
  `site/factordata/alpha.json` inside the fenced vintage tree
  (`scripts.build_site.build_alpha_data` runner) and refuses on a stamp mismatch,
  BEFORE the board build. Board build is cached keyed on the fence `state_digest`
  (`tree_fingerprint` — result-keyed, not delta-keyed).
- Wall clock: every vintage subprocess runs `TZ=UTC`; the admission path anchors to
  the rebuilt alpha stamp (verified in the ancestor); the residual `date.today()`
  channels (earnings-days chip, opex-days, FOMC-days) are MEASURED per run and named
  in the receipt (`earnings_blackout_delta` pattern).
- Origination runs inside the vintage tree via the `_ORIGINATION_RUNNER` pattern
  (vintage `sys.path`, never imported into the orchestrator process), with
  `existing_ids` / `active_keys` from `--plans-baseline` (default `origin/main`).

## §2b Known residuals (named, not hidden — adversarial review 2026-08-18)

1. **Vintage-state context stores.** The real counterfactual bake COLLECTS before it
   builds; a replay's non-price context stores (news, southbound, fundamentals,
   limit tape) are the vintage tree's — for a freeze-era vintage, older than what
   the lost bake would have seen. The control pass cannot price this residual (its
   own stores match its session by construction). It is a bounded infidelity in the
   direction of staleness, never lookahead, and it is named here and in receipts
   rather than silently enjoyed.
2. **Substituted aux panels.** Gitignored close caches (russell/china/hk breadth)
   are supplied wholesale from a lane checkout and truncated at the ceiling: their
   HISTORICAL rows are today's bytes (restated adjustments enter) and their COLUMN
   SET is today's (a name delisted since the session drops out — survivorship in
   the conservative direction). The overlay manifest names substitutions and their
   column diff vs the vintage constituents; the fidelity control prices the effect.
3. **Live-drip collectors inside a vintage build.** The vintage tree runs OLD code,
   so current-code gating cannot protect a replay: CN's build refreshes ~13 context
   stores unconditionally, and the review proved one (`data/china_st` ST board,
   via limit-width → relay counts) reaches board ADMISSION — a true lookahead
   channel. The harness therefore (a) points every vintage subprocess at a dead
   proxy so live fetches fail fast and best-effort collectors keep vintage bytes,
   and (b) asserts post-build that every `pinned_stores` path is byte-identical to
   the vintage commit, refusing on any modification. Fail-closed, measured, both
   passes.
4. **Wall clock.** TZ=UTC pinned everywhere; the earnings-days channel is measured
   per run (rows named); the opex/FOMC channels are named as not independently
   re-measured per session.

## §3 What the harness writes, by mode

| | dry-run (default) | `--execute` |
|---|---|---|
| work dir (scratch) | boards, receipts, previews, build logs | same |
| repo checkout | NOTHING | US: plans + origination receipt; all markets: pending-entry file + harness receipt |
| any nightly-advanced store | never | never (absorb happens inside the next nightly) |

`--execute` output ends with the merge-window warning inherited from charter §0.9
(merge only while no engine job is between checkout and its prophet checkpoint) and
the instruction to run `--verify-collisions` immediately before merge.

## §4 Execution sequencing after this PR merges (not this PR)

1. US 2026-08-14: `--execute` in a fresh worktree → PR with plans + pending entry +
   receipt → verify-collisions → merge → next nightly absorbs + advances.
2. CN 2026-08-17 and HK 2026-08-17: same, via the CN/HK registry entries.
   **Data availability CONFIRMED for CN** (measured 2026-08-18 ~10:0xZ): the
   Tuesday asia-close's trailing-window collect landed both missing days —
   `origin/main`'s `data/china_search/closes.parquet` tails
   2026-08-14 → 2026-08-17 → 2026-08-18 (commit `906499a21350`,
   "data: asia collection 2026-08-18", after a freeze-shaped gap since
   `2c39d8afca95` on 08-14). Verify the HK stores' tails the same way before
   executing HK; a store that never collected 08-17 makes the harness refuse
   with the named gap (DEC's own fallback: a disclosed gap, not a silent one).
3. `ca` / `intl`: a later session completes their registry entries (bake lane,
   surface census, control validation) before any replay; the postmortem's
   per-market freshness follow-up tracks the need.

## §5 Explicit non-goals

- No `us_standouts_v2` / SA-W5 v2-lane replay (isolated lane, own snapshot file) —
  registry-extendable later.
- No re-publication of reconstructed boards to `site/factordata/*`, ever.
- No touch of the 2026-08-01→08-06 window (data defect, `backfillable: false`,
  DEC-preserved).
- No workflow/lane changes beyond the three absorb hooks; the harness is
  operator/session-run, never scheduled.
