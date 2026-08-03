# Exit-policy horse race — US buy-lane episodes

**Study date:** 2026-08-03T01:33Z · **Script:** `scripts/exit_policy_study.py` · **Charter:** `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §0 G3/G4, §1

**Tier: measurement / display. Nothing here promotes anything.** The public track record keeps the incumbent rule. Every verdict below is descriptive — what this sample shows, on this cohort, at this size. A policy that eventually replaces the incumbent has to be pre-registered first; see *Promotion path* at the end.

---

## What was measured

One question: **on identical entries, what does a holder-with-rules capture?** The Track-record ledger answers a different one (is the SIGNAL any good?) and has to stay policy-free to answer it, so this is a separate study reading the same episodes — the ledger, the board and every weight are untouched.

* **Cohort** — buy-lane episodes on boards from **2026-06-25** onward (the board-definition cut; earlier boards published a 120-name broad screen and are a different instrument). One episode = one contiguous board run. Entry = the **next session's close** after the board date, identical for every policy — the board is computed from that close and published that evening, so the signal bar is unbuyable.
* **Boards** — 17 board days, 2026-06-30 → 2026-07-31. Prices run to **2026-07-31**.
* **Episodes** — **173 episodes across 8 board days.** Forward bars available per episode: 11 min / 18 median / 21 max.
* **Benchmark** — SPY total return over each episode's own fill→exit window.
* **Provenance** — board membership is `snapshots.jsonl` UNION the buy-lane rows of `retro_grades.parquet`. In this run the snapshot store already covered the whole post-cut era: retro contributed 0 extra board days and 0 extra tickers. The union is kept anyway so a future gap in the forward store heals from git archaeology instead of silently shrinking the cohort.

`n_board_days` is the number that matters. Episodes surfaced on the same night share the tape, the regime read and the ranker's state — they are one bet, not N. **8 board days is the effective sample here**, not 173.

### Coverage and exclusions (nothing dropped silently)

| Excluded because | Episodes |
|---|---:|
| no close series in the breadth caches (delisted / not in S&P 1500) | 12 |
| close column present but all-null | 0 |
| next-session fill has not printed yet | 29 |
| fill price non-finite or ≤ 0 | 0 |
| fewer than 10 forward bars (in flight) | 240 |
| no high/low path, or ATR14 not computable at the fill bar | 0 |
| **kept — the horse-race cohort** | **173** |
| *total episodes built from the 17 boards* | *454* |

No-price names (10 distinct tickers, 12 episodes): `ASTS`, `BIDU`, `CRDO`, `NET`, `NVO`, `NXE`, `TEAM`, `U`, `UROY`, `VALE`.

Exclusions are by **data coverage** and by **age** only. Neither can know which way a trade went, so both are symmetric — unlike an exclusion keyed on outcome, which would delete the losers.

### The censoring caveat — read before the table

The record starts 2026-06-30 and prices end 2026-07-31. Of the 173 episodes, **173 have 10 forward bars** (8 board days), **34 have 21** (1 board day), and **0 have 63**.

So the 21- and 63-bar caps mostly cannot be reached. A position still open when the data ends is **marked at the last available close and flagged `data_end`** — it is not dropped, because dropping it would delete precisely the trades that were still running, and a denominator conditioned on how a trade ended is the single artefact `engine/track_scoring.py` exists to forbid. Every policy row prints its `data_end` count. **A `data_end` row is a mark, not a realised exit, and its hold length is a lower bound.** Read the cap-63 rows as *what these rules were still holding on 2026-07-31*, not as *what these rules returned*.

## Calibration — does P0 reproduce the shipped ledger?

P0 is the incumbent rule executed through `engine.track_scoring` itself, on the ledger's own cohort (close path only, no ATR requirement) so a non-zero delta would mean the reconstruction drifted rather than that the cohorts differ.

| Key | Shipped `us_track_ledger.json` | Rebuilt here | Δ |
|---|---:|---:|---:|
| `n_matured` | 173 | 173 | 0.0000 |
| `n_board_days` | 8 | 8 | 0.0000 |
| `win_pct` | 63.60 | 63.60 | 0.0000 |
| `expectancy_pct` | 1.19 | 1.19 | 0.0000 |
| `median_pct` | 1.74 | 1.74 | 0.0000 |
| `avg_win_pct` | 4.54 | 4.54 | 0.0000 |
| `avg_loss_pct` | -4.67 | -4.67 | 0.0000 |
| `profit_factor` | 1.70 | 1.70 | 0.0000 |
| `ci_lo_pct` | 55.60 | 55.60 | 0.0000 |
| `ci_hi_pct` | 69.80 | 69.80 | 0.0000 |
| `exp_lo_pct` | 0.21 | 0.21 | 0.0000 |
| `exp_hi_pct` | 1.98 | 1.98 | 0.0000 |
| `median_hold` | 9 | 9 | 0.0000 |
| `capture` | 0.71 | 0.71 | 0.0000 |
| `mfe_median_pct` | 3.44 | 3.44 | 0.0000 |
| `mae_median_pct` | -2.14 | -2.14 | 0.0000 |

**Calibration delta: exact — 0.0000 on every key.** The horse-race cohort is a strict subset of this one (it additionally requires a high/low path for ATR14).

## The horse race

All 173 episodes, all policies, identical entries. Win = return > 0 (no dead band). `capture` = median(realised / MFE) over the policy's own hold window — the ledger's own definition. MAE/MFE are close-path and understate the intraday excursion.

| Policy | n | expectancy | vs SPY | win % | avg win | avg loss | PF | med hold | max hold | capture | med MAE | `data_end` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 173 | **1.19%** | 1.72% | 63.6 | 4.54 | -4.67 | 1.70 | 9 | 10 | 0.71 | -2.14 | 0 |
| P0f · pure fixed H=10 | 173 | **0.93%** | 1.88% | 60.7 | 5.07 | -5.46 | 1.43 | 10 | 10 | 0.69 | -2.14 | 0 |
| P1 · pure fixed H=21 | 173 | **0.53%** | 0.83% | 53.2 | 6.19 | -5.89 | 1.19 | 18 | 21 | 0.31 | -3.17 | 139 |
| P2 · ATR trail k=2 (cap 63) | 173 | **-0.59%** | 0.07% | 42.8 | 5.65 | -5.25 | 0.80 | 13 | 21 | 0.07 | -2.64 | 66 |
| P2 · ATR trail k=3 (cap 63) | 173 | **0.28%** | 0.76% | 51.4 | 6.31 | -6.10 | 1.10 | 15 | 21 | 0.26 | -3.17 | 126 |
| P3 · plan target/stop, +3R (cap 21) | 173 | **0.41%** | 0.80% | 52.0 | 6.26 | -5.94 | 1.14 | 15 | 21 | 0.34 | -3.17 | 112 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 173 | **-0.36%** | 0.29% | 39.9 | 6.38 | -4.84 | 0.87 | 14 | 21 | -0.04 | -2.41 | 92 |

Date-blocked 95% intervals (whole board days resampled, seeded — 8 blocks):

| Policy | expectancy 95% CI | win-rate 95% CI | vs-SPY expectancy 95% CI |
|---|---|---|---|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 0.21 … 1.98 | 55.6 … 69.8 | 1.00 … 2.59 |
| P0f · pure fixed H=10 | -0.75 … 2.09 | 47.8 … 70.7 | 0.43 … 3.44 |
| P1 · pure fixed H=21 | -1.09 … 1.80 | 43.9 … 62.1 | -0.60 … 1.97 |
| P2 · ATR trail k=2 (cap 63) | -1.81 … 0.36 | 34.2 … 50.9 | -0.93 … 0.85 |
| P2 · ATR trail k=3 (cap 63) | -1.19 … 1.44 | 42.3 … 59.8 | -0.42 … 1.79 |
| P3 · plan target/stop, +3R (cap 21) | -1.05 … 1.56 | 43.5 … 60.7 | -0.49 … 1.79 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | -1.63 … 0.64 | 33.8 … 45.6 | -0.73 … 1.26 |

Exit-reason mix (how each rule actually ended):

| Policy | `horizon` | `trail_stop` | `plan_stop` | `plan_target` | `stop` | `target` | `data_end` |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 77 | 0 | 0 | 0 | 1 | 95 | 0 |
| P0f · pure fixed H=10 | 173 | 0 | 0 | 0 | 0 | 0 | 0 |
| P1 · pure fixed H=21 | 34 | 0 | 0 | 0 | 0 | 0 | 139 |
| P2 · ATR trail k=2 (cap 63) | 0 | 107 | 0 | 0 | 0 | 0 | 66 |
| P2 · ATR trail k=3 (cap 63) | 0 | 47 | 0 | 0 | 0 | 0 | 126 |
| P3 · plan target/stop, +3R (cap 21) | 27 | 0 | 32 | 2 | 0 | 0 | 112 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 0 | 81 | 0 | 0 | 0 | 0 | 92 |

(`stop` / `target` are the incumbent's own legs — the 90d-trough break and the 3D-StochRSI overbought read — and appear only on the P0 row.)

## Does anything separate from the incumbent?

Paired per-episode deltas: same entry, same window, so the difference isolates the exit rule. The interval still resamples whole board days. **No p-values** — with 8 blocks a per-policy p-value would be decoration, and the block structure is the only thing making the interval honest.

| Policy | Δ vs P0 (incumbent) | 95% CI | excludes 0? | Δ vs P0f (fixed H=10) | 95% CI | excludes 0? |
|---|---:|---|:--:|---:|---|:--:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | — | — | — | +0.26 pp | -0.36 … 1.14 | no |
| P0f · pure fixed H=10 | -0.26 pp | -1.14 … 0.36 | no | — | — | — |
| P1 · pure fixed H=21 | -0.66 pp | -1.56 … 0.15 | no | -0.40 pp | -1.25 … 0.63 | no |
| P2 · ATR trail k=2 (cap 63) | -1.78 pp | -2.60 … -1.11 | **yes** | -1.52 pp | -2.35 … -0.67 | **yes** |
| P2 · ATR trail k=3 (cap 63) | -0.91 pp | -1.75 … -0.16 | **yes** | -0.65 pp | -1.49 … 0.29 | no |
| P3 · plan target/stop, +3R (cap 21) | -0.78 pp | -1.79 … 0.11 | no | -0.53 pp | -1.52 … 0.48 | no |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | -1.55 pp | -2.30 … -1.04 | **yes** | -1.30 pp | -2.18 … -0.25 | **yes** |

## Winners kept vs losers cut

The operator's question, decomposed. Anchor = **P0f, a hard exit at bar 10**, so "extended beyond 10d" and "cut before 10d" are literal. Every episode lands in exactly one bucket; each bucket's contribution is `sum(Δ in bucket) / n_total`, so the five contributions **sum to the policy's total Δ vs P0f**. Both halves get their cost leg printed beside their benefit leg — a decomposition that shows only the benefit legs is an advert.

| Policy | extended·winner | extended·loser | **winners-kept net** | cut·loser | cut·winner | **losers-cut net** | same bar | total Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | +0.00 pp<br><sub>n=0</sub> | +0.00 pp<br><sub>n=0</sub> | **+0.00 pp** | +0.76 pp<br><sub>n=27</sub> | -0.51 pp<br><sub>n=63</sub> | **+0.26 pp** | +0.00 pp<br><sub>n=83</sub> | **+0.26 pp** |
| P1 · pure fixed H=21 | -0.36 pp<br><sub>n=105</sub> | -0.04 pp<br><sub>n=68</sub> | **-0.40 pp** | +0.00 pp<br><sub>n=0</sub> | +0.00 pp<br><sub>n=0</sub> | **+0.00 pp** | +0.00 pp<br><sub>n=0</sub> | **-0.40 pp** |
| P2 · ATR trail k=2 (cap 63) | -0.98 pp<br><sub>n=97</sub> | -0.20 pp<br><sub>n=34</sub> | **-1.18 pp** | +0.12 pp<br><sub>n=31</sub> | -0.46 pp<br><sub>n=8</sub> | **-0.34 pp** | +0.00 pp<br><sub>n=3</sub> | **-1.52 pp** |
| P2 · ATR trail k=3 (cap 63) | -0.46 pp<br><sub>n=105</sub> | -0.20 pp<br><sub>n=52</sub> | **-0.66 pp** | +0.01 pp<br><sub>n=13</sub> | +0.00 pp<br><sub>n=0</sub> | **+0.01 pp** | +0.00 pp<br><sub>n=3</sub> | **-0.65 pp** |
| P3 · plan target/stop, +3R (cap 21) | -0.45 pp<br><sub>n=104</sub> | -0.15 pp<br><sub>n=53</sub> | **-0.59 pp** | +0.02 pp<br><sub>n=12</sub> | +0.05 pp<br><sub>n=1</sub> | **+0.07 pp** | +0.00 pp<br><sub>n=3</sub> | **-0.53 pp** |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | -0.78 pp<br><sub>n=96</sub> | -0.27 pp<br><sub>n=48</sub> | **-1.05 pp** | +0.09 pp<br><sub>n=14</sub> | -0.34 pp<br><sub>n=9</sub> | **-0.25 pp** | +0.00 pp<br><sub>n=6</sub> | **-1.30 pp** |

## Horizon ladder

| Horizon | Episodes with that many forward bars | Board days |
|---:|---:|---:|
| 10 | 173 | 8 |
| 21 | 34 | 1 |
| 63 | 0 | 0 |

The **21-bar sub-cohort** (34 episodes, 1 board day) is the only slice where the 21-cap policies resolve without a data mark. It is shown for completeness and is **descriptive only**: with a single board day there is nothing to resample, so `date_block_ci` correctly returns no interval — any number printed here would be one bet.

| Policy | n | expectancy | win % | med hold | `data_end` |
|---|---:|---:|---:|---:|---:|
| P0 · incumbent as shipped (H=10 + StochRSI target + trough stop) | 34 | 2.08% | 73.5 | 10 | 0 |
| P0f · pure fixed H=10 | 34 | 2.82% | 73.5 | 10 | 0 |
| P1 · pure fixed H=21 | 34 | 1.62% | 50.0 | 21 | 0 |
| P2 · ATR trail k=2 (cap 63) | 34 | 0.19% | 41.2 | 17 | 8 |
| P2 · ATR trail k=3 (cap 63) | 34 | 1.16% | 47.1 | 21 | 26 |
| P3 · plan target/stop, +3R (cap 21) | 34 | 1.02% | 47.1 | 21 | 0 |
| P4 · breakeven at +1 ATR then trail k=3 (cap 63) | 34 | 0.60% | 35.3 | 19 | 14 |

**63 sessions: 0 episodes support it.** The ladder's 63-bar rung cannot be printed at all yet — it is not truncated, it does not exist. It will exist around the turn of the quarter and this study re-runs unchanged.

## Note on P3's geometry

P3's stop is the board row's own published invalidation level where present (72 episodes; 101 fell back to entry − 2×ATR14). That level is a break of the setup's 90-session trough × 0.97 — a **thesis** invalidation, not a risk stop. Its median distance below entry in this cohort is **7.79%** (p10 4.18%, p90 18.80%), which puts the +3R target a median **23.38%** above entry.

A target that far away is essentially unreachable inside 21 sessions, so **P3 as specified degenerates toward a fixed H=21 with a rarely-touched stop** — which is what its exit-reason mix above shows. That is a finding about the plan geometry, not a bug in the walker: the desk publishes an invalidation level, not a stop-loss, and the two are not interchangeable. Sizing a stop off that level is a separate question this study does not answer.

## Read

**No policy beats the incumbent in this sample.** Not one paired delta versus P0 has a date-blocked 95% interval sitting above zero. **P2 k=2**, **P2 k=3**, **P4** sit BELOW zero — in this cohort they gave up ground to the incumbent rather than gaining on it. **P0f**, **P1**, **P3** straddle zero, which at 173 episodes across 8 board days is the expected result whether or not a real difference exists. The study is not powered to find a small edge; a point estimate that happens to be positive is not evidence that one is there.

**On the operator's question — *let winners run, cut losers short* — the two halves do not behave alike in this sample.** Take the cleanest pair: P1 is P0f held to bar 21 instead of bar 10, so its whole delta IS the "let it run" half. Extending the 105 episodes P0f had green cost **-0.36 pp** of expectancy (-0.59 pp each), while extending the 68 it had red contributed **-0.04 pp**. Running further did not, here, pay for itself.

The cutting half already exists in the product: the incumbent's 3D-StochRSI target leg exits 90 of the 173 episodes before bar 10. Cutting the 27 that P0f had red is worth **+0.76 pp**; cutting the 63 that P0f had green costs **-0.51 pp**; net **+0.26 pp**. So in this cohort the benefit of the desk's early exit comes with a real cost leg attached, and the net is small enough that 8 board days cannot resolve it — the P0-vs-P0f interval straddles zero.

**Every "run it longer" number above is contaminated by the data edge.** 139 of P1's 173 rows never reached bar 21 — they are marks on 2026-07-31, not exits. The extended buckets therefore mostly measure "held 11–20 sessions and marked", not "held 21". That biases nothing in a known direction; it just makes the estimate mushier than its decimal places suggest.

The structural finding that does not depend on sample size: **the record is too young for this question.** A trailing stop is the instrument for capturing moves that extend for months, and the longest forward path in existence here is 21 sessions — the cap-63 family has never once been allowed to reach its cap. The horse race is wired, calibrated against the shipped ledger, and cheap to re-run; what it needs is time.

## Promotion path: prereg required

Nothing in this report promotes anything. It is measurement tier: the numbers are printed, the nulls are printed, and the incumbent keeps the headline. For any policy here to change what the product does, it has to go through the promotion pipeline first — a pre-registration that fixes the policy, the cohort, the horizon, the metric and the decision rule **before** the outcome is recomputed, then a verdict against those pre-registered gates on a sample with enough independent board days to carry one. This study is an input to that prereg, not a substitute for it (masterplan §0 G4/G7).

