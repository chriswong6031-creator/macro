# CN WINDOW-TARGET BATTERY v1 — rerating windows + the sub-limit big-day class

**Program** CN LIMIT-MOVE ALPHA, Wave 3, lane W3-A
**Tier** display / audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits. No LLM is involved.
**Instrument** `research/cn_prophet_audit/window_target_battery_v1.py` (deterministic, 40.7 s)
**Data** `research/cn_prophet_audit/WINDOW_TARGET_BATTERY_V1_2026-08-09.json`
**Builds on** v0 footprint (`claude/cn-limit-footprint-v0`) · L1 continuation rider (`claude/cn-limit-w1-rider`) · L2 board-ecology dial (`claude/cn-limit-w1-regime-salvage`) · W2-B weakness battery (`claude/cn-limit-w2-weakness`) · blinded map C12

Waves 1 and 2 asked one question — *does the name close limit-up again tomorrow* — and
answered it twice. The ladder P(board T+1 | 连板 N) is real, large and era-stable; the T+1
opening auction prices it away completely. That is a null about **boards**. The operator's
charter never asked for boards:

> "Do not lock into 10%-every-day rigidity: the target is the trajectory of rerating windows
> (6% one day, 8% the next, a board here and there)."

A board is the unfillable spike of a rerating window. The 6–8% days are its buyable flesh.
Neither had ever been an outcome class in this program. This instrument makes them one, and
asks the single question that follows: **the auction prices tomorrow's board — does it also
price the window?**

---

## DECISION SUMMARY

**1. THE AUCTION PRICES THE WINDOW TOO. On the main board the answer is an unambiguous no
edge, and the sign is negative.** 99 (signal × H × variant × board-key) cells were evaluated
against the pre-registered two-window bar. 11 clear it. **Every one of the 11 dies against
the drift control** (see §5) — and 7 of the 11 are the foresight-requiring `peak_best`
upper-bound variant, which was never a strategy. The 4 implementable clears are all the same
signal on the same board key (S3 on chinext_20pct_post2020, H=5 and H=10). On main, every
implementable cell of every
signal at every horizon is **negative in excess of the same-session universe return, in both
windows**, most at |t| > 3:

| Signal (main board, fixed-H exit) | H | fit excess net / t | holdout excess net / t |
|---|---|---|---|
| S2 first board N=1 | 10 | **−1.049% / −8.35** | **−0.913% / −4.44** |
| S3 big-day non-board | 10 | **−0.365% / −3.96** | **−0.460% / −3.17** |
| S4 near-miss untouched | 10 | −0.954% / −3.35 | −0.283% / −0.45 |
| S1 f3 top-decile × regime hot | 10 | −1.273% / −1.76 | **−4.712% / −2.80** |

The daily-resolution null is now close to total: it covers the board (W1), weakness entries
(W2-B), and — as of this lane — the sub-limit big day, the multi-session cumulative window,
and the window's peak.

**2. THE CENTRAL MEASUREMENT — the big-day class is essentially UNCONDITIONAL.** ~7% of
board days are followed by a sub-limit big day (≥ 0.6w, not a board), and that number barely
moves for anything:

| Conditioner (main board) | P(board T+1) range | P(big-day T+1) range |
|---|---|---|
| ladder N = 1 → 2 → 3+ (fit) | 16.8% → 40.4% → **61.9%** | 7.47% → 6.92% → **3.62%** |
| i5 regime cold → mid → hot (fit) | 15.7% → 21.6% → **36.3%** | 7.53% → 6.65% → **6.69%** |
| six eras, 2011 → 2026 | 17.4% … **32.9%** (1.9×) | 5.39% … 7.88% (**1.5×, no trend**) |

The ladder ranks the board by a factor of **3.7** and ranks the big day *slightly downward*.
Everything this program learned to condition on is information about the seal, not about the
move.

