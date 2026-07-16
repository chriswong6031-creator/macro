# International Turns & Rotation Revamp (ITR) — adjudicated failure record + build spec

**Repo:** Macro Dashboard · **Date:** 2026-07-16 · **Author:** Fable (main loop), from a 6-lane
audit + 3-lane Opus adversarial verification (9 agents, run `wf_81c02263-833`).
**Operator ask:** "intl.html is a failing dashboard, unable to see turns and rotations in world
markets. Korea KOSPI is currently blowing up and rolling over, with clear signs in technicals and
momentum weeks before, yet our system is still lagging — no warnings, no signals. Full audit and
revamp."

Predecessors (unchanged by this program): `INTL_FIX_MASTERPLAN.md` (2026-07-02, scoring
constitution — untouched), `INTL_RISK_DESK_MASTERPLAN_BY_FABLE.md` (2026-07-12, IRD W0–W4 —
kept as-is; the EM-aggregate risk desk is complementary to, not a substitute for, per-market
turn detection).

---

## §1 — The KOSPI case, verified ground truth

^KS11: parabolic melt-up into an all-time high **9,115 on 2026-06-22** (+67% vs 200dma on
2026-05-06; RSI-14 climax **83.9 on 2026-05-11**), then **−24.9% in 3.5 weeks** to 6,848
(2026-07-16), realized vol 77. Critical path detail (verified in `data/intl/_KS11.parquet`):
a **−15% off-high shakeout on 2026-06-08 that fully recovered to the new ATH 06-22** — any
naive drawdown-threshold detector whipsaws there; the terminal top was distinguished by
**exhaustion divergence** (ATH at RSI 66.6 vs 83.9 at the May climax, a 17-pt lower high on a
+16.5% higher price).

## §2 — Adjudicated failure record (each verified by an independent Opus lane)

- **F1 · Memoryless extension flag — "the bubble that burst clears its own flag."** The engine
  DID print `parabolic` + `bubble_flag=True` from the first committed record (06-16) through
  06-26 including ATH day. As price crashed, `ext_z` fell below thresholds → grade reverted to
  **"steady" mid-crash** (flicker 06-29→07-01, then permanently off). `extension.grade()` is a
  memoryless snapshot; there is no "was parabolic recently → now breaking = TURN" transition
  anywhere. (engine/extension.py:58-70; engine/intl_equity_risk.py:65-66.)
- **F2 · Self-defeating extension normalization.** `ext_z` z-scores extension vs the market's
  **own trailing 252d**: a months-long parabola inflates the baseline mean, so ext_z FELL
  (2.51 on 06-19 → 2.26 at the 06-22 ATH) while price rose — the normalization fights the
  detector exactly at the top. A raw-extension long-history percentile must ride alongside.
- **F3 · `drawdown_risk` is coincident by construction.** `0.5·realized-dd + 0.3·below-200dma
  + 0.2·vol` ≈ "low" at the ATH by arithmetic. Compounding: the parabola left the 200dma so
  far below spot that `above_200d` stayed True through the **entire −25% crash** — the trend
  leg is structurally disabled for months after any melt-up. It measures damage done, not risk.
- **F4 · No momentum/turn machinery at all.** No mom20, no MACD state, no dd-velocity, no
  vol-regime z, no peak-RSI memory → the textbook RSI divergence at the top was uncomputable.
  RSI is computed but **never rendered**; `intl_rates` IRD-R13 velocity fields are computed
  but **dropped by the template**.
- **F5 · Every rotation surface is structurally lagged.** Leaderboard default-sorts 12m USD
  return (Korea still **#1 today**, −25% into the crash; needs ~80-100 more crash days to
  demote). RRG momentum = 63d (still "Leading"). intl_cycles rs_63d: top-2 through 07-13.
  EWY rs_20d flipped negative **06-26, 4 days post-ATH** — three weeks earlier than any
  shipped surface. This is the identical failure China killed in PR #2634.
- **F6 · Macro-first information architecture.** Hero mid-crash: "Goldilocks · South Korea
  leads (+98% 12m)" in green. Off-high −24.9% buried 15 columns into a scroll table; IRD
  stance chips below the fold and EM-aggregate only (cannot name Korea); rankings block has
  zero momentum column. Doctrine glance-tier verdict: FAIL.
