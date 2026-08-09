# CN BOARD ECOLOGY — regime instruments v1

**Lane:** CN LIMIT-MOVE ALPHA, Wave 1, L2 (board ecology / regime instruments) ·
**Builds on:** `research/cn_prophet_audit/limit_move_footprint_v0.py` (PR #4999).
**Instrument:** `research/cn_prophet_audit/board_ecology_regime_v1.py` ·
**Frozen numbers:** `BOARD_ECOLOGY_REGIME_V1_2026-08-08.json` ·
**Series artifact:** `board_ecology_series_v1.parquet` (9,277 board-sessions) ·
**Runtime:** ~16s · **Window:** 2011-01-04 → 2026-08-07 · **Basis:** `data/china_stocks_raw`.

**Tier: display / audit. MEASUREMENT ONLY.** Nothing here ranks, sizes, gates, admits or
promotes anything. No LLM is involved at any point. **No statistic is pooled across board
types**, and ChiNext is never pooled across its 2020-08-24 band change.

---

## DECISION SUMMARY

1. **The instruments exist, are committed, and pass the mania sanity check.** Six daily
   board-level dials over 3,786 main-board sessions. Main-board 2015-05→09 vs the full-window
   mean: first boards 38.4 vs 10.2, limit-ups 58.8 vs 13.3, max active ladder **7.3 vs 4.2**
   (12.4–13.3 in May–June 2015 alone); 2024-09→10: first boards 23.3, ladder 5.4, 炸板 count
   **36.9 — higher than 2015's 25.6**. Quiet 2023: 7.2 / 8.5 / 2.5. The dials light up where
   they must.
2. **THE HEADLINE, and it inverts the practitioner's dial.** Between years, breadth and
   continuation move *together* (v0's era finding). **Within a year they move opposite.** Once
   the quintiles are recut inside each calendar year and every year gets one vote,
   `i1_first_board_count` has a **median top/bottom ratio of 0.724 and a mean −4.21pp**, with
   **12 of 16 years negative**; `i2_limit_up_total` gives 0.795 / −2.79pp / 12 of 16. The naive
   pooled reading (holdout 1.068× / 1.069×) is the era clock, not the ecology. **涨停家数 read
   as a same-year dial gets the sign backwards.**
3. **The strongest era-robust instrument is the market's own continuation print, not any
   breadth count.** `i5_realized_continuation_ma5` — the 5-session mean of "of the names whose
   prior usable bar was a limit-up, what share held today" — is the only instrument that is
   monotone (rho **1.0**), sign-stable fit→holdout, AND survives the era-neutral test.
   **Holdout top-vs-bottom quintile: 26.73% vs 12.61% = 2.121×** (n=1,010 / 1,293 rows;
   47 / 161 dates). Era-neutral: median ratio **1.183**, mean **+2.97pp**, **12 of 16 years**.
   The raw (un-smoothed) `i5_realized_continuation` is weaker but steadier: holdout 1.578×,
   era-neutral 1.063× / +2.95pp / 11 of 16.
4. **炸板率 IS a real inverse dial pooled, and it does NOT survive the era control.** Direction
   confirmed everywhere the practitioner claims it: full-window first→second 20.94% → 14.54%
   across quintiles (**0.694×**, rho −0.9), holdout **0.724×**, r(d+1) fit 0.766 → holdout
   0.710 (sign-stable). But era-neutral it is a coin flip — first→second median ratio
   **0.974**, mean −1.09pp, **9 of 16 years**; r(d+1) median ratio **0.988**, mean −0.70pp,
   **8 of 16 years**. **Printed as a near-null under the era control, not promoted.**
5. **The ladder-leader cascade is REAL same-day and nearly gone by the next day.** On main
   board at the declared headline stratum H ≥ 4 (469 leader-failure vs 1,052 leader-extend
   sessions): same-day continuation *with the leaders themselves removed* is **19.53% vs
   25.72% (0.759×)**, year-equal-weight **−2.67pp, 11 of 16 years**. The next-day channel —
   P(first→second) for the failure day's own first boards, which is the tradeable one —
   shrinks to **15.61% vs 17.13% (0.911×)**, year-equal-weight −1.52pp, **10 of 16 years**, and
   at H ≥ 5 the year-equal-weight sign **flips positive (+2.36pp)**. 高标断板 marks a bad *day*;
   it barely marks a bad *tomorrow*.
6. **The weekend-fermentation hypothesis is CONFIRMED, and the sharper test is the calendar
   gap, not the weekday.** P(first→second) by the calendar gap between the first board and the
   session that grades it: **1 day 15.47% (yearEW 13.87%) · 3 days 19.43% (18.01%) · 4–7 days
   21.78% (19.90%) · 8–10 days 34.20% (22.91%)** — monotone in non-trading days, over 15–16
   years each. Read from the other side, Monday prints the week's highest realized continuation
   (29.15% pooled / **25.40%** year-equal-weight vs Thursday's 20.97% / 20.22%).
7. **The suspension confound was tested and came back empty.** Every usable first-board pair in
   this study is a **market-wide** calendar gap: 0 of 1,147 gap-≥4 pairs is a name-specific
   suspension. Suspension-resumption cannot be driving #6 — those pairs are removed upstream by
   the zero-volume exclusion and the 10-day pair rule.
8. **M5 — THE NUMBER THE PROGRAM NEEDS. Our regime dials undercount the market by ~2.7×, and
   the bias is NOT stable.** Against the market-wide vendor pool on 36 clean weekday dates:
   median undercount **2.748×** (first boards 2.667×), pooled 2.545×, but **min 1.49× to max
   10.0×, IQR/median 0.53**. The dial's *level* is not comparable across dates without this
   caveat.
9. **M5 side finding, one-directional and load-bearing: inside the universe we DO hold, we
   over-detect.** Recall of the vendor is **99.79%** (949/951) but precision is **77.85%**
   (949/1,219) — 270 names we call limit-ups the vendor's pool does not list, **51.5%** of them
   admitted by the 0.2% cushion. Restated against only the events both sources agree on, the
   true undercount is **3.269×**, not 2.545×.
10. **M5 independently re-confirms v0's definition adjudication, from a direction v0 could not
    use.** v0 argued the tolerant close is primary from 连板 agreement *within already-matched*
    rows. Set recall is a different test and agrees: tolerant recovers **99.79%** of the
    vendor's limit-ups, **strict only 52.16%** — while strict buys almost no precision (79.11%
    vs 77.85%). The cushion is a cushion.
11. **The ladder SHAPE survives the undercount even though the LEVEL does not.** Vendor vs ours
    on the clean dates, share of limit-ups at each 连板: 83.46/11.67/2.97/1.13/0.39 vs
    **83.35/12.22/2.87/1.07/0.41**. Our curated slice is close to an unbiased *sample* of the
    ladder distribution. The exception is the 6+ tail (0.39% vs **0.08%**) — and correspondingly
    our `i3_max_active_ladder` is **lower than the market's on 21 of 36 dates, mean gap 1.81
    boards**. **The 高标 dial is the one instrument this universe measurably cannot see.**
12. **The zt_pool store's `date` is a SCRAPE STAMP, not a trade date, from 2026-07-02 onward.**
    11 of 47 dates are Saturdays/Sundays and **all 11** carry a payload byte-identical to the
    preceding Friday's. Diagnosed, worked around (36 clean dates), **not fixed here** — the L0
    lane owns the heal.
13. **ChiNext is a printed null for this lane.** In its ±20% band era it has 873 fit / 515
    holdout first-board rows, and **8 of 14 instruments collapse to a single realised bucket**.
    Its base rate also halves inside the era (13.06% → 6.60%), so even the era-split is not
    like-for-like. No ChiNext regime conclusion is drawn. STAR is not attempted at all.
14. **Every Wilson interval below is understated.** Outcomes inside one session are massively
    correlated — that correlation *is* this lane's subject. The effective sample size of a
    date-conditioned bucket is nearer its `n_dates` than its `n`. Both are printed, plus a
    per-date-first estimator, so the reader never has to take the interval at face value.

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Price basis | `data/china_stocks_raw` — nominal/unadjusted. The adjusted twin would fabricate limit misses. |
| Names | 1,842 files · 1,836 kept · 1 skipped ST · boards **main 1,243 · chinext 351 · star 242 · bse 0** |
| Ticker-days | 4,981,168 · live after exclusions 4,843,576 |
| Events | limit-up **60,298** primary / 31,897 strict · 炸板 proxy **35,901** primary / 16,361 strict |
| Excluded bars | zero-volume/suspension 133,781 · IPO window 2,793 · ex-div suspect 621 |
| Sessions in the series | main 3,786 (2011-01-04 → 2026-08-07) · chinext 3,786 · star 1,705 (2019-07-29 →) |
| **THE BINDING CAVEAT — the universe is curated, and a REGIME dial inherits that directly** | A per-name feature can survive a curated universe; a market-level *count* cannot. Only **1 of 100** current ST names and **514 of 1,770 (29%)** of the names that hit the vendor limit-up pool exist here. **M5 measures the consequence: median 2.748× undercount, 3.269× vendor-consistent, IQR/median 0.53.** Read every count in the series as a curated-slice count, never as 涨停家数. |
| 高标 blindness | our `i3_max_active_ladder` is below the market's on 21 of 36 clean dates, **mean gap 1.81 boards**; our 6+ ladder share is 0.08% against the vendor's 0.39%. |
| Detector precision | inside the shared universe: recall of the vendor **99.79%**, precision **77.85%** (51.5% of the excess is the 0.2% cushion). Our `i2` level is inflated relative to a vendor-consistent count. |
| Survivorship | the store holds the CURRENT listed universe; delisted names are absent, which biases `i2_limit_down_total` most. Its ladder was not measured at all (ORE LEDGER). |
| Clustering | Wilson intervals are printed by house convention and are **understated**; read `n_dates`. |
| Determinism | ticker-sorted, no sampling anywhere. Two consecutive runs produce byte-identical JSON (modulo `generated_utc`/`runtime_sec`) and an identical parquet MD5. |

---

## DEFINITIONS (stated inline, as required)

- **`w`** — `engine.china_microstructure.limit_width_for_date`, imported: STAR 20%; ChiNext 20%
  on/after `CHINEXT_WIDE_DATE` 2020-08-24 else 10%; main 10%; BSE 30%. Board from
  `_board_from_ticker`. Never reimplemented.
- **`limit_up_close` (PRIMARY)** — `close ≥ round(prev_close×(1+w), 2) × (1 − 0.002)`, v0's
  adjudicated primary (the 0.2% is a feed-precision cushion; v0 measured 43.4% of the marginal
  events moving strictly *more* than the full band, which is impossible for a real limit-up).
  Strict `close ≥ round(prev_close×(1+w), 2)` is carried in parallel.
- **`连板 N`** — consecutive PRIMARY limit-up closes ending on the bar; any non-limit bar,
  including an excluded one, resets to 0. **first board** = N is 1.
- **`T → T+1`** — the name's next usable bar, at most 10 calendar days later.
- **Exclusions** — ST cohort (all dates); STAR/ChiNext first 5 sessions and pre-2014 listings'
  first session; ex-div suspects (`|open − prev_close|/prev_close > 1.5w`); zero-volume bars.

### The six instruments (all observable at that session's own close)

| # | Column | Definition |
|---|---|---|
| I1 | `i1_first_board_count` | names printing 连板 == 1 at d |
| I2 | `i2_limit_up_total` / `i2_limit_down_total` / `i2_net_breadth` | all limit closes at d, any ladder; net = up − down |
| I3 | `i3_max_active_ladder` | the 高标 height — max 连板 across all names limit-up at d |
| I4 | `i4_zhaban_count` / `i4_zhaban_rate` | **炸板 proxy**: `high ≥ limit_price × (1 − 0.002)` and NOT a limit-up close; rate = count / (count + `i2_limit_up_total`) |
| I5 | `i5_realized_continuation` | of the names whose PRIOR usable bar was a limit-up, the share closing limit-up at d |
| I6 | `i6_near_limit_count` | return ≥ 0.95w at d and not a limit close |

Rolling forms: `_ma5` (5 sessions, ≥3 non-null). De-trended forms: `_rel250` (value ÷ its own
trailing 250-session median, ≥60 sessions) — both computed on the board's own session index and
both backward-looking only.

**I4 IS A PROXY AND ITS LEVEL IS NOT 炸板率.** A name that traded through the band at 09:31 and
one that tagged it at 14:58 are the same row, and a name that merely printed a high inside the
cushion without ever sealing is counted the same as one that sealed and broke. Its main-board
mean is **0.402** (strict-touch 0.367) — well above the 10–25% a practitioner would quote, exactly
because "reached the price" is not "formed a queue". The strict column is carried through and
M3 is re-run on it. What survives is the *direction*, not the level.

---

## THE SERIES (STAGE B)

| Board | Sessions | I1 mean/max | I2 up mean/max | I2 down mean | I3 mean/max | I4 count mean | I4 rate mean | I5 mean (null sessions) |
|---|---|---|---|---|---|---|---|---|
| main | 3,786 | 10.22 / 473 | 13.32 / 510 | 6.37 | 4.20 / 25 | 8.02 | 0.402 | 0.227 (67) |
| chinext | 3,786 | 1.75 / 99 | 2.38 / 116 | 1.23 | 1.71 / 25 | 1.32 | 0.389 | 0.238 (1,344) |
| star | 1,705 | 0.46 / 64 | 0.52 / 98 | 0.07 | 0.33 / 10 | 0.32 | 0.407 | 0.096 (1,254) |

Rates are null (not 0) where the denominator is empty. ChiNext's 1,344 and STAR's 1,254 null I5
sessions are the printed reason neither board carries a regime conclusion here.

---

## M6 — MANIA SANITY (main board, monthly means)

| Window | I1 | I2 up | I2 down | I3 ladder | I4 count | I4 rate | I5 |
|---|---|---|---|---|---|---|---|
| **full window** | 10.22 | 13.32 | 6.37 | **4.20** | 8.02 | 0.402 | 0.227 |
| 2015-05 | 33.6 | 53.1 | 12.1 | **12.4** | 23.0 | 0.318 | 0.434 |
| 2015-06 | 33.5 | 47.7 | 70.8 | **13.3** | 18.9 | 0.344 | 0.358 |
| 2015-07 | 51.1 | 104.8 | 147.7 | 3.9 | 42.3 | 0.383 | 0.353 |
| 2015-08 | 39.7 | 47.2 | 116.7 | 4.2 | 16.1 | 0.361 | 0.263 |
| 2015-09 | 32.4 | 35.8 | 53.9 | 3.2 | 26.2 | 0.434 | 0.160 |
| 2024-09 | 28.9 | 35.5 | 1.3 | 3.2 | 13.9 | 0.352 | 0.324 |
| 2024-10 | 17.4 | 34.8 | 16.3 | 5.4 | **61.1** | 0.454 | 0.314 |
| *2023 baseline* | *7.2* | *8.5* | *1.95* | *2.5* | *5.8* | *0.412* | *0.158* |

Two readings the table gives for free. **May–June 2015 is the ladder mania** (I3 12–13) and
**July 2015 is the crash** (I2 down 147.7, I3 collapses to 3.9) — the same year, opposite
ecologies, which is precisely why a year is not an era. And **2024-10 is a 炸板 event, not a
breadth event**: I1 *halves* from September while the 炸板 count more than quadruples to 61.1.

Top main-board sessions by limit-up count: 2015-07-13 (510), 2015-07-09 (474, I1 **473** — the
mass-rescue day, I5 = 1.00), 2015-07-10 (463), **2024-09-30 (419, I1 358)**, 2015-09-16 (323).

---

## M1 — REGIME CONDITIONALS (main board)

Unit: one row per (name, T) where the name printed its **first** board at T and has a usable
T+1 bar. Outcome: it closes limit-up again at T+1. **Dates** are quantiled on the instrument's
value; edges are fitted on the pre-2021-11-26 window and applied unchanged to the holdout. Fit
2,647 sessions / 24,555 rows (base **16.80%**); holdout 1,139 sessions / 13,735 rows (base
**15.95%**).

Three era controls, in increasing severity: **holdout** (out-of-sample dates), **within-year
pooled** (quintiles recut inside each calendar year), and **era-neutral** (within-year *and*
every year gets one vote — the strictest, and the one that matters).

| Instrument | fit | **holdout** | rho | within-yr pooled | **era-neutral median ratio** | **mean pp** | years in direction |
|---|---|---|---|---|---|---|---|
| `i5_realized_continuation_ma5` | 2.361 | **2.121** | **1.0** | 1.327 | **1.183** | **+2.97** | **12/16** |
| `i5_realized_continuation` | 1.709 | **1.578** | **1.0** | 1.446 | **1.063** | **+2.95** | **11/16** |
| `i1_first_board_count_ma5` | 1.426 | 2.510 | 0.9 | 1.187 | 0.973 | −0.08 | 7/16 |
| `i4_zhaban_rate` *(inverse)* | 0.687 | **0.724** | −0.6 | 0.826 | 0.974 | −1.09 | 9/16 |
| `i2_limit_down_total` *(inverse)* | 0.866 | 0.790 | **−1.0** | 1.020 | 1.023 | −0.27 | 10/16 |
| `i2_limit_up_total_rel250` | 1.053 | 1.229 | 0.0 | 1.001 | 0.900 | −1.86 | 6/16 |
| `i6_near_limit_count` | 1.227 | 1.211 | — | 1.798 | 0.953 | +0.16 | 2/8 |
| `i3_max_active_ladder` | 1.382 | 1.159 | 0.8 | 0.620 | 1.002 | −0.62 | 8/16 |
| `i2_limit_up_total` | 1.520 | 1.069 | −0.1 | 0.977 | **0.795** | **−2.79** | 12/16 *(inverse)* |
| `i1_first_board_count` | 1.167 | 1.068 | −0.2 | 0.918 | **0.724** | **−4.21** | 12/16 *(inverse)* |
| `i4_zhaban_count` | 0.652 | 1.331 | 1.0 | 0.563 | 0.912 | −4.53 | 10/16 · **UNSTABLE** |
| `i4_zhaban_rate_ma5` | 1.510 | 0.999 | −0.6 | 1.170 | 1.038 | −0.41 | 9/16 · **UNSTABLE** |
| `i2_net_breadth` | 1.030 | 0.943 | −0.3 | 1.043 | 0.835 | −1.60 | 6/16 · **UNSTABLE** |
| `i1_first_board_count_rel250` | 0.962 | 1.081 | 0.1 | 0.944 | 0.989 | −2.57 | 8/16 · **UNSTABLE** |

*rho* = Spearman between bucket index and bucket rate across every realised bucket — a
top-over-bottom ratio can be produced by one freak end cell, rho cannot. *UNSTABLE* = the fit
and holdout spreads disagree in sign.

### The winner, in full — `i5_realized_continuation_ma5`, holdout

| Bucket | value range | rows | dates | rate | Wilson 95% | per-date median |
|---|---|---|---|---|---|---|
| b0 | 0.000–0.106 | 1,293 | 161 | **12.61%** | 10.91–14.53 | 7.85% |
| b1 | 0.106–0.190 | 4,926 | 413 | 14.11% | 13.17–15.11 | 11.11% |
| b2 | 0.190–0.263 | 4,303 | 325 | 15.71% | 14.65–16.83 | 14.29% |
| b3 | 0.264–0.360 | 2,203 | 193 | 17.52% | 15.99–19.17 | 14.29% |
| b4 | 0.361–0.477 | 1,010 | 47 | **26.73%** | 24.10–29.55 | 18.62% |

Perfectly monotone in both fit and holdout, and the per-date-median column moves with the
pooled one — so it is not one huge session carrying the top cell. **Top-vs-bottom spread on the
holdout: 2.121×.**

### The sign flip, in full — `i1_first_board_count`, within-year quintiles

| Bucket (within-year) | rows | dates | rate |
|---|---|---|---|
| b0 (fewest first boards) | 1,328 | 565 | **19.05%** |
| b1 | 3,464 | 719 | 16.40% |
| b2 | 5,980 | 862 | 14.75% |
| b3 | 8,731 | 807 | 15.20% |
| b4 (most) | 18,787 | 833 | 17.49% |

U-shaped, with the **quiet** end highest. Year by year (each year's own quintiles): median
ratio **0.724**, mean **−4.21pp**, negative in **12 of 16** years. `i2_limit_up_total` behaves
identically (18.35% → 17.92%, median ratio 0.795, 12 of 16). The plain reading: on a quiet day
a first board is a *selected* event; on a mania day hundreds of names board indiscriminately
and each one is worth less. Across years the opposite holds, because mania years have both
more boards and a higher base rate. **Both are true. Only one of them is a same-year dial.**

### Double sort — holdout, `i1_first_board_count_ma5` × `i5_realized_continuation_ma5`

5×5 (4 of 25 cells THIN), collapsed to 3×3 (0 of 9 THIN):

| | I5 low | I5 mid | I5 high |
|---|---|---|---|
| **I1 low** | 10.64% (n=188) | 11.11% (n=72) | 24.00% (n=25) |
| **I1 mid** | 13.79% (n=870) | 16.37% (n=941) | 13.90% (n=403) |
| **I1 high** | 13.67% (n=3,380) | 15.07% (n=5,834) | **23.99% (n=2,022)** |

The 5×5 corners are sharper and tell the same story: within the **top** breadth bucket, the
continuation print separates 11.11% (n=432, 23 dates) from **29.63% (n=800, 22 dates)** — a
2.67× spread that breadth alone does not see. **Breadth is the wrong axis; ladder health is the
right one.** Read the 3×3's left column: more breadth buys ~3pp. Read its bottom row: more
ladder health buys ~10pp.

---

## M2 — LADDER-LEADER CASCADE (main board)

**Leader-failure day d:** every name that stood at the board's `i3_max_active_ladder` on the
previous session, and that has a usable bar at d, fails to close limit-up at d. **Leader-extend
day:** at least one holds. Strata declared *before* the measurement ran: headline H ≥ 4,
sensitivity H ≥ 3 and H ≥ 5. Of 3,785 main sessions: 2,081 extend, 1,599 fail, 66 no pairs, 39
undefined (no leader had a usable bar).

**The same-day statistic is circular unless the leaders are removed** — on a failure day the
leaders mechanically drag it down. Both versions are printed; only the first is load-bearing.

| Stratum | days fail / extend | same-day r **ex-leaders** | ratio | same-day r *(circular)* | next-day P(first→second) | ratio |
|---|---|---|---|---|---|---|
| H ≥ 3 | 695 / 1,362 | 18.35% vs 25.78% | **0.712** | *17.15% vs 30.37% (0.565)* | 15.39% vs 17.29% | 0.890 |
| **H ≥ 4** | 469 / 1,052 | **19.53% vs 25.72%** | **0.759** | *18.37% vs 30.19% (0.608)* | **15.61% vs 17.13%** | **0.911** |
| H ≥ 5 | 303 / 834 | 20.59% vs 26.39% | 0.780 | *19.41% vs 30.89% (0.628)* | 15.83% vs 16.77% | 0.944 |

Year-equal-weight (fail minus extend, percentage points):

| Stratum | same-day r ex-leaders | years negative | next-day first→second | years negative |
|---|---|---|---|---|
| H ≥ 3 | **−4.58pp** | 13/16 | −1.60pp | 10/16 |
| **H ≥ 4** | **−2.67pp** | 11/16 | −1.52pp | 10/16 |
| H ≥ 5 | **−4.69pp** | 11/15 | **+2.36pp** | 9/15 |

**Verdict: 高标断板, 情绪退潮 is confirmed as a same-day contagion and is close to a null as a
next-day signal.** The same-day effect is large (−6.2pp at H ≥ 4), survives removing the
leaders from the statistic, and is year-stable (11–13 of 16). The next-day effect is −1.5pp,
year-stable in only 10 of 16, and its sign *inverts* under year-equal-weighting at H ≥ 5. The
circular column is 0.565–0.628 — i.e. roughly **half of the naive same-day cascade is just the
leaders themselves**, which is exactly the artefact that would have been reported as a finding
had the leaders not been removed.

**ChiNext M2 is a printed null:** in the ±20% era only 6 failure days and 12 extend days clear
H ≥ 4, and 702 of 1,443 sessions have no usable pair at all. Its apparently spectacular ratios
(0.215, 0.341) rest on n = 9–14 rows and are reported in the JSON, not here.

---

## M3 — 炸板率 AS A DIAL (main board)

Practitioner claim: a high 炸板率 means fragile sentiment, so tomorrow should be worse.

| Channel | full-window | rho | fit | holdout | sign-stable | **era-neutral median ratio** | **mean pp** | years |
|---|---|---|---|---|---|---|---|---|
| P(first→second) at d | **0.694** | −0.9 | 0.687 | **0.724** | yes | **0.974** | −1.09 | 9/16 |
| r(d+1) | **0.724** | −0.9 | 0.766 | **0.710** | yes | **0.988** | −0.70 | 8/16 |
| *robustness: strict touch, P(first→second)* | *0.680* | *−0.9* | — | *0.972* | — | — | — | — |
| *robustness: strict touch, r(d+1)* | *0.726* | *−0.9* | *0.714* | *0.931* | *yes* | *1.050* | *−2.56* | *7/16* |

Full-window quintiles of `i4_zhaban_rate` at d against P(first→second):
**20.94% → 15.10% → 14.89% → 14.25% → 14.54%.** Clean, monotone through b3, and it holds
out-of-sample.

**And it does not survive the era control.** Recut inside each calendar year with one vote per
year, the effect is a coin flip on both channels (0.974 / 0.988; 9 and 8 of 16 years). The
strict-touch robustness column agrees on the full window (0.680) and then goes **flat in the
holdout (0.972)**. **Verdict: directionally right, out-of-sample stable, and mostly an era
proxy. Display tier, printed, not promoted.**

---

## M4 — DAY OF WEEK AND THE WEEKEND (main board)

### P(first→second) by the weekday of the first board T

| Weekday of T | n | rate | Wilson 95% | year-equal-weight | per-date median |
|---|---|---|---|---|---|
| Mon | 8,946 | 15.54% | 14.80–16.30 | 14.23% | 9.45% |
| Tue | 7,417 | 14.52% | 13.74–15.34 | 13.95% | 11.54% |
| Wed | 7,797 | **13.75%** | 13.00–14.53 | **13.22%** | 10.00% |
| Thu | 7,377 | 19.82% | 18.92–20.74 | 15.28% | 9.09% |
| **Fri** | 6,753 | **19.47%** | 18.55–20.44 | **18.05%** | 14.29% |

Thursday's pooled 19.82% collapses to 15.28% under year-equal-weighting — an era artefact.
Friday's holds at 18.05% and its per-date median is the highest of the week.

### The realized continuation print r(d), by the weekday of d — the mirror

| Weekday of d | sessions | pairs | rate | year-equal-weight |
|---|---|---|---|---|
| **Mon** | 736 | 8,950 | **29.15%** | **25.40%** |
| Tue | 762 | 11,769 | 21.22% | 19.74% |
| Wed | 769 | 9,948 | 21.46% | 20.79% |
| Thu | 766 | 9,951 | **20.97%** | **20.22%** |
| Fri | 753 | 9,244 | 25.84% | 22.14% |

Monday grades Friday's boards. Both tables are the same phenomenon seen from opposite ends.

### The control the hypothesis actually needs — the calendar gap

Weekend fermentation is a claim about **non-trading days**, not about Fridays. The gap between
a first board and the session that grades it separates the two:

| Calendar gap | n | rate | Wilson 95% | year-equal-weight | years |
|---|---|---|---|---|---|
| 1 (overnight) | 30,768 | 15.47% | 15.07–15.88 | **13.87%** | 16 |
| 2 | 23 | 26.09% | 12.55–46.47 | 28.47% | 4 |
| **3 (weekend)** | 6,352 | **19.43%** | 18.47–20.42 | **18.01%** | 16 |
| 4–7 | 606 | 21.78% | 18.68–25.24 | **19.90%** | 16 |
| 8–10 | 541 | 34.20% | 30.32–38.29 | **22.91%** | 15 |

**Monotone in the number of non-trading days, on the year-equal-weight column, with 15–16 years
behind every cell.** The load-bearing comparison is gap 1 vs gap 3 — 13.87% → 18.01%, a
**1.30× lift on n = 30,768 vs 6,352**, because those two cells cannot be anything but the
weekend. The 4–10 cells are an independent replication on *different weekdays* (public
holidays), and their pooled/year-equal-weight divergence (34.20% vs 22.91% at 8–10) says that
cell is era-concentrated — read the 22.91%.

**The suspension confound is measured, not assumed: 0 of 1,147 gap-≥4 pairs is name-specific.**
Every one is a market-wide shutdown. A 停牌 resumption bar cannot be driving this, because those
pairs are removed upstream by the zero-volume exclusion and the 10-day pair rule.

ChiNext's DOW tables are THIN and show no clean pattern (Tuesday highest r(d), Monday highest
first→second, n = 237–415); its gap-8–10 cell is 86.5% on n = 52 across 3 years — noise, not a
finding. Reported in the JSON, not adopted.

---

## M5 — ZT_POOL CROSS-VALIDATION (the mandatory honesty probe)

### 1. The date semantics are wrong, and were diagnosed before anything was computed

`data/china_zt_pool/pool.parquet` carries 47 dates, of which **11 are Saturdays or Sundays** —
including the 2026-08-08 row the brief flagged. All 11 carry a payload **byte-identical** to the
preceding Friday's on every column except `date`/`asof`. The store changed semantics mid-life:

- **2026-06-15 → 06-26** (`asof` 2026-07-06): a backfill, trade-date stamped, **no weekend rows
  at all**.
- **2026-06-30, 07-01**: `asof` = `date` + 1 — a trade date scraped the next morning.
- **2026-07-02 onward**: `asof` == `date`. The vendor endpoint returns the last trading day's
  pool and the writer stamps it with the **run date**, so weekends re-stamp Friday.

Taken at face value every Friday would be counted three times. **36 clean dates** survive
(weekday, non-duplicate, present in our tape); 11 weekend dates are dropped. The heal — a real
trade-date column, or de-duplication at write time — belongs to the L0 lane; this lane only
refuses to be fooled.

> **This diagnosis is pinned to the PRE-HEAL store.** The sibling L0 lane (PR #5059,
> `claude/cn-limit-w1-dataheal`) rewrites `data/china_zt_pool/pool.parquet`. When it lands,
> re-running this instrument will legitimately produce different M5 numbers — more clean dates,
> nothing to drop — and that is the heal working, not this instrument breaking. The detection
> logic is defensive by construction: weekend and payload-duplicate rows are identified from the
> data itself (day-of-week plus a payload hash against every earlier date), never from a
> hardcoded date list, so the same code stays correct on both sides of the heal. The undercount
> and precision figures below should be **re-measured after #5059 merges**; only the *level* of
> the clean-date count should move.

**Empirically confirmed, not asserted:** on the clean weekday rows, `date` **is** the trade
date — vendor tickers match our same-day limit-up set at **99.79%** (949/951) versus **14.72%**
for the previous session.

### 2. The undercount factor

| | median | mean | p25 | p75 | min | max | IQR/median |
|---|---|---|---|---|---|---|---|
| all limit-ups | **2.748×** | 3.103 | 2.186 | 3.650 | 1.494 | 10.000 | **0.533** |
| first boards | **2.667×** | 3.293 | 2.320 | 3.585 | 1.468 | 11.500 | 0.474 |

Pooled **2.545×** · **vendor-consistent 3.269×** (see below) · vendor rows that are names we
hold at all: **30.66%**.

**The bias is NOT stable.** A stable undercount would mean our dials are the market's dials on a
different scale — safe to quantile, since a monotone rescaling preserves quantile membership.
An IQR of 0.53 medians means the factor itself moves day to day, so **a bucket boundary drawn
on our counts is not the same market state on every date**. This is the single largest threat to
M1's count instruments — and it is a further reason the era-neutral verdict on `i1`/`i2`
(summary #2) should be read as "these counts are not a clean dial", not merely "these counts
have the opposite sign".

### 3. Inside the universe we hold, we over-detect

| | matched | ours only | vendor only | recall | precision |
|---|---|---|---|---|---|
| PRIMARY (tolerant) | 949 | **270** | 2 | **99.79%** | **77.85%** |
| strict | 496 | 131 | — | **52.16%** | 79.11% |

**51.48%** of the 270 ours-only rows are admitted by the 0.2% cushion and rejected by the strict
test; the other half are a genuine difference of opinion about the event (or a vendor pool
filter we cannot see). Either way the consequence is one-directional: **our `i2` level is
inflated relative to a vendor-consistent count, so the true undercount is 3.269×, not 2.545×.**

**This also re-confirms v0's definition adjudication from a direction v0 could not use.** v0
argued from 连板 agreement *within already-matched rows*; set recall is an independent test and
says the same thing louder — tolerant recovers 99.79% of the vendor's limit-ups, strict only
52.16%, and strict buys 1.3 points of precision for 47.6 points of recall.

### 4. The ladder shape survives; the ladder HEIGHT does not

| 连板 | 1 | 2 | 3 | 4 | 5 | 6+ |
|---|---|---|---|---|---|---|
| vendor (share) | 83.46% | 11.67% | 2.97% | 1.13% | 0.39% | **0.39%** |
| ours (share) | 83.35% | 12.22% | 2.87% | 1.07% | 0.41% | **0.08%** |
| vendor (count) | 2,589 | 362 | 92 | 35 | 12 | 12 |
| ours (count) | 1,016 | 149 | 35 | 13 | 5 | 1 |

Near-perfect agreement through N = 5 — our curated slice is close to an **unbiased sample of the
ladder distribution**, which is why the *shape*-based instruments (I5, and the ladder tables in
v0) travel better than the *count*-based ones. The 6+ tail is the exception, and it shows up
directly in `i3_max_active_ladder`: ours is **lower on 21 of 36 dates**, equal on 14, higher on
1, **mean gap 1.81 boards**. **The 高标 is the one dial this universe measurably cannot see**,
which is independent corroboration of I3's era-neutral null in M1 (median ratio 1.002).

### 5. 炸板 proxy vs the vendor's failed_seals

Spearman **0.677**, Pearson 0.467, n = 36 dates (ours mean 17.5 names/day, vendor mean 180.4).
**These are not the same object.** Ours counts *names* that reached the band and closed below
it. The vendor's `failed_seals` is a per-name *count* of intraday seal breaks among names that
are **in** the limit-up pool — i.e. mostly names that did hold by the close, running 0–47 per
name. A Spearman of 0.68 says both track a common seal-fragility state; it is **not** a
validation of either as a measurement of the other, and it does not rescue I4's level.

---

## WHAT THIS DOES **NOT** ESTABLISH

- **No significance claim.** The tests used are spread magnitude, monotonicity across every
  realised bucket, sign stability across an independent time block, and a year-equal-weight era
  control. Never a p-value. Every Wilson interval printed is understated by clustering.
- **No causal claim anywhere.** M4's gap gradient is consistent with attention accrual over
  non-trading days; it is equally consistent with news accumulating over the same days, and the
  study cannot separate them.
- **Nothing here is a signal, a gate, or a ranker.** The gauntlet applies at promotion and
  nothing is being promoted. The counts are not tradeable levels — see the undercount.
- **The counts are not 涨停家数.** Median 2.748× undercount, unstable (IQR/median 0.53), and
  inflated within our own universe by a 77.85% precision. Anyone reading `i2_limit_up_total`
  as the market's limit-up count will be wrong by a factor that moves.
- **`i3_max_active_ladder` is measurably blind.** Mean 1.81 boards below the market's.
- **ChiNext and STAR carry no conclusion.** ChiNext: 8 of 14 instruments collapse to one bucket
  in the ±20% era and its base rate halves inside that era. STAR: not attempted.
- **A single instrument's era-neutral null is not a kill.** It closes *that construction* —
  a quintile of *that* daily value against *that* outcome on *this* universe. The ORE LEDGER
  below names the constructions that were never tested at all.

---

## ORE LEDGER / UNTESTED VARIANTS

THE ORE LAW binds this lane. A null here closes the **specific construction tested**, never the
search space. Every variant below was *not measured*, and no reader should treat this file's
coverage as the topic's coverage.

| # | Variant | Why it was not tested | Status |
|---|---|---|---|
| 1 | **题材 / concept-level heat** (板块 / 概念 limit-up counts) | needs a THS/同花顺 concept mapping we do not hold. Our sector map is a CURRENT GICS-ish classification, not the 概念 taxonomy the 打板 crowd trades. | **Wave 2** |
| 2 | **Volume-weighted ecology** (turnover-weighted first-board count, market turnover as heat) | the instrument set was frozen at six counts before the run. Volume is in the store — this is the cheapest next variant. | buildable now, out of scope |
| 3 | **Index-return interaction** (dials conditional on CSI300/CSI1000 same-day and trailing return) | no index series joined. A limit-up count on a +2% index day and a −2% index day are plausibly different objects and this lane cannot tell them apart. | **Wave 2** |
| 4 | **Northbound-flow interaction** (陆股通 net flow as a co-dial) | not joined; northbound daily disclosure was also suspended in 2024, so any such instrument has a hard coverage break. | Wave 2, with a coverage caveat |
| 5 | **Regime replication on the zt_pool (market-wide) universe** | 47 scrape dates, 36 clean. A regime measurement needs regimes; this history cannot contain two. **MEASURED-TOO-SHORT, not a null.** | blocked on history, not method |
| 6 | **Intraday heat propagation** (does the first hour's seal count predict the close's?) | daily bars only. v0 Stage-4 collector. | blocked on a collector |
| 7 | **炸板率 leading-vs-coincident decomposition** | M3 measures 炸板率 at d against d+1, which cannot separate "炸板率 predicts tomorrow" from "both are driven by one slow sentiment state". No innovation/residualised lead-lag was run — and given M3's era-neutral near-null, this is the variant most likely to contain the real signal. | buildable now, out of scope |
| 8 | **Regime × per-name feature crosses** (does v0's f3 run-up lift depend on the regime bucket?) | needs v0's per-name feature panel in the same process. | **Wave 2, with L1/L3** |
| 9 | **Seal-quality dials** (封单量 / 首封时间 aggregated to market level) | `seal_fund_yi` for 47 dates only, no first-touch time at all. v0 Stage-4 #1 is the unblocker. | blocked on a collector |
| 10 | **Limit-DOWN ecology as a regime dial** (跌停 breadth, down-ladder depth and its own cascade) | `i2_limit_down_total` is built, carried in the series and conditioned in M1 — but the down-**ladder**, its continuation rate and its own leader cascade were never measured. Survivorship bites hardest exactly here. | partially built; the down-ladder is untested |
| 11 | **ST-cohort and small-cap ecology** | the ST cohort is excluded wholesale (v0's rule) and the store carries 1 of 100 current ST names. The 打板 game lives disproportionately here. M5 measures the blindness; it does not fix it. | blocked on the universe |
| 12 | **A weighted or precision-corrected count instrument** | M5 shows the undercount is unstable and our precision is 77.85%. A count re-weighted by a modelled coverage factor was NOT attempted — with 36 overlap dates any such correction would be fitted on noise. | blocked on overlap history |

---

## DEVIATIONS AND CORRECTIONS

1. **Six controls were added that the brief did not name**, all of which attack the result
   rather than extend it: the **within-year re-quantile**, the **year-equal-weight** column
   (the one that flipped `i1`/`i2` and nulled `i4_zhaban_rate`), the **bucket-monotonicity
   rho**, the **calendar-gap / suspension split** in M4, the **per-date-first** estimator, and
   M5's **detection-precision** probe. No instrument was added after seeing results.
2. **A bug found and fixed mid-build, recorded rather than tidied away.** The by-year table
   originally hardcoded bucket 0 as "bottom". Because `searchsorted(..., side="right")` cannot
   return 0 when the 20th percentile equals the value floor, that made the bottom cell empty
   and the yearly spread `None` for every count instrument and for `i5` — i.e. the era check
   silently returned nothing while looking like it ran. Ends are now read from the **rows**,
   not the dates, which also fixes `i3`, whose bucket 0 ("no name held a board") contains zero
   first-board rows by construction.
3. **The 炸板 proxy uses the same 0.2% cushion as the close test, and this is a genuine
   deviation in spirit.** v0's cushion is justified by feed noise pushing a *close* above the
   band; for a *high* the same noise creates false touches, so the tolerant touch is the more
   permissive direction. The strict column is carried in full and M3 is re-run on it — where it
   holds on the full window and goes flat on the holdout, which is reported rather than
   averaged away.
4. **The instrument's ranking uses `max(spread, 1/spread)`**, so an inverse dial is not ranked
   last by construction. `|spread − 1|` would have buried `i4_zhaban_rate`.
5. **Self-inclusion is not corrected, deliberately.** A conditioned row is itself one of the
   day's first boards, so it adds exactly +1 to `i1` and `i2` on *every* conditioned row — a
   constant shift, not a differential bias. A leave-one-out would have made bucket membership
   row-level and reintroduced the weighting problem it was meant to solve.
6. **Not done, flagged instead:** the zt_pool trade-date/scrape-date defect (Summary #12) is
   the L0 lane's. Separately, `limit_move_footprint_v0.py`'s module docstring and its output
   `definitions.limit_up_close` block still describe **strict** as PRIMARY, while the code's
   `limit_up` column and its own `definition_adjudication` verdict use **tolerant** — the
   receipt is correct and the two prose sites are stale. Not touched from this lane.

---

## REPRODUCE

```
cd <repo root>
TZ=UTC python3 research/cn_prophet_audit/board_ecology_regime_v1.py
```

Deterministic — ticker-sorted, no sampling anywhere. Two consecutive runs produce byte-identical
JSON (modulo `generated_utc`/`runtime_sec`) and an identical parquet MD5. Runtime ~16s. Writes
`BOARD_ECOLOGY_REGIME_V1_2026-08-08.json` (every cell in this document plus the full bucket
tables, all three era controls per instrument, the per-year detail, the 5×5 double sort, all
three M2 strata under both same-day definitions, M3 under both touch definitions, and the full
per-date M5 reconciliation) and `board_ecology_series_v1.parquet` (9,277 board-sessions × 25
columns, no run-date stamp on any row).
