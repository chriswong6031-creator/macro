# PROPHET US "EYES OPEN" MASTERPLAN — unfreeze, fail-closed disclosure, early-turn parity

**Author:** Fable main loop, 2026-08-07 (operator session: US board missed the precious-metals washout turn)
**Predecessor program:** `research/PROPHET_US_MISSED_IGNITIONS_MASTERPLAN_BY_FABLE.md` (2026-08-05, W-A..W-H — this is its Phase 2; that plan's waves are ~shipped except W-H, and its §4 P2 law "watch-lanes, never buy claims" carries forward here unchanged)
**Trigger:** gold/silver/platinum miners rallied 20–30% off a 6-month washout (cluster of lows 2026-07-16..07-20); CN and CA boards carried Gold Miners in `act_now.buy` by 08-06; the US board showed gold_miners on reduce/avoid, sector_central showed STAND ASIDE, commodities showed MOMENTUM DOWN, and the operator (with $11M deployed in the complex) is right that the flagship board was blind.

## §0 ACCEPTANCE GATES (not done unless)

- **G0.1** A nightly `daily.yml` run completes its collect job past the capital-structure step AND the next `us_standouts.json` / `alpha.json` / `factors.json` advance past 2026-07-31 (verify `as_of` in the committed artifact, not the log).
- **G0.2** `us_standouts.json.staleness.delayed` can NEVER read `false` while `panel.majority_through` lags `as_of`-expected by ≥2 sessions. The 6-of-3,029 fail-open (measured 2026-08-06) must be impossible by construction, and a test pins it.
- **G0.3** No LIMITED/un-analyzable record is ever published as a confident score again: the nine miners' `score 14 / "No setup" / fuel 0.000 / trigger 0.400` signature (2026-08-01..08-06 stamps) becomes a printed null with plain-word disclosure. Test pins the sentinel path.
- **G0.4** `days_since_signal` can never be negative-and-passing: the six rows (HD, ASML, ELV, TSM, TJX, AEP at −5) would fail the fresh-only filter under the fix. Age is measured from the 3D bucket's LAST session (knowability), not its open label.
- **G0.5** The graded US universe contains the gold AND silver miner complexes (at minimum: PAAS, AG, FSM, EXK, SVM, MAG, GATO, FNV, SSRM joining the existing gold names), with honest PIT stamps on basket membership (`added` = actual add date, never a back-dated seed).
- **G0.6** A US washout-lifecycle organ exists (port of `engine/china_basket_turn.py`, the only detector in the estate that fired BEFORE the low — cn_gold TURNING 2026-07-16, CONFIRMED 07-20) writing a forward ledger for US baskets, display-tier, zero scored authority.
- **G0.7** Every PR: tests, merge-on-green label, no forced directional calls (`DNR:KILL-FORCED-CALLS` — the Mag-7 postmortem is the precedent; detection sees, the operator decides).

## §1 MEASURED DIAGNOSIS (2026-08-07, 7-lane forensic workflow; all numbers from committed artifacts or replay)

1. **The board was frozen, not blind.** `site/factordata/{alpha,factors,us_standouts}.json` carried `as_of=2026-07-31` on all 16 renders 08-04→08-07 while CN/HK/CA boards read 08-06. Every miner gained 10–19% AFTER the frozen date (NEM +12.5%, AEM +15.6%, EGO +19.0%, GDX +13.3% 07-31→08-06). Cause: **`daily.yml` failed every night since 2026-08-03** (collect job: 08-03 "run collectors"; 08-06 "compile capital-structure direct document terms" after hundreds of `sec_capital_structure … deferred: TypeError: non-finite numbers are not canonical manifest values` warnings), so runner-local price/factor caches never advanced; the render then recomputes 07-31 answers from 07-31 inputs (last good engine-render log: "wrote alpha.json (1588 names)" = the stale n). A `SURFACE STALE` ::warning has been firing inside GREEN runs since 08-06 with no consumer.
2. **The staleness badge failed open at the worst moment.** `scripts/build_stock_library.py:1383-1403` takes `max()` over member reach: 6 of 3,029 panel members reaching 08-06 flipped `delayed` to `false` on the 08-06/08-07 renders while `panel.majority_through` stayed 07-31. WD (Walker & Dunlop, not Western Digital) published "primed 88 @ $49.69" (the 07-31 close) straight through its −13.9% session on 08-06 — the model never saw the tape.
3. **The confluence cascade was on time; the layers above it were not.** Replay: NEM/AEM T2 from 07-23, T1 07-29/30; KGC/GFI T1 from 07-22 — median **+6.2%** off the low at first eligibility (refutes "already up 10% at the cross"). What arrived at +16.9% was the published score (NEM's first `setting_up` stamp: 08-06). Between cascade and board sat: FRESH_TICKS=2 expiry (window closed 07-31, the leg ran 08-03→08-06), the 200-reclaim buy-filter leg (miners −12..−27% below 200dma; NOTE: measured counterfactual shows `reclaim_veto=False` alone converts those T1s to "failed next-bar hold" — it is a co-refusing gate, not a single lever), T4's `above200` conjunct (structurally unreachable in a washout), and the freeze.
4. **Most of the complex wasn't even graded.** Only NEM/FCX are S&P 500; AEM/KGC/AU/GFI/HMY/AGI/EQX/EGO/BTG/GOLD enter only as hand-curated extras — and those nine published **LIMITED-record sentinels scored as "No setup" (14)** for six straight nightlies while AEM ran +13.9% (honest recompute on the same tape: BTG 80 primed, GOLD 67, AU 65, HMY 64, EGO 63). The silver complex (PAAS, AG, FSM, EXK, SVM, MAG, GATO, FNV, SIL) is absent entirely. `data/russell_breadth/_closes_cache.parquet` is gitignored and its absence silently drops ~1,400 small caps.
5. **The organs that DID see it have no path to the surface.** `sector_cycles` printed `b-gold_miners Trough pos=2.0 signal=BUY` on 08-04 and Recovery on 08-05, but `theme_scoring._label()` (20d-relative monoculture) never reads it, `_reco()` maps deteriorating→avoid unconditionally, and `us_act_now.py` is architecturally display-only (G0.1/G0.3 of the predecessor plan). The published "20d vs market −8.1%" was itself the FROZEN number — the true 08-06 read is ~+6.9pp (eq-weight vs SPY). **Once unfrozen, the existing shared `_label()` likely flips gold_miners to emerging/enter on its own** — CN flipped 07-21 and CA 08-06 through the identical code on fresher data.
6. **The APH/FCX "date bug" is a chart look-ahead, not a detection lag.** The Terminal 3D bar OPEN date is the chart marker (Jul 30); the panel's Aug 3 is that same bar's LAST session — and the knowability replay proves the signal did not exist until the 08-03 close. The chart backdates by up to 2 sessions; the panel is honest. Three incompatible 3D grids are in production (43/60 names disagree macro-vs-Terminal; golden contract has 0 overlapping dates on NVDA); 236/237 `site/signals/*.json` publish `asof` one session early; `days_since_signal` measured from the bucket OPEN makes fresh turns read 4 sessions old (fails FRESH_DAYS=2) while six negative-age rows pass. Full family: `research/SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md` — the 3-grid reconciliation owes a blast-radius report before any semantic change (its §4).
7. **Commodities lag is constructed, bounded, and disclosed nowhere.** Gold's smoothed momentum score was already +0.051 on 08-06 (state still "bear", day 1 of a 3-day confirm run; flips bear→neutral in ~1 session, bull by ~day 9 at trailing pace; silver ~+2/+19). The "~261d to a typical bottom" popover is a calendar lookup against a median of n=7 ZigZag legs whose clock only resets on a full 35%-amplitude confirmed leg — blind to a V-turn by construction. #4603 (W-C) added `turn_developing`/`armed_recent` display states but left both mechanisms untouched by design.
8. **China's edge is architectural, and portable.** `china_sector_turn.py`: days-scale 2D-MACD×3D-StochRSI cascade on a 63/126-session washout composite + peer-basing breadth (40% of washed peers' 10-session decline-velocity flattening) vs the US `sector_cycles` clock (252d double-smoothed oscillator, 22-bar slope with |slope|>3 vote, weekly-MACD 2× weight, BUY needs pos≤45 AND slope>0.5). Plus `china_basket_turn.py` (washout lifecycle, W8-R5) — no US/CA analog — which fired TURNING four sessions BEFORE the low.

## §2 STANDING-LAW COMPLIANCE

- `DNR:KILL-FORCED-CALLS` — nothing here pins a directional call. Every new surface is watch/disclosure vocabulary; the board's Buy lane changes only through its own (unfrozen) machinery.
- `DNR:KILL-WASHOUT-TURN` — scoped to the 2W operator-seed SCORED entry trigger (#1747). The washout-lifecycle organ (W1-D below) is a display-tier state disclosure, the same lawful form the predecessor plan's G0.4 already reasoned through.
- `DNR:KILL-COMMODITY-XSEC-MOM` — closed cross-sectional L/S momentum; single-asset time-series turn detection remains open (display-tier free; authority needs `research/COMMODITY_BOTTOM_TOP_PREREG.md` + gauntlet).
- `DNR:KILL-PRIMED-DIRECTIONAL-GATE`, `DNR:KILL-200DMA-RECLAIM-VETO-FLAT` — untouched; the reclaim-veto flat drop stays rejected (our own counterfactual re-confirms it: the flip alone rescues nothing). Any veto change is regime-conditional + prereg + era stamp (W-F path), operator-gated.
- `DNR:KILL-PROPHET-POP-MERGE` — Prophet↔sector/commodity linkage ships presentation-tier only (chips + residual sub-boards), never a graded-population or blended-ranking change.

## §3 WAVE 1 (this session, 4 parallel PRs + this doc)

| PR | Lane | Scope |
|---|---|---|
| W1-A `nightly-unfreeze` | ops heal (P0) | Fix the collect-job kill chain: sanitize non-finite values at the `sec_capital_structure` manifest boundary (defect class: NaN → canonical-JSON writer), bound the deferred backlog, and re-order/fail-soften the "compile capital-structure direct document terms" step so a context-only compile can never again block the store-advancing steps. Read the stale codex branch `codex/capital-structure-wave01-dagfix` first if it exists on origin — cherry-pick with `-x` if its version is better. |
| W1-B `fail-closed-freshness` | disclosure (P0) | `_compute_board_staleness` → majority-based; `delayed` fails closed; surface the stale state on the board (port the CN engine-driven delayed-board disclosure pattern, #4812); clamp negative `days_since_signal` out of the fresh filter; measure age from bucket LAST session (use `signal_quality.confirmation_date`, already production for HK); LIMITED records → printed null ("insufficient history/data — not scored"), never `score 14 no_setup`; make the russell closes-cache drop loud in the artifact (universe_sources disclosure), not just a ::warning. |
| W1-C `miners-universe-parity` | universe/data (P1) | Silver+PGM+missing-gold names into the graded universe extras; price coverage for silver_miners members (MAG, GATO have no store file); honest PIT stamps on `data/baskets/membership.json` (`added` = true add date; disclosure note for the back-dated seed); platinum/PGM basket (display-tier) if proxy data supports it. |
| W1-D `us-washout-lifecycle` | detection port (P1) | Port `engine/china_basket_turn.py` → `engine/us_basket_turn.py`: WASHED→TURNING→CONFIRMED lifecycle over US basket members, forward ledger `data/us_basket_turn/ledger.jsonl` (nightly-advanced, per-file commit law), display-tier, zero authority. Surface lands on the BOTTOM WATCH shelf AFTER #4729 merges (engine+data+tests only in this PR — no act-board template edits; #4729/#4735 own that surface right now). |

Collision notes: #4729 (BOTTOM WATCH shelf) + #4735 (icon sweep) own `templates/_us_act_now_board.html.j2` + `scripts/build_site.py` act-board sections — Wave 1 does not touch them. W1-B owns `scripts/build_stock_library.py`; W1-C stays out of that file (config/universe lists + membership + fetch wiring only).

## §3.1 WAVE 1 EXECUTION RECORD (2026-08-07, single session)

| Lane | PR | State at handoff | Outcome |
|---|---|---|---|
| Masterplan | #4919 | MERGED `15d4a6fa036` | This doc. |
| W1-A | #4927 | MERGED | Root cause sharper than briefed: `iterrows()` launders a legit `None` (`collection_scope`, pre-Wave-2C rows) into `float('nan')`; canonical writer correctly refuses; broad per-filing `except` → 130 filings re-deferring nightly. Sanitize at the manifest boundary + parking bound + ledger migration, all mutation-verified. The briefed DAG re-order was ALREADY on main (#4731/#4746) and both fatal step errors already healed (#4740; base.py getattr fix) — builder correctly declined to churn `daily.yml`. |
| W1-B | #4933 | OPEN, armed (waits on #4934's heal — shares the red job) | Majority-based fail-closed staleness (+`max_through` disclosure, unknown→delayed); `fresh_bars_knowable` via new `signal_quality.marker_last_session()` (brief's `confirmation_date` REJECTED with evidence — it anchors past the bucket close and would have inverted the defect); LIMITED → printed null cross-market; fresh filter bounded both sides; universe_sources disclosure; the pre-existing stale banner + Delayed pill turn out to have NEVER been reachable — now lit, and the freshness-sentinel regex contract over the banner is tested. |
| W1-C | #4931 | MERGED | +10 graded names (PAAS AG FSM EXK SVM · FNV · SBSW IMPUY ANGPY PLG); `pgm_miners` basket SHIPPED (4 members, 3,167 bars each); MAG/GATO were delistings-by-acquisition (25-NSE receipts), not fetch gaps — stamped removed; PIT truth via `curated_added` on all 1,034 members (`added` is the load-bearing EW inclusion mask — rewriting it would truncate 768 members across 34 baskets). |
| W1-D | #4924 | MERGED (+ #4935 heal) | `engine/us_basket_turn.py` CN washout-lifecycle port, display-tier, ledger + nightly hook. Honest replay: US complex bottomed 07-20 (not CN's 07-16 shape); TURNING 2026-07-22 at +8.8%/+10.0% off trough = 9 sessions earlier than the incumbent's 08-05 IGNITION; CONFIRMED ties the incumbent (08-05) — the earliness lives in TURNING, which oscillates (6 false-fire sessions in Jun–Jul, disclosed). |
| W1-E | #4935 | OPEN, armed | Post-review heal. BLOCKER fixed pre-first-ledger-row: universe-wide `max()` data stamp let a frozen basket manufacture CONFIRMED from one stale bar (per-basket stamp + adjacency-reset hysteresis + at-session coverage + stale-basket annotation). Plus: `stored_parser_deferred` now inside the parking bound; `CS_MAX_RETRIEVAL_ATTEMPTS` env lever replaces the phantom `--rebuild`; `to_dict("records")` regression-fenced. Review verdicts: #4927 MERGE-SAFE, #4924 one blocker (this). |
| Heal | #4934 | OPEN, armed | Base-side reds: `per_horizon` KeyError = #4684's era migration missed one fixture file (test-side fix, `_IN_ERA` imported from sibling); XPASS(strict) = a DELIBERATE tripwire that fired via a 28-second merge race (#4732 vs #4747) — marker dropped, obligation moved into the era-break proposal's Status block instead of vanishing. |
| W1-F | #4942 | OPEN, armed (carries #4934; may red on #4744-owned pre-existing exit-policy fixtures) | Track-record era break RULED (Fable, §0.1 of `US_TRACK_RECORD_ERA_BREAK_PROPOSAL.md`) and EXECUTED: `meta.anchor_era = abs-session-2026-08-06`, pre-era headline preserved in-artifact + side-by-side on every surface, permanent fail-closed guard on unstamped headline moves (mutation-verified). **§0.6 direction disclosure: the move is DOWN, not the proposal's up** — SHIPPED 1.19% exp / 63.6% win → LEGACY 0.92/61.5 (unfreeze: 201 newly matured episodes) → NEW 0.75/59.4 (era isolated; exp_lo −0.10). Published honestly; hero stance now follows the interval, not win-rate alone. |

**Operator escalations (cannot be fixed in code):** (1) `R2_CAPITAL_STRUCTURE_*` secrets print EMPTY in daily.yml while generic `R2_*` are set — a repo-secrets configuration gap; (2) the public track record moves down under the era break — pre-era numbers preserved and shown, reversal is a re-render away if vetoed; (3) fleet decision wanted on unifying the two delisting ledgers (`config/delisted_symbols.yml` vs membership `removed` stamps); (4) retrieval-queue receipt schema lacks a `parked` field (consumer-contract change, deferred).

**Merge-order notes for the next session:** #4744 (exit-policy frozen slice) should merge before #4942's pack can green — if #4942 sits `merge-blocked` on `test_exit_policy_study` reds, that is why (do NOT regenerate that report; it would revert #4744 — the #4850 failure mode). #4734 (board-ledger backfill, stale/unarmed) needs a rebase after #4942. After #4729/#4735 land, wire `us_basket_turn` state into the BOTTOM WATCH shelf (Wave-2 item 3).

**G0 status at handoff:** G0.2–G0.7 satisfied by the PRs above (G0.2/G0.4 pending #4933's merge). **G0.1 is UNVERIFIED** — it can only be proven by the next nightly: check `site/factordata/us_standouts.json` `as_of` > 2026-07-31, then whether `gold_miners`' theme label flips on fresh data (its true 20d relative was ~+6.9pp vs the frozen −8.14% that kept it on avoid). That check is the next session's first action.

## §4 WAVE 2 (next sessions, in ship order)

1. **Sector fast-leg dual-read (display):** run the CN cascade + peer-basing breadth legs over US baskets and show the result as a second read on sector_central ("slow clock says X · fast turn evidence says Y — windows, not certainties"), never replacing the cycle wheel. The 252d oscillator stays; it gains an honest companion. (Fixes "STAND ASIDE while ripping" as a *disclosure* defect first; any authority change needs prereg.)
2. **Commodities turn-state machine (display):** generalize `armed_recent` into WATCH/TURNING/CONFIRMED on each commodity; momentum cell dual-reads while state and score disagree; cycle popover gains sample-size honesty ("median of 7 historical legs — a calendar prior, not a price read") and stops leading with the ETA when `turn_developing` is armed. Re-run conviction calibration post-rally.
3. **Theme cycle-aware dual-read chip (display):** act-board rows show the cycle organ's read next to the momentum label when they disagree ("momentum label lags · cycle organ: Recovery, turned <date>") — the graduation-gap the predecessor plan measured (median 6.5-session Recovery run) becomes visible instead of a silent side-channel.
4. **Prophet linkage, presentation-tier:** cohort-ignition chips on graded rows (basket TURNING/CONFIRMED/IGNITION state from W1-D + `basket_turn` + sector fast leg), a "cohort turning" residual sub-board in the ratified ⚡ form, and Neural Web synapse registration so Mastermind chat can cite the same state. Population/ranking untouched (`DNR:KILL-PROPHET-POP-MERGE`).
5. **Score stability measurement → hysteresis prereg:** the ladder-step `_TRIGGER` map moves scores ≥30 points on 10.15% of day-pairs (p95=43; WD 12→73→15→88 on ±1.3% price). Add `hysteretic_not_topped`-style smoothing behind a prereg + shadow grade before it touches the published score.
6. **Signal-date family:** blast-radius report for the 3-grid reconciliation (absolute anchor + last-session label, both repos, ANCHOR_ERA bump per R-SQ3) per `SQ_BUCKET_LABEL_AS_DATE_FINDINGS_2026-08-07.md` §4; chart markers stop back-dating; golden contract becomes satisfiable. Cross-repo — its own program.
7. **FRESH_TICKS admission and washout cohorts:** `DNR:KILL-FRESH-TICKS-WINDOW` closed *widening* on the general population; whether a washout-turn cohort behaves differently is exactly the "regime-store evidence + fresh prereg" its re-open clause names. Accrue the cohort via W1-D's ledger first; propose nothing until it has bodies.

## §5 SESSION-CHAIN PROTOCOL

One wave per session; this doc is the durable state. Each session: read §0 gates → check ACTIVE_BUILD_MAP + open PRs for the act-board surface → build → update the wave table with PR numbers and measured outcomes → handoff. Do not grind an orchestrator past ~250k context; checkpoint here instead.

## §6 ANTICIPATION PROGRAM (operator command 2026-08-07; ruling recorded 2026-08-08)

### §6.0 OPERATOR RULING (supersedes default promotion sequencing for this program)

New detection/selection SHIPS LIVE DIRECTLY; the OLD selection continues accruing a **legacy
shadow ledger** so the two can be compared later. Operator rationale, recorded: the product is
not yet live to other users; the operator reviews live picks daily and feeds corrections —
iteration speed IS the review mechanism. The gauntlet still governs any later *claim* of
superiority (era-stamped track record, side-by-side, printed nulls) — it no longer sequences
the shipping. Falsifier language stays off user surfaces; "validated" wording stays banned.

### §6.1 Evidence base (all committed in `research/prophet_us_audit/`)

- `ENTRY_LATENESS_FORENSIC_2026-08-07.md` — median pre-signal run-up +6.34% (p75 +11.72%);
  entry placed +2.72% above signal close; publication lag median 5d (max 57d); provisional
  repaint erased fired events on 4/5 dissected names; frozen-vintage service receipts; ASTS
  seen pre-run at rank 7, classified `extended`, never a plan.
- `CN_US_PROPHET_PARITY_ANATOMY_2026-08-07.md` — same engine, same veto, divergent SELECTION:
  US hard-gates `act_level >= 2` (patience statuses map to 0) and keeps the chase-first entry
  map; CN featured patience-first on measured evidence (2026-08-04) and the US re-measurement
  was never run. CN-only: weekly ripening shelf, theme_timing 15pts, reversal_member 10pts.
- `GATE_COUNTERFACTUAL_2026-08-07.md` — 713 names × 180 sessions, equality gate PASS.
  Veto variants admit the exhibit cohort ~2 weeks earlier (GDX 11-25 @ 6.6% run-up vs live
  12-17 @ 8.4%; NEM 12-04/11-28 vs 12-17; MRNA 04-16 @ 12.1% vs 06-16 @ 21.4%; RKLB first
  admission @ 25.1% run-up vs 52.3%). Pooled cost: precision 14.3→13.3–13.4%, loser
  32.6→33.7–33.9%; per-name-first precision IMPROVES 7.4→8.8–10.0%. Gate pressure: 60.4% of
  tier-reachable name-days vetoed.

**2026-08-09 evidence revalidation:** §6.1 is a historical evidence ledger, not a current
system census. The plan corpus has expanded since the lateness receipt. A current-main replay
still reproduces the gate algebra with zero equality mismatches, but the unpinned Yahoo universe
expanded from 713 to 732 graded names and changed the aggregate/named-exhibit output. Preserve
the recorded measurements as display-tier history; they cannot promote a gate/rank/Prophet
change without a source-manifest-pinned rerun and the separate authority gauntlet.

### §6.2 WAVE A — the selection inversion (ships now; two parallel builder PRs, disjoint files)

**A1 `patience-admission` (`engine/prophet_bridge.py`, `scripts/build_prophet.py`):**
admission becomes status-class — `entry_signal ∈ {bounce_wait, wait_pullback, hold, buy_now,
partial}`, `band != low`, dir up; the `act_level >= 2` hard gate is REMOVED. Every plan stamps
`admission_class: patience|confirmation` and `selection_era: anticipation-v1-2026-08-08`.
Publication-lag guard: an entry basis older than 3 sessions vs the run's asof re-derives from
the current close or skips with a printed reason (kills the 57d-lag class). Legacy shadow
ledger: the OLD gate's would-be selections written nightly (nightly-lane-gated, idempotent,
schema in §6.5). Cap 12→16 with sector cap 4. `index.json intake.basis` text updated.

**A2 `patience-rank` (`engine/us_board_rank.py`):** entry-value map re-ordered patience-first
(CN ordering as v1 constants — bounce_wait 1.0 … buy_soon 0.35; the §6.6 US re-measurement
revises them); FEATURED_STATUSES widened to the CN set; `ext_z_unknown` blackout fixed (the
featured lane must never silently read 0/N — printed null + fallback); stale provenance
string at `us_board_rank.py:896` corrected; `selection_era` stamped in the ranking definition.

### §6.3 WAVE B (next sessions, in order)

B1 ripening shelf US port (HK template `hk_board_rank.py:1063-1233`) — the pre-cross bench.
B2 wire `us_basket_turn` (W1-D, currently dark) + `subsector_confluence.funnel()` double_buy
as intake chips and a US theme-timing rank channel (display first, then paid points).
B3 deep-base veto conditioning (waive legs only in the replay's `deep_base_state`) — the
tier-path earliness for the RKLB class; changes the shared gate, so it ships with its own
regression fence and the CN/HK blast radius checked. B4 young-name shelf (30–158 bars,
LIMITED-labeled; 7-stock cohort today incl. SPCX at 38 bars). B5 US PIT latch (fired
eligibility can never be un-fired) — coordinate with unmerged sibling `a8d6fe034ad` on
`claude/missing-300363-china-prophet-8702fa` before building. B6 signal-date family (§4.6).

### §6.4 Standing constraints honored

`DNR:KILL-PROPHET-POP-MERGE` (cohort linkage presentation-tier only); `DNR:KILL-FRESH-TICKS-WINDOW`
(no general fresh_ticks widening — the FRESH4 replay variant was measurement-only and is weak
anyway); nightly is the sole ledger advancer; GitHub annotations start-of-line; bilingual
surfaces; era-stamp law on any published-number shift (#4942 pattern).

### §6.5 Comparison contract (so "check later" is real)

Legacy shadow ledger: one row per night per legacy-admitted candidate
`{date, ticker, entry_signal, act_level, score, rank, would_have_planned}` under
`data/prophet/legacy_shadow/` (day parts, per W7 storage law). Grading reuses
`engine.grading.forward_metrics` — never a forked ruler. After 10 accrued sessions the
miss-audit artifact publishes new-live vs legacy side-by-side (cohort → horizon → class, no
pooled top-line), era-stamped.

### §6.6 The US re-measurement (evidence loop for the map constants)

Nightly job over the W7 stamped store: entry-status → forward outcome table (the CN §2.3
methodology on US episodes), published in the scorecard. The v1 CN-ordered constants in A2
are provisional by construction; this table is what revises them — visibly, in days.

**FIRST RUN (2026-08-08, PR #4988; source deviation disclosed: the W7 grade store has NEVER
advanced — grades/ empty since merge, `priority_score_scorecard` nightly-null; measured off
`data/us_board_ledger/retro_grades.parquet` instead, the closer CN-§2.3 parity match):**
the CN ordering did NOT reproduce. 2,816 statused episodes, 23 dates 06-15→07-30, loser :=
excess_spy ≤ 0: bounce_wait H=5 loser 54.9% (n=153) / H=10 65.4% (n=52) vs buy_now H=5
39.0% (n=95); watch lane independently repeats bounce_wait 55.3% (n=76). AND the binding
null: bounce_wait carries ZERO marks at H≥21 in every lane — the patience thesis's own
chartered horizon (basing→H=63) has no US data. Caveats logged: fading-tape window ending
07-30 (pre-ignition), short-ruler-only, flat-counts-as-loss.

**RULING (Fable, 2026-08-08): the A2 entry map goes STATUS-NEUTRAL** — one flat value
(0.75) across the five admissible statuses; refused-class values unchanged. Neither
chase-first nor patience-first is defensible as a ranking claim today, in either direction.
Admission breadth (A1), entry zones (Wave B), and the washout/cohort discriminators carry
the earliness; the map claims nothing the data does not. **Pre-registered revision rule:**
an ordering may be re-introduced only at its chartered horizon, n ≥ 50 per cell, sign-stable
across two half-splits, measured on era-stamped `anticipation-v1` episodes. Amendment
dispatched to #4976 before merge; a NEUTRALITY pin test replaces the ordering pin.

### §6.7 Wave A execution record (2026-08-08, single session)

| Lane | PR | State at record | Outcome |
|---|---|---|---|
| Evidence + §6 | #4972 | armed | 3 receipts + this section; first proof run green pre-heal, re-proving post-#4984 |
| A1 patience admission | #4977 | armed | act-gate removed; dir is a TONE — `{up, caution}` (literal "up" admits zero bounce_wait; **`down`/BOTTOM WATCH refused for plans by ruling** — routes to ripening/watch, 1 row affected); legacy shadow ledger; 3-session lag guard; cap 12→16 sector-cap 4; live proof 16 plans / 7 patience (BHP RIO UUUU ALB AEIS WBD FN) |
| A2 patience rank | #4976 | armed, neutrality amendment pushed | ladder built CN-ordered in-PR, **NEUTRALIZED pre-merge by §6.6's first run — the CN ordering never reached main**; ENTRY_NEUTRAL_VALUE ruled 1.0 (range continuity + fixed-threshold safety); featured widened; ext_z blackout fixed (0→8 featured on the 08-06 board); found the NEXT lock: stage-bucket sort + `stage_not_live` featured veto (under the flat map the live prize is 2 rows, not 10 — A3 stands structurally, restated at that strength; gated on this PR's merge) |
| ext_z data plane | #4979 | armed | coverage-floor anchor (6/3034-member sparse row blanked ext_z board-wide); LIVE_LOOKBACK=63 vs anchor lookback 10, mutation-verified; HK featured relights with ext_unknown disclosed (HK has NO ext input — Wave B decision) |
| Fleet heal | #4984 | **CLOSED — superseded by sibling #4983** (identical floor mechanics, merged 09:27Z while this one queued; closed per the superseded-heal law rather than forcing a content conflict) | seasonality ledger count pin == 28 vs nightly-accrued 43 — scheduled failure red-blocking every post-append merge-ref fleet-wide; the grade-row-assertion next-scheduled-failure flag handed to the seasonality lane in the closing comment |
| Signal dates | #4987 | armed | `signal_date`/`confirmed_date`/`recorded_at` split, additive, mutation-fenced; **outage audit: forward ledger CLEAN (0/27), no run-date stamping** — but marker `date` is the bucket OPEN label (panel "Buy Aug 7" for NVDA was honest; the chart x-anchor misleads), 7/7 pre-outage ledger rows carry the OPEN label as signal_date, QCOM/MS rows carry non-bucket dates (board-as_of leak) → board-coherence follow-up gated on #4976 |
| §6.6 instrument | #4988 | armed | table above; also surfaced: W7 grade store never advanced (own lane needed) |

### §6.8 ENTRY LANES BATTERY + ORACLE V3 + EARNINGS IGNITION (operator session 2026-08-08, second wave of orders)

**(a) Structure-stop redesign (Tencent receipt — "sold at the lowest point of the mini cycle").**
The swing-low-break confirm fired at the terminal flush while the 3D MACD-RSI was rising — the
break WAS the capitulation, not distribution. HK-O2 design: condition the CONFIRM on context —
momentum divergence (3D MACD-RSI above signal and rising since ARM ⇒ disarm or demote to
"flush watch"), washout-maturity, and volume-climax signature; a contradicted break emits
"stop hit — flush signature, re-entry watch armed" (the RE-ENTRY machinery already exists)
instead of a clean SELL. MEASURE FIRST: replay all sell_confirms — P(low within ±2 sessions |
confirm) split by momentum-context; if the contradicted-confirm cohort marks lows, the
conditioning ships.

**(b) Grey dot → EARLY TURN lane (operator: "redo grey dot into something else").** Promote
`early_dots` from a 2.2px toggle-hidden glyph to a first-class starter-grade marker tier:
visible, labeled as a window not a certainty (voice law), qualified by lane context —
HTF-washout maturity OR leader-pullback structure (uptrend intact + shallow reset; the ADAM
2026-07-27→08-05 receipt: dot at the 8.4-8.5 reset, 3D confluence +15% later with the zone
printed 9.61-9.82 AT THE TOP) — carrying a structure-anchored zone (retest band / anchored
VWAP, never price-at-signal-time), the STARTER entry; the full BUY becomes the ADD.
MEASURE FIRST: historical replay of every early_dot — P(low within ±2 sessions), fwd excess,
false-positive rate, CONDITIONAL on washout-mature / leader-pullback / naked — four
anecdotes (9988, ADAM, NVDA-adjacent, 0700 Jul-2) do not carry the promotion; the
conditional table does. Zone law for the entry-zone builder: ADAM is acceptance case #2 —
a Continuation/Ready leader-pullback's zone is the RESET BAND (8.40-8.70), chase-above at
the pullback high, never the post-pop range.

**(c) Washout-state release (Alibaba 90→128 missed).** `bear_block`'s sole release (completed
2W cross) gains a second release: monthly/2W washout-mature + turning + cohort confirmation
(the discriminator stack) ⇒ starter-grade emission below the 200dMA. Plus the shallow-cross
re-fire repair (a name grinding −20% inside one bull cross can never re-fire — Tencent Jul-3).

**(d) US entry-lanes battery (operator: "is the 3D edge crowded? how do institutions buy?").**
Working hypothesis, honestly held: single-name lagging-confluence entries on liquid US names
are heavily arbitraged; edge migrates to composition and context. Institutions run BOOKS of
entry types, not one signal. We mirror with stacked lanes, each measured side-by-side in the
shadow/scorecard framework: (1) WASHOUT-IGNITION (built — deep-base + cohort + turn); (2)
**LEADER-PULLBACK — the NVDA/AVGO-class catcher** (they were never washed out: high-RS leaders,
shallow controlled retrace, daily stoch reset <20-30 while the 3D uptrend stays intact, entry
at rising structure — anchored VWAP / prior breakout / 20-50d MA — on the resumption print);
(3) FLOW-CONFIRMATION chips from in-house planes (polygon GEX dealer positioning, darkpool_eod,
si_handoff short structure) as confluence context, display-tier first; (4) EVENT lane = (e).
Each lane display-tier → forward-graded → promoted per §6.6 mechanics. NO claim that one lane
is THE answer; the battery is the answer.

**(e) EARNINGS IGNITION (AMZN Jul-31, MSFT Jul-29 re-entry, DLB Jul-23 receipts).** The
observable phenomenon: fresh buy-confluence within days before earnings = anticipatory
positioning flow, whatever its source — we detect the FOOTPRINT, mechanism-agnostic (no
insider-knowledge claims in any user copy). Measurement lane FIRST (launched 2026-08-08):
all fresh confluences within 5 sessions pre-earnings over the marker history — reaction
stats vs SPY, vs non-earnings confluences, vs earnings-without-confluence base rate; the
ADVERSE TAIL is the load-bearing unknown (does a confluence ever precede a miss? this
quarter's broad beats confound — measure across quarters). LLM role bounded by A7: transcript/
history analysis may de-escalate or contextualize (display-tier chips), never originate or
escalate a signal. Coordinate with the active 'Earnings Intelligence' session (Struct/Jodie
group-reaction build) — cite, never duplicate; group/peer-reaction inputs come from their
artifacts when they land.

**FIRST RUN VERDICT (2026-08-08, PR #4993 — 12 years, 726 pre-report confluences /
9,497 base-rate reports): the confluence-footprint construction does NOT reproduce.**
Cohort A reaction +0.03% vs base-rate C +0.35%; adverse tail POPULATED at 49.3% (n=358;
VRT −36.7%, AMD −16.2%, SBUX −15.9% incl. take-quality); half-split sign unstable; no
lead-time gradient. The one stable read is RISK, not edge: pre-report entries carry a
fatter loser tail at an indistinguishable mean (take 10.2% vs 3.0%) — and a calendar-gated
risk/sizing channel is a forbidden construction (`DNR:KILL-CALENDAR-GATED-RISK`); report-
proximity DISCLOSURE (existing earnings_soon chips) remains the compliant surface. Decisive
nuance: **neither operator receipt lands in the cohort** — AMZN's marker was knowable
2026-08-04, three sessions AFTER its 07-30 report (the chart's bucket-OPEN label drew it
pre-report — the §6.7 signal-date defect manufacturing the visual pattern), MSFT led by 8
sessions; the builder refused post-hoc window-widening (`DNR:KILL-OUTCOME-AUDITION`).
DLB/SPCX absent from the signals universe. Coverage: EDGAR history ends 07-02; recent dates
ride a stale forecast store — named in the receipt. THE KILL IS CONSTRUCTION-SCOPED: the
tested construction (marker-confluence within [T-5,T-1]) is closed; the FLOW-footprint
variant (pre-report volume/darkpool/GEX anomaly — the SPCX shape) is a different
construction and remains open for a chained session, as does the Earnings Intelligence
group-reaction angle.

**(f) CN WINNER CHAIN + LIMIT-MOVE FOOTPRINT (operator 2026-08-08, third wave; re-audited
2026-08-09).** (1) The 300363 case is retained only as an outcome-selected pipeline forensic:
contradictory same-date stores, missing common run identity, mutable ledger provenance, and no
execution receipt. Its exact price, return, legal-band, fillability, score, and rank claims are
quarantined and have zero candidate, rank, gate, Prophet, Neural Web, or trading authority.
(2) The limit-move construction space remains open, but exact event measurement must start from
the canonical full-A substrate: authorized TuShare unadjusted `daily`, same-key vendor
`stk_limit`, point-in-time security/session state, and a promoted manifest. False-discovery,
fillability, and collector-proposal constraints still bind after that substrate exists.

**§6.8(f)(2) LEGACY FIRST RUN — `STOP_SHIP_UNVALIDATED` (2026-08-09 re-audit).** The former
positive verdict and every exact-board count, continuation/base rate, feature lift, tolerant
agreement rate, legal-band classification, return, and strategy license are withdrawn. The
Wave-0 input was Yahoo-adjusted `data/china_stocks`, so a reconstructed percentage/tolerance
band cannot establish nominal CNY ticks or an exchange limit event. The current authoritative
receipt is `research/cn_limit_alpha_sol/W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.md`:
`BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT`.

Reopening requires one-to-one TuShare `daily`/`stk_limit` joins with exact integer-cent
previous-close parity, OHLC containment inside the vendor interval, and legal event predicates
`high_cents == up_limit_cents` (touch) and `close_cents == up_limit_cents` (seal). Missing
limits, unknown rule/lifecycle state, mixed generations, adjusted prices, tolerant returns, or
`>=` comparisons fail closed. No CN context chip, probability, score, rank input, Prophet fact,
Neural Web fact, or live surface is licensed by the legacy run.

**(g) v2-vs-v3 RULING (operator question 2026-08-08: "does 300363 mean v2 > v3?").** NO
reversion and no species/weight change may follow from an outcome-selected case. The stored
plumbing discrepancies can motivate a pre-registered full-board comparison only after the
canonical substrate and immutable run/entry receipts pass. Selection quality, outcome returns,
and exact legal-band events must remain separate evidence families; none may promote another.

### §6.9 THE RESIDUAL-LATENESS ATTACK + AUTONOMOUS RUN ORDER (operator 2026-08-08, overnight full-auto grant)

**The operator's check is correct:** even the A1 patience picks (BHP RIO UUUU ALB) were up
hard over the prior 2 sessions at admission. Decomposed, US lateness = (1) the state machine
labels `bounce_wait` only AFTER the first impulse; (2) nothing admits on the EARLIEST
mechanical evidence (the dot signature); (3) the 3D confluence confirms 10-20% late; (4) EOD
cadence floor = signal at close T, actionable T+1; (5) entry = asof close, no zones. CN's
"robustness" is (1)+(5) solved plus species machinery — not clairvoyance. The legacy 300363
adjusted-price account cannot establish exact entry timing or legal-band continuation and is
not evidence for this claim. **The systematic answer is not
predicting before evidence exists — it is entering on the EARLIEST evidence tier at starter
size with structure zones, and letting confirmation ADD.** Three compressions ship it:
EARLY-TURN starter tier (dot signature engine-side, context-conditioned), structure-anchored
entry zones on every plan (a late signal stops implying a late PRICE — the plan waits at the
band), leader-pullback lane (catches the reset BEFORE the run in the NVDA/AVGO class).

**AUTONOMOUS RUN ORDER (standing, execute without asking; each step gated only by its file):**
R1 merge cascade lands Wave A (branches refreshed 11:35Z; watcher live).
R2 on #4976 merge → spawn A3+COHORT builder (`engine/us_board_rank.py`): stage-gate relax
(featured stage veto after status check; sort respects score within admissible stages) +
US `reversal_member` channel port (binary membership, 10/100-class weight, scarcity-honest,
sourced from `us_basket_turn` + subsector reversal cohorts; era-stamped, ship-live per §6.0).
R3 on #4977 merge → spawn ENTRY-MECHANICS builder (`engine/prophet_bridge.py` +
`engine/us_early_turn.py` new): structure-anchored zones on every plan (buy_zone_low/high +
chase_above; NVDA acceptance: 3D signal + daily stoch both >80 ⇒ wait_reset zone, never
market-chase; ADAM acceptance: Continuation/Ready zone = the reset band) + EARLY-TURN
starter-class admission (daily/2D stoch-cross-from-washed + histogram curling via
bars_to_cross machinery, conditioned on washout-mature OR leader-pullback context, starter
size, window-not-certainty copy).
R4 now (no gate) → LEADER-PULLBACK organ + replay (`engine/us_leader_pullback.py` new +
receipt): RS-leader universe, controlled retrace, daily stoch reset, resumption print;
2-year replay with precision/loser/entry-vs-low stats + NVDA/AVGO/ADAM receipts.
  **R4 VERDICT (PR #5007, 933 fires/504 sessions): RESET_TURN standalone = NULL**
  (+2.9pp pooled is a repeat-firer artifact; −0.6pp per-name-first vs the leader base) —
  retained as a confluence input, not promoted. **THE ZONE REPRODUCES: median entry-vs-low
  7.26% → 2.29% (−4.97pp of pure entry location, half-stable ±0.75pp)** — the §6.9
  lateness target achieved by MECHANICS. All three case receipts MISS under v0 constants
  (not tuned to capture them): NVDA — RS percentile measured AT the low is depressed by
  the pullback itself (0.52 vs 0.75 gate; pre-pullback RS is the v1 candidate) + 200dMA
  undercut at the low; AVGO — recovery-exit closes the episode the same bar the cross
  lands (ordering, pinned as deliberate non-repair); ADAM — the two turn legs never
  coincide on one bar (needs a within-N-bars window). Population scale: 50% of
  never-turned episodes were lost to leg-TIMING mechanics, not failed turns — three v1
  candidates pre-registered in the receipt §3.2. Close-basis + survivorship caveats
  binding; read the LEADER-state control row.
R5 on #4977 merge → small builder: why-not receipts LIVE on the Prophet surface (nightly,
per-name blocking reason — ends the manual RKLB-class digs).
R6 after tonight's nightly → verify anticipation-v1 board live (era stamps, patience picks,
legacy shadow rows accruing, zones if R3 landed); check `data/us_prophet_rank/grades/`
advanced (W7 store dark since merge) — if still empty, spawn its heal.
R7 session-chain handoff: update §6.7/§6.9 execution records + memory with every PR/outcome.
**RESUME STATE v2 — 2026-08-09 06:30Z (SUPERSEDED-BASE EVENT; the v1 block below is
historical):** #5071 "lossless US origination and date-safe outage recovery" MERGED 03:37Z —
a fleet lane REBUILT the US Prophet intake/date/durability path and removed the live cap.
#4977 (A1) was CLOSED by its audit with the surviving debt named: **status-class/patience
admission + selection-era stamps + zero-authority legacy shadow ledger** — port these onto
the #5071 base as a FRESH PR (read #5071's diff first; do not resurrect the old branch).
#4976 (A2) reds on packs 1/2/3 post-#5071 — re-audit it the same way before any refresh
(its featured/ext_z/neutral-ladder content may partially survive; its stage-gate finding =
R2 still stands). The other eight armed PRs (4972 4979 4987 4988 4993 4999 5000 5007 5026)
need per-PR re-audit vs the new base — assume nothing merged; some may be partially
superseded like A1. THEN the run order continues: R3 entry mechanics (zones + wait_reset +
zone-with-expiry-to-starter + EARLY-TURN starter) built directly on the #5071 base in the
same PR as the patience-admission port (one coherent intake change); R2 stage-gate+cohort
on whatever us_board_rank looks like post-audit; R5, R6. The CN limit-alpha Fable session
runs independently (Wave 1 PRs #5059/#5061) — do not collide with its lanes.

**§6.9 EXECUTION RECORD — 2026-08-09 EOD (RESUME v2 discharged; blocks below are historical).**
The run order completed through R5 with R2 in flight and R6 pending tonight's bake:
**R1/armed cascade** — the full set landed 08-09: #5105 (09:25Z, the A1+R3 coherent port:
status-class admission, `selection_era`/`admission_class` stamps, legacy shadow ledger,
zones on every plan with wait_reset clamp + zone-expiry→starter, EARLY-TURN starter; live
proof 79 buys → 54 admitted (31 patience) → 47 plans vs 29 legacy), then post-livelock-heal
the rest drained 16:43–18:07Z: #4972 #4976 #4979 #4988 #4993 #4999 #5000 #5109.
**R3** shipped inside #5105 (one coherent intake change, per RESUME v2's instruction).
**R4** — organ #5007 + seam heal #5117 + the production publisher #5146 (task #8): per-run
PIT `site/anticipationdata/us_leader_pullback.json` (680 states/39s, dag-wired before
build_prophet), leader half now EVALUATES in production (26/54 board candidates stated,
honest-zero admissions on day one); killed a latent raw-token leak (`RESET_TURN`
interpolated into entry-zone copy) mutation-checked. **Minted:** STORE_LADDER coverage
widening (28/54 uncovered incl. ADAM, the §6.8b acceptance name) = a JOINT §6.6
re-measurement with the TURN WATCH desk — restates the pre-registered RS_TOP_PCT quartile
(697→2,994); parameter test-pinned, never widen unilaterally. `context_sources` computed
but unpublished (minor debt).
**R5** — #5143: per-name `refusal_receipts` through #5105's own `entry_status()`/
`admission_class()` helpers (the #5071-era `intake_stats` was AGGREGATE-only — the
"disclose per-candidate" claim in earlier notes was wrong; partition test-pinned
54+25=79); glance-tier EN/ZH, era stamp plain-worded at Tier 1 + literal on hover.
**Rider debt:** a future Terminal receipts rider must headline `declined` (build_prophet
56/23 vs build_site 25/48 count basis) or the surfaces disagree.
**R6** — GATED correctly: no nightly checked out post-#5105 until tonight's 22:30Z cron
(running as of this record); verification chip armed. W7 grades darkness reclassified
NOT-A-BUG: grader alive (`candidates=7465 dates=4 pending=29860 new=0`, H=10/21/42/63),
first possible grade ~08-18 — do not spawn a heal before then.
**R2** — builder in flight this evening (stage-gate veto after status check, sort respects
score within admissible stages, `reversal_member` binary channel from `us_basket_turn` +
subsector cohorts, era-stamped; carries the #4976 riders: `ext_unknown` carrier +
don't-chase-at-P100 deviation).
**R7** — session-chain handoffs on main (`research/ANTICIPATION_CONTINUATION_HANDOFF_2026-08-09B.md`) + program memory current.
**R8** — #5026 merged (TURN WATCH data plane; real-organ PIT adapter took leader fires
28→7); the page ships under the design lane in a later session.
**Fleet context that shaped the day** (details in the handoff + memory): baseline-dispatch
livelock diagnosed and healed (#5133 law + #5136 event-conditional cancel fence, verified
live), a 12:34Z mass-cancel killed ~30 runs incl. the live proof (recovered by rerun),
the afternoon mega-drain's cross-PR interactions redded all four packs at 18:46Z, healed
atomically by #5188 (20:19Z) — post-#5188 baseline dispatched 22:52Z as this record closes.

**R6 addendum (2026-08-10):** first post-#5105 bake (nightly 31343218391, run-level SUCCESS)
verified live: era-stamped index + zones publishing, leader-pullback regenerated (952 states),
turn_watch riding site/turn_watch/ with weekend-honest as_of 08-07, legacy shadow accruing
(30 rows). ONE wedge: all 30 eligible candidates refused at clock_provenance because the panel
reach summary counted six weekend-calendar members at Sunday 2026-08-09 against the equity
majority's Friday — mixed_vintage true on every Sunday/holiday bake by construction. Healed
producer-side (session-clamped reach dates; raw max reach still disclosed; off-modal members
now named in the receipt); the #5071 gate itself is unchanged. Shadow parquet was runner-local
only — now registered in the prophet checkpoint manifest. First-issuance cost: ~2 days (the 25
clean candidates originate on the next clean bake); 5 candidates remain correctly refused on
per-candidate formation/tier chronology.

**RESUME STATE 2026-08-08 13:05Z (session limit hit, resets 15:20Z):** R4 DONE (#5007 armed —
RESET_TURN null standalone/confluence-input, ZONE proven 7.26%→2.29% entry-vs-low; NVDA/AVGO/
ADAM missed under v0 with leg-timing causes + 3 pre-registered v1 candidates; NEW v1 candidate
from operator chart review: zone-with-expiry-to-starter, class-conditioned washout-vs-V).
R8 data plane PARTIAL: builder died at session limit with 55 tests passing in worktree
`agent-acb91d77c23bc843c` (branch `worktree-agent-acb91d77c23bc843c`) — RESUME IT via its
transcript, do not rebuild. Wave-A merges: none of ours landed by 13:00Z (nine siblings did);
runs from the 11:35Z branch-refresh conclude ~13:10Z+ — on wake, check states, diagnose any
NEW red honestly (nine merges moved main), then R2 (#4976→A3+cohort), R3 (#4977→entry
mechanics incl. BABA/NVDA/ADAM acceptance + expiry-to-starter), R5, R6 nightly verify.
Armed set: 4972 4976 4977 4979 4987 4988 4993 4999 5000 5007.

R8 **TURN WATCH desk (operator reframe 2026-08-08: "if we get the signal early, I do the
holistic review myself — but if we don't surface them, names reach my desk up 10-15% and I
chase").** The operator IS the second-stage filter, so this surface optimizes RECALL + CONTEXT
DENSITY, not precision: a nightly deck of every name whose EARLIEST-evidence trigger fired —
union of (a) the dot signature on 1D (stoch cross up from washed + histogram rising), (b) 2D
fresh cross while the 3D has NOT yet crossed (pre-confluence, btc printed), (c) basket/cohort
turn membership (us_basket_turn TURNING members), (d) leader-pullback RESET_TURN — each row
carrying the operator's own checklist PRE-COMPUTED: HTF washout state (monthly/2W pinned +
duration), S1/S2, off-high %, base depth/age, 20d RS vs SPY, theme/basket heat + turn state,
200d distance, and what the slow tier currently says (so "3D not crossed, ~2 bars to cross"
is visible instead of hidden). Sorted by a display-only context score, capped, honest about
noise ("windows, not certainties"). Data plane ships FIRST (engine + artifact + receipt with
the day's actual deck); the page ships next session under the design lane (doctrine +
frontend-design skill — never rushed). Acceptance: a mini-replay showing surfacing dates for
RKLB / ASTS / miners / NVDA / ADAM vs their eventual admission dates and % off low at each.
confluence implementation — parity forensic in flight; Tencent Jul-24 sell rule + Alibaba
grey-dot identity pending). HK board receipts: 156-name universe, buy=2 (live=1 + ran=1),
12 vetoed, 12 ripening, featured=0 (no ext input) — complete-fix lane gated on #4976 merge,
acceptance gates: never 2 buys while ripening+vetoed hold 24 with undisclosed reasons; featured
never silently 0; universe coverage audited.
