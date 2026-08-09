# CN WINDOW-TARGET BATTERY v1 — rerating windows + the sub-limit big-day class

**Program** CN LIMIT-MOVE ALPHA, Wave 3, lane W3-A
**Tier** display / audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits. No LLM is involved.
**Instrument** `research/cn_prophet_audit/window_target_battery_v1.py` (deterministic, 39.8 s)
**Data** `research/cn_prophet_audit/WINDOW_TARGET_BATTERY_V1_2026-08-09.json`
**Builds on** v0 footprint (`claude/cn-limit-footprint-v0`) · L1 continuation rider (`claude/cn-limit-w1-rider`) · L2 board-ecology dial (`claude/cn-limit-w1-regime-salvage`) · W2-B weakness battery (`claude/cn-limit-w2-weakness`) · blinded map C12
**Reviewed** a commissioned adversarial review (statistics + code) reported 3 blockers and 9 lesser findings against the first build. All are addressed; the changes are pre-registered as amendments A1–A6 in §DEVIATIONS. **Three headline numbers moved — see §WHAT MOVED.**

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

**1. THE AUCTION PRICES THE WINDOW TOO. No implementable construction survives its own drift
control, and on the main board the sign is negative everywhere.** 99 (signal × H × variant ×
board-key) cells were evaluated against the pre-registered two-window bar. **10 clear it. 2
survive the drift control — and both are `peak_best`, the foresight-requiring upper bound that
was never a strategy.** On main, all **48 of 48** implementable window-cells (fixed-H and
peak-first; 4 signals × 3 horizons × 2 windows) are **negative in excess of the same-session
universe return**, sign uniform, **25 of 48 at |t| ≥ 3**:

| Signal (main board, H=10, fixed-H) | fit excess / t | holdout excess / t |
|---|---|---|
| S2 first board N=1 | **−1.288% / −10.25** | **−0.948% / −4.56** |
| S1 f3 top-decile × regime hot | **−2.293% / −3.21** | **−4.393% / −2.41** |
| S4 near-miss untouched | **−1.147% / −4.00** | −0.293% / −0.46 |
| S3 big-day non-board | **−0.549% / −6.01** | **−0.445% / −3.05** |

The daily-resolution null is now close to total: it covers the board (W1), weakness entries
(W2-B), and — as of this lane — the sub-limit big day, the multi-session cumulative window,
and the window's peak.

**2. THE FLAGSHIP CELL, POST-FIX, PLAINLY.** S3 (big-day non-board) on
**chinext_20pct_post2020** at H=10, fixed-H exit — the only implementable cell that clears in
both windows — on complete windows only, with its excess on matched censoring and matched date
sets:

| | fit | holdout |
|---|---|---|
| n trades / dates / names | 491 / 205 / 195 | 2,287 / 747 / 341 |
| date-equal net | +2.432% | +1.494% |
| date-clustered t | **+2.65** ✓ | **+2.62** ✓ |
| mean per-trade net | +1.508% | +0.733% |
| median net / win rate | **−0.929% / 46.64%** | **−2.198% / 43.42%** |
| p10 / p90 / worst | −14.4% / +19.8% / −32.2% | −17.7% / +22.3% / −47.2% |
| universe on the same sessions | +0.893% | +0.501% |
| **excess net** | **+1.539%** | **+0.993%** |
| **excess t** | **+1.75** ✗ | **+1.98** ✗ |

Every one of the cell's dates carries a benchmark (`dates_missing_benchmark: 0`), so its
expectancy on the excess's own dates is identical to its full-sample figure — the date-set
mismatch amendment A5 exposes elsewhere does not bite here.

**It clears the pre-registered bar in both windows and FAILS the drift control in both** —
narrowly, at t = 1.75 and 1.98 against a 2.0 bar. Said plainly: *the cell is not a finding.*
Its payoff shape argues the same way — the median trade **loses** in both windows and the win
rate is under 50%, so the positive mean is a right tail, on one board key whose fit window is
15 months long. The first build reported this cell at **+1.299% per trade / t +3.32**; that
number was inflated by truncated windows and is **retracted** (§WHAT MOVED).

