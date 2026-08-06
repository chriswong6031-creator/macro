# CN Prophet — rank-feature battery + S-COIL port test (frozen, 2026-08-04)

Instrument: `rank_feature_battery.py`. Frozen numbers: `rank_feature_battery_results.json`.
Frame: the same 407 matured `cn_standout_v1` (legacy) episodes `v1_loser_audit.py`
grades, rebuilt through the same production code paths and the same `GRADE_ASOF`
pin (imported from that module, not re-implemented). **These are MEASUREMENTS, in
sample, on one era. Nothing here is promoted, ranked, gated, or sized.**

---

## DECISION SUMMARY

1. **Top-5 stable ordering features** (date-demeaned Spearman IC on `excess_h10`;
   all sign-agree across both era halves, all 12/12 dates, all p<0.05 nominal):
   `trail_21` **−0.212**, `in_basket` **+0.196**, `vs_ma200` **−0.194**,
   `trail_63` **−0.181**, `setup` **−0.157**. Direction: less recent thrust, more
   theme membership, further below the long MA ranks better.
2. **These five are not five axes.** The collinearity matrix collapses the 31
   graded features to ~5: thrust (`trail_5/21`, `vs_ma20/50`, `setup`, ρ .48–.76),
   long-horizon position (`trail_63`/`vs_ma200`/`dd_from_high`, ρ .66–.83),
   crowding (`turnover_pctile_60d`/`vol_surge`, ρ .87), range width (ρ .87), theme.
3. **`in_basket` is the only stable non-price axis** and the only one the pick
   chain does not already contain — the board is otherwise re-ranking its own
   thrust with the sign inverted (`setup` IC −0.157: it orders backwards).
4. **Compression adds ordering information, with the sign REVERSED vs the US
   thesis.** Wider is better, quieter is worse: `donch_width_pctile_252` +0.142
   (halves +0.135/+0.150), `bbw20_pctile_252` +0.105, `sq_on` −0.070, `sq_duration`
   −0.057. Effects are small and only the Donchian encoding clears p<0.05.
5. **It is genuinely NEW information vs the board's `coiled` flags** — but only
   because those flags are not compression at all. `coiled` is a cohort-washout
   composite (`engine/coiled.py`: weekly-D washout + cohort fraction + bull
   divergence). Every compression × coiled correlation is |ρ| ≤ 0.11 (`sq_on` vs
   `coiled_i` **+0.068**). They are near-orthogonal AND point opposite ways
   (`coiled_i` IC +0.178, strongest on `mfe_21` +0.263 and `clean_liftoff` +0.202).
6. **S-COIL does NOT port to China. Verdict: NO-GO on both arms.** vs gate-matched
   breakouts, BB/KC arm H10 **−1.9pp** / H21 +1.3pp / H63 −1.1pp (every Wilson CI
   overlaps; month-block **3 of 12 months positive**). ATR-percentile arm (the
   literal US mirror) H10 **−9.0pp** / H21 −5.5pp / H63 −6.9pp, CIs disjoint —
   but 85% of its events sit in one month, so read it as one time block, not 637 bets.
7. **The washout-context variant is the strongest NO.** A squeeze release inside a
   washout is *worse* than a plain washout reclaim: 30.7% vs 38.5% win at H10
   (**−7.8pp**), −5.5pp at H63. CN's habitat is where the port fails hardest.
8. **The state does not exist in the admitted pool.** S-COIL fired 0/407 episodes.
   Per-leg proof it is a real zero, not a dead detector: close>50dMA 116/407,
   50dMA rising 53/407, ATR pctile<p25 14/407, all three **0**.
9. **Recommended for the next score iteration** (recommendations only, no
   authority): invert or remove the `setup` thrust leg; add `in_basket` as the one
   new leg; cap rather than reward short-horizon thrust; do **not** add a
   compression leg. Preregister before any of it.

---

## What this is not

- **Not a pre-onset winner claim.** DNR rows 114–115 (W3 fingerprint census, W4
  matched controls) established that *"nothing measurable today identifies the
  future winner pre-onset."* This battery orders a pool the board has **already
  admitted**. It says nothing about the universe and may not be cited as if it did.
