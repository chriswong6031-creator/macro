# Divergence Radar predictive-power audit — 2026-08-05 (by Fable)

**Subject:** radar.html's forward ledger verdict — *"Across 4,011 past calls we can now
grade, the themes this radar flagged have tended to lag the market, not lead it — and the
ones it rated highest did the worst."*

**Finding in one line:** that sentence was manufactured by the scoreboard, not earned by
the radar. Five grader-construction defects turned a **statistically-null early read in a
single violent theme-unwind era** into a damning verdict — while the radar's actual
promised test (63-trading-day watch theses) has **zero matured grades** (130 open, first
deadlines 2026-09-17). Separately, the audit did surface one real product defect: the
edge ranking promoted the radar's own "already priced" diagonal to the top of the board
at the exact moment of the July 2026 AI-infra blow-off.

---

## §0 Status after this PR

| Layer | Before | After |
|---|---|---|
| Grader (`engine/radar_ic.py`) | v1: unsigned pooled IC, no base rate, row-pooled overlap, CONFIRMED_* graded as calls, stamped rows starved out of panels, wall-clock snapshot dates | v2: signed + claims-only HAC, base-rate + excess-vs-dart, episode grading, claims/diagonal split, session-keyed snapshots, 91-cal block matching the 63-trading-day promise, machine-readable pre-registered `verdict` |
| Edge ranking (`radar_plus`/`radar_ticker`) | CONFIRMED_* could top `edge_ranked` (salience rewards activity-z ≫ price-z even when both lead) | Diagonal docked to ≤0.40× with extension penalty (floor 0.20×); attributed CONFIRMED ×0.40, BROKEN_LAGGARD ×0.25 |
| Page copy (`site/radar_panel.js`) | Hardcoded warn verdict from pooled unsigned `ic_all > 0.03` at n≥30 rows; hero strip hardcoded "these calls have lagged the market" | All worked/failed claims key off `ic.verdict` (pre-registered gates); base-rate line printed; claims vs "already priced" cohorts split; tiles count independent calls, not row-replicas |
| Tests | pins on v1 semantics (incl. one that had gone vacuous) | 259 downstream tests green; new pins for signed IC, base rate, episodes, session keys, denominator fixes, verdict gates, docks |

Era break stamped: rows from 2026-08-05 are **era 2** (session keys + docked scores);
`era_breaks` ships in `radar_ic.json` and the receipt discloses cross-era pooling.

---

## §1 The five scoreboard defects (with receipts)

Ledger: `data/radar/edge_snapshots.jsonl`, 8,922 rows, 2026-06-20 → 2026-08-03 (37
distinct dates, ~44 calendar days), 661 subjects, 1,505 contiguous (subject,state)
episodes ⇒ **~5.9 duplicate daily rows per episode**. 91% of rows are per-ticker
(`kind:ticker`, incl. `basket_attributed`), not the theme flags the page is about.

1. **Unsigned pooling.** `edge_score` is a salience magnitude; direction lives in
   `state`. The headline `ic_all` correlated the unsigned score with signed returns, so
   a high-edge bearish flag that correctly preceded a fall graded as a miss.
   Measured: pooled unsigned **−0.27** → pooled signed **−0.105** → episode-level signed
   **−0.026** → overlap-robust daily HAC **t=−0.96, p≈0.34** (n=20 daily cross-sections
   vs a 21-day overlap ⇒ ~1.4 independent windows). The rigorous number was always in
   the file; the page copy keyed off the naive one.
2. **Grading the diagonal as calls.** `engine/radar.py` doctrine: *"the radar is SILENT
   on the diagonal — CONFIRMED means corroborated and already priced, no edge."* The
   grader treated CONFIRMED_UP/DOWN (47% of rows) as directional calls. CONFIRMED_UP —
   hot activity on an already-leading price, i.e. the momentum-chase cohort — was the
   single worst cohort: 30% direction, −4.7% mean fwd vs SPY, and its whales (INTC,
   ai_infra, MRVL, NBIS, APLD, IREN, CIFR, GLW) are precisely the July 2026 AI-infra
   unwind (real moves, verified against parquets: GLW 255→153, INTC 131→97 while SPY was
   flat). The "-11%/-9% top buckets" in the old verdict were mostly this cohort.
3. **No base rate.** Era base rate P(beat SPY, 21d) = **0.39** (mean −3.1%): the whole
   tracked cross-section underperformed a flat SPY. Read against the matching
   directional base, every cohort collapses to ≈era: POSITIVE_DIVERGENCE 0.396 vs 0.388
   (+0.8pp), NEGATIVE_DIVERGENCE 0.611 vs 0.612 (−0.1pp), CONFIRMED_UP 0.300 (−8.8pp),
   CONFIRMED_DOWN 0.506 (−10.6pp). The old copy implicitly benchmarked 50/50.