- **F7 · Dead/frozen wires.** `data/yahoo/_GSPC.parquet` frozen at **2026-06-12** (RRG and all
  vs-US relative reads blind for a month; 8 consumer engines). EWY carries `to_others ≈ 92` in
  the spillover object in every commit but the display shows only top-3 transmitters — Korea
  never named.
- **F8 · (Design constraint, not a failure.)** The 06-08 shakeout proves turn detection cannot
  key on drawdown thresholds alone; it needs exhaustion evidence (divergence, extension
  percentile) + state memory. A system that stayed "parabolic — protect gains, don't chase"
  through the shakeout and the recovery was RIGHT both times.
- **F9 · Quad headline lags by design.** Growth score was already negative; hysteresis holds
  Goldilocks ~4 weeks into the crash (Q3 confirms ~07-20). Macro data IS slow — the fix is
  demotion from the hero + an independent fast path, not tuning the quad.

Fairness (Opus ruling): "the system gave no warning" is unfair as stated. Accurate: *the page
gave a correct but snapshot-only parabolic warning (one small chip, 06-16..06-26) that
self-erased as the crash began, plus coincident drawdown warnings (watch at −10%, elevated at
−24%); it never surfaced a turn, never demoted Korea from leader boards, and its hero promoted
KR as the green #1 leader throughout.*

## §3 — Rulings (ITR-R1..R7)

- **ITR-R1 · Scope fence.** Display/context tier only; zero scoring-seam wires; no change to
  quad hysteresis, `risk_radar_intl` profiles, `intl_feed`, or any INTL_FIX constitution
  machinery. Per house law the gauntlet is a promotion gate, not a build gate — this ships
  freely as descriptive infrastructure. No forward ledgers: state + events are recomputed
  deterministically from full price history each build (nothing to advance, nothing for
  intraday lanes to discard).
- **ITR-R2 · State memory is the fix.** A per-market turn state machine with hysteresis and
  path memory (`was_parabolic` lookback, peak-RSI-at-high memory, dd velocity) replaces
  snapshot grades as the surface's primary read. Memoryless grades stay as inputs.
- **ITR-R3 · Dual-scale extension.** Raw extension (px/200dma−1) percentile vs own ≥8y history
  rides beside the adaptive ext_z; either can establish extended/parabolic. Fixes F2.
- **ITR-R4 · Fast rotation, state-gated.** Port the #2634 pattern (mom20-primary + state
  governor + continuous overbought penalty); 12m/63d returns remain visible columns, never the
  default sort. NO macro gate on rotation (INTL-50: the uniform macro gate HARMED Korea).
- **ITR-R5 · Whipsaw honesty.** Turn states must degrade gracefully: `crash` is an
  unconditional velocity override; `topping` requires exhaustion evidence, not just a red week.
  Backfill replay over KOSPI 2026-01→07 (and prior crash episodes) is a required PR artifact —
  descriptive sanity, not a gauntlet claim; no "validated" wording anywhere.
- **ITR-R6 · Benchmark freshness fail-open.** Any vs-US read checks benchmark staleness
  (>5 business days behind the newest intl close → fall back ^GSPC→SPY and disclose on Tier 2).
  The ^GSPC frozen-tail root cause gets its own collector fix lane.