- **Not promotion evidence.** In-sample, one era, 12 admission dates, no
  multiplicity correction, no out-of-sample split. Motivates preregs only.
- **Not a surfaced state.** See fence compliance below.

## Fence compliance

**DNR #1747 / Entry-stack Amendment-3 — washout DEPTH ranking is KILLED.** The
adjudication reads: *"Multi-TF stoch washout DEPTH behind a fire = H1 FAIL (+3.5pp
stop tax; `w2_deep ≈ 0 alone`)"*, and the registry row is `Washout × turn (2W
operator seed) | KILLED — operator seed dies in test`. Depth features were tested
here for completeness and **this document flags a live collision**: `vs_ma200`
(ladder #3, IC −0.194) correlates with `dd_from_high` at **ρ = 0.83**. It is
largely drawdown depth in another coordinate system. The direct depth encodings
are null on this frame anyway (`dd_from_high` −0.070, p .24; `washout_2w` −0.031,
p .66), so nothing here argues the kill was wrong. **The `vs_ma200` read is NOT a
revival of depth ranking.** It is a differently-constructed feature on a different
market, and it can re-enter only inside a composite with a fresh pre-registration
that names the collision explicitly. A standalone depth ranker remains killed.

**ESX §9 / DT-R5 — the "arming" variant is BANNED.** ESX §9 risk row: *"Squeeze
study quietly re-derives H2 → Release-bar-only definition frozen pre-run; an
'arming' variant is BANNED from the family."* DT-R5: the void-box family is killed
because *"the 'inside/armed' state is the BANNED arming variant (ESX §9)"*.

*Part B is compliant by construction*: it grades the **release bar only** (`first
close above the prior 21d high with the compression run read at t−1`), exactly the
US instrument's frozen definition. No armed-state cohort is graded or reported.

*Part A is a different construction, and here is why.* The banned thing is a
**standalone anticipatory read surfaced to a user or ranked as a signal**: "this
name is coiled, therefore act". Part A's `sq_on` / `sq_duration` / width
percentiles are (a) computed only over a pool the board's own detector cascade has
already admitted — they never select a name into anything, (b) evaluated as
ordering *inputs* against outcomes, never emitted, (c) attached to no surface, no
chip, no score, and no ledger. The distinction ESX §9 protects is *confirmation vs
anticipation as a firing rule*; nothing here fires. **That said, the compliant path
narrows further on the result**: the sign is negative (quiet ranks *worse*), so
even the non-banned use — an internal ordering leg — has no case here, and the
recommendation below is not to build one. If a future wave wants compression as a
ranking leg it needs a prereg that re-states this fence and shows the leg is not
an arming read in disguise.

## P0 reproduction (trust gate, asserted before any new number prints)

`584 episodes · 407 matured · win 68.55% · 128 losers · 1 locked-limit excluded`,
every price series truncated at `GRADE_ASOF = 2026-08-03` first. All four values
are hard asserts. Part B shares the same truncation, so the whole instrument is
one frozen replay — verified byte-identical across two consecutive runs.
Runtime **25s** end to end.

---

# PART A — within-pool ordering battery

## Method

Per episode, at admission, trailing-only: 31 continuous + 8 categorical features
(board-row fields, price character via the audit's own `admission_character`,
the compression family via `engine/compression_signals.py` + `stock_technicals`,
theme/cycle joins mirroring `sector_intel_exante_test.py`, and
`turnover_pctile_60d` mirrored from `flow_exante_battery.py`).

Outcomes: `excess_h10` (recomputed via `score_from_fill`), `fwd_mfe_10`,
`fwd_mfe_21`, `mae_10` + `day_of_max` (computed from prices via the audit's
`forward_path`), `catastrophic` (abs pnl ≤ −15%), `clean_liftoff`
(`terminal_state_clean8_21`).

Every IC is reported **pooled** and **date-demeaned** (mean of per-admission-date
Spearman ICs, ≥8 pairs per date — the same idiom as the audit's `board_rank_ic`).
**Every verdict below quotes the date-demeaned number**, which is the honest
within-pool basis: it asks "did this feature order the names admitted on the same
night", not "did it also pick the good night".

### Outcome coverage — one metric is unusable

| Metric | n | status |
|---|---|---|
| `excess_h10`, `mfe_10`, `mae_10`, `catastrophic` | 407 | graded |
| `mfe_21`, `clean_liftoff` | 150 | graded (thin) |
| `mfe_63` | **0** | **UNUSABLE — the column is empty for every legacy row** |

`terminal_state_clean15_126` is likewise all-null and not graded. The board frame
simply has not matured that far. Printed rather than quietly dropped.

## The ordering ladder (date-demeaned IC on `excess_h10`)

| # | feature | family | IC | p | pooled | h1 / h2 | sign agrees |
|---|---|---|---|---|---|---|---|
| 1 | `trail_21` | char | **−0.212** | .007 | −0.218 | −0.183 / −0.242 | yes |
| 2 | `in_basket` | theme | **+0.196** | .011 | +0.216 | +0.161 / +0.232 | yes |
| 3 | `vs_ma200` | char | **−0.194** | .006 | −0.189 | −0.230 / −0.158 | yes |
| 4 | `trail_63` | char | **−0.181** | .003 | −0.176 | −0.161 / −0.201 | yes |
| 5 | `coiled_i` | row | +0.178 | .051 | +0.146 | +0.028 / +0.278 | yes (weak h1) |
| 6 | `setup` | row | **−0.157** | .008 | −0.172 | −0.233 / −0.081 | yes |
| 7 | `vs_ma20` | char | −0.151 | .050 | −0.169 | −0.164 / −0.139 | yes |
| 8 | `turnover_pctile_60d` | char | −0.149 | .053 | −0.126 | +0.008 / **−0.305** | **NO** |
| 9 | `vol_surge` | char | −0.144 | .085 | −0.130 | +0.013 / **−0.301** | **NO** |
| 10 | `donch_width_pctile_252` | compression | +0.142 | .047 | +0.126 | +0.135 / +0.150 | yes |
| 11 | `trail_5` | char | −0.130 | .048 | −0.159 | −0.171 / −0.090 | yes |
| 13 | `vs_ma50` | char | −0.116 | .012 | −0.132 | −0.098 / −0.133 | yes |
| 14 | `bbw20_pctile_252` | compression | +0.105 | .108 | +0.108 | +0.118 / +0.092 | yes |
| 18 | `nr7_last3` | compression | +0.096 | .075 | +0.086 | +0.091 / +0.101 | yes |
| 19 | `board_rank` | row | +0.073 | .326 | +0.070 | +0.242 / −0.096 | **NO** |
| 21 | `sq_on` | compression | −0.070 | .172 | −0.049 | −0.040 / −0.101 | yes |
| 22 | `dd_from_high` | char | −0.070 | .241 | −0.019 | −0.034 / −0.106 | yes |
| 27 | `washout_2w` | row | −0.031 | .662 | −0.057 | −0.068 / −0.019 | yes |
| 29 | `coiled_fire_i` | row | +0.006 | .905 | −0.028 | −0.060 / +0.050 | **NO** |

**Not rankable, disclosed rather than dropped:** `scoil_state` and `scoil_run_21`
(no variation — see below), `basket_rs_rank` (3 of 12 dates), `extended_i`
(5 of 12 dates; the extension flag fires on 2.2% of the pool).

The rankability gate (≥6 of 12 dates) matters: on the first pass `scoil_run_21`
sorted **4th** on an IC estimated from a single date with one non-zero value. A
feature that varies on one night produces the sparsest possible number wearing
the ladder's strongest possible position.

### Reading the ladder as axes, not as 31 findings

| Axis | members (ρ within axis) | sign | stable |
|---|---|---|---|
| A. Short-horizon thrust | `trail_5`/`trail_21`/`vs_ma20`/`vs_ma50`/`setup` (.48–.76) | **negative** | yes |
| B. Long-horizon position / depth | `trail_63`/`vs_ma200`/`dd_from_high` (.66–.83) | negative | yes, **but see the depth fence** |
| C. Crowding | `turnover_pctile_60d`/`vol_surge` (.87) | negative | **no** (sign flips across halves) |
| D. Range width | `donch_width`/`bbw` (.87), `sq_on` (−.46/−.63) | **wider = better** | yes, small |
| E. Theme membership | `in_basket` | **positive** | yes |

Axis A is the audit's chase fingerprint reappearing as a continuous ranker, and it
is the same axis `setup` is built on — which is why `setup`'s IC is negative. The
board's own rank driver orders the pool backwards. Axis C is the flow battery's
crowding separator; on this frame it is an artifact of the second half only
(h1 +0.008, h2 −0.305) and should not be carried forward on this evidence.

## Cross-metric consistency (date-demeaned IC)

| feature | excess_h10 | mfe_10 | mfe_21 | mae_10 | catastrophic | clean_liftoff |
|---|---|---|---|---|---|---|
| `trail_21` | −0.212 | −0.083 | −0.098 | −0.182 | **+0.256** | −0.040 |
| `in_basket` | +0.196 | +0.220 | +0.130 | +0.198 | −0.084 | +0.156 |
| `vs_ma200` | −0.194 | −0.123 | −0.126 | −0.136 | **+0.291** | −0.113 |
| `trail_63` | −0.181 | −0.130 | −0.188 | −0.127 | +0.193 | −0.125 |
| `coiled_i` | +0.178 | +0.084 | **+0.263** | +0.151 | −0.180 | **+0.202** |
| `setup` | −0.157 | −0.026 | −0.124 | −0.170 | +0.195 | −0.090 |
| `donch_width_pctile_252` | +0.142 | +0.081 | +0.110 | +0.177 | −0.105 | +0.087 |
| `rvol20_pctile_252` | −0.050 | −0.068 | **−0.221** | −0.036 | +0.023 | −0.113 |
| `sq_on` | −0.070 | −0.044 | −0.108 | −0.025 | +0.057 | −0.034 |

The signs are coherent across six independently-constructed outcomes, which is the
one thing that argues against pure noise: thrust features are positive on
`catastrophic` (more thrust → more −15% outcomes) and negative on everything else;
`in_basket` and `coiled_i` are the mirror image. `catastrophic` carries the largest
magnitudes — the axes separate disasters better than they separate winners.

## Winners-only magnitude ordering (n=279 with excess>0)

The operator's "what ranks the +50s above the +5s" question. Answer: **almost
nothing does.** Date-demeaned ICs among winners collapse toward zero —
`nr7_last3` +0.111, `vs_ma200` −0.107, `in_basket` +0.101, `dd_from_high` −0.099,
`turnover_pctile_60d` −0.080, `coiled_i` +0.069, `trail_21` −0.053. The ladder's
top axis loses three-quarters of its strength (−0.212 → −0.053). **These features
separate winners from losers; they do not order winners by size.** Any score built
on them should be read as a loss-avoidance ranker, not a magnitude ranker.

## Categorical cuts (median excess; within-date percentile = 0.50 means "performed
like the pool admitted that same night")

| feature | bucket | n | median excess | within-date pctile |
|---|---|---|---|---|
| `entry_status` | wait_pullback | 13 | +6.90 | 0.607 (thin) |
| | bounce_wait | 58 | +6.26 | **0.537** |
| | extended | 94 | +4.95 | 0.508 |
| | partial | 29 | +2.97 | 0.474 |
| | hold | 31 | +4.74 | 0.442 |
| | **buy_now** | 10 | +5.72 | **0.304** (thin) |
| `stage` | RAN_LATE | 24 | +6.02 | **0.656** |
| | ENTRY | 233 | +5.09 | 0.500 |
| `species_id` | cn_coiled | 107 | +6.43 | 0.548 |
| | cn_washout | 26 | +4.75 | 0.484 |
| | cn_tier | 13 | +1.60 | 0.214 (thin) |
| `phase_slope` | Recovery+ | 7 | +9.03 | 0.727 (thin) |
| | **Trough+** | 28 | +8.32 | **0.707** |
| | Trough− | 37 | +5.91 | 0.429 |
| | Downturn− | 4 | −7.53 | 0.155 (thin) |
| `ab_tier` | B | 198 | +5.50 | 0.538 |
| | A | 35 | +1.79 | 0.467 |
| `chop_regime` | trend | 19 | +4.35 | 0.533 |
| | range | 48 | +5.27 | 0.491 |

The demeaned view **confirms** three prior audit findings on a stricter basis —
the entry-status inversion, `RAN_LATE` beating `ENTRY`, `ab_tier` A inverting —
and adds `Trough+` (0.707) vs `Trough−` (0.429): among basket members, the
osc-slope sign is the separator, not membership alone. `narr_level` HOT 0.592 vs
WARMING 0.500 (n=38/25) does **not** reproduce the audit's HOT-is-worse result on
the within-date basis; the audit's version is a pooled loser-rate comparison and
the two are measuring different things. Flagged, not resolved.

## Compression vs the board's existing `coiled` flags (Spearman ρ)

| | `coiled_i` | `coiled_star_i` | `coiled_fire_i` | `ticks` | `setup` |
|---|---|---|---|---|---|
| `sq_on` | +0.068 | −0.018 | −0.096 | −0.018 | +0.047 |
| `sq_duration` | +0.065 | −0.027 | −0.107 | −0.015 | +0.054 |
| `bbw20_pctile_252` | −0.101 | −0.003 | +0.077 | +0.104 | −0.121 |
| `rvol20_pctile_252` | **−0.200** | +0.008 | +0.040 | +0.023 | +0.038 |
| `donch_width_pctile_252` | −0.083 | −0.033 | +0.033 | +0.132 | −0.190 |
| `nr7_last3` | +0.033 | +0.027 | +0.032 | −0.119 | −0.065 |

**Answer to "does compression add information beyond the coiled flags": yes,
because they are not the same measurement.** Despite the name, `coiled` is a
cohort-washout composite (weekly-D washout + cohort fraction + bull divergence,
`engine/coiled.py`), not a volatility state. Maximum |ρ| against any compression
column is 0.20. The two are near-orthogonal *and* opposite in sign: `coiled_i`
+0.178 (and its best reads are on `mfe_21` +0.263 / `clean_liftoff` +0.202) while
the compression family says quiet is worse. **The information is additive but
points away from the coiled-thrust thesis, not toward it.**

## Multiplicity honesty

186 continuous feature × metric IC tests (31 graded features × 6 usable metrics),
plus 8 categorical features. **At α=0.05, ~9 nominal hits are expected under the
global null.** Observed nominal hits on the demeaned ICs: **34**. That is ~3.7×
chance — but the tests are *not independent*: the features collapse to ~5 axes, so
34 correlated hits over ~5 axes is a much weaker statement than 34 over 34.

No correction is applied and none is claimed. **Only axes that are (a) sign-stable
across both era halves, (b) mechanism-backed, and (c) survive a fresh prereg on
out-of-era data may graduate to the score ladder.** By that standard exactly one
feature here is *new* and clean: `in_basket`. Everything else is either the audit's
already-known chase fingerprint in continuous form, an axis the depth kill fences,
or unstable across halves.

---

# PART B — S-COIL CN retro (12 months)

## Method

Universe **1,643** `data/china_stocks` names with ≥200 bars in
[2023-06-01, 2026-08-03]; events 2025-08-01 → 2026-07-31; benchmark 510300.SS;
T+1 (H+L)/2 fills with locked-limit bars excluded (11 events on ARM 1, 1 on
ARM 2 — the arms fire on different bars); excess computed
as a vectorised mirror of `score_from_fill(include_fill_bar=True)`.

Two arms, both reported, **neither selected on its result**:

- **ARM 1 `bbkc` (primary, the brief's construction):** BB/KC squeeze via the
  market-agnostic `ttm_squeeze`, ≥10 compressed sessions in the trailing 21, run
  read at t−1, release = first close above the prior 21d high, uptrend qualifier
  (close > 50dMA ∧ 50dMA rising over 10) at the release bar.
- **ARM 2 `atr_pctile` (literal US mirror):** compression = ATR21 percentile of own
  252 < 0.25 ∧ above a rising 50dMA — verbatim `ignition_standins.coil_compression`
  constants (ATR_WIN 21, PCT_WIN 252, PCT_MAX 0.25, MA_WIN 50, MA_SLOPE 10,
  BREAK_WIN 21, COMP_LOOKBACK 21, COMP_MIN 10).

Controls: **(a) gate-matched** — same uptrend, same first breakout, no compression
run; **(b) all-days** — every fillable name-day in the window.

## Fire counts (name-days over the full panel; per-leg, so a zero is provable)

| leg | `bbkc` | `atr_pctile` |
|---|---|---|
| compressed | 289,369 | 25,572 |
| compression run ≥10/21 | 250,189 | 20,520 |
| uptrend | 428,426 | 428,426 |
| first breakout | 40,992 | 40,992 |
| **events** (in window) | **1,887** | **638** |
| gate-matched controls (in window) | 8,932 | 10,181 |
| locked-limit excluded | 11 | 1 |

## Results — event vs gate-matched control (all-context)

| arm | H | event n / win | control n / win | Δ win | Δ median | CIs overlap |
|---|---|---|---|---|---|---|
| `bbkc` | 10 | 1,869 / 43.5% [41.3, 45.8] | 8,799 / 45.4% [44.3, 46.4] | **−1.9pp** | −0.28 | yes |
| `bbkc` | 21 | 1,857 / 45.3% [43.1, 47.6] | 8,706 / 44.0% [43.0, 45.1] | +1.3pp | +0.49 | yes |
| `bbkc` | 63 | 1,731 / 42.5% [40.2, 44.8] | 7,009 / 43.6% [42.4, 44.8] | −1.1pp | −0.01 | yes |
| `atr_pctile` | 10 | 637 / 36.6% [32.9, 40.4] | 10,031 / 45.6% [44.6, 46.6] | **−9.0pp** | −1.36 | **no** |
| `atr_pctile` | 21 | 637 / 39.1% [35.4, 42.9] | 9,926 / 44.6% [43.6, 45.6] | −5.5pp | −0.96 | **no** |
| `atr_pctile` | 63 | 635 / 37.0% [33.3, 40.8] | 8,105 / 43.9% [42.8, 45.0] | −6.9pp | −1.85 | **no** |

All-days baseline: 43.7% / 42.2% / 41.7% win at H10 / H21 / H63.

## Results — washout context (dd ≤ −20% at the event bar; CN's habitat)

| arm | H | squeeze release in washout | plain washout reclaim | Δ win |
|---|---|---|---|---|
| `bbkc` | 10 | 199 / **30.7%** | 356 / 38.5% | **−7.8pp** |
| `bbkc` | 21 | 196 / 32.1% | 347 / 34.3% | −2.2pp |
| `bbkc` | 63 | 193 / 27.5% | 297 / 33.0% | −5.5pp |
| `atr_pctile` | 10 | 145 / 34.5% | 410 / 36.1% | −1.6pp |
| `atr_pctile` | 21 | 145 / 38.6% | 398 / 31.7% | +7.0pp (CIs overlap) |
| `atr_pctile` | 63 | 145 / 39.3% | 345 / 27.3% | +12.1pp (CIs overlap) |

The `atr_pctile` washout positives at H21/H63 are **not a finding**: n=145, Wilson
CIs overlap the control at every horizon, and 85% of that arm's events sit in a
single month. The primary arm says the opposite at every horizon.

## Dependence check — the pooled CIs are too narrow, so here is a time-block view

Wilson intervals above treat every name-day as an independent bet. A-share
name-days are strongly cross-correlated and the H21/H63 windows overlap, so the
true intervals are several times wider — most severely for the all-days baseline
(n≈381k name-days is nothing like 381k independent observations). Month-block
sign count on the H10 event-minus-control win delta:

| arm | months graded | event beats control | event loses | largest single month's share of events |
|---|---|---|---|---|
| `bbkc` | 12 | **3** | 9 | 29.7% |
| `atr_pctile` | 3 | **0** | 3 | **84.9%** |

`bbkc` is well distributed and loses in 9 of 12 months — that is the credible
verdict. `atr_pctile` compression in the A-share tape is episodic (market-wide vol
compresses in bursts), so its n=637 is one or two time blocks; its disjoint CIs
should not be read as a strong kill, only as a consistent one.

## Why the port fails — mechanism, and it agrees with Part A

The construction requires an **uptrend** (above a rising 50dMA). The CN board
admits **washouts**. On the 407 admitted episodes the S-COIL state fired **0
times**, and the per-leg decomposition proves it is a real zero rather than a dead
detector: close>50dMA 116/407, 50dMA rising 53/407, ATR pctile<p25 14/407,
conjunction 0/407. The US coiled-thrust family lives in a continuation regime this
board structurally does not enter. Part A says the same thing from the other
direction: inside the admitted pool, quiet ranks *worse* and wide ranks *better* —
a reversal-in-progress reads better than a coiled base. The two parts are one
finding.

---

## Deviations from the brief (all deliberate, all disclosed)

1. **Two Part-B arms, not one.** The brief describes S-COIL as "uptrend BB/KC
   squeeze"; the US implementation uses an ATR-percentile compression leg. Both are
   run and both reported so neither reading is selected after the fact.
2. **Gate-matched controls also carry the uptrend qualifier**, which the US
   instrument's controls do not. Tighter, and it makes "same uptrend + breakout,
   no compression" literally true as the brief specifies.
3. **Uniform T+1 HL2 fills in Part B.** Production `_t1_fill` prefers a true T+1
   open, but the `open` column only backfills from 2026-06 (≈18% coverage before,
   ~100% after) — using it would put a fill-basis break in the middle of the halves
   split. Part A keeps the production fill (open-preferred) because it must
   reproduce the shipped ledger, and its era is fully open-covered.
4. **Panel warm-up floor pushed to 2023-06-01.** At the natural 2024-06-01 floor
   the ATR percentile first becomes valid 2025-07-15 — two weeks before the event
   window — and the arm's fires piled up on that boundary (82% in one month).
   Corrected before the verdict was read.
5. **`mfe_63` and `terminal_state_clean15_126` are not graded** — both columns are
   empty for every legacy row.
6. **Rankability gate (≥6 of 12 dates)** added after `scoil_run_21` sorted 4th off
   a single date.

## Recommendations for the next score iteration (recommendations only, no authority)

- **Fix the sign before adding anything.** `setup` orders the admitted pool
  backwards (IC −0.157, both halves). Inverting or removing that leg is a larger
  move than any new leg on this evidence.
- **One new leg is justified: `in_basket`** (+0.196, both halves, positive on five
  of six outcomes). It is the only stable axis that is not price-derived and not
  already inside the pick chain. Condition it on osc-slope sign — `Trough+` 0.707
  vs `Trough−` 0.429 within-date percentile — rather than on membership alone.
  Coverage is 84/407 (21%), so it needs a defined behaviour for the uncovered 79%.
- **Cap, do not reward, short-horizon thrust.** The audit already priced blanket
  vetoes as winner-destructive; a rank *cap* on axis A is the form that does not
  amputate the right tail.
- **Do not add a compression leg.** The effect is small, the sign is opposite to
  the thesis that motivated it, and the ESX §9 fence narrows the compliant uses.
- **Do not build a magnitude ranker on these features.** Winners-only ICs collapse
  to ≤0.11; this is loss-avoidance information, not right-tail information.
- **Nothing above ships without a prereg.** One era, 12 admission dates, 186
  correlated tests, no out-of-sample split. Pre-register the legs, the caps, and
  the falsifiers, then accrue forward.