**3. The same features that rank the board do not rank the big day — and the comparison is
clean.** Identical rows, identical fit-window cuts, top decile vs rest (main board, lift ×,
fit / holdout):

| Feature | P(board T+1) | O1 big-day non-board |
|---|---|---|
| f6_gap_pct | **3.96 / 2.63** | 0.73 / 0.72 |
| f3_runup_5 | **2.46 / 2.09** | 0.73 / 1.11 *(sign-unstable)* |
| f8_consec_up_days | 1.68 / 1.69 | 0.74 / 1.10 *(sign-unstable)* |
| f4_sector_heat | 1.50 / 1.36 | 0.94 / 2.65 *(sign-unstable)* |
| f7_dist_52w_low | 1.12 / 1.05 | 1.11 / 1.39 |
| f1_vol_z20 | 0.87 / 0.80 | 0.64 / 0.71 |

Only **f7_dist_52w_low** has a big-day lift above 1 in both windows, and it is 1.1–1.4× —
the weakest signal in the set. f1 is *below* 1 on every outcome in both windows, which is W1's
anti-monotone volume finding reproduced on a new target.

**4. MOST OF A RERATING WINDOW IS A PEAK YOU CANNOT SCHEDULE.** O3 (max drawup reached) minus
O2 (still there at the scheduled exit), main board:

| Window | peak reached | held to exit | retained |
|---|---|---|---|
| H=5, ≥ 0.8w — fit / holdout | 61.5% / 58.0% | 30.3% / 23.6% | **49.3% / 40.6%** |
| H=5, ≥ 1.5w — fit / holdout | 33.5% / 28.4% | 18.4% / 13.3% | **55.1% / 46.8%** |
| H=10, ≥ 2.5w — fit / holdout | 24.1% / 19.4% | 12.9% / 8.1% | **53.7% / 41.7%** |

Roughly **half in fit and closer to 40% in holdout** of the windows that *touched* a target
still hold it at a fixed exit. The window contains far more than a scheduled book collects;
that gap is where an intraday exit policy would have to live, and it is not reachable from
daily bars. This is a measurement of what is missing, not a claim that it is collectable.

**5. The one cell that survives everything except the bar — and why it is not a finding yet.**
S3 (big-day non-board) on **chinext_20pct_post2020** at H=10 is the only implementable cell
positive on *both* weightings in *both* windows with a positive benchmark excess:

| | fit | holdout |
|---|---|---|
| n trades / dates / names | 493 / 205 / 196 | 2,420 / 776 / 342 |
| date-equal net | +2.552% | +1.881% |
| date-clustered t | +2.78 | +3.32 |
| mean per-trade net | +1.704% | +1.299% |
| **excess over universe** | **+1.660%** | **+1.207%** |
| **excess t** | **+1.89** ✗ | +2.39 ✓ |
| median net / win rate | **−0.879% / 46.9%** | **−1.704% / 45.4%** |
| p90 / worst | +20.3% / −32.2% | +22.5% / −47.2% |

It **fails** the excess bar in the fit window (1.89 < 2.0). And its shape is a warning, not a
prize: the median trade *loses* in both windows and the win rate is under 50% — the positive
mean is a right tail. This is a lottery-ticket payoff on one board key whose fit window is
only 15 months long (2020-08-24 → 2021-11-26). It is recorded as **the single open thread**,
not as a candidate.

**6. C12 (blinded map) — the near-miss discontinuity is real and runs AGAINST the near-miss.**
Matched on (board key, split, prior ladder N, f3 quintile), a close in [0.85w, the limit) whose
high *never touched* the board is a materially **worse** state than a matched seal — on the
main board, in both windows, on almost every outcome:

| Outcome (main, standardised to the near-miss cells) | fit ratio | holdout ratio |
|---|---|---|
| P(board T+1) | **0.38×** | **0.31×** |
| O2 cum H5 ≥ 1.5w | 0.56× | 0.49× |
| O3 peak H5 ≥ 1.5w | 0.54× | 0.58× |
| O1 big-day non-board | 0.70× | 1.58× *(sign-unstable — no claim)* |