**3. The two cells that DO beat their control are the ones you cannot trade.** Both are S3 ·
ChiNext-20% · `peak_best` (H=5: excess +2.054 / t 2.49 fit, +0.913 / t 2.31 holdout; H=10:
+2.396 / t 2.26 fit, **+2.029 / t 3.55** holdout). `peak_best` sells into the *best* open in
the window after a 1.5w drawup — it requires knowing in advance which open that is. Its
implementable sibling `peak_first` fails the control in the holdout (+0.830 / t 1.86).
**The only thing that beats the drift control is foresight** — a capacity measurement of what
the window contains, not an edge.

**4. THE CENTRAL MEASUREMENT — the big-day class is weakly conditioned and sign-unstable,
where the board is strongly and monotonically conditioned.** Both windows, main board:

| Conditioner | P(board T+1) fit / holdout | P(big-day T+1) fit / holdout |
|---|---|---|
| ladder N = 1 | 16.80% / 15.94% | 7.47% / 7.44% |
| ladder N = 2 | 40.37% / 29.68% | 6.92% / 6.65% |
| ladder N = 3+ | **61.87% / 47.26%** | **3.62% / 5.32%** |
| regime cold | 15.68% / 17.18% | 7.53% / 7.14% |
| regime hot | **36.27% / 25.30%** | 6.69% / **9.11%** |
| six eras, 2011→2026 | 17.38% … 32.86% | 5.39% … 7.88% |

P(board) is **monotone in the ladder in both windows** and spans 15.7–61.9% (3.9×). The
big-day rate spans 3.6–9.1% (2.5×) and moves **non-monotonically and with unstable sign**: it
*falls* with the ladder, and the one cell where it rises materially — holdout regime-hot,
9.11% on n = 2,507 — has the **opposite** sign to its own fit cell (6.69%, *below* cold).
Not "unconditional", but: nothing this program conditions on ranks the big day in a way that
holds across both windows.

**5. The same features that rank the board do not rank the big day.** Identical rows,
identical fit-window cuts, top decile vs rest (main board, lift ×, fit / holdout):

| Feature | P(board T+1) | O1 big-day non-board |
|---|---|---|
| f6_gap_pct | **3.96 / 2.63** | 0.73 / 0.72 |
| f3_runup_5 | **2.46 / 2.09** | 0.73 / 1.11 *(sign-unstable)* |
| f8_consec_up_days | 1.68 / 1.69 | 0.74 / 1.10 *(sign-unstable)* |
| f4_sector_heat | 1.50 / 1.36 | 0.94 / 2.65 *(sign-unstable)* |
| f7_dist_52w_low | 1.12 / 1.05 | 1.11 / 1.39 |
| f1_vol_z20 | 0.87 / 0.80 | 0.64 / 0.71 |

Only **f7_dist_52w_low** has a big-day lift above 1 in both windows, and it is 1.1–1.4× — the
weakest signal in the set. f1 is *below* 1 on every outcome in both windows: W1's anti-monotone
volume finding, reproduced on a new target. **These are point estimates with no interval and
no test**; `stable_sign` is a sign agreement across two windows, nothing more.

**6. MOST OF A RERATING WINDOW IS A PEAK YOU CANNOT SCHEDULE.** O3 (max drawup reached) minus
O2 (still there at the scheduled exit), main board:

| Window | peak reached | held to exit | retained |
|---|---|---|---|
| H=5, ≥ 0.8w — fit / holdout | 61.5% / 58.0% | 30.3% / 23.6% | **49.3% / 40.6%** |
| H=5, ≥ 1.5w — fit / holdout | 33.5% / 28.4% | 18.4% / 13.3% | **55.1% / 46.8%** |
| H=10, ≥ 2.5w — fit / holdout | 24.1% / 19.4% | 12.9% / 8.1% | **53.7% / 41.7%** |

Roughly half in fit and closer to 40% in holdout of the windows that *touched* a target still
hold it at a fixed exit. That gap is where an intraday exit policy would have to live, and it
is not reachable from daily bars — which is exactly why the only control-beating cells in §3
are the foresight ones. This measures what is missing; it is not a claim that it is
collectable.

**7. C12 (blinded map) — the near-miss discontinuity is real and runs AGAINST the near-miss.**
Matched on (board key, split, prior ladder N, f3 quintile), a close in [0.85w, the limit) whose
high *never touched* the board is a materially **worse** state than a matched seal — main
board, both windows:

