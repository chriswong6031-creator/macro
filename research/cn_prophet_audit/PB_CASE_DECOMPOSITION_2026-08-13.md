# P-B — case decomposition of the 300363-class first-board winners (2026-08-13)

Authority: `none_research_display_only`. Tier: display / audit tier — counts, orders and distributions of WINNERS only; not a promotion, not a gate, not a ranker, not a sizing input; no lift, no t-statistic, no interval and no selection-skill claim is quoted anywhere in this artifact.

**Winners only. There is no comparison arm.** Every count, order and distribution below describes names that DID print a first limit board out of a washout state. No lift, no t-statistic, no interval and no selection-skill claim appears anywhere in this artifact — the matched non-winner study is ore (§9) and needs its own preregistration.

Governing ruling: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`. Program home: `research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md` §3 (the P-B row). Pinned definitions: `washout_onset_w1.py` (W-P0), **imported — not re-derived**.

---

## 1. What was read, and how the cohort is built

One store: `data/china_stocks_raw`, through W-P0's own `build_panel()` over W-P0's own window **2011-01-01 → 2026-08-07** — 4,840,077 live bars, 1,779 names, 3,786 sessions. No embedded outcome column is read anywhere; the tolerant detector and the cold rule are W-P0's, reached by import.

A cohort **event** is a tolerant limit-up close whose **eve** — the name's previous panel session — was **cold** (no tolerant board in the prior 20 sessions). Every state in this file is read at the eve, so nothing is measured on the board bar itself. The eve→event pair must sit inside W-P0's own 21-day closure-tolerant step rule (§8 A1).

**Honest-N, whole run.** 26432 ev / 1724 names / 3585 sess first-board events; **15893 ev / 1597 names / 3262 sess in cohort** (dd250 ≤ −20% at the eve).

**Out of cohort, reported once as context and used nowhere else:** 10539 ev / 1672 names / 2697 sess — of which `d0_gt_m20` 9427 ev, `na` 1112 ev (`d0_gt_m20` = the drawdown was shallower than −20%; `na` = W-P0's 250-session high was not yet measurable, fewer than 200 bars of history). A first board printed from a shallower drawdown is a different physical object and is not folded in; an unmeasurable one is not silently treated as shallow.

## 2. Cohort — boards never pooled, eras never averaged

`chinext10` (SZ 300x/301x **before** 2020-08-24) and `chinext20` (on/after) are two populations, and neither shares a cell with `main` or `star`.

| board | cohort honest-N | d1 (−20..−35] | d2 (−35..−50] | d3 (≤−50) | arming-eligible honest-N | excluded: <60 sess lookback |
|---|---|---|---|---|---|---|
| `main` | 13606 ev / 1177 names / 3161 sess | 5835 | 4820 | 2951 | 13504 ev / 1177 names / 3118 sess | 102 |
| `chinext10` | 1444 ev / 208 names / 752 sess | 501 | 549 | 394 | 1441 ev / 208 names / 750 sess | 3 |
| `chinext20` | 569 ev / 224 names / 391 sess | 247 | 187 | 135 | 569 ev / 224 names / 391 sess | 0 |
| `star` | 274 ev / 140 names / 166 sess | 111 | 91 | 72 | 274 ev / 140 names / 166 sess | 0 |

_Arming-eligible = at least 60 prior sessions on the name's own axis (§8 A2). Excluded events stay in the cohort and presence tables._

### Per era (W-P0's own era boundaries, keyed on the event year)

| board | e1 2011 14 | e2 2015 mania | e3 2016 18 crackdown | e4 2019 21 revival | e5 2022 23 grind | e6 2024 26 current |
|---|---|---|---|---|---|---|
| `main` | 1977 / 651n | 1245 / 697n | 2152 / 803n | 3231 / 976n | 2086 / 843n | 2915 / 913n |
| `chinext10` | 187 / 74n | 176 / 92n | 603 / 172n | 478 / 178n | — | — |
| `chinext20` | — | — | — | 120 / 88n | 111 / 77n | 338 / 176n |
| `star` | — | — | — | 18 / 15n | 54 / 42n | 202 / 124n |

_Cells are `events / distinct names`. An empty cell is a board that did not exist in that era (chinext20 begins 2020-08-24), not a zero._

## 3. Footprint presence at the eve

Share of cohort events whose footprint was TRUE on the eve. These are presence shares among winners — they are not conditional board probabilities and cannot be read as any. **Two columns are true by construction and are not findings:** DD20 is 100% everywhere because the cohort IS the dd250 ≤ −20% class, and DD35 is 0% in `d1` and 100% in `d2`/`d3` because the bands are cuts of the same series. They are printed so the partition is auditable, not because they carry information.

**`main`**

| dd band | honest-N | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|
| `d1_m20_m35` | 5835 ev / 1144 names / 2387 sess | 100.0% | 0.0% | 47.34% | 53.26% | 11.91% | 18.75% | 32.96% | 30.64% |
| `d2_m35_m50` | 4820 ev / 1084 names / 2041 sess | 100.0% | 100.0% | 82.49% | 55.44% | 12.72% | 46.02% | 33.4% | 28.24% |
| `d3_le_m50` | 2951 ev / 908 names / 1111 sess | 100.0% | 100.0% | 97.26% | 54.9% | 10.67% | 73.47% | 27.52% | 28.77% |

**`chinext10`**

| dd band | honest-N | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|
| `d1_m20_m35` | 501 ev / 176 names / 372 sess | 100.0% | 0.0% | 39.92% | 53.09% | 13.37% | 19.96% | 29.14% | 27.94% |
| `d2_m35_m50` | 549 ev / 179 names / 399 sess | 100.0% | 100.0% | 78.51% | 56.28% | 9.84% | 41.35% | 33.88% | 28.78% |
| `d3_le_m50` | 394 ev / 148 names / 230 sess | 100.0% | 100.0% | 95.94% | 52.79% | 11.17% | 73.35% | 31.73% | 26.65% |

**`chinext20`**

| dd band | honest-N | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|
| `d1_m20_m35` | 247 ev / 150 names / 188 sess | 100.0% | 0.0% | 19.03% | 63.97% | 19.84% | 12.96% | 22.67% | 41.3% |
| `d2_m35_m50` | 187 ev / 137 names / 154 sess | 100.0% | 100.0% | 74.33% | 61.5% | 10.7% | 37.43% | 22.46% | 40.11% |
| `d3_le_m50` | 135 ev / 88 names / 108 sess | 100.0% | 100.0% | 91.85% | 63.7% | 17.78% | 55.56% | 28.89% | 26.67% |

**`star`**

| dd band | honest-N | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ |
|---|---|---|---|---|---|---|---|---|---|
| `d1_m20_m35` | 111 ev / 89 names / 83 sess | 100.0% | 0.0% | 14.41% | 56.76% | 13.51% | 8.11% | 16.22% | 40.54% |
| `d2_m35_m50` | 91 ev / 75 names / 57 sess | 100.0% | 100.0% | 70.33% | 67.03% | 28.57% | 24.18% | 17.58% | 43.96% |
| `d3_le_m50` | 72 ev / 50 names / 44 sess | 100.0% | 100.0% | 93.06% | 66.67% | 16.67% | 37.5% | 15.28% | 45.83% |

Legend: **DD20** dd250 <= -20% off the 250-session high (W-P0 S2, shallow cut) · **DD35** dd250 <= -35% off the 250-session high (W-P0 S2, deep cut) · **MA200** close below the 200DMA (W-P0 S3, `under_ma`) · **CONF** the Terminal oracle's 3D long state (W-P0 S1, `s1_3d_long`) · **CB** 3D crossover-buy within 2 3D bars (W-P0 S1, `s1_3d_cb_recent`) · **SECT** 40%+ of the name's sector members 35%+ off their own 250-session highs, leave-one-out (W-P0 S4) · **QB** 20-bar realised-vol rank in the bottom third (W-P0 S5a, `base_flag`) · **VZ** volume z-score of the bar > 1 (W-P0 S5a, `volz_band` above v1).

_Full band distributions (`below_band`, `dur_band`, `sect35_band`, `volz_band`) per board × dd band × era are in the JSON receipt under `presence`._

## 4. Arming order

**Arming** = the start of the FINAL true-run ending at the eve. A footprint that oscillates arms at the start of its LAST run, never its first (`verify.arming_is_final_true_run`). **Lead** = sessions from the arming session to the board. A footprint already true throughout the whole 60-session window is **censored** and printed `≥60` — a floor, never a value.

### 4a. Most frequent complete orders (CORE-4)

Over events where all four of the operator's named families armed: **DD20** (washout depth), **MA200** (basing), **CONF** (terminal confluence), **SECT** (sector-wide washout). Censored footprints form one leading tied group `{…}≥60` because their mutual order is unknowable from the window; uncensored ones follow earliest-first with their lead in parentheses.

**`main`** — all four armed on 2596 of 13504 arming-eligible cohort events (19.22%); 903 names, 999 sessions, 1432 distinct orders.

| arming order (earliest → latest) | events | % of all-four-armed |
|---|---|---|
| `{CONF,DD20,SECT,MA200}>=60` | 358 | 13.79% |
| `{DD20,SECT,MA200}>=60 > CONF(3)` | 24 | 0.92% |
| `{DD20,SECT,MA200}>=60 > CONF(2)` | 22 | 0.85% |
| `{DD20,SECT,MA200}>=60 > CONF(4)` | 20 | 0.77% |
| `{DD20,SECT,MA200}>=60 > CONF(21)` | 19 | 0.73% |
| `{DD20,SECT,MA200}>=60 > CONF(23)` | 18 | 0.69% |

**`chinext10`** — all four armed on 288 of 1441 arming-eligible cohort events (19.99%); 139 names, 187 sessions, 220 distinct orders.

| arming order (earliest → latest) | events | % of all-four-armed |
|---|---|---|
| `{CONF,DD20,SECT,MA200}>=60` | 47 | 16.32% |
| `{CONF,DD20,MA200}>=60 > SECT(2)` | 3 | 1.04% |
| `{DD20,SECT,MA200}>=60 > CONF(11)` | 3 | 1.04% |
| `{DD20,SECT,MA200}>=60 > CONF(12)` | 3 | 1.04% |
| `{DD20,SECT,MA200}>=60 > CONF(3)` | 3 | 1.04% |
| `{CONF,DD20,MA200}>=60 > SECT(1)` | 2 | 0.69% |

**`chinext20`** — all four armed on 87 of 569 arming-eligible cohort events (15.29%); 70 names, 77 sessions, 73 distinct orders.

| arming order (earliest → latest) | events | % of all-four-armed |
|---|---|---|
| `{CONF,DD20,SECT,MA200}>=60` | 13 | 14.94% |
| `{CONF,DD20,MA200}>=60 > SECT(1)` | 2 | 2.3% |
| `{CONF,DD20,SECT}>=60 > MA200(4)` | 2 | 2.3% |
| `CONF(17) > DD20(9) > SECT(3) > MA200(2)` | 1 | 1.15% |
| `CONF>=60 > DD20(24) > SECT(10) > MA200(9)` | 1 | 1.15% |
| `CONF>=60 > SECT(34) > MA200(23) > DD20(22)` | 1 | 1.15% |

**`star`** — all four armed on 25 of 274 arming-eligible cohort events (9.12%); 25 names, 22 sessions, 23 distinct orders.

| arming order (earliest → latest) | events | % of all-four-armed |
|---|---|---|
| `{CONF,DD20,SECT,MA200}>=60` | 3 | 12.0% |
| `DD20(35) > CONF(33) > MA200(30) > SECT(12)` | 1 | 4.0% |
| `DD20>=60 > MA200(53) > SECT(49) > CONF(4)` | 1 | 4.0% |
| `{CONF,DD20,MA200}>=60 > SECT(16)` | 1 | 4.0% |
| `{CONF,DD20,MA200}>=60 > SECT(40)` | 1 | 4.0% |
| `{CONF,DD20,MA200}>=60 > SECT(56)` | 1 | 4.0% |

_Per dd band × era signatures, and the full 8-footprint signature counts, are in the JSON under `arming_order`._

### 4b. Pairwise precedence (CORE-4 pairs)

Among events where BOTH footprints armed: how often the row's first-named footprint armed earlier. Pairs where both are censored are **unresolved** — never a tie and never a coin flip — and same-session armings are excluded from the strict denominator. Both counts are printed.

**`main`**

| precedence | rate | strict denom | both armed | unresolved (both censored) | same session |
|---|---|---|---|---|---|
| `DD20` before `MA200` | 86.96% | 4876 | 9569 | 4257 | 436 |
| `DD20` before `CONF` | 76.33% | 5472 | 7355 | 1863 | 20 |
| `DD20` before `SECT` | 78.26% | 3505 | 5467 | 1842 | 120 |
| `MA200` before `CONF` | 63.17% | 4334 | 5589 | 1239 | 16 |
| `MA200` before `SECT` | 49.92% | 3315 | 4701 | 1235 | 151 |
| `CONF` before `SECT` | 42.08% | 2360 | 2929 | 549 | 20 |

**`chinext10`**

| precedence | rate | strict denom | both armed | unresolved (both censored) | same session |
|---|---|---|---|---|---|
| `DD20` before `MA200` | 90.26% | 544 | 1006 | 431 | 31 |
| `DD20` before `CONF` | 72.82% | 585 | 781 | 195 | 1 |
| `DD20` before `SECT` | 64.93% | 365 | 616 | 245 | 6 |
| `MA200` before `CONF` | 57.37% | 448 | 577 | 127 | 2 |
| `MA200` before `SECT` | 37.25% | 357 | 512 | 142 | 13 |
| `CONF` before `SECT` | 33.58% | 265 | 345 | 79 | 1 |

**`chinext20`**

| precedence | rate | strict denom | both armed | unresolved (both censored) | same session |
|---|---|---|---|---|---|
| `DD20` before `MA200` | 94.48% | 145 | 310 | 161 | 4 |
| `DD20` before `CONF` | 80.93% | 257 | 359 | 101 | 1 |
| `DD20` before `SECT` | 85.47% | 117 | 177 | 59 | 1 |
| `MA200` before `CONF` | 65.24% | 164 | 213 | 48 | 1 |
| `MA200` before `SECT` | 60.87% | 92 | 134 | 38 | 4 |
| `CONF` before `SECT` | 39.53% | 86 | 109 | 23 | 0 |

**`star`**

| precedence | rate | strict denom | both armed | unresolved (both censored) | same session |
|---|---|---|---|---|---|
| `DD20` before `MA200` | 85.19% | 54 | 147 | 90 | 3 |
| `DD20` before `CONF` | 84.17% | 120 | 172 | 52 | 0 |
| `DD20` before `SECT` | 72.41% | 29 | 58 | 26 | 3 |
| `MA200` before `CONF` | 76.0% | 75 | 102 | 27 | 0 |
| `MA200` before `SECT` | 73.68% | 19 | 39 | 20 | 0 |
| `CONF` before `SECT` | 33.33% | 30 | 35 | 5 | 0 |

_All 28 pairs per board × dd band × era are in the JSON under `arming_order.pairwise`._

## 5. Lead-time distributions

Sessions from arming to the board, per footprint. Quantiles use the nearest-rank rule with the censored block at the top of the order, so a quantile landing inside it prints `≥60` rather than an imputed number. `armed%` is the share of the group's events on which the footprint was armed at all.

**`main`** — honest-N 13504 ev / 1177 names / 3118 sess (arming-eligible cohort events)

| footprint | armed% | n armed | Q1 | median | Q3 | cens ≥60 | med `d1_m20_m35` | med `d2_m35_m50` | med `d3_le_m50` |
|---|---|---|---|---|---|---|---|---|---|
| `DD20` | 100.0% | 13504 | 25 | ≥60 | ≥60 | 57.63% | 36 (n=5759) | ≥60 (n=4796) | ≥60 (n=2949) |
| `DD35` | 57.35% | 7745 | 12 | 41 | ≥60 | 39.78% | — (n=0) | 26 (n=4796) | ≥60 (n=2949) |
| `MA200` | 70.86% | 9569 | 16 | 52 | ≥60 | 46.63% | 28 (n=2740) | 59 (n=3961) | ≥60 (n=2868) |
| `CONF` | 54.47% | 7355 | 16 | 37 | ≥60 | 32.92% | 33 (n=3073) | 38 (n=2663) | 43 (n=1619) |
| `CB` | 11.94% | 1612 | 2 | 5 | 7 | 0.0% | 5 (n=687) | 5 (n=610) | 5 (n=315) |
| `SECT` | 40.48% | 5467 | 11 | 40 | ≥60 | 40.1% | 28 (n=1088) | 38 (n=2212) | 47 (n=2167) |
| `QB` | 31.86% | 4302 | 5 | 14 | 32 | 9.16% | 15 (n=1889) | 14 (n=1602) | 14 (n=811) |
| `VZ` | 29.41% | 3972 | 1 | 1 | 3 | 0.0% | 2 (n=1765) | 1 (n=1358) | 1 (n=849) |

**`chinext10`** — honest-N 1441 ev / 208 names / 750 sess (arming-eligible cohort events)

| footprint | armed% | n armed | Q1 | median | Q3 | cens ≥60 | med `d1_m20_m35` | med `d2_m35_m50` | med `d3_le_m50` |
|---|---|---|---|---|---|---|---|---|---|
| `DD20` | 100.0% | 1441 | 27 | ≥60 | ≥60 | 58.22% | 34 (n=501) | ≥60 (n=547) | ≥60 (n=393) |
| `DD35` | 65.23% | 940 | 14 | 46 | ≥60 | 41.38% | — (n=0) | 31 (n=547) | ≥60 (n=393) |
| `MA200` | 69.81% | 1006 | 14 | 49 | ≥60 | 43.94% | 19 (n=200) | 54 (n=429) | ≥60 (n=377) |
| `CONF` | 54.2% | 781 | 16 | 37 | ≥60 | 32.91% | 33 (n=266) | 37 (n=307) | 50 (n=208) |
| `CB` | 11.45% | 165 | 3 | 5 | 8 | 0.0% | 5 (n=67) | 5 (n=54) | 5 (n=44) |
| `SECT` | 42.75% | 616 | 18 | ≥60 | ≥60 | 52.27% | 49 (n=100) | ≥60 (n=227) | ≥60 (n=289) |
| `QB` | 31.51% | 454 | 5 | 14 | 30 | 5.73% | 15 (n=146) | 13 (n=184) | 15 (n=124) |
| `VZ` | 27.97% | 403 | 1 | 1 | 2 | 0.0% | 1 (n=140) | 1 (n=158) | 1 (n=105) |

**`chinext20`** — honest-N 569 ev / 224 names / 391 sess (arming-eligible cohort events)

| footprint | armed% | n armed | Q1 | median | Q3 | cens ≥60 | med `d1_m20_m35` | med `d2_m35_m50` | med `d3_le_m50` |
|---|---|---|---|---|---|---|---|---|---|
| `DD20` | 100.0% | 569 | 31 | ≥60 | ≥60 | 64.15% | 47 (n=247) | ≥60 (n=187) | ≥60 (n=135) |
| `DD35` | 56.59% | 322 | 17 | ≥60 | ≥60 | 51.86% | — (n=0) | 34 (n=187) | ≥60 (n=135) |
| `MA200` | 54.48% | 310 | 17 | ≥60 | ≥60 | 52.9% | 20 (n=47) | ≥60 (n=139) | ≥60 (n=124) |
| `CONF` | 63.09% | 359 | 16 | 35 | ≥60 | 33.98% | 33 (n=158) | 39 (n=115) | 30 (n=86) |
| `CB` | 16.34% | 93 | 3 | 5 | 7 | 0.0% | 5 (n=49) | 4 (n=20) | 5 (n=24) |
| `SECT` | 31.11% | 177 | 14 | 38 | ≥60 | 38.42% | 36 (n=32) | 56 (n=70) | 35 (n=75) |
| `QB` | 24.08% | 137 | 6 | 13 | 32 | 9.49% | 17 (n=56) | 12 (n=42) | 11 (n=39) |
| `VZ` | 37.43% | 213 | 1 | 2 | 4 | 0.0% | 2 (n=102) | 2 (n=75) | 2 (n=36) |

**`star`** — honest-N 274 ev / 140 names / 166 sess (arming-eligible cohort events)

| footprint | armed% | n armed | Q1 | median | Q3 | cens ≥60 | med `d1_m20_m35` | med `d2_m35_m50` | med `d3_le_m50` |
|---|---|---|---|---|---|---|---|---|---|
| `DD20` | 100.0% | 274 | 25 | ≥60 | ≥60 | 65.69% | 40 (n=111) | ≥60 (n=91) | ≥60 (n=72) |
| `DD35` | 59.49% | 163 | 29 | ≥60 | ≥60 | 59.51% | — (n=0) | 57 (n=91) | ≥60 (n=72) |
| `MA200` | 53.65% | 147 | 35 | ≥60 | ≥60 | 62.59% | 56 (n=16) | ≥60 (n=64) | ≥60 (n=67) |
| `CONF` | 62.77% | 172 | 13 | 41 | ≥60 | 31.98% | 34 (n=63) | 37 (n=61) | 50 (n=48) |
| `CB` | 19.34% | 53 | 1 | 3 | 5 | 0.0% | 2 (n=15) | 3 (n=26) | 3 (n=12) |
| `SECT` | 21.17% | 58 | 6 | 40 | ≥60 | 46.55% | 6 (n=9) | 26 (n=22) | ≥60 (n=27) |
| `QB` | 16.42% | 45 | 6 | 15 | 31 | 6.67% | 9 (n=18) | 15 (n=16) | 19 (n=11) |
| `VZ` | 43.07% | 118 | 1 | 2 | 4 | 0.0% | 2 (n=45) | 2 (n=40) | 3 (n=33) |

_The last three columns are the median lead inside each dd band, with that band's own armed count. Per board × era and per board × dd band × era distributions, with Q1/Q3 and censoring rates on every cell, are in the JSON under `lead_times`._

## 6. Worked example — `300363.SZ`, board 2026-08-07

The genesis case. Board `2026-08-07`, eve `2026-08-06`, board key `chinext20`, era `e6_2024_26_current`, sector `Healthcare`.

**PIT / EVENT FACTS ONLY. No price level, no return, no expectancy and no outcome magnitude is quoted for this case in any form. The earlier case-study exhibit's price and return claims remain withdrawn under their own stamp and no number from it is cited here.**

State at the eve:

| dd250 | dd band | duration band | below-200DMA band | sector deep35 band | sector deep35 % | vol-z band |
|---|---|---|---|---|---|---|
| -0.4398 | `d2_m35_m50` | `t3_gt120` | `b3_61_120` | `s2_40_60` | 44.87 | `v0_le0` |

Full footprint arming timeline:

| footprint | true at eve | armed on | lead (sessions to board) | censored |
|---|---|---|---|---|
| `DD20` — dd250 <= -20% off the 250-session high | yes | — | >=60 | yes |
| `DD35` — dd250 <= -35% off the 250-session high | yes | — | >=60 | yes |
| `MA200` — close below the 200DMA | yes | — | >=60 | yes |
| `CONF` — the Terminal oracle's 3D long state | yes | 2026-06-24 | 32 | no |
| `CB` — 3D crossover-buy within 2 3D bars | no | — | — | no |
| `SECT` — 40%+ of the name's sector members 35%+ off their own 250-session highs, leave-one-out | yes | 2026-07-17 | 15 | no |
| `QB` — 20-bar realised-vol rank in the bottom third | no | — | — | no |
| `VZ` — volume z-score of the bar > 1 | no | — | — | no |

CORE-4 arming order: `{DD20,MA200}>=60 > CONF(32) > SECT(15)`

Full 8-footprint arming order: `{DD20,DD35,MA200}>=60 > CONF(32) > SECT(15)`

Footprint tape, the last 20 sessions into the board (`•` true, `·` false):

| session | DD20 | DD35 | MA200 | CONF | CB | SECT | QB | VZ | mark |
|---|---|---|---|---|---|---|---|---|---|
| 2026-07-10 | • | • | • | • | · | • | · | • |  |
| 2026-07-13 | • | • | • | • | · | • | · | · |  |
| 2026-07-14 | • | • | • | • | · | • | · | · |  |
| 2026-07-15 | • | • | • | • | · | · | · | • |  |
| 2026-07-16 | • | • | • | • | · | · | · | · |  |
| 2026-07-17 | • | • | • | • | · | • | · | · |  |
| 2026-07-20 | • | • | • | • | · | • | · | · |  |
| 2026-07-21 | • | • | • | • | · | • | · | · |  |
| 2026-07-22 | • | • | • | • | · | • | · | · |  |
| 2026-07-23 | • | • | • | • | · | • | · | · |  |
| 2026-07-24 | • | • | • | • | · | • | · | · |  |
| 2026-07-27 | • | • | • | • | · | • | · | · |  |
| 2026-07-28 | • | • | • | • | · | • | · | · |  |
| 2026-07-29 | • | • | • | • | · | • | · | · |  |
| 2026-07-30 | • | • | • | • | · | • | · | · |  |
| 2026-07-31 | • | • | • | • | · | • | · | · |  |
| 2026-08-03 | • | • | • | • | · | • | · | · |  |
| 2026-08-04 | • | • | • | • | · | • | · | • |  |
| 2026-08-05 | • | • | • | • | · | • | · | · |  |
| 2026-08-06 | • | • | • | • | · | • | · | · | **eve** |
| 2026-08-07 | • | · | • | • | · | · | · | • | **board** |

## 7. Verification

**8 of 8 checks passed; 8 of 8 mutation probes detected their mutation.**

_A check that cannot fail is a defect. Every check is paired with a mutation it MUST detect; `detected: false` anywhere means the check is vacuous and the run is not evidence._

| check | result | probe | mutation applied |
|---|---|---|---|
| `no_lookahead_armings_and_footprints` | pass | detected | scale a two-year slab INSIDE the pre-cut history instead of the post-cut tail (must move the armings and the pre-cut footprints) |
| `cold_window_ejects_a_planted_board` | pass | detected | plant the same board 25 sessions back — OUTSIDE the prior-20 window, where the event must survive (so the check returns failure) |
| `detector_vs_zt_pool` | pass | detected | switch off 5% of the detector's board flags |
| `dd_band_partition_complete` | pass | detected | append an event carrying a band label outside the W-P0 registry |
| `era_board_table_disjointness` | pass | detected | add a pooled 'ALL_BOARDS' key to an output table |
| `arming_is_final_true_run` | pass | detected | assert the FIRST-true-run answer (lead 16) for the oscillator — the naive/wrong semantics, which the check must reject |
| `pin_line_numbers_resolve` | pass | detected | shift a pinned line number by +5 (simulates a W-P0 edit above it) |
| `stop_ship_reference_scan` | pass | detected | introduce a withdrawn-artifact reference into a scanned surface |

**Detector cross-check.** On the 36 sessions where `china_zt_pool` and the footprint plane both have coverage, 921 pool rows fall inside the footprint universe and the tolerant detector agrees on 919 — recall **99.78%**. One-directional by construction: `china_zt_pool` is a PARTIAL vendor store, so this is a RECALL measurement on the pool's own rows and is not a precision test.

**No-lookahead.** 64 names rebuilt with every bar after each cut scaled by 1.35, at three cuts spanning the history. The state is re-read at FIXED `(ticker, eve)` anchors, because a corruption that starts after the eve necessarily rewrites the board bar — re-extracting the event set would compare a different set of events and report the corruption doing its job as a leak.

| cut | anchors | armings changed | pre-cut footprint cells changed | pre-cut rows | anchors where corruption starts the next session |
|---|---|---|---|---|---|
| 2015-01-05 | 136 | 0 | 0 | 29,991 | 1 |
| 2019-01-02 | 356 | 0 | 0 | 66,016 | 1 |
| 2022-01-04 | 606 | 0 | 0 | 102,499 | 0 |

The last column is the literal *strictly after the eve* case: those anchors have the corruption beginning on the very next session. It is small by construction — it requires a cut to land on an anchor's own eve — and it is not what carries the check. What carries it is that the ENTIRE tape after each cut is rewritten while every anchor's 60-session arming window and 250-session footprint lookbacks sit wholly before it. The probe scales a two-year slab INSIDE the pre-cut history instead — which must move both columns, because every footprint here is a ratio and a uniform whole-history rescale would leave them bit-identical for the wrong reason.

**Cold window.** Planting a tolerant board 5 sessions before `000001.SZ @ 2013-07-11` ejects it from the first-board set; the probe plants the same board 25 sessions back — outside the prior-20 window — where the event must survive.

## 8. What this does NOT establish

- NO COMPARISON ARM, therefore NO selection skill and NO predictive claim. Every number in this file is computed on WINNERS — names that did print a first board. There is no matched non-winner cohort, no market baseline, no random draw. A footprint present in 90% of winners may be present in 90% of everything; this artifact cannot tell you which, and does not try. The comparison arm is ore, reserved for a preregistered study.
- NO lift, no t-statistic, no interval, no p-value, no effect size. None is computed and none may be inferred by dividing two numbers in this file.
- NO CAUSALITY, in either direction. That a footprint armed before a board is a statement about the order of two observations on the same tape. It is not evidence that the footprint produced the board, that the board was produced by anything measured here, or that either would recur.
- ARMING-ORDER STATISTICS ARE DESCRIPTIVE OF WINNERS ONLY. A precedence rate of X% means: among winners where both footprints were armed, one armed first X% of the time. It is not a conditional probability of a board and cannot be read as one.
- CENSORED LEADS ARE A FLOOR, NOT A VALUE. `>=60` (rendered `≥60` in the writeup) means the footprint was already true throughout the whole lookback window. The true arming age is unknown and is never imputed; a footprint with a high censoring rate has an UNMEASURED lead-time distribution, not a long one.
- SURVIVORS ONLY, LARGE-CAP SLICE. The footprint plane is W-P0's curated survivor universe; delisted names are absent, so every event here is an event on a name that lived. Nothing supports a claim about small caps in either direction.
- BACK-ADJUSTED BASIS. The tolerant detector runs on back-adjusted bars, so the cohort is a tolerant-detector cohort and not an exchange-exact legal-limit cohort. The residual is measured in verify.detector_vs_zt_pool, not assumed away. The reopen path to authority-tier limit work is unchanged and this artifact makes no claim to be on it (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT).
- NOTHING ABOUT THE WITHDRAWN W1-W3 CONSTRUCTIONS. No number and no artifact from them is cited (grep-verified in verify.stop_ship_reference_scan).
- NO PRICE OR RETURN CLAIM for any named episode, including the worked example. What is printed for a case is its footprint state and its event dates; the earlier case exhibit's price and return claims remain withdrawn under their own stamp.
- CURRENT SECTOR MEMBERSHIP. The sector-washout footprint applies today's sector map to 15 years of history (W-P0's own caveat); it is not a point-in-time sector statistic and eras are not comparable on it without that qualifier.

## 9. Ore ledger — mapped, not built

- THE COMPARISON ARM. The single most valuable follow-up and deliberately NOT built here: a matched non-winner cohort (names in the same dd band, same board, same session, that did NOT print a board) decomposed the same way. That is an INFERENTIAL study and it needs a PREREGISTRATION — matched-control construction, era-preserving null, date-clustered inference, and the volatility-matched control W-P0 already had to add. Reading a precedence rate here as evidence of selection would be exactly the error that preregistration exists to prevent.
- ARMING ON THE BANDED FORMS. Only the eight BOOLEAN footprints have armings; a band transition (say b2_21_60 -> b3_61_120) is also an arming-like event and is not measured. Cheap to add once the boolean anatomy is read.
- INTRADAY / CHIP FOOTPRINTS remain P-C: auction demand, seal-time structure and chip-concentration shifts cannot arm in this instrument because the histories do not exist in this checkout.
- SUSPENSION-AWARE CONFLUENCE. W-P0 replicates production's close-only, volume-blind indicator input, so suspension placeholder closes enter the 3D session grouping. The suspension-aware variant is W-P0's own logged ore and is inherited unchanged.
- LEAD-TIME BEYOND 60 SESSIONS. The censored block is a floor, not a distribution. A longer lookback would resolve the slow footprints' true arming ages; 60 was fixed in the pre-registration and is not re-shopped after seeing the censoring rate.

## 10. Amendments — every deviation declared

**A1 — The EVE is the name's previous PANEL session, not its previous calendar session, and the eve->event pair must sit inside W-P0's own MAX_STEP_GAP_DAYS = 21 step rule.**

- why: china_stocks_raw encodes suspensions as zero-volume stale-price placeholder rows, which W-P0's live-bar law already excludes from the panel. Without the step rule a name resuming after a long suspension would be credited with an 'eve' from before the halt — a state read months before the board and presented as the day before it.
- controlled by: the step rule is W-P0's OWN pre-registered constant (L354), not a new one; `eve_to_event_calendar_days` is carried on every event and its distribution is in the JSON.

**A2 — Events with fewer than ARMING_LOOKBACK = 60 prior sessions on their own axis are EXCLUDED from the arming and order tables (they remain in the cohort and presence tables), and the exclusion count is printed.**

- why: A shorter window produces a censoring bound BELOW 60, which would break the ordering assumption the censored quantile rule rests on (every censored lead >= every uncensored one). Mixing those events in would make a median silently wrong rather than visibly censored.
- controlled by: `arming_ineligible_short_lookback` is printed per board in the cohort tables; the arming tables carry their own honest-N, which is the eligible subset.

**A3 — The 'complete order' tables run on the pre-registered CORE-4 (dd_le_m20, under_ma200, confluence_long, sector_deep35_ge40); the full 8-footprint signature counts are emitted to the JSON only.**

- why: An 8-way signature over a censoring-aware alphabet is sparse enough that nearly every event is its own singleton — a list, not a pattern. The CORE-4 is the operator's own named footprint families (program home sec.1) and was fixed in the pre-registration block before any signature was counted.
- controlled by: both are computed and both are in the receipt; the writeup states which one each table is on, and the full-8 counts are one key away in the JSON.

**A4 — Chips (W-P0 S5b winner / trajectory) join skipped — attach_conditioners is called with chips=None.**

- why: The P-B footprint list is washout / basing / confluence / sector / quiet-base / volume. S5b is none of those and its store begins long after most of the cohort, so joining it would add a column that is null for 14 of 15 years.
- controlled by: W-P0's own None branch sets the S5b bands to 'na'; no S5b column appears in any table here.

**A5 — Vintage stamps that resolve to a SHALLOW-CLONE GRAFT commit are relabelled `SHALLOW_BOUNDARY_UNRESOLVED(<sha>)` rather than printed as provenance.**

- why: In a shallow checkout `git log -1 -- <path>` stops at the graft, so a path untouched inside the visible history resolves to the graft commit. That reads exactly like a real store vintage and is not one. This run was deepened until the stamps resolved; the guard exists so a future shallow run cannot emit a confident wrong stamp.
- controlled by: `vintage.repo_is_shallow`, `vintage.shallow_graft_commits` and `vintage.stamps_unresolved_by_shallow_graft` are all in the receipt, and a bare `::warning` is emitted on any hit.

## 11. Provenance

| stamp | value |
|---|---|
| `base_sha` | `a4f018871007c0dc6fac95cf06e3ec17ef4a774c` |
| `build_head_sha` | `a4f018871007c0dc6fac95cf06e3ec17ef4a774c` |
| `raw_store_commit` | `88c745513ac03d0a1d5244ce923f43618da5c349` |
| `members_commit` | `88c745513ac03d0a1d5244ce923f43618da5c349` |
| `st_snapshot_commit` | `212a640d50cc368782637912b0707ba1e83fe62a` |
| `zt_pool_commit` | `b7f6746df6c8024d0826765bb3df5e3f35e821d6` |
| `w1_pin_commit` | `b50cf9461be794f3190b0bc985a35f6dfb3078d1` |
| `w1_sha256` | `11ac61de71f0f595e618f6f152dcea2334370d34cb736df919fb7127f1325cbf` |

Every store stamp is verified to be an ancestor of the build head before either file is written (the A4 provenance guard); a checkout that moved mid-run refuses to write rather than emit polluted provenance. A stamp that resolves to a shallow-clone graft is relabelled rather than printed as provenance (§10 A5): `repo_is_shallow` = `False`, unresolved stamps `none`. Consecutive runs of this instrument are byte-identical — no wall-clock value enters either receipt.

Pinned definitions: `washout_onset_w1.py` @ sha256 `11ac61de71f0f595…`, **imported**. Inherited limits travel with the pin: the footprint plane is a curated large-cap **survivor** slice (delisted names absent); `china_stocks_raw` is **back-adjusted**, so this is a tolerant-detector cohort and not an exchange-exact legal-limit one; and the sector footprint applies today's sector map to 15 years of history.