Support is strong (2,400 near-miss rows in 14 cells fit; 972 in 12 cells holdout). Stopping
one tick short of the board is not a discount on the same window — it is a different, weaker
state. **The difference is BUNDLED**: attention, supply at the limit and whatever stopped the
name short are not separated and this lane does not claim to separate them.

**7. Where the program's weight should go.** The buyable class is *more* buyable — the big-day
signal offers a fillable T+1 open **98.98%** of the time on main against **93.15%** for the
first board and **58.07%** for the f3×hot cohort — so fillability was never the binding
constraint on this target. What binds is that the class carries no daily-resolution
information at all. The remaining live directions are the ones the daily bar cannot see
(intraday exits into the O3 gap, seal-queue and auction-imbalance data) and the universe
expansion — not another daily conditioner on the same 1,836 names.

---

## PRE-REGISTRATION (written before the first run; reproduced from the JSON verbatim in spirit)

- **Split** 2021-11-26 — v0's computed 70/30 date, reused as a frozen constant. **One holdout
  pass.** Every threshold, band edge, exit rule, cost bar, cell floor and signal below was
  fixed before the first number was read.
- **Outcomes**, all scaled by w (the name-day's own limit width):
  - **O1 big-day** — return[T+1] ≥ 0.6w **and not** a tolerant limit-up close at T+1. The upper
    edge is the tolerant limit *flag*, not a return threshold, so big-day and board partition
    the ≥ 0.6w class exactly. Sibling **O1-incl-boards** printed beside it.
  - **O2 window-cum** — close[T+H]/close[T] − 1 ≥ θw, H ∈ {3,5,10}, θ ∈ {0.8,1.5,2.5}.
  - **O3 window-peak** — max(high[T+1..T+H])/close[T] − 1 ≥ θw, same grid.
  - **O4 / C12** — near-miss (close ≥ 0.85w, high never at the limit price) vs sealed closes,
    matched on (board key, split, prior ladder N cohort, f3 quintile).
- **Conditioning** — v0's f1/f3/f4/f6/f7/f8, ladder N at T, i5 regime tercile at T, era.
  **Timing:** v0's Stage-3 convention measures features at T−1 predicting T. This lane keeps
  that offset exactly and shifts the frame one bar forward — features read at **T**, outcomes
  over **T+1..T+H** — so a feature is always measured on the last close before the first
  outcome bar in both studies. Feature *definitions* are v0's, unchanged.
- **Cuts** — every quantile cut (feature deciles, f3 quintiles, regime terciles) computed on
  **fit-window rows only**, per board key, on **tolerant-basis rows only**. No strict∪tolerant
  population is ever pooled to form a cut. Realised top-decile shares are receipted (ties share
  a bucket, v0's correction: f3 realises 9.96% on main, 15.46% on ChiNext-20%).
- **Signals** (≤ 4, fixed before running): S1 f3 top decile × regime hot; S2 first board N=1;
  S3 big-day non-board; S4 near-miss untouched. **S4 ⊂ S3 and S1 ⊂ the board population — the
  four are not four independent tests** and are not counted as such.
- **Book** — entry at the T+1 open, fillable only (`open < limit×(1−0.002)`, L1's censor);
  fixed-H exit at the open of T+H+1 (L1's E3 with k = H) with L1's locked-exit rolls; 15 bp
  round trip.
- **Decision bar** — a cell CLEARS only if its date-equal-weighted net expectancy is positive
  **and** its date-clustered t ≥ 2 in **both** windows with n_dates ≥ 30 in each.
- **Window overlap — ONE treatment, chosen in advance: cluster by START DATE.** The
  alternative (restrict to non-overlapping starts) would delete the ladder, since consecutive
  board days *are* the ladder, and would answer a different question. Consequence, accepted:
  row n is **not** an independent-observation count; every expectancy collapses to per-date
  means before any t is formed. Measured overlap (share of rows whose H=10 window overlaps a
  prior row of the same name, calendar-day upper bound): S2 29.7%, S3 36.3%, S4 5.4%, S1 27.1%.

---

## COVERAGE RECEIPT

| | |
|---|---|
| Raw store | `data/china_stocks_raw`, 1,842 names — **BACK-ADJUSTED, not nominal** |
| Names kept | 1,836 (1 ST-excluded, 5 thin/unreadable) — main 1,243 · ChiNext 351 · STAR 242 |
| Window | 2011-01-01 → 2026-08-07 · 4,981,168 bars, **4,843,577 live** |
| Bars excluded | zero-volume 133,781 · IPO 2,793 · ex-div open jump 620 |
| Populations | **A** board days 60,298 · **C** big-day non-board 77,605 · **B** near-miss untouched 4,289 (B ⊂ C) |
| Sector map | 1,716 tickers / 12 sectors (current membership applied to 15 y — v0's caveat, inherited by f4) |
| Universe gap | zt_pool names present in raw: 514 / 1,770 (**29.0%**) |
| Vintage | base `3e8ec0ada0c` · data-store `3babbce7b5f` |

**Store basis.** L1's `price_basis_audit` measured this store as back-adjusted, correcting v0's
header, which calls it "nominal/unadjusted". Adjustment **preserves returns**, so every return,
gap, cumulative window and drawup in this file is unaffected; only the round-to-tick limit
*price* is, and v0's 0.002 tolerance is exactly the cushion that absorbs it. Every limit test
here is v0's adjudicated tolerant rule.

**Survivors only, pre-expansion.** The store holds a curated subset of the listed market;
delisted names are absent, so every down-tail here — limit-down rates, worst trades, forced
closes — **reads better than the truth**. A sibling Codex lane is expanding the universe; these
numbers are pre-expansion. This lane touched no collector, no Tushare surface and no universe
store.

### Gates that had to pass before any number above was read

| Gate | Result |
|---|---|
| **v0 ladder parity** (this panel is v0's panel) | **PASS — 15/15 published cells, exact n, rate to published precision** |
| **Corruption experiment** — every bar after 2019-01-02 replaced with garbage, conditioning arrays recomputed, pre-cut values compared **bitwise** | **PASS**, 30 tickers, 12 arrays each (f1/f3/f6/f7/f8, 连板, prior N, live, lu, ret, touched, width) |
| **f4 date-locality** — drop every row after the cut, re-derive the sector-heat map | **PASS**, identical |
| **i5 dial lookahead** (W2-B's mechanical check, re-run) | **PASS** — reproduces the trailing ma5 to float precision, disagrees with a forward window |
| **Determinism** | two runs byte-identical apart from `generated_utc` / `runtime_sec` |

`is_board` / `is_bigday` / `is_nearmiss` are pure functions of (live, lu, ret, touched, width);
those five inputs are what the corruption experiment pins, and the receipt names them that way
rather than claiming to have tested the flags directly.

---

## 1 — THE BIG-DAY CLASS (O1)

The class the operator asked about, made an outcome for the first time. Main board, board-day
population, denominators are rows with a usable T+1 bar:

| | fit | holdout |
|---|---|---|
| rows | 33,132 | 17,289 |
| P(board T+1) | 25.37% | 19.93% |
| **P(big-day, not a board)** | **6.92%** | **7.19%** |
| P(≥ 0.6w including boards) | 32.29% | 27.12% |

Two facts, both stable across the split:

- The big day is **a fifth to a quarter** of the ≥ 0.6w mass. It is not a rounding class.
- It is **flat in everything**. Across ladder N it goes 7.47 → 6.92 → 3.62 (fit) and
  7.44 → 6.65 → 5.32 (holdout) — mildly *decreasing*. Across regime terciles: 7.53 / 6.65 /
  6.69 (fit). Across six eras: 5.39 – 7.88 with no trend, while P(board) over the same eras
  swings 17.38 – 32.86.

**Reading.** Conditional on a board today, the chance of a big-but-sub-limit day tomorrow is
about 7%, and this program's entire conditioning apparatus does not move it. The ladder, the
regime dial and the feature set are information about *sealing*, not about *moving*.

---

## 2 — THE WINDOW (O2 / O3)

Window outcomes **are** monotone in N (main, fit, O2 cum H5 ≥ 1.5w: 12.75 → 25.19 → 46.55%).
That is not a second edge. Since O1 is flat in N, the ladder's grip on the multi-session window
must arrive through the board channel — a board is worth ≈ 1w on its own, so a ladder that
predicts boards mechanically predicts cumulative windows. This is an **inference from the two
tables**, not a decomposition; separating the board contribution from the window is an ore item.

The peak-vs-close gap is in DECISION SUMMARY §4. Two further readings:

- **The gap widens in the holdout.** Retention falls from ~50% to ~41% at H=10 ≥ 2.5w. Windows
  in the recent regime give back more of what they reach.
- **The peak is much more common than the close.** At H=5 ≥ 0.8w, 58–61% of board days reach the
  target intraday at some point; 24–30% still hold it at the scheduled exit. Any strategy that
  wants the window's upper half needs an exit rule the daily bar cannot express.

---

## 3 — THE BOOK

99 cells at the pre-registered bar; 11 clear; **0 clear against the benchmark.**

**The benchmark leg is an addition by this lane, beyond the brief's letter, and is disclosed as
such.** The pre-registered bar has no control for board drift, and the first run admitted cells
whose board key rose over the sample. The control is the *identical* trade — buy the open of
T+1, sell the open of T+H+1, same fillability censor — taken on every live name of the same
board key, aggregated per session; `excess_net` is the date-equal-weighted (signal − universe)
on the sessions the signal actually fired. Measured universe levels (net of the same 15 bp):

| Board key | H=10 fit | H=10 holdout |
|---|---|---|
| main (≈ 876–1,197 names/session) | +0.360% | +0.151% |
| chinext_20pct_post2020 (≈ 249–317 names/session) | **+0.927%** | +0.348% |

**The pre-registered bar is reported unchanged.** `CLEARS_vs_BENCHMARK` and
`positive_on_BOTH_weightings` are labelled **post-hoc** in the JSON and are not folded into the
bar — moving a pre-registered bar after seeing results is the exact failure this design exists
to prevent. Read `CLEARS` as the registered result and the two controls as what survives
scrutiny.

Other book facts worth keeping:

- **S1 (f3 top decile × regime hot) owns the five worst well-supported cells in the study**
  (every fixed-H cell with n_dates ≥ 30, ranked by date-equal net). Worst: main holdout H=10,
  **−4.18% date-equal, t = −2.42, excess t = −2.80**. Buying the strongest momentum in the
  hottest tape is a *paid* negative. This is W1's anti-monotone result reproduced against a
  window target, on an independently-cut conditioner.
- **Entry availability is not the constraint here.** Fillable T+1 opens: S3 98.98%, S4 93.62%,
  S2 93.15%, S1 58.07% (main). The fillability tax that made the L1 ladder unbuyable barely
  touches the big-day class — and the class still carries no edge.
- **Roll and forced-close rates are small** (main S3 H=10: roll 0.11–0.55%, forced close
  5.1–7.4%), so the locked-exit machinery is not driving any result.
- **The foresight premium is large.** `peak_best` (sell into the window's best open after a
  1.5w drawup — an upper bound requiring foresight) beats `peak_first` (the implementable
  sibling) by **0.9–1.6 pp date-equal-weighted** at H=10 (ChiNext-20%: +3.73 vs +2.81 fit,
  +3.27 vs +1.67 holdout; main: +0.95 vs −0.08 fit, +1.22 vs −0.14 holdout). **7 of the 11
  pre-registered clears are `peak_best` cells** — a capacity measurement of what the window
  contains, not a strategy. The remaining 4 are S3 on ChiNext-20% at H=5 and H=10.

---

## 4 — C12, THE NEAR-MISS MAP

Headline in DECISION SUMMARY §6. Mechanics worth recording:

- **Why prior N.** A near-miss has no ladder of its own (its 连板 is 0 by construction), so
  matching on the event-day N would have produced *no overlapping support at all*. The match is
  on the tolerant board streak ending at **T−1**, capped at 3+ — W2-B's convention, and the only
  reading under which a near-miss and a seal can share a cell.
- **Shared edges.** f3 quintile edges are cut on the fit window of the **pooled** matched
  population per board key, so both arms are binned identically; a per-arm cut would make the
  cells non-comparable.
- **Standardisation.** The sealed arm is re-weighted to the near-miss arm's own cell
  distribution. Cells where either arm is empty are dropped from both and the surviving support
  is printed (main: 14 cells fit / 12 holdout; 100% of near-miss rows land in support).
- **ChiNext-20% is unstable and thin** — the fit arm says the near-miss is worse on every
  outcome, the holdout arm says it is better on next-day outcomes and worse on 5-day windows, on
  38 fit rows. **No claim.**

---

## HONESTY GATES, AND WHERE THEY BIT

- **Date-clustered t beside per-trade stats everywhere.** It bit hard: the ChiNext-20% S3 cell
  has a *positive* date-equal mean and a *negative* per-trade median in both windows. The two
  weightings disagree because the many-trade sessions are the losing sessions. Both are printed
  on every cell; neither is allowed to carry a claim alone.
- **Denominators never conflated.** Every cell prints n (rows), n_dates, n_names and
  top5_name_share. O2/O3 use their own per-H denominators and the truncated-window count is
  printed, never silently dropped.
- **Multiplicity per family, never across.** Rate tables 172 cells, book 99, C12 50 — expected
  false positives at 5%: 8.6 / 5.0 / 2.5. **No below-chance reading is taken anywhere in this
  file.** A cell below the chance rate in a family this size is the expected shape of noise, not
  a short signal.
- **`*_NA` levels are data-availability slices**, flagged as such in every record, never
  conditioners, never carrying a lift (f1 NA 2.5% on main from the 20-bar warm-up; regime NA
  0.08% main / 12.0% ChiNext).
- **Basis-pure cuts.** Every cut in this file is on tolerant-basis rows; the strict column is
  used for nothing.

---

## DEVIATIONS FROM THE LANE BRIEF (all disclosed, none silent)

1. **ChiNext is split at 2020-08-24** into `chinext_10pct_pre2020` / `chinext_20pct_post2020`
   and never pooled, enforcing the brief's never-pool rule structurally. The raw board label
   survives only inside the v0 parity gate, which must reproduce v0's *pooled* published ladder.
2. **The benchmark leg (§3) was added after the first run** and is labelled post-hoc. Without
   it, 11 cells would have been reported as clears; with it, none survive. Reporting the first
   number without the control would have answered the operator's decision question wrongly.
3. **The implementable `peak_first` sibling** was added beside the brief's `peak_best` upper
   bound, so the foresight premium is a number rather than a caveat.
4. **f2 and f5 are not used.** f2 (turnover ratio) needs shares outstanding, which this store
   does not carry; f5 (near-limit-prev) is this instrument's own population B one bar earlier
   and would be near-tautological as a conditioner on it. The brief named f1/f3/f4/f6/f7/f8 and
   that is exactly the set used.
5. **The regime dial is read from a pinned git blob**
   (`b1348fe6a320fdd2479650a6dfc13dd977adf933`) rather than a scratch file, so the input is
   reproducible, cannot be edited under the run, and leaves no untracked artifact. In-tree wins
   if the salvage lane merges.

---

## WHAT THIS DOES **NOT** ESTABLISH

- Nothing here is a promotion, a gate, a ranker or a signal. Display tier.
- Every outcome is measured on **daily bars**: every peak is a daily high, every exit an open.
  Nothing here says an intraday exit into the O3 gap is available, only that the gap exists.
- The `peak_best` book requires foresight and is an **upper bound**. The `peak_first` sibling
  is the implementable version and is much smaller.
- C12 compares a **bundle**. Attention, supply at the limit and the cause of stopping short are
  not separated.
- The benchmark leg controls for the board key's own drift on the signal's own sessions. It does
  **not** control for size, liquidity, sector or volatility exposure — a cell that beats the
  universe mean may still be paid for by carrying more risk than the universe carries.
- Survivors-only, pre-expansion universe; slippage unmodelled; fills assumed at the printed open.
- **A null on any construction here closes that construction only.** The ORE LEDGER below is the
  search space this lane did not touch.

---

## ORE LEDGER

| Ore | Why it is still ore | Cost |
|---|---|---|
| **Other signal families on the window target** | Four signals were priced. Volume-shape, sector-cohort breadth, L1's gap-band conditioner, W2-B's 龙回头 pullback state and the failed-seal cohort are all untested **against this outcome**. | one lane |
| **H beyond 10 sessions** | The charter's "trajectory" has no stated length. H = 20/30 and a time-to-target clock are untested. | one lane, same instrument |
| **Intraday window exits** | The O3−O2 gap is the single largest quantity this lane found and it is unreachable from daily bars. Minute bars (v0's Stage-4 gap list) would turn the capacity bound into an exit policy. | collector-dependent |
| **Stop-loss / trail / scale-out overlays** | Every book here is entry + fixed-H exit. | one lane |
| **Window outcomes on the failed-seal cohort** (W2-B's 13,871 events) | W2-B measured that cohort against tomorrow's board only. Its O1/O2/O3 window outcomes have never been measured; both instruments already exist. | one lane |
| **Decomposing the window from the board** | O2/O3 are monotone in N while O1 is flat, which *implies* the ladder reaches the window through the board channel. Measuring P(window \| N, no board at T+1) would settle it. | small |
| **zt_pool-universe replication** | Only 29.0% of zt_pool names are in this store. The cheapest external check available. | small |
| **Soft-label model integration** (L3 ore #10) | The window outcome is graded — cum/w and peak/w are natural regression labels and this lane thresholded them into rates. | one lane |
| **Per-name effects** | Every table pools names within a board key; concentration is measured only as top5_name_share. | one lane |
| **Post-expansion re-run** | Survivors-only. Every rate here is measured on names that lived. | re-run, no new code |
| **Entry anchors other than the T+1 open** | W2-B showed the T-close anchor is fillable for non-sealed populations; the big-day and near-miss signals could be entered at the T close. | small, W2-B's machinery |
| **The ChiNext-20% S3 H=10 thread** | The one cell positive on both weightings in both windows with positive excess, failing only the fit-window excess t (1.89 < 2.0), with a losing median and a right-tail payoff. Post-expansion re-run and a longer fit window would settle it. | re-run |

---

## REPRODUCE

```
TZ=UTC python3 research/cn_prophet_audit/window_target_battery_v1.py
```

Deterministic; two runs are byte-identical apart from `generated_utc` and `runtime_sec`.
`build_head_sha` in the vintage block **by construction** pre-dates the commit carrying this
file and will differ on any re-run after commit; `base_sha` and `data_store_sha` are the stable
vintage identity. Requires the L2 dial blob (pinned SHA, fetched via `git cat-file`); if it is
unreachable every regime cell prints NULL and S1 loses its regime leg — reported, not patched.