| Outcome (main, standardised to the near-miss cells) | fit ratio | holdout ratio |
|---|---|---|
| P(board T+1) | **0.38×** | **0.31×** |
| O2 cum H5 ≥ 1.5w | 0.56× | 0.49× |
| O3 peak H5 ≥ 1.5w | 0.54× | 0.58× |
| O1 big-day non-board | 0.70× | 1.58× *(sign-unstable — no claim)* |

Support: 2,400 near-miss rows in 14 cells (fit) and 972 in 12 cells (holdout), of which 8 and
7 respectively are THIN. **Two caveats materially limit the match**, both now printed in the
JSON: **prior ladder N carries 95.3–97.4% of the near-miss weight at N = 0**, so that leg of
the match is near-vacuous and the comparison is carried almost entirely by the f3 quintile;
and the **STAR arm is voided entirely** (161 real near-miss rows, no fit-window f3 support,
therefore no comparison in either window). **The difference is BUNDLED** — attention, supply
at the limit, and whatever stopped the name short are not separated. Ratios are point
estimates with no interval.

**8. Where the program's weight should go.** The buyable class is *more* buyable — the big-day
signal offers a fillable T+1 open **98.98%** of the time on main against **93.15%** for the
first board and **58.07%** for the f3×hot cohort — so fillability was never the binding
constraint on this target. What binds is that the class carries no daily-resolution
information that survives a drift control. The live directions are the ones the daily bar
cannot see (intraday exits into the §6 gap, seal-queue and auction-imbalance data) and the
universe expansion — not another daily conditioner on the same 1,836 names.

---

## WHAT MOVED (first build → this build)

| Number | first build | this build | cause |
|---|---|---|---|
| Flagship S3·ChiNext·H=10 fixed-H, **holdout per-trade net / t** | +1.299% / +3.32 | **+0.733% / +2.62** | A1 — truncated windows were priced at a mark-to-market close |
| **Cells surviving the drift control** | "0 of 11" | **2 of 10**, both `peak_best` | A2 — 66 peak cells had no control built; "untested" was reported as "failed" |
| C12 **STAR near-miss population** | 0 (asserted) | **161 rows, arm voided** | A3 — totals were taken after the support filter |
| Roll / forced-close claim in §THE BOOK | "not driving any result" | **retracted** | those were truncated windows, not locked-exit rolls |
| Big-day headline | "essentially UNCONDITIONAL" | "**weakly conditioned, sign-unstable**" | fit-only citation; holdout regime-hot is 9.11% |

The truncated tail was the whole of the first defect and is worth seeing directly: on
ChiNext-20% the **133 truncated holdout trades** (37 dates, **100% force-closed**) averaged
**+11.03%** net, and main's 1,560 truncated holdout trades over just 95 dates averaged
**+4.21%**. Those are mark-to-market prints at the edge of an exchange closure or of the
store, and they were being pooled into the headline.

---

## PRE-REGISTRATION (written before the first run)

- **Split** 2021-11-26 — v0's computed 70/30 date, frozen. **One holdout pass.** Every
  threshold, band edge, exit rule, cost bar, cell floor and signal was fixed before the first
  number was read. **No pre-registered value was changed by the amendments below**; A1–A6 fix
  censoring, controls and receipts.