- **ITR-R7 · Doctrine binds.** Market-action-first page order; every state carries a plain-word
  stance (Act/Get ready/Watch — don't chase/Protect gains/Stand aside/Ignore vocabulary);
  internal names (ext_z, percentiles, MACD) demoted to hover receipts; bilingual EN/ZH parity;
  one as-of per panel. CJK authored via Write/Edit tools only.

## §4 — Build spec (W1, one PR)

**New engine `engine/intl_market_state.py`** (pure leaf, closes-only, fail-open, deterministic):
per configured country (JP ^N225, KR ^KS11, TW ^TWII, IN ^NSEI, AU ^AXJO, GB ^FTSE, EZ ^STOXX)
compute daily: ext_raw_pct, causal ext percentile (≥3y min, 10y target window), ext_z (reuse
engine.extension), mom20/mom5, rs20 vs fresh benchmark (ITR-R6), Wilder RSI-14 + peak-RSI
memory at each new 252d high + divergence detector (new high within 60 sessions of a prior
high-segment peak with RSI ≥5 pts lower), MACD(12,26,9) cross state + date, dd from 252d high,
dd 10-session velocity, 21d realvol z vs own 3y, MA20/50/200 states.

State machine (precedence): `crash` (ret20 ≤ −15% OR [dd ≤ −18% reached within 30 sessions
AND current dd ≤ −10%] — the current-dd gate ratified 2026-07-16 after review showed the
ungated sticky clause labeled KOSPI "crash" at its own ATH on 05-13 post-V-recovery) >
`breaking` (was extended/parabolic ≤60 sessions ago AND dd ≤ −8% AND < MA20) > `topping`
(was extended/parabolic ≤40 sessions ago AND [RSI divergence OR MA20 lost OR MACD bear cross]
AND dd > −8%) > `parabolic` (ext_z ≥ 2 OR ext pctile ≥ 98) > `extended` (ext_z ≥ 1 OR
pctile ≥ 90) > `downtrend` (< MA50 ≥15 sessions AND mom20 < 0) > `recovery` (reclaims MA50,
mom20 > 0, after downtrend/crash/basing) > `basing` (post-crash/downtrend, dd stabilized,
vol_z falling, > MA20) > `uptrend` (> MA50 & MA200, mom20 > 0) > `calm`. Each state carries
EN/ZH label + stance + css class + `since` date. Event log derived per build: state
transitions + component crossings (MA20 loss, MACD bear cross, −15%/20d, new parabolic entry),
last 45 sessions, bilingual.

**`engine/intl_rotation.py`**: #2634-pattern re-rank over the 7 primary markets (and the
country-ETF world panel where cheap): score = mom20-led fast RS vs fresh benchmark, gated by
turn state (crash/breaking/topping cap the score), minus continuous overbought penalty
(ext pctile), minus gated MACD-cross penalty. Emits rank + plain-word movement chips.

**Wiring** (`scripts/build_intl.py`): vm gains `turn_board` (urgency-sorted per-market state
tiles), `turn_events` (cross-market recent events), `rotation_ranks`, `bench_note`; each
country record gains `record["turn"]`. All existing keys unchanged (intl_stocks mode +
existing tests must keep passing).

**Surface** (`templates/intl.html.j2`, macro mode):
1. New hero: **World Markets turn board** — one tile per market (flag, index, plain-word state
   chip, stance line, 20d move, off-high), urgency-sorted, crash/breaking first. KR today must
   render: state "Crash in progress", stance "Stand aside", −24%/20d, −25% off high.
2. "What changed" strip: top recent turn events (dated, plain words, bilingual).
3. Old macro hero demoted to a compact context strip below the board; "Goldilocks" translated
   to plain words with the quad label as Tier-2 receipt; low-confidence disclosed.
4. Leaderboard: state chip column; default sort = rotation rank (12m stays as a column).
5. Comparison table: stretch chip becomes the state chip (memory-aware, e.g. "was parabolic in
   June"); DD-risk gauge relabeled as realized drawdown ("damage"), leading role moves to the
   state chip.
6. Rankings block gains a 20d momentum ranking (first position).
7. Rates desk renders the existing-but-dropped velocity fields as small direction arrows.
8. Bilingual throughout; doctrine budgets; one as-of per panel.

**Fixes:** intl_performance benchmark staleness fail-open (ITR-R6). ^GSPC collector heal is a
separate lane (chip filed) — the fallback ships here.

**Tests:** state-machine units on synthetic paths (parabola→crash; shakeout-recovery
no-whipsaw; quiet market stays calm), KOSPI replay golden dates, divergence detector unit,
benchmark-fallback unit, render smoke for both template modes (jinja missing-key law), Monday/
holiday-calendar safety (per-series independent computation — no cross-market joins).

## §5 — Follow-ups (filed, not in W1)

- KR/JP/TW/IN/AU/GB/EZ `risk_radar_intl` RadarProfiles (calibrated forward-drawdown radar with
  forward-log governance) — the biggest *leading* upgrade, needs its own calibration wave.
- `^GSPC` frozen-tail root cause + frozen-tail detector coverage for the yahoo group.
- intl_stocks sector-rotation board re-rank (same #2634 pattern, stocks mode).
- Spillover display: name any single market with to_others ≥ threshold even when not top-3
  (Korea case).
- World Market Cycles page (intl_cycles) fast-RS refresh.

### Status log
- 2026-07-16 — Audit run (6 lanes + 3 Opus verifiers), failure record adjudicated, W1 spec
  frozen (Fable). Build dispatched same session.