4. **Overlap + weekend triple-counting.** Daily snapshots of a persisting flag re-graded
   the same call ~6×; nightly weekend runs stamped Friday's readings (and Friday's entry
   close) under Sat/Sun dates (calendar-vs-session trap, #4568 family). "4,011 calls"
   ≈ **785 independent episodes**. Episode-entry grading also reads better than
   duration-weighted rows (claims 53.5% vs 50% dart bar) because row-pooling
   over-weights the crash phase of long-lived flags.
5. **Horizon starvation + unit mismatch.** Hypotheses are seeded at 63 **trading** days
   (~91 calendar); the grader's "63" block used 63 **calendar** days, and stamped rows
   were excluded from the 21d panel while the 63d panel had nothing matured — so the
   only populated scoreboard was the horizon the radar never promised, on the cohort mix
   it never claimed. (Bonus row-level defect: BROKEN_LAGGARD — an explicit non-claim —
   sat in bucket denominators as a guaranteed miss; 151 rows.)

**The statistically defensible statement today:** *no evidence of lead or lag either
way at the 21-day check (claims HAC t≈+0.09 on a degenerate window; claims episodes
53.5% vs 50% direction-weighted dart); the promised 3-month test starts maturing
2026-09-17.* The daily signed IC even flipped +0.18…+0.28 in the back half of the
window — one fortnight of a theme unwind dominated the pooled number.

## §2 The real defects the audit confirms (survives the measurement fixes)

- **The board promoted the diagonal.** Whatever the grader said, the product showed
  CONFIRMED_UP momentum names at edge 70–100 on top of `edge_ranked` into a blow-off
  top. Fixed this PR (docks); the diagonal cohort's −9.6pp vs base is now displayed as
  the *reason* it ranks near the bottom.
- **The observable is slow by construction.** Federal contracts drop the most recent
  `LAG_MONTHS=3` incomplete months and compare a 3-month window YoY; congress trades
  disclose at ≤45d; lobbying is quarterly. Only news velocity is fresh. A signal whose
  freshest heavy leg is ~3 months stale cannot plausibly lead 2–3 week returns — the
  21d check was never the right test (it stays as a labeled "early check" only).
- **The consensus leg is 60d trailing RS.** A theme up 15% off a 3-week-old low can
  still read "price flat" at 60d, so late-stage moves can flag as POSITIVE_DIVERGENCE.
  Candidate fix registered for replay (§4), not shipped: blend a 20d leg / require
  activity *acceleration*, and expose entry freshness in lifecycle.
- **Buy-the-laggard attribution is unproven.** `basket_attributed` hands the deepest
  20d laggard in a hot basket the highest attributed edge. Cross-sectional momentum
  literature says laggards keep lagging; the BROKEN_LAGGARD guard trims the worst case,
  but the construction itself is now separable (source stamped into snapshots) so the
  September data can adjudicate it as its own cohort.

## §3 Pre-registered adjudication (gates committed in code)

The scoreboard may claim "led"/"lagged" only when **both** hold at some horizon
(`engine/radar_ic.py::V_MIN_EPISODES/V_T_SIG`, `_verdict()`):

- ≥ **60** matured, independent **claim** episodes (divergence states only), and
- a valid, non-degenerate claims HAC (n_days ≥ lag = horizon) with **|t| ≥ 2.0**.

Otherwise the page must say "measuring" or "no evidence either way" — enforced by copy
keying exclusively off `verdict.status`. The 63-trading-day promise itself is graded by
`engine/radar_scorer.py` against each thesis's own falsifier (`rel_return < −5%` vs SPY)
at `check_by`; `data/radar/track_record.json` starts filling from **2026-09-17** and the
by-source split (signal vs basket_attributed) accrues in era-2 snapshots. Changing any
gate constant is a new pre-registration and belongs in a reviewed PR, not a hotfix.

## §4 The predictive-power program (proposal — next builds, off the render path)

Display-tier accrual continues freely (house epistemics); **authority** (any rank/gate
influence beyond the existing governed de-escalation) requires the gauntlet below.

1. **Historical replay gauntlet (the decisive test).** The repo stores only current
   aggregates (`data/usaspending/obligations.parquet` = 27 ticker rows), so a replay
   needs a history collection build first: USAspending bulk award history (action-date
   bounded, full depth available), Quiver congress/lobbying history, and a news-velocity
   proxy reconstructed or dropped (PIT-honest: mark which legs existed per vintage).
   Then replay `compute_radar` on monthly vintages 2019→2026 with each source lagged by
   its real disclosure delay, grade PD/ND claims at 63 trading days vs SPY **and vs
   matched sector benchmarks** (the SPY-only benchmark bakes a breadth bet into every
   grade), report per-regime and per-source attribution. Compute belongs on the Mac
   Studio off the nightly path, artifacts to R2. This answers "does months-lagged real
   activity lead at months horizon" — the radar's actual thesis — in one build.
2. **Construction candidates to test inside the replay** (not ship): 20d/60d blended
   consensus leg; require `fused_accel` for emerging; extension gate on the consensus z;
   laggard-quality filter beyond BROKEN_LAGGARD (e.g. above own 50d); crowding penalty
   validation; per-source ICs (which leg carries any lead — if only one does, the fusion
   should reweight).
3. **Benchmark repair (cheap, high-value):** add a matched-benchmark forward return
   (sector ETF or equal-weight theme complex) next to the SPY-relative one in
   `radar_ic` so era effects like Jun–Aug 2026 (39% base rate) stop dominating grades.
4. **Kill criteria:** if the replay shows PD claims ≤ dart bar (per-regime, ≥300
   episodes, matched benchmark) the divergence construction as a *standalone ranker* is
   dead per the one-construction-per-kill rule — it survives only as confluence input,
   and the page's divergence lanes stay honestly labeled context.

DO_NOT_REBUILD check: no standing kill covers the Divergence Radar IC/edge construction
(the 2026-07-29 audit was macro.html's Risk Radar; ignition/bottom-radar kills are other
engines). Display-only ordering changes are lawful per the bottom-radar precedent.

## §5 Receipts (2026-08-05 recompute, 21-calendar-day horizon)

- Rows: 8,922 · matured graded 4,045 · episodes matured 785 · base rate p_up **0.388**
- Pooled unsigned −0.2695 · pooled signed −0.1054 · episode signed −0.0255
- Claims (divergence): rows 2,041 @48.5% vs dart 48.1%; episodes 396 @**53.5% vs 50.0%**;
  HAC t **+0.09** (20 daily cross-sections — degenerate vs lag 21 ⇒ verdict `insufficient`)
- Diagonal (CONFIRMED_*): rows 1,943 @38.5% vs dart 48.1% (**−9.6pp**) — mean-reversion
  cohort, now docked on the board and labeled context
- By kind: basket rows 336 @34.2% · ticker rows 3,709 @44.5% (61 non-claim rows excluded
  from directional denominators)
- Whale check (real moves, not data artifacts): GLW 255.69→153.10, INTC 131.72→97.06,
  CRML 10.27→6.21 (2026-06-29→07-20) while SPY 741→742
- SPY over the ledger window: +1.46%; graded cross-section mean vs SPY: −3.1%

*Forensic scripts:* session scratchpad `radar_audit.py` (decomposition) — method
reproducible from the ledger + `engine/radar_ic.py` v2 alone.

---

## §6 Addendum (2026-08-05 evening) — SAM/Grants keys landed; two dark legs lit

Operator installed `SAM_API_KEY` + `GRANTS_GOV_API_KEY` as repo secrets. Verified live:
both keys authenticate; full `grants_gov` collect works (124 FOAs / 22 CFDAs → 16
baskets); `compute_radar` fuses **grants_foa on 16 themes** and **sam_presolicitation on
6** (max sources 9). This activates the §4.2 "fresher legs" path — pre-award FOAs and
solicitations lead obligations by weeks-to-months.

**Measured constraint:** the free personal SAM key allows ~**10 requests/day** (docs
confirm a daily role-based cap; empirically exactly 10 → hard 429s), shared between the
nightly radar leg (was 14 requests) and the 30-minute government-revenue-live lane
(≥14/cycle × 48 cycles — could never complete one cycle and would starve the nightly).
Shipped allocation (radar-first): `SamGovAdapter` v2 batches all NAICS into one probed
request (accepted only when rows span ≥2 distinct codes), falls back to component-packed
rotation ≤7 requests/night with a cursor (full sweep ≈3 nights on 90d windows), stops on
the first 429, and merges per-basket with a 7-day age-out sidecar; the GovRev lane's SAM
step quiet-skips outside 00-01 UTC. **Lifting the gate properly needs a higher-tier
(federal system account) SAM key — flagged to the Government Revenue program;** its own
collector could also adopt comma-batching if its per-shard evidence contract allows.
Per-source IC attribution (v2 snapshots stamp `source`) begins grading these legs as
their first episodes mature (~late August at 21d; the promised read later).