- **Outcomes**, all scaled by w (the name-day's own limit width):
  - **O1 big-day** — return[T+1] ≥ 0.6w **and not** a tolerant limit-up close at T+1, so
    big-day and board partition the ≥ 0.6w class exactly. Sibling **O1-incl-boards** printed.
  - **O2 window-cum** — close[T+H]/close[T] − 1 ≥ θw, H ∈ {3,5,10}, θ ∈ {0.8,1.5,2.5}.
  - **O3 window-peak** — max(high[T+1..T+H])/close[T] − 1 ≥ θw, same grid.
  - **O4 / C12** — near-miss (close ≥ 0.85w, high never at the limit price) vs sealed closes,
    matched on (board key, split, prior ladder N cohort, f3 quintile).
- **Conditioning** — v0's f1/f3/f4/f6/f7/f8, ladder N at T, i5 regime tercile at T, era.
  **Timing:** v0's Stage-3 convention measures features at T−1 predicting T. This lane keeps
  that offset exactly and shifts the frame one bar forward — features at **T**, outcomes over
  **T+1..T+H** — so a feature is always measured on the last close before the first outcome bar
  in both studies. Feature *definitions* are v0's, unchanged.
- **Cuts** — every quantile cut computed on **fit-window rows only**, per board key, on
  **tolerant-basis rows only**. A frozen cut does **not** stay a decile out of sample, and the
  realised OOS share is now printed beside the fit share (amendment A4): ChiNext-20% f3 top
  decile is 10.08% of fit rows and **16.57%** of holdout rows; main regime-hot is 33.19% of fit
  rows and **13.84%** of holdout rows. Exact ties at the cut are **0.000%** for every
  continuous feature, so the first build's "ties" explanation of an over-sized decile was
  wrong; the cause is distribution shift.
- **Signals** (≤ 4, fixed before running): S1 f3 top decile × regime hot; S2 first board N=1;
  S3 big-day non-board; S4 near-miss untouched. **S4 ⊂ S3 and S1 ⊂ the board population** —
  the four are not independent tests and are not counted as such.
- **Book** — entry at the T+1 open, fillable only; fixed-H exit at the open of T+H+1 (L1's E3
  with k = H) with L1's locked-exit rolls; 15 bp round trip. `hold_sessions` counts entry bar
  to exit bar **inclusive**, so a complete fixed-H trade reports H+1 and is **not** comparable
  to L1's `hold_sessions`.
- **Decision bar** — a cell CLEARS only if its date-equal-weighted net expectancy is positive
  **and** its date-clustered t ≥ 2 in **both** windows with n_dates ≥ 30 in each.
- **Window overlap — ONE treatment, chosen in advance: cluster by START DATE.** Restricting to
  non-overlapping starts would delete the ladder, since consecutive board days *are* the
  ladder. Consequence, accepted: row n is **not** an independent-observation count; every book
  expectancy collapses to per-date means before any t is formed. Measured overlap (share of
  rows whose H=10 window overlaps a prior row of the same name, calendar-day upper bound):
  S2 29.7%, S3 36.3%, S4 5.4%, S1 27.1%.
- **Inference scope, stated once.** The date-clustered standard error is a **BOOK-ONLY** gate.
  Rate tables carry Wilson intervals computed on **overlapping, non-independent rows** — read
  them as a width indication, not a test. Feature lifts and C12 ratios carry **no interval and
  no test at all**, and none is claimed.

---

## COVERAGE RECEIPT

| | |
|---|---|
| Raw store | `data/china_stocks_raw`, 1,842 names — **BACK-ADJUSTED, not nominal** |
| Names kept | 1,836 (1 ST-excluded, 5 thin/unreadable) — main 1,243 · ChiNext 351 · STAR 242 |
| Window | 2011-01-01 → 2026-08-07 · 4,981,168 bars, **4,843,577 live** |
| Bars excluded | zero-volume 133,781 · IPO 2,793 · ex-div open jump 620 |
| Populations | **A** board days 60,298 · **C** big-day non-board 77,605 · **B** near-miss untouched 4,289 (B ⊂ C) |
| Trades | 1,127,223 eligible → **1,083,201 priced, 44,022 truncated and excluded** |
| Sector map | 1,716 tickers / 12 sectors (current membership applied to 15 y — v0's caveat, inherited by f4) |
| Universe gap | zt_pool names present in raw: 514 / 1,770 (**29.0%**) |
| Vintage | base `3e8ec0ada0c` · data-store `3babbce7b5f` |

**Window truncation and its root cause (amendment A1).** The forward chain reuses v0's
**10-calendar-day** T→T+1 pair rule as its *step* rule, so any exchange closure longer than
that truncates every open window at once, market-wide. Measured: **7 closure sessions**, of
which four are market-wide at exactly 11 calendar days —

| Last session before the closure | names truncated | gap |
|---|---|---|
| 2026-02-13 (Chinese New Year) | 1,816 | 11 d |
| 2024-02-08 (Chinese New Year) | 1,750 | 11 d |
| 2023-09-28 (National Day) | 1,740 | 11 d |
| 2020-01-23 (Chinese New Year) | 1,375 | 11 d |

Truncated share of rows: **3.44% at H=3, 4.45% at H=5, 6.55% at H=10**. The step rule was
*documented* rather than widened, deliberately: widening it would move every outcome
denominator that the commissioned review verified as exact, for a 3–7% recovery. Widening it
properly is an ore item.

**ST band bound.** ST/*ST is excluded from a **single snapshot** (asof 2026-07-06), of which
only **one** name is present in this store. There is no ST membership history, so a name that
was ST in the past and is not ST today carries a 10% (or 20%) band on bars where the real band
was **5%**. On those bars w is overstated, every w-scaled threshold is too high (O1/O2/O3
**undercount**), the limit price sits too far away (the bar is scored non-board and fillable
when it may have been sealed at 5%), and the sellable/unfillable judgements are wrong. The
bound is the ST share of listings on any historical date — of order 2–5% — and it **cannot be
measured from this store**. v0 made the same exclusion; this lane discloses the consequence
rather than patching it.

**Store basis.** L1's `price_basis_audit` measured this store as back-adjusted, correcting
v0's "nominal/unadjusted" header. Adjustment **preserves returns**, so every return, gap,
cumulative window and drawup here is unaffected; only the round-to-tick limit *price* is, and
v0's 0.002 tolerance is the cushion that absorbs it.

**Survivors only, pre-expansion.** Delisted names are absent, so every down-tail — limit-down
rates, worst trades, forced closes — **reads better than the truth**. A sibling Codex lane is
expanding the universe; these numbers are pre-expansion. This lane touched no collector, no
Tushare surface and no universe store.

### Gates that had to pass before any number above was read

| Gate | Result |
|---|---|
| **v0 ladder parity** (this panel is v0's panel) | **PASS — 15/15 published cells, exact n, rate to published precision** |
| **Corruption experiment** — every bar after 2019-01-02 replaced with garbage, conditioning arrays recomputed, pre-cut values compared **bitwise** | **PASS**, 30 tickers, 12 arrays each |
| **f4 date-locality** — drop every row after the cut, re-derive the sector-heat map | **PASS**, identical |
| **Book-implementation parity** (new, A2) — the bar-walking loop vs the vectorised universe kernel, on complete windows with zero rolls | **PASS**, max abs diff **7.9e-08** |
| **i5 dial** — trailing-window property | **PASS** (predicate hardened by A6: a missing comparison now FAILS, and the forward-window difference is required) |
| **Determinism** | two runs of this build compared field-by-field: identical apart from `generated_utc` / `runtime_sec` |

`is_board` / `is_bigday` / `is_nearmiss` are pure functions of (live, lu, ret, touched, width);
those five inputs are what the corruption experiment pins, and the receipt names them that way
rather than claiming to have tested the flags directly. The i5 **target-date indexing** claim
is **inherited** from W2-A's producer-level verification and re-read in the producer source —
it is not re-derived here, because the parquet no longer carries the pairs it was built from.

---

## 1 — THE BIG-DAY CLASS (O1)

The class the operator asked about, made an outcome for the first time. Main board, board-day
population; denominators are rows with a usable T+1 bar:

| | fit | holdout |
|---|---|---|
| rows | 33,132 | 17,289 |
| P(board T+1) | 25.37% | 19.93% |
| **P(big-day, not a board)** | **6.92%** | **7.19%** |
| P(≥ 0.6w including boards) | 32.29% | 27.12% |

The big day is **a fifth to a quarter** of the ≥ 0.6w mass — not a rounding class — and its
conditioning behaviour is in DECISION SUMMARY §4: a 2.5× total span against the board's 3.9×,
non-monotone, and sign-unstable on the one conditioner that moves it.

---

## 2 — THE WINDOW (O2 / O3)

Window outcomes **are** monotone in N (main, fit, O2 cum H5 ≥ 1.5w: 12.75 → 25.19 → 46.55%).
That is not a second edge. Since O1 is flat-to-falling in N, the ladder's grip on the
multi-session window must arrive through the board channel — a board is worth ≈ 1w on its own,
so a ladder that predicts boards mechanically predicts cumulative windows. This is an
**inference from the two tables**, not a decomposition; measuring P(window | N, no board at
T+1) would settle it and is an ore item.

The peak-vs-close gap is in DECISION SUMMARY §6. Two further readings: the gap **widens in the
holdout** (retention 53.7% → 41.7% at H=10 ≥ 2.5w), and the peak is far more common than the
close — at H=5 ≥ 0.8w, **61.5% (fit) / 58.0% (holdout)** of board days reach the target at some
point intraday, while only **30.3% / 23.6%** still hold it at the scheduled exit.

---

## 3 — THE BOOK

99 cells at the pre-registered bar; **10 clear; 2 survive the benchmark, both `peak_best`.**
After amendment A2 **no cell is untested** — the first build left all 66 peak cells without a
control and reported them as having failed one.

**The benchmark leg is an addition by this lane, beyond the brief's letter, and is disclosed as
such; A2 extended it to every exit rule.** The control is the *identical* trade — same entry
(T+1 open, fillable), same **exit rule**, same complete-window censoring — taken on every live
name of the same board key and aggregated per session. Universe levels (net of the same 15 bp),
fixed-H:

| Board key | H=10 fit | H=10 holdout |
|---|---|---|
| main (875–1,197 names/session) | +0.371% | +0.149% |
| chinext_20pct_post2020 (249–317 names/session) | **+0.927%** | +0.349% |

**One difference from the signal leg remains and is bounded rather than hidden**: the universe
leg does not *roll* a locked exit — it requires the scheduled exit bar to be sellable and drops
the bars that fail (count in `benchmark_leg.exit_unsellable_bars_dropped`). The signal leg's
roll rate is printed on every cell and is **0.00%** on the flagship cell in both windows. Every
excess also prints the signal's expectancy **on the excess's own dates** beside the full-sample
figure, plus what the dropped dates were worth (amendment A5), so the two legs are never read
against different date sets.

**The pre-registered bar is reported unchanged.** `CLEARS_vs_BENCHMARK` and
`positive_on_BOTH_weightings` are labelled **post-hoc** in the JSON and are not folded into the
bar — moving a pre-registered bar after seeing results is the exact failure this design exists
to prevent.

Other book facts worth keeping:

- **S1 (f3 top decile × regime hot) is the worst book in the study.** Main, H=10, fixed-H:
  excess **−2.293% (t −3.21) fit** and **−4.393% (t −2.41) holdout**. Buying the strongest
  momentum in the hottest tape is a *paid* negative — W1's anti-monotone result reproduced
  against a window target on an independently-cut conditioner.
- **Entry availability is not the constraint.** Fillable T+1 opens: S3 98.98%, S4 93.62%,
  S2 93.15%, S1 58.07% (main). The fillability tax that made L1's ladder unbuyable barely
  touches the big-day class — and the class still carries no surviving edge.
- **Truncated windows are counted, never headline.** 44,022 trades sit in
  `the_book.truncated_windows` flagged `EXCLUDED_FROM_THE_PRICED_BOOK`, 100% force-closed by
  construction.
- **The foresight premium is the whole of the surviving result.** `peak_best` beats its
  implementable sibling `peak_first` by ~0.9–1.6 pp date-equal-weighted at H=10, and it is the
  only variant that clears the drift control anywhere.

---

## 4 — C12, THE NEAR-MISS MAP

Headline and the two support caveats are in DECISION SUMMARY §7. Mechanics worth recording:

- **Why prior N.** A near-miss has no ladder of its own (its 连板 is 0 by construction), so
  matching on the event-day N would have produced *no overlapping support at all*. The match
  is on the tolerant board streak ending at **T−1**, capped at 3+ — W2-B's convention. Its
  weight is 95.3–97.4% concentrated at N = 0, which makes that leg near-vacuous; stated rather
  than implied.
- **Shared edges.** f3 quintile edges are cut on the fit window of the **pooled** matched
  population per board key, so both arms are binned identically.
- **Standardisation.** The sealed arm is re-weighted to the near-miss arm's own cell
  distribution; cells where either arm is empty are dropped from both, and the surviving
  support, the dropped rows and the thin-cell count are all printed.
- **Voided arms print as voided (A3).** STAR has 161 real near-miss rows and 878 sealed rows
  but only 152 fit-window f3 observations — below the 200 floor — so no edges are cut and it
  contributes nothing. The first build reported its population as **zero**.
- **ChiNext-20% is unstable and thin** — the fit arm (38 rows, 6 cells, all thin) says the
  near-miss is worse on every outcome; the holdout arm says it is better on next-day outcomes
  and worse on 5-day windows. **No claim.**

---

## HONESTY GATES, AND WHERE THEY BIT

- **Date-clustered t beside per-trade stats on every book cell.** It bit hard: the flagship
  ChiNext cell has a *positive* date-equal mean and a *negative* per-trade **median** in both
  windows. Both are printed; neither carries a claim alone. **Scope is book-only** — see
  §PRE-REGISTRATION, "Inference scope".
- **Denominators never conflated.** Every cell prints n, n_dates, n_names and
  top5_name_share. O2/O3 use their own per-H denominators, the truncated-window count is
  printed, and after A1 the book, the rate tables and the benchmark all censor identically.
- **Multiplicity per family, never across.** Rate tables 172 cells, book 99, C12 50 — expected
  false positives at 5%: 8.6 / 5.0 / 2.5. **No below-chance reading is taken anywhere.**
- **`*_NA` levels are data-availability slices**, flagged in every record, never conditioners,
  never carrying a lift.
- **Basis-pure cuts.** Every cut is on tolerant-basis rows; the strict column is used for
  nothing.
- **A control that cannot fail is worse than none** — A6 found exactly that in the i5 dial
  predicate, where a missing comparison silently passed.

---

## DEVIATIONS AND AMENDMENTS

**Pre-registration deviations (disclosed from the first build):**

1. **ChiNext is split at 2020-08-24** into `chinext_10pct_pre2020` / `chinext_20pct_post2020`
   and never pooled. The raw board label survives only in the v0 parity gate, which must
   reproduce v0's *pooled* published ladder.
2. **The benchmark leg was added after the first run** and is labelled post-hoc throughout.
3. **The implementable `peak_first` sibling** was added beside the brief's `peak_best` upper
   bound, so the foresight premium is a number rather than a caveat.
4. **f2 and f5 are not used.** f2 needs shares outstanding, which this store lacks; f5 is this
   instrument's own population B one bar earlier and would be near-tautological. The brief
   named f1/f3/f4/f6/f7/f8 and that is exactly the set used.
5. **The regime dial is read from a pinned git blob**
   (`b1348fe6a320fdd2479650a6dfc13dd977adf933`), so the input is reproducible and leaves no
   untracked artifact. In-tree wins if the salvage lane merges.

**Amendments after the first run (commissioned adversarial review).** None moves a
pre-registered value; all fix censoring, controls or receipts. Full text in
`pre_registration.amendments_after_first_run`.

| | Severity | Change |
|---|---|---|
| **A1** | BLOCKER | Truncated forward windows are removed from the **priced** book and reported in their own block. They were force-closed at a mark-to-market last close and pooled into every headline, while the rate tables and the benchmark both excluded them — three parts of one file disagreeing about the same window. Root cause receipted, not silently changed. |
| **A2** | BLOCKER | The benchmark is built for **all three exit rules** by applying the same peak rule to the unconditional cohort under the same censoring. Cells with no control are labelled CONTROL-NOT-BUILT and counted separately from cells that failed one (currently zero of each). |
| **A3** | BLOCKER | C12 arm populations are counted **before** the support filter; an arm voided by the fit floor prints as voided with its true population. |
| **A4** | SHOULD-FIX | Cut receipts print realised **OOS** shares beside fit shares; the false "ties" explanation is replaced with the measured cause (distribution shift), with exact ties printed (0.000%). |
| **A5** | SHOULD-FIX | Every excess prints the signal's expectancy on the **excess's own dates** plus what the dropped dates were worth. |
| **A6** | SHOULD-FIX | The i5 dial verdict FAILS on a missing comparison and requires the forward-window difference; the target-date claim is scoped as **inherited**, not measured here. |

Also corrected: inference scope stated per table (book-only clustering; lifts and C12 ratios
labelled point estimates; Wilson caveat cross-referenced); `hold_sessions` documented as H+1
and L1-incomparable; the peak-exit comment corrected (the untriggered fallback is the one path
that can settle past e+H, and it is excluded from the priced book); the ST band bound
disclosed; the runtime and determinism receipts reconciled with the shipped JSON.

---

## WHAT THIS DOES **NOT** ESTABLISH

- Nothing here is a promotion, a gate, a ranker or a signal. Display tier.
- Every outcome is measured on **daily bars**: every peak is a daily high, every exit an open.
  Nothing here says an intraday exit into the §6 gap is available, only that the gap exists.
- The two cells that beat the drift control are **`peak_best`** — they require foresight and
  are an **upper bound**, not a strategy.
- C12 compares a **bundle**, on a match whose prior-N leg is near-vacuous, with the STAR arm
  voided entirely.
- The benchmark leg controls for the board key's own drift on the signal's own sessions. It
  does **not** control for size, liquidity, sector or volatility exposure — a cell that beats
  the universe mean may still be paid for by carrying more risk than the universe carries.
- Survivors-only, pre-expansion universe; slippage unmodelled; fills assumed at the printed
  open; ST bands wrong on an unmeasurable slice of historical bars.
- **A null on any construction here closes that construction only.** The ORE LEDGER is the
  search space this lane did not touch.

---

## ORE LEDGER

| Ore | Why it is still ore | Cost |
|---|---|---|
| **Other signal families on the window target** | Four signals were priced. Volume-shape, sector-cohort breadth, L1's gap-band conditioner, W2-B's 龙回头 pullback state and the failed-seal cohort are untested **against this outcome**. | one lane |
| **H beyond 10 sessions** | The charter's "trajectory" has no stated length. H = 20/30 and a time-to-target clock are untested. | one lane, same instrument |
| **Intraday window exits** | The O3−O2 gap is the largest quantity this lane found, and the only control-beating cells are the foresight ones that live inside it. Minute bars would turn the capacity bound into an exit policy. | collector-dependent |
| **A forward chain that tolerates exchange closures** | A1 documented the 11-day CNY / National-Day truncation rather than widening the step rule, to protect verified denominators. Widening it (pre-registered, denominators re-verified) recovers 3–7% of rows. | small |
| **Stop-loss / trail / scale-out overlays** | Every book here is entry + fixed-H exit. | one lane |
| **Window outcomes on the failed-seal cohort** (W2-B's 13,871 events) | Measured against tomorrow's board only; its O1/O2/O3 outcomes have never been measured. Both instruments exist. | one lane |
| **Decomposing the window from the board** | O2/O3 are monotone in N while O1 is not, which *implies* the ladder reaches the window through the board channel. P(window \| N, no board at T+1) would settle it. | small |
| **A risk-matched control** | The benchmark equalises drift, not exposure. A size/liquidity/volatility-matched cohort would test whether the surviving `peak_best` cells are paid for by risk. | one lane |
| **C12 with a non-vacuous ladder match** | prior N carries ~96% of the weight at N = 0. A conditioner with real spread across both arms would make the match do work. | small |
| **STAR C12 arm** | 161 near-miss rows exist and are unmatched for want of 48 more fit-window f3 observations. A lower floor with disclosure, or a pooled-edge variant, recovers it. | trivial |
| **zt_pool-universe replication** | Only 29.0% of zt_pool names are in this store. The cheapest external check available. | small |
| **Soft-label model integration** (L3 ore #10) | The window outcome is graded — cum/w and peak/w are natural regression labels and this lane thresholded them into rates. | one lane |
| **Per-name effects** | Every table pools names within a board key; concentration is measured only as top5_name_share. | one lane |
| **Post-expansion re-run** | Survivors-only. Every rate here is measured on names that lived. | re-run, no new code |
| **Entry anchors other than the T+1 open** | W2-B showed the T-close anchor is fillable for non-sealed populations. | small, W2-B's machinery |

---

## REPRODUCE

```
TZ=UTC python3 research/cn_prophet_audit/window_target_battery_v1.py
```

Deterministic: two consecutive runs of this build were compared field-by-field and are
identical apart from `generated_utc` and `runtime_sec` (39.8 s shipped). `build_head_sha` in
the vintage block **by construction** pre-dates the commit carrying this file and will differ
on any re-run after commit; `base_sha` and `data_store_sha` are the stable vintage identity.
Requires the L2 dial blob (pinned SHA, fetched via `git cat-file`); if it is unreachable every
regime cell prints NULL and S1 loses its regime leg — reported, not patched.
