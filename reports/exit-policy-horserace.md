# Exit-policy horse race — US buy-lane episodes

**Study date:** 2026-08-06T20:15Z · **Script:** `scripts/exit_policy_study.py` · **Charter:** `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §0 G3/G4, §1

**Input state:** prices to 2026-08-05 · boards 2026-06-30 → 2026-07-31 (17) · inputs `359b334c2edb`

**Tier: measurement / display. Nothing here promotes anything.** The public track record keeps the incumbent rule. Every verdict below is descriptive — what this sample shows, on this cohort, at this size. A policy that eventually replaces the incumbent has to be pre-registered first; see *Promotion path* at the end.

---

## What was measured

One question: **on identical entries, what does a holder-with-rules capture?** The Track-record ledger answers a different one (is the SIGNAL any good?) and has to stay policy-free to answer it, so this is a separate study reading the same episodes — the ledger, the board and every weight are untouched.

* **Cohort** — buy-lane episodes on boards from **2026-06-25** onward (the board-definition cut; earlier boards published a 120-name broad screen and are a different instrument). One episode = one contiguous board run. Entry = the **next session's close** after the board date, identical for every policy — the board is computed from that close and published that evening, so the signal bar is unbuyable.
* **Boards** — 17 board days, 2026-06-30 → 2026-07-31. Prices run to **2026-08-05**.
* **Episodes** — **257 episodes across 11 board days.** Forward bars available per episode: 10 min / 17 median / 24 max.
* **Benchmark** — SPY total return over each episode's own fill→exit window.
* **Provenance** — board membership is `snapshots.jsonl` UNION the buy-lane rows of `retro_grades.parquet`. In this run the snapshot store already covered the whole post-cut era: retro contributed 0 extra board days and 0 extra tickers. The union is kept anyway so a future gap in the forward store heals from git archaeology instead of silently shrinking the cohort.

`n_board_days` is the number that matters. Episodes surfaced on the same night share the tape, the regime read and the ranker's state — they are one bet, not N. **11 board days is the effective sample here**, not 257.

### The 11 blocks are not 11 independent bets

Resampling whole board days fixes the dependence WITHIN a night. It does nothing about the dependence BETWEEN nights — and here that is the bigger problem. A board day's window is simply the next 10 sessions, so two board days a session apart hold the same tape minus one bar. Measured on this cohort:

* Neighbouring board days share a median **90%** of their 10 forward sessions (min 70%, max 90%); 10 of the 10 neighbour pairs share more than half.
* The 11 windows span 110 bar-slots but only **24 distinct sessions** of tape.
* At most **2 of the 11 board days** have windows that share no session with each other.

So the block bootstrap draws 11 blocks that are mostly the same fortnight priced 11 times. **The effective sample is materially smaller than 11**, every interval in this report is narrower than the evidence supports, and a bolded "excludes 0" below should be read as "excludes 0 under a method that assumes more independence than this record has". No correction is applied: a correction needs a covariance model 11 blocks cannot support, so the overlap is printed instead of estimated away. This is the masterplan's G3 caveat, and it is the reason nothing here moves to promotion on an interval alone.

### Coverage and exclusions (nothing dropped silently)

| Excluded because | Episodes |
|---|---:|
| no close series in the breadth caches (delisted / not in S&P 1500) | 12 |
| close column present but all-null | 0 |
| next-session fill has not printed yet | 0 |
| fill price non-finite or ≤ 0 | 0 |
| fewer than 10 forward bars (in flight) | 185 |
| no high/low path, or ATR14 not computable at the fill bar | 0 |
| **kept — the horse-race cohort** | **257** |
| *total episodes built from the 17 boards* | *454* |

No-price names (10 distinct tickers, 12 episodes): `ASTS`, `BIDU`, `CRDO`, `NET`, `NVO`, `NXE`, `TEAM`, `U`, `UROY`, `VALE`.

Exclusions are by **data coverage** and by **age** only. Neither can know which way a trade went, so both are symmetric — unlike an exclusion keyed on outcome, which would delete the losers.

### The censoring caveat — read before the table

The record starts 2026-06-30 and prices end 2026-08-05. Of the 257 episodes, **257 have at least 10 forward bars** (11 board days), **94 have at least 21** (4 board days), and **0 have at least 63**.

So the 21- and 63-bar caps mostly cannot be reached. A position still open when the data ends is **marked at the last available close and flagged `data_end`** — it is not dropped, because dropping it would delete precisely the trades that were still running, and a denominator conditioned on how a trade ended is the single artefact `engine/track_scoring.py` exists to forbid. Every policy row prints its `data_end` count. **A `data_end` row is a mark, not a realised exit, and its hold length is a lower bound.** Read the cap-63 rows as *what these rules were still holding on 2026-08-05*, not as *what these rules returned*.

**And the marks are not spread across the sample: every one of them lands on the same session, `2026-08-05`** — all 707 of them, counting each policy's rows separately. One day's tape prices every unresolved position in this report. How much that one day is carrying is measured under *Does anything separate from the incumbent?*.

## Method — the conventions that decide the numbers

Each of these is a CHOICE. A reader should see them, not infer them from a table that looks self-explanatory.

**One excursion window for every row (changed 2026-08-03).** `MFE`, `MAE` and `capture` are measured over the policy's **own held window** — the bars it actually held, `fwd[:exit_bar]` — for every policy INCLUDING P0. They previously came, for P0 only, from `track_scoring.score_from_fill`, which measures the full 10-bar forced-verdict window even when the incumbent's target leg exited on bar 3; the headline table then mixed two definitions in one column. Only those three columns moved: P0's P&L legs (`pnl`, `excess`, `held`, `exit`, `exit_reason`) still come straight from the grader, which is why the calibration comparison below is untouched by the change. **The cost of the fix:** the P0 row's `capture`/`MFE`/`MAE` are no longer the shipped ledger's numbers — the ledger keeps the full-horizon window. The Calibration table, not the horse race, is the ledger-comparable surface.

**Read `capture` as "how much of the best close it saw while holding did it keep"** — not as a share of the move the name eventually made. A rule that exits ON strength scores near 1.00 almost by construction, because its window ends at its own exit; that is a property of the measure, not an edge. `capture` is also **undefined where MFE ≤ 0** (the position never traded above entry inside the window): realised/MFE there is a ratio of two negatives that prints as a healthy positive, so those rows are dropped from the median and counted instead — P0 40, P0f 21, P1 13, P2 k=2 23, P2 k=3 16, P3 18, P4 16 of 257 rows.

**Every stop here is close-only, and that is not free.** No walker looks at an intraday low: a stop fires when the SESSION'S CLOSE is through the level, and the fill is that close. A real stop order triggers intraday and fills near the level. Measured on this study's own rows — the 1285 rows of the 5 stop-carrying policies (P0, P2 k=2, P2 k=3, P3, P4):

* **419** of those rows exited on a stop under the close-only rule. Their fills landed a mean **2.02%** of entry BELOW the level that triggered them (median 0.97%, p90 4.79%, worst 35.42%). That slip is a cost this study charges every stop-carrying policy and does not charge the fixed-horizon ones.
* **158 of the 419 stop exits (37.7%)** had a session LOW through the resting stop on an EARLIER bar — a true intraday stop would have exited them sooner, and at a different price.
* A further **137 rows (10.7% of the 1285)** never stopped on a close at all but did trade through the level intraday. The close-only rule kept those positions; a real stop would not have.

Together, **295 of 1285 stop-carrying rows (23.0%) would have resolved differently under a true intraday stop.** The counterfactual tests each session's low against the stop that was RESTING before that session opened, never against a band the session's own close raised — the reverse would manufacture breaks on up-then-down days. It is a diagnostic only: it never changes an exit, a P&L or an interval anywhere in this report.

**The rest of the pinned conventions** — ATR14 fixed at the fill bar, the running-max trailing anchor, stop-before-target on a same-bar tie, and which comparisons are strict (`<` on the synthetic ATR bands) versus inclusive (`<=`/`>=` on the desk's published levels) — are documented at the top of `scripts/exit_policy_study.py` and pinned in both directions by `tests/test_exit_policy_study.py`.

## Calibration — does P0 reproduce the shipped ledger?

P0 is the incumbent rule executed through `engine.track_scoring` itself, on the ledger's own cohort (close path only, no ATR requirement). **The input files have moved since this ledger was generated** (ledger vintage: 2026-08-04 · this render: prices to 2026-08-05): the daily-collection lane advances the panel independently of the regime-update lane that regenerates the ledger, so the deltas below measure the tape's advance — episodes that matured after the ledger was written, plus in-place total-return re-adjustments to shared history — not reconstruction drift. Exactness is defined only at matched inputs; the next regime-update run regenerates the ledger against the current panel and re-renders this report at one vintage.

| Key | Shipped `us_track_ledger.json` | Rebuilt here | Δ |
|---|---:|---:|---:|
| `n_matured` | 173 | 257 | 84.0000 |
| `n_board_days` | 8 | 11 | 3.0000 |
| `win_pct` | 63.60 | 62.30 | -1.3000 |
| `expectancy_pct` | 1.19 | 0.94 | -0.2500 |
| `median_pct` | 1.74 | 1.13 | -0.6100 |
| `avg_win_pct` | 4.54 | 4.55 | 0.0100 |
| `avg_loss_pct` | -4.67 | -5.02 | -0.3500 |
| `profit_factor` | 1.70 | 1.50 | -0.2000 |
| `ci_lo_pct` | 55.60 | 54.60 | -1.0000 |
| `ci_hi_pct` | 69.80 | 67.90 | -1.9000 |
| `exp_lo_pct` | 0.21 | -0.25 | -0.4600 |
| `exp_hi_pct` | 1.98 | 1.91 | -0.0700 |
| `median_hold` | 9 | 9 | 0.0000 |
| `capture` | 0.71 | 0.51 | -0.2000 |
| `mfe_median_pct` | 3.44 | 3.75 | 0.3100 |
| `mae_median_pct` | -2.14 | -2.64 | -0.5000 |

**Calibration delta: non-zero at unmatched inputs — expected under the tape's advance, and not attributable to drift from this tree.** The horse-race cohort is a strict subset of this one (it additionally requires a high/low path for ATR14).

## The horse race

All 257 episodes, all policies, identical entries. Win = return > 0 (no dead band). `capture`, `MFE` and `MAE` are measured over each policy's **own held window**, one definition for every row including P0 — see *Method* for what that changed and what it costs. MAE/MFE are close-path and understate the intraday excursion; a rule that exits on strength scores a high `capture` by construction.

| Policy | n | expectancy | vs SPY | win % | avg win | avg loss | PF | med hold | max hold | capture | med MAE | `data_end` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 257 | **0.94%** | 1.07% | 62.3 | 4.55 | -5.02 | 1.50 | 9 | 10 | 0.76 | -1.77 | 0 |
| P0f · pure fixed H=10 | 257 | **1.18%** | 0.97% | 58.4 | 5.82 | -5.32 | 1.53 | 10 | 10 | 0.54 | -2.64 | 0 |
| P1 · pure fixed H=21 | 257 | **2.11%** | -0.23% | 55.6 | 8.45 | -5.84 | 1.81 | 17 | 21 | 0.38 | -3.87 | 163 |
| P2 · ATR trail k=2 (cap 63) | 257 | **0.26%** | -0.55% | 45.1 | 7.65 | -5.82 | 1.08 | 12 | 24 | -0.02 | -3.06 | 92 |
| P2 · ATR trail k=3 (cap 63) | 257 | **1.67%** | -0.31% | 53.3 | 8.91 | -6.58 | 1.54 | 14 | 24 | 0.35 | -3.79 | 178 |
| P3 · plan target/stop, +3R (cap 21) | 257 | **1.60%** | -0.22% | 52.9 | 8.62 | -6.29 | 1.54 | 15 | 21 | 0.31 | -3.79 | 142 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 257 | **1.08%** | -0.22% | 43.2 | 8.89 | -4.86 | 1.39 | 13 | 24 | -0.05 | -2.75 | 132 |

`capture` is a median over the rows where it is defined; rows with MFE ≤ 0 have no favourable excursion to capture and are excluded rather than divided (P0 40, P0f 21, P1 13, P2 k=2 23, P2 k=3 16, P3 18, P4 16 excluded). `data_end` counts positions the data ran out on — marks, not exits.

Date-blocked 95% intervals (whole board days resampled, seeded — 11 blocks):

| Policy | expectancy 95% CI | win-rate 95% CI | vs-SPY expectancy 95% CI |
|---|---|---|---|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | -0.25 … 1.91 | 54.6 … 67.9 | 0.08 … 2.05 |
| P0f · pure fixed H=10 | -0.05 … 2.20 | 49.6 … 66.0 | -0.36 … 2.43 |
| P1 · pure fixed H=21 | 1.01 … 3.20 | 50.6 … 60.7 | -1.48 … 0.99 |
| P2 · ATR trail k=2 (cap 63) | -0.62 … 0.91 | 39.6 … 49.8 | -1.27 … 0.23 |
| P2 · ATR trail k=3 (cap 63) | 0.43 … 2.78 | 47.9 … 58.6 | -1.36 … 0.79 |
| P3 · plan target/stop, +3R (cap 21) | 0.41 … 2.69 | 47.7 … 58.3 | -1.47 … 0.90 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | -0.14 … 2.24 | 37.7 … 48.7 | -1.37 … 1.02 |

Exit-reason mix (how each rule actually ended):

| Policy | `horizon` | `trail_stop` | `plan_stop` | `plan_target` | `stop` | `target` | `data_end` |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 114 | 0 | 0 | 0 | 8 | 135 | 0 |
| P0f · pure fixed H=10 | 257 | 0 | 0 | 0 | 0 | 0 | 0 |
| P1 · pure fixed H=21 | 94 | 0 | 0 | 0 | 0 | 0 | 163 |
| P2 · ATR trail k=2 (cap 63) | 0 | 165 | 0 | 0 | 0 | 0 | 92 |
| P2 · ATR trail k=3 (cap 63) | 0 | 79 | 0 | 0 | 0 | 0 | 178 |
| P3 · plan target/stop, +3R (cap 21) | 68 | 0 | 42 | 5 | 0 | 0 | 142 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 0 | 125 | 0 | 0 | 0 | 0 | 132 |

(`stop` / `target` are the incumbent's own legs — the 90d-trough break and the 3D-StochRSI overbought read — and appear only on the P0 row.)

## Does anything separate from the incumbent?

Paired per-episode deltas: same entry, same window, so the difference isolates the exit rule. The interval still resamples whole board days. **No p-values** — with 11 blocks a per-policy p-value would be decoration, and the block structure is the only thing making the interval honest.

| Policy | `data_end` | Δ vs P0 (incumbent) | 95% CI | excludes 0? | Δ vs P0f (fixed H=10) | 95% CI | excludes 0? |
|---|---:|---:|---|:--:|---:|---|:--:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 0 (0%) | — | — | — | -0.24 pp | -0.60 … 0.15 | no |
| P0f · pure fixed H=10 | 0 (0%) | +0.24 pp | -0.15 … 0.60 | no | — | — | — |
| P1 · pure fixed H=21 | 163 (63%) | +1.17 pp | 0.37 … 2.10 | **yes** | +0.93 pp | -0.09 … 2.11 | no |
| P2 · ATR trail k=2 (cap 63) | 92 (36%) | -0.68 pp | -1.38 … 0.02 | no | -0.92 pp | -1.68 … -0.10 | **yes** |
| P2 · ATR trail k=3 (cap 63) | 178 (69%) | +0.73 pp | -0.16 … 1.62 | no | +0.49 pp | -0.49 … 1.57 | no |
| P3 · plan target/stop, +3R (cap 21) | 142 (55%) | +0.66 pp | -0.22 … 1.61 | no | +0.42 pp | -0.64 … 1.62 | no |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 132 (51%) | +0.14 pp | -0.79 … 1.16 | no | -0.10 pp | -1.16 … 1.04 | no |

`data_end` repeats here on purpose: a delta is only as real as the exits behind it, and on the high-`data_end` rows most of the difference is a mark taken on the last session in the caches rather than an exit the rule produced.

**Read every bolded "excludes 0" with this attached: the blocks overlap.** Neighbouring board days hold the same tape — a median **90%** of each other's 10 forward sessions (range 70–90%) — and at most **2 of the 11 board days** have windows that share no session at all. The bootstrap resamples the 11 days as if they were 11 independent bets; they are closer to 2. Every interval here is therefore **too narrow**, and an interval that excludes zero is a weaker statement than it looks.

**Those marks are not spread across the sample: every one of them lands on the same session, `2026-08-05`.** All 707 of them (counting each policy's rows separately) are priced off that one session's close, so a single day's tape sets the exit price for every unresolved position in this report at once — one draw of the terminal day, not 11. Marking one session earlier instead moves the policy deltas by at most **0.53 pp**, which is that dependency's measured size — not a small number against deltas this size.

**One-session-back sensitivity.** The same horse race, re-run on a panel that ends one session earlier (234 of 257 episodes survive the maturity gate, 23 dropped). P0 itself does not move at all — its window closes before the data edge — so every shift below belongs to the marked policies. This is the size of the one-day dependency, measured rather than asserted.

| Policy | Δ vs P0 as printed | Δ vs P0 one session back | shift | `data_end` (printed → one back) |
|---|---:|---:|---:|---:|
| P0f · pure fixed H=10 | 0.14 pp | 0.14 pp | **+0.00 pp** | 0 → 0 |
| P1 · pure fixed H=21 | 1.16 pp | 1.69 pp | **+0.53 pp** | 140 → 155 |
| P2 · ATR trail k=2 (cap 63) | -0.78 pp | -0.50 pp | **+0.28 pp** | 82 → 88 |
| P2 · ATR trail k=3 (cap 63) | 0.75 pp | 1.14 pp | **+0.39 pp** | 161 → 169 |
| P3 · plan target/stop, +3R (cap 21) | 0.77 pp | 1.16 pp | **+0.39 pp** | 123 → 135 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 0.12 pp | 0.49 pp | **+0.37 pp** | 118 → 126 |

Largest shift: **0.53 pp**, and every policy that moves at all moves the same way — which is what one session's tape moving every mark at once looks like. The ordering of the policies does NOT survive the change; the magnitudes do not. Read the deltas as accurate to roughly this shift, not to their second decimal.

## Winners kept vs losers cut

The operator's question, decomposed. Anchor = **P0f, a hard exit at bar 10**, so "extended beyond 10d" and "cut before 10d" are literal. Every episode lands in exactly one bucket; each bucket's contribution is `sum(Δ in bucket) / n_total`, so the five contributions **sum to the policy's total Δ vs P0f**. Both halves get their cost leg printed beside their benefit leg — a decomposition that shows only the benefit legs is an advert.

| Policy | `data_end` | extended·winner | extended·loser | **winners-kept net** | cut·loser | cut·winner | **losers-cut net** | same bar | total Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 0 (0%) | +0.00 pp<br><sub>n=0</sub> | +0.00 pp<br><sub>n=0</sub> | **+0.00 pp** | +0.72 pp<br><sub>n=51</sub> | -0.96 pp<br><sub>n=80</sub> | **-0.24 pp** | +0.00 pp<br><sub>n=126</sub> | **-0.24 pp** |
| P1 · pure fixed H=21 | 163 (63%) | +0.30 pp<br><sub>n=138</sub> | +0.63 pp<br><sub>n=96</sub> | **+0.93 pp** | +0.00 pp<br><sub>n=0</sub> | +0.00 pp<br><sub>n=0</sub> | **+0.00 pp** | +0.00 pp<br><sub>n=23</sub> | **+0.93 pp** |
| P2 · ATR trail k=2 (cap 63) | 92 (36%) | -0.49 pp<br><sub>n=122</sub> | +0.20 pp<br><sub>n=43</sub> | **-0.29 pp** | +0.02 pp<br><sub>n=58</sub> | -0.65 pp<br><sub>n=17</sub> | **-0.63 pp** | +0.00 pp<br><sub>n=17</sub> | **-0.92 pp** |
| P2 · ATR trail k=3 (cap 63) | 178 (69%) | +0.35 pp<br><sub>n=135</sub> | +0.40 pp<br><sub>n=71</sub> | **+0.75 pp** | -0.04 pp<br><sub>n=26</sub> | -0.22 pp<br><sub>n=4</sub> | **-0.26 pp** | +0.00 pp<br><sub>n=21</sub> | **+0.49 pp** |
| P3 · plan target/stop, +3R (cap 21) | 142 (55%) | +0.17 pp<br><sub>n=135</sub> | +0.36 pp<br><sub>n=77</sub> | **+0.53 pp** | -0.06 pp<br><sub>n=18</sub> | -0.05 pp<br><sub>n=5</sub> | **-0.11 pp** | +0.00 pp<br><sub>n=22</sub> | **+0.42 pp** |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 132 (51%) | -0.05 pp<br><sub>n=121</sub> | +0.37 pp<br><sub>n=63</sub> | **+0.32 pp** | +0.11 pp<br><sub>n=33</sub> | -0.53 pp<br><sub>n=19</sub> | **-0.42 pp** | +0.00 pp<br><sub>n=21</sub> | **-0.10 pp** |

The printed parts add up to the printed nets: the contributions are computed at full precision and rounded together (largest remainder), not rounded one at a time — five independently-rounded parts do not reconcile to their own total.

`data_end` is repeated here too. On the rows carrying a high count, the "extended" buckets are mostly measuring **held-and-marked on 2026-08-05**, not held-to-exit: an extension whose end is a mark cannot tell you what letting it run would have returned. The concentration and its one-session-back sensitivity are in the section above.

## Horizon ladder

| Horizon | Episodes with AT LEAST that many forward bars | Board days |
|---:|---:|---:|
| 10 | 257 | 11 |
| 21 | 94 | 4 |
| 63 | 0 | 0 |

The **21-bar sub-cohort** (94 episodes, 4 board days) is the only slice where the 21-cap policies resolve without a data mark. It is shown for completeness and is **descriptive only**: 4 board days is far too few blocks for an interval to mean much.

| Policy | n | expectancy | win % | med hold | `data_end` |
|---|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 94 | 1.56% | 66.0 | 10 | 0 |
| P0f · pure fixed H=10 | 94 | 1.53% | 67.0 | 10 | 0 |
| P1 · pure fixed H=21 | 94 | 2.64% | 58.5 | 21 | 0 |
| P2 · ATR trail k=2 (cap 63) | 94 | 0.08% | 40.4 | 15 | 18 |
| P2 · ATR trail k=3 (cap 63) | 94 | 2.70% | 55.3 | 22 | 62 |
| P3 · plan target/stop, +3R (cap 21) | 94 | 1.69% | 53.2 | 21 | 0 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 94 | 1.20% | 39.4 | 19 | 38 |

**63 sessions: 0 episodes support it.** The ladder's 63-bar rung cannot be printed at all yet — it is not truncated, it does not exist. It will exist around the turn of the quarter and this study re-runs unchanged.

## Note on P3's geometry

P3's stop is the board row's own published invalidation level where present (151 episodes; 106 fell back to entry − 2×ATR14). That level is a break of the setup's 90-session trough × 0.97 — a **thesis** invalidation, not a risk stop. Its median distance below entry in this cohort is **10.47%** (p10 4.33%, p90 21.34%), which puts the +3R target a median **31.40%** above entry.

A target that far away is essentially unreachable inside 21 sessions, so **P3 as specified degenerates toward a fixed H=21 with a rarely-touched stop** — which is what its exit-reason mix above shows. That is a finding about the plan geometry, not a bug in the walker: the desk publishes an invalidation level, not a stop-loss, and the two are not interchangeable. Sizing a stop off that level is a separate question this study does not answer.

## Limitations

Five, in the order they damage the numbers:

1. **The blocks overlap.** 11 board days, but their 10-session windows share a median 90% of their tape and at most 2 of them are mutually disjoint. Every interval here is too narrow and the effective sample is materially below 11. Not corrected — disclosed.
2. **The terminal marks are one day.** 707 `data_end` marks across the policies, and every one of them lands on the same session, `2026-08-05`. Moving the mark back one session shifts the policy deltas by up to 0.53 pp — the deltas are worth about that much precision, not their second decimal.
3. **Stops are close-only.** A stop fires on the SESSION'S CLOSE and fills at it: the 419 stop exits here filled a mean 2.02% of entry below their trigger level, 37.7% of them would have fired earlier under a true intraday stop, and another 137 rows (10.7% of 1285) traded through their level intraday without ever stopping on a close. The stop-carrying policies here are therefore NOT the policies a desk would actually run — they are their close-only cousins.
4. **MFE/MAE are close-path.** The caches carry no intraday path for the walk, so both excursions understate the real ones, and `capture` — built on MFE over the policy's own held window — flatters any rule that exits on strength. It is a diagnostic, not a score.
5. **The record is too young for the long-horizon policies.** The longest forward path in existence is 24 sessions, so the cap-63 family has never been allowed to reach its cap and its rows are mostly marks. Time is the only fix; the study re-runs unchanged.

## Read

**P1** show a paired delta versus the incumbent whose date-blocked 95% interval sits ABOVE zero in this sample. That is a description of 11 board days, not an edge claim — and any policy here has to clear its own pre-registration before it can change anything.

**On the operator's question — *let winners run, cut losers short* — the two halves do not behave alike in this sample.** Take the cleanest pair: P1 is P0f held to bar 21 instead of bar 10, so its whole delta IS the "let it run" half. Extending the 138 episodes P0f had green added **+0.30 pp** of expectancy (+0.55 pp each), while extending the 96 it had red contributed **+0.63 pp**. Running further did, here, pay something — on eight board days.

The cutting half already exists in the product: the incumbent's early legs exit 131 of the 257 episodes BEFORE bar 10 (123 on the 3D-StochRSI target read + 8 on the trough stop), and a further 12 fire ON bar 10 itself, which is why the exit-reason mix above counts more early exits than this decomposition buckets as "cut". Cutting the 51 that P0f had red is worth **+0.72 pp**; cutting the 80 that P0f had green costs **-0.96 pp**; net **-0.24 pp**. So in this cohort the benefit of the desk's early exit comes with a real cost leg attached, and the net is small enough that 11 board days cannot resolve it — the P0-vs-P0f interval straddles zero.

**Every "run it longer" number above is contaminated by the data edge.** 163 of P1's 257 rows never reached bar 21 — they are marks on 2026-08-05, not exits. The extended buckets therefore mostly measure "held 11–20 sessions and marked", not "held 21". Which way that pushes the estimate is unknown, so it cannot be corrected for; it makes the numbers mushier than their decimal places suggest, and moving the mark back a single session shifts the deltas by up to 0.53 pp.

The structural finding that does not depend on sample size: **the record is too young for this question.** A trailing stop is the instrument for capturing moves that extend for months, and the longest forward path in existence here is 24 sessions — the cap-63 family has never once been allowed to reach its cap. The horse race is wired, calibrated against the shipped ledger, and cheap to re-run; what it needs is time.

## Promotion path: prereg required

Nothing in this report promotes anything. It is measurement tier: the numbers are printed, the nulls are printed, and the incumbent keeps the headline. For any policy here to change what the product does, it has to go through the promotion pipeline first — a pre-registration that fixes the policy, the cohort, the horizon, the metric and the decision rule **before** the outcome is recomputed, then a verdict against those pre-registered gates on a sample with enough independent board days to carry one. This study is an input to that prereg, not a substitute for it (masterplan §0 G4/G7).

