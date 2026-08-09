# LEADER-PULLBACK replay — the above-200 early-entry lane (2026-08-08)

**Tier: RESEARCH / display.** Measurement only. No engine, gate, board, ranker, grader or ledger changes; nothing under `site/` or `data/` is written. Organ: `engine/us_leader_pullback.py` (v0 constants, ungauntleted). Instrument: `research/prophet_us_audit/leader_pullback_replay.py`. Charter: `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(d), §6.9 R4.

---

## §0 Verdict, in plain words

**As a standalone signal the RESET_TURN does not reproduce; as an entry-LOCATION instrument the zone does.** Two findings, and they point opposite ways.

1. **The fire adds nothing over being a leader.** Pooled precision 28.6% against a LEADER-state base rate of 25.7% on the same sessions (+2.9pp), and per-name-first 25.1% (-0.6pp) — the pooled margin is carried by names that fire repeatedly and does not survive one-event-per-name. Loser rate 33.6% vs 33.7% is flat, and the median forward path is within a quarter-point of zero at every horizon out to 20 sessions. Under the house epistemics this is a NULL on the standalone-ranking question — printed, not hidden — and it neither blocks this display-tier organ nor retires the factor: a null standalone signal is retained as a confluence input.

2. **The zone is the finding.** Median distance from a fire to the subsequent 20-session low is 7.26% taking the fire-day close, and 2.29% waiting at the zone floor — 4.97pp of entry location, on 889 fires, repeating in both halves. That is exactly the residual-lateness target of §6.9: a late SIGNAL stops implying a late PRICE when the plan waits at a structure-anchored band.

3. **All three operator case receipts MISS under the v0 constants** (§3). They are reported as misses; no constant was moved to capture them (`DNR:KILL-OUTCOME-AUDITION`). Each miss names a leg, and §3.1 measures the two shapes behind them across the whole universe rather than leaving them anecdotal.

## §1 What this lane is, and what it is not

The shipped US early-entry machinery is built around WASHOUT-IGNITION: a deep base, a cohort, and a turn from BELOW the 200dMA. The NVDA/AVGO/ADAM class never washes out. This organ is the ABOVE-200 complement — high-RS leaders taking a shallow controlled retrace, resetting the daily oscillator, and resuming. It is one member of the entry battery (§6.8d), not a replacement for any other lane, and it carries zero authority: it ranks nothing, gates nothing, sizes nothing, escalates nothing.

**Nothing is wired.** The organ is not imported by any board, ranker, plan builder or nightly job in this PR; no surface renders it and no ledger accrues from it. Wiring is a later change, and this receipt is what that change would have to argue with.

Window: **2024-08-05 → 2026-08-07** (504 sessions). Universe: **721 names** from `data/yahoo` with ≥ 260 bars (18 dropped short). Benchmark: SPY. Runtime 37.5s.

## §2 Headline

| set | n fires | names | graded (h10) | precision (≥+5pp) | loser (≤-3pp) | median entry-vs-20d-low | median zone-floor-vs-low |
|---|---|---|---|---|---|---|---|
| pooled (every RESET_TURN fire) | 933 | 407 | 913 | 28.6% | 33.6% | 7.26% | 2.29% |
| per-name-first (each name's first fire only) | 407 | 407 | 403 | 25.1% | 32.8% | 6.60% | 2.33% |

Right-censored (fired inside the last 20 sessions, no complete forward window — counted as fires, excluded from forward stats): **20**.

### Controls — the denominators

| control | n name-days | precision | loser | median excess (h10) |
|---|---|---|---|---|
| whole universe, same sessions | 354,182 | 20.4% | 30.2% | -0.19% |
| LEADER-qualified name-days (fire days removed), same sessions | 78,624 | 25.7% | 33.7% | -0.09% |

The LEADER-state row is the one that matters: it asks whether the RESET_TURN adds anything over simply being a high-RS leader on that session. Absolute precision on a current-universe store is survivorship-inflated; the DIFFERENCE against a control drawn from the same biased universe is not.

### Median forward path (excess vs SPY)

| horizon | h1 | h2 | h3 | h5 | h10 | h20 |
|---|---|---|---|---|---|---|
| pooled (every RESET_TURN fire) | -0.04% | +0.24% | -0.11% | +0.25% | +0.12% | +0.43% |
| per-name-first (each name's first fire only) | +0.01% | +0.18% | -0.12% | +0.32% | +0.06% | +0.03% |

## §2.1 Half-split (sign stability)

Boundary: 2025-08-07.

| half | n graded | precision | loser | median entry-vs-low | median zone-floor-vs-low |
|---|---|---|---|---|---|
| H1 | 383 | 25.9% | 35.2% | 6.84% | 2.55% |
| H2 | 530 | 30.6% | 32.5% | 7.59% | 1.99% |

Sign of (precision − LEADER-state base rate) stable across halves: **yes**.
Read it with the magnitudes, not just the sign: H1 is +0.2pp over the base rate and H2 is +4.9pp. A stable sign on a margin that small in one half is not an edge; it is a coin that landed the same way twice. The entry-location columns, by contrast, agree to within 0.75pp across the halves.

## §3 Case receipts

Constants were NOT tuned to make these fire (`DNR:KILL-OUTCOME-AUDITION`). Where a case does not fire on the operator's date, the failing legs are named.

### NVDA — operator receipt: Jul-29 reset -> Aug run

- source `data/yahoo` (adjusted); anchored VWAP available
- fired in window: **NO**
- on the operator's date 2026-07-29: state `NONE`, RS percentile 0.522 (gate ≥ 0.75)
  - failing ENTRY legs (gate a name into an episode): `rs_top_quartile, above_200dma`
  - failing FIRE legs (gate the RESET_TURN): `stoch_dipped_below_30, stoch_k_crossed_d, hist_rising_2_sessions`
- **Blocker**: never entered an episode in the window — the LEADER gate held on only 4/18 sessions (rs_top_quartile), so no qualifying pullback was ever opened

### AVGO — operator receipt: same window as NVDA

- source `data/yahoo` (adjusted); anchored VWAP available
- fired in window: **NO**
- on the operator's date 2026-07-29: state `PULLBACK`, RS percentile 0.728 (gate ≥ 0.75)
  - failing ENTRY legs (gate a name into an episode): `rs_top_quartile`
  - failing FIRE legs (gate the RESET_TURN): `stoch_k_crossed_d, hist_rising_2_sessions`
- **Blocker**: entered an episode but the turn legs never coincided inside it: %K crossed %D on no session inside the episode, the histogram was rising on no session inside the episode; episode closed 2026-07-30:recovered_without_reset — and the %K/%D cross printed on that very bar, one session outside the episode

### ADAM — operator receipt: Jul-27 reset (masterplan §6.8b)

- source `baskets_ohlcv` (adjusted); anchored VWAP **null** (no volume in that store)
- **Source deviation**: ADAM is absent from data/yahoo; resolved via the price_ladder rung 'baskets_ohlcv'. That rung is ADJUSTED, so its excess-vs-SPY legs share one adjustment basis. It is also outside the replay cross-section, so its RS percentile is computed against that same cross-section by reindexing — the name is scored against the universe, not added to it.
- fired in window: **NO**
- on the operator's date 2026-07-27: state `PULLBACK`, RS percentile 0.714 (gate ≥ 0.75)
  - failing ENTRY legs (gate a name into an episode): `rs_top_quartile`
  - failing FIRE legs (gate the RESET_TURN): `stoch_k_crossed_d`
- **Blocker**: entered an episode but the turn legs never coincided inside it: %K crossed %D on ['2026-07-24'], the histogram was rising on ['2026-07-27', '2026-07-28', '2026-07-29', '2026-07-30']; episode closed 2026-07-31:recovered_without_reset — and the histogram was rising on it, one session outside the episode

## §3.1 Episode anatomy — the two misses, measured at population scale

Three anecdotes carry nothing. These are the same two shapes counted across every episode in the window.

| quantity | n |
|---|---|
| episodes opened (a leader entered the retrace band above its 200dMA) | 5236 |
| of those, reached the oscillator reset (%K < 30 inside the episode) | 4165 |
| of those, contained a RESET_TURN | 940 |
| — first RESET_TURN day inside the window (the headline fire count) | 933 |
| **reset but never turned** (the population this lane loses) | 3225 |
| — %K crossed %D on the very bar the episode CLOSED (the AVGO shape) | 840 |
| — …and the histogram was rising on that bar too, so ordering alone would fire it | 242 |
| — %K cross and rising histogram both seen inside the episode, never on one bar (the ADAM shape) | 860 |
| — **union of the two shapes** (they overlap; do not add them) | 1623 |

Episode end reasons: `recovered_without_reset` 2539, `depth_exceeded_band` 1222, `anchor_high_reclaimed` 790, `pullback_stale` 235, `below_200dma` 209, `resumed_hold_expired` 163, `still_open_at_window_end` 78.

Read the middle rows together: of the 3225 episodes that reset and never turned, **1623 (50%)** were lost to WHERE the two turn legs landed rather than to the name failing to turn — against 933 fires in total. (That figure is the UNION of the two shapes, not their sum: an episode can be in both.) Two v0 mechanics produce it, and both are structural, not tuning:

- **The recovery exit is evaluated before the transition.** `recovered_without_reset` closes an episode the moment depth drops back under 5%, and that test runs BEFORE the RESET_TURN test on the same bar. A V-shaped two-day reset — dip on day one, cross on day two as price jumps back — therefore lands one session outside the episode. AVGO is exactly this: %K dipped to 26.3 on 07-29, crossed on 07-30, and the 07-30 bar closed the episode instead of firing on it.
- **AND-ing two daily turn legs is expensive.** The %K/%D cross and a 2-session rising histogram are near-simultaneous in principle and days apart in practice. ADAM crossed on 07-24 and had a rising histogram from 07-27 onward — the legs never shared a bar, so nothing fired inside a textbook shallow reset. AVGO fails this one too: its histogram only turned up on 07-31, the session after its cross.

Neither observation is a licence to loosen anything today. They are the reason §3.2 pre-registers the alternatives *before* they are measured.

## §3.2 Pre-registered v1 revision candidates (NOT applied here)

Named now so the next measurement is a comparison and not a rediscovery. None of these is applied in this artifact, and none may be adopted on the strength of the three case names — adoption goes through §6.6 (chartered horizon, n ≥ 50 per cell, sign-stable across half-splits, era-stamped episodes), with the v0 population kept as the comparison arm.

1. **Transition-before-exit ordering.** Evaluate the RESET_TURN test before the `recovered_without_reset` exit on the same bar. Pre-registered measurement: does the recovered population (242 episodes where both legs printed on the exit bar) grade better or worse than the v0 fires on the same window and horizon, and what does it do to entry-vs-low?
2. **Turn-leg window instead of coincidence.** Accept the %K cross and the rising histogram within N sessions of each other rather than on one bar, firing on the LATER of the two. Pre-registered: N ∈ {2, 3}, measured against the 860-episode population above, reporting both the added fires' grade AND the entry-vs-low cost of firing later — a later fire that grades the same is a WORSE instrument for this lane, since lateness is the thing being attacked.
3. **RS reflexivity — the gate reads leadership at the worst possible moment.** A leader's own pullback lowers its trailing 126-session return, so the leg that admits it closes precisely while it draws down. NVDA is the clean case: percentile 0.747 on 07-15, **0.522 at the 07-29 low**, back to 0.79–0.82 by 08-05 — above the gate only AFTER the move it was supposed to catch. It never entered an episode at all. (AVGO and ADAM did enter, and their percentiles also sagged under the gate mid-pullback — 0.728 and 0.649 respectively — which is the v0 design working: the LEADER legs are checked when an episode OPENS and not thereafter, precisely because requiring top-quartile RS throughout would make the lane self-defeating.) Pre-registered candidates: evaluate the LEADER legs at the episode's ANCHOR HIGH rather than on the current bar; or measure RS on the pullback-start date; or lengthen `rs_lookback` so a 4-week drawdown moves the rank less. All three are PIT-legal. None may be chosen by which one lights NVDA up — the selection rule is the §6.6 gate on the whole population, with the v0 arm reported beside it.

## §4 Definitions, limits, nulls

- **Close basis.** `data/yahoo` carries close and volume, no intraday high/low. Every high, low, drawdown and reset level is close-basis; an intraday restatement is a different measurement, not a refinement.
- **Entry.** fire-day CLOSE (EOD cadence: knowable at close T, actionable T+1 — this is the optimistic end). The zone floor column is what the zone machinery is trying to deliver; the entry column is what an EOD close-taker pays.
- **Forward low window.** min close over [T, T+20] inclusive of the fire day — a fire ON the low reads 0.00%.
- **Excess.** forward-10-session excess vs SPY >= 5pp; loser forward-10-session excess vs SPY <= -3pp. Both legs from `data/yahoo` — ADJUSTED (price_adjustment_audit §1) — name and benchmark legs share it.
- **Survivorship.** `data/yahoo` is a CURRENT-universe store; names that delisted inside the window are largely absent, so absolute forward statistics are biased upward. Nothing here corrects it. Read the control differences, not the levels.
- **Rank invariance.** The RS percentile ranks excess-vs-SPY, but subtracting a per-date constant cannot change a cross-sectional ordering — the SPY leg does no selection work in the LEADER gate. It is retained because the excess is what the lane reports. Stated so nobody reads the benchmark as a filter it is not.
- **The universe is the raw store, not a curated equity list.** data/yahoo is the raw price store, not a curated equity universe — FX crosses (`*_X`) and fund/ETF proxies sit beside single names. Filtering to an equity universe is a v1 candidate; here it is measured instead. Measured contamination: 16 FX-suffixed names in the universe produced 1 of 933 fires, and 6 fires came from names with no volume (so their resumption test used the zone top alone). Too small to move a headline; named because 'too small' is a measurement, not an assumption.
- **Thin cells.** Any cell with n < 20 is labelled *(thin)*.
- **Nulls printed.** 19 universe names carry no usable volume, so their anchored VWAP is null and the resumption test falls back to the zone top: AUDUSD_X, EURUSD_X, GBPUSD_X, IBIT, PMPEX, SIL, USDBRL_X, USDCAD_X, USDCHF_X, USDCLP_X, USDHKD_X, USDIDR_X, USDJPY_X, USDMXN_X, USDPLN_X, USDSEK_X, USDSGD_X, USDTRY_X, USDZAR_X.
- **v0 constants are revisable, not fitted.** They are named once at the top of `engine/us_leader_pullback.py`, stamped into every row via `construction_era`, and may only move through the §6.6 discipline (chartered horizon, n ≥ 50 per cell, sign-stable across half-splits, era-stamped episodes).

## §5 Constants (v0, printed)

| constant | value |
|---|---|
| `rs_lookback` | 126 |
| `rs_top_pct` | 0.75 |
| `high_52w_lookback` | 252 |
| `high_52w_recency` | 60 |
| `pullback_high_lookback` | 20 |
| `pullback_depth_min` | 0.05 |
| `pullback_depth_max` | 0.2 |
| `pullback_max_age` | 25 |
| `trend_ma` | 200 |
| `stoch_reset_max` | 30.0 |
| `hist_rise_sessions` | 2 |
| `zone_band_fraction` | 0.5 |
| `resumed_hold_sessions` | 20 |
| `min_history_bars` | 260 |
| `construction_era` | leader-pullback-v0-2026-08-08 |
| `price_basis` | close-only (no intraday high/low in the US research stores) |
| `avwap_form` | sum(close*volume)/sum(volume) from the pullback anchor high |

