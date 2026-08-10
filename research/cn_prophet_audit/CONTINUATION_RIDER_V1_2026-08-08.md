# CN CONTINUATION RIDER v1 — open-gap conditioned, fillability-honest

**Program:** CN LIMIT-MOVE ALPHA, Wave 1, lane L1 — THE CONTINUATION RIDER.
**Instrument:** `research/cn_prophet_audit/continuation_rider_v1.py` ·
**Frozen numbers:** `CONTINUATION_RIDER_V1_2026-08-08.json` · **Runtime:** 10.6 s ·
**Window:** 2011-01-01 → 2026-08-07 · **Basis:** `data/china_stocks_raw`.
**Builds on:** `limit_move_footprint_v0.py` (PR #4999) — conventions reused verbatim, ladder
re-derived and pinned.

**Tier: display / audit. MEASUREMENT ONLY.** Nothing here ranks, sizes, gates, admits or
promotes anything. No LLM is involved at any point. **No rate or return in this document is
pooled across board types** — a ±10% main-board name and a ±20% ChiNext name do not share a
base rate. **THE ORE LAW binds:** the nulls below close the *constructions tested* and nothing
else; §ORE LEDGER names what was not tested.

---

## DECISION SUMMARY

1. **The panel is provably v0's panel.** Before any finding is read: this instrument
   re-derives v0's Stage-2 ladder and pins it against v0's *published* numbers. **15 of 15
   cells match, max |Δn| = 0, max |Δrate| = 0.005 pp** (the published-precision floor). Same
   60,298 limit-up board-days, same exclusion counts, same unconditional rates. Any
   disagreement with v0 below is therefore a new measurement, not a different universe.
2. **THE OPEN GAP IS THE STRONGEST ENTRY-TIMED CONDITIONER IN THE DAILY BASIS, AND IT IS
   ERA-STABLE.** Main board, first board (N=1), holdout: P(next board) runs **3.19%** when the
   name gaps below −3% to **41.57%** when it gaps +5%…+9.5% — a **13× spread inside one
   cohort**, decidable at the 09:25 call auction and tradable at 09:30. The fit window says
   2.17% → **41.25%**: the strongest cell reproduces to 0.32 pp out of sample on 1,251 fresh
   observations. Across all 16 years the g4 cell never drops below 19.7% and sits in 27–46% in
   **14 of them**.
3. **THE FILLABILITY TAX — 46.7% of the main board's realised next-day boards cannot be
   bought.** They open at or above the limit (一字). Per cohort the tax is **31.6% (N=1),
   49.9% (N=2), 75.0% (N≥3)**; ChiNext N≥3 is **83.1%**. So the ladder's headline collapses
   once you require a fill: main N≥3 goes from a published **58.51%** to **28.06%**
   conditional on a fillable open, and only **14.62%** of N≥3 board-days produce a board you
   could have bought. **The most impressive cells of the published ladder are the least
   buyable ones.**
4. **The gap curve is monotone, with no exhaustion hump.** 20 quantile bins, main N=1: a flat
   floor of ~3.5% across every down-gap, an elbow at **g ≈ +1%**, then a monotone climb to the
   top bin. Across all six curves (3 eras × all-opens/fillable-only) there are **zero adjacent
   decreases whose Wilson intervals are disjoint**, and `rolls_over_after_peak` is **False**
   everywhere. The peak is always the last bin. The hypothesised weak-demand-vs-exhaustion
   hump **is not there** in the fillable range.
5. **THE CENTRAL NULL — probability is not edge. The auction prices the information.** Every
   fillability-honest entry book at the board level loses money on the holdout: main **E1
   −0.384%, E2 −0.341%, E3 −0.209%** mean per trade, gross, on 15,428 trades — worse after
   costs. Worse, the return is **anti-monotone in the very conditioner that drives the
   probability**: the g4 band (41.57% continuation) has the *worst* day-1 open→close
   (**−1.009%** mean) and the worst E1 expectancy (−0.570%), while the g2 band (5.94%
   continuation) has the *best* (+0.224% / −0.114%). You are paid for the gap you did not pay
   for.
6. **Censused, not curated: two cells survive, and neither is a trade.** 35 cells have a
   positive holdout mean at n ≥ 100; **15** are also positive in fit; **2** have n ≥ 500 in
   *both* windows. One of those two has a fit mean of **+0.001%** — literally zero. The other
   — main, E3 time stop, N=1, gap in [0, +2%) — is **+0.047%** holdout (n = 4,646) against
   **+0.062%** fit (n = 8,110), and **−0.103%** after a 15 bp round trip. Ten of the 15
   sign-stable cells are STAR with 7–38 trades in their fit window.
7. **The confirmed ladder is a WORSE trade, not a better one.** N ≥ 2 versus N = 1, main
   holdout, same book: Δmean **−0.75 / −0.87 / −1.06 pp** for E1 / E2 / E3, and Δwin-rate
   −4.5 / −3.2 / −4.3 pp — despite a continuation rate roughly double. Two reasons, both
   measured: the fillable subset of a confirmed ladder is adversely selected (75% of its
   realised boards open unbuyable, and only 52% of its board-days offer any entry at all), and
   its loss tail is far fatter (E3 p10 **−18.8%** vs −9.7% at N=1).
8. **Weekend fermentation is REAL in probability — and it is the gap wearing a weekday hat.**
   Friday boards continue more than midweek boards on both sides of the split, with disjoint
   Wilson intervals: main N=1 fit **19.69% vs 16.71%**, holdout **19.12% vs 14.64%**. It is
   monotone in break length (1-day **14.19%** → weekend **18.86%** → holiday **32.99%**). But
   the operator's mechanism claim does not survive the control: **inside every gap band, on the
   holdout, every Friday-vs-midweek interval overlaps** (Δ = +0.19 / +0.45 / +0.22 / +3.97 pp).
   Friday boards simply gap up more (mean gap 2.20% vs 1.52–1.68%). The fermentation shows up
   as a bigger overnight gap, not as extra continuation given the gap — and it converts to no
   expectancy at all (Friday E1 holdout −0.229%, mid-pack among five negative weekdays).
9. **The gap's clearest use is as a RISK conditioner, not a return one.** Main N ≥ 3 gapping
   below −3%: **50.0%** of those names close at the *down* limit the same day (n = 142). The
   same band at N=1 is 12.06%. Survivors-only, so this reads *better* than the truth.
10. **Locked-exit honesty is materially load-bearing, not a footnote.** 1.67% of main holdout
    E1 exits could not be sold at the scheduled open because the bar opened at the down limit;
    rolling cost them **−2.14% on average and −20.96% at worst**, and the roll rate reaches
    **9.98%** at N ≥ 3. Worked example below: one trade a naive book would have marked at
    −17.3% actually cost **−32.3%**.
11. **Side finding, measured not asserted: `data/china_stocks_raw` is BACK-ADJUSTED, not
    nominal.** The share of closes sitting exactly on the 0.01 tick rises monotonically from
    **36.4% (2011) to 96.6% (2026)**, and 609 of 1,836 names are on-tick for their whole
    history — the back-adjustment signature. v0's header calls this store "nominal/unadjusted";
    that description is wrong. It **explains** v0's definition adjudication rather than
    overturning it, and the measured cushion requirement is fine: the tick-rounding error on
    the limit price is p99 **0.15%**, p99.9 **0.30%**, and only **0.375%** of live bars exceed
    the adopted 0.2% tolerance. Returns are unaffected — adjustment preserves them.
12. **THE BINDING CAVEAT is v0's and is unchanged.** The universe is a curated **1,842** names
    against a listed A-share market of roughly 5,400; only **1 of 100** current ST names and
    **514 of 1,770 (29%)** of the names that hit the vendor's limit-up pool exist here; the
    store is survivors-only. The 打板 game lives disproportionately in exactly the small-cap and
    ST names this universe omits. **No number below is a market-wide statistic.**

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Price basis | `data/china_stocks_raw`. The correct one of the two — the twin `data/china_stocks` carries a second, larger adjustment factor. **Measured here: this store is itself back-adjusted, not nominal** (§PRICE BASIS). |
| Names | 1,842 in store · **1,836 kept** · main 1,243 · chinext 351 · star 242 · **bse 0** |
| ST names present | **1 of 100** current ST names |
| zt_pool names present | **514 of 1,770 (29%)** |
| Ticker-days | 4,981,168 · live after exclusions **4,843,576** |
| Excluded bars | zero-volume/suspension 133,781 · ex-div suspect 621 · IPO window 2,793 |
| Limit-up board-days | **60,298** · with a usable T+1 **59,657** · **fillable entries 51,486** |
| Unconditional next-bar limit-up | main **1.27%** · chinext **1.14%** · star **0.32%** |
| Fit / holdout | split **2021-11-26** (v0's date, reused frozen). Holdout is the headline. |
| Usability asymmetry | A bar's usability at T+1 is a property of T+1, so conditioning on it is a filter a trader at T could not apply. Applied uniformly to numerator and denominator (v0's handling), so ratios are essentially unaffected; absolute rates are rates **among usable next bars**. **The fillability filter is a different animal and is legitimate** — the 09:25 auction prints *before* the 09:30 entry, so an entrant genuinely knows it. |
| Ex-dividend residual | The store is back-adjusted for splits but a cash dividend still prints a mechanical gap-down of about the yield on its ex-date, far under the 1.5·w exclusion trigger. Those land in band g1 and are arithmetic, not demand. A name goes ex once a year, so this is order 0.4% of g1's rows, and it is noise rather than direction because an ex-date is uncorrelated with having boarded the day before. Disclosed, not patched — patching needs a per-date dividend calendar this repo does not hold. |
| Survivorship | Current listed universe only. Delisted names are absent, which biases the **limit-down** cells most; every limit-down figure here is **survivors-only** and reads better than the truth. |
| Clustering | `n` counts trades, not independent episodes — limit runs arrive in theme waves. Every entry-book cell carries `n_dates` and `top5_name_share_pct` in the JSON so the effective sample is visible. Main E1 holdout: 15,428 trades over **1,134 distinct dates**. |
| ChiNext era | ChiNext's fit window is mostly a ±10% market and its holdout entirely ±20%. Its fit and holdout cells are **not like-for-like** and must never be pooled or compared as if they were. |
| STAR | 872 board-days in total. Every STAR cell below is thin; several are printed only so the null is visible. |

---

## DEFINITIONS (stated inline, as required)

- **`w`** — `engine.china_microstructure.limit_width_for_date`, **imported, not reimplemented**:
  STAR 20%; ChiNext 20% on/after 2020-08-24 else 10%; main 10%; BSE 30%. Board from
  `_board_from_ticker`.
- **`limit_up_close` (PRIMARY)** — `close ≥ round(prev_close×(1+w), 2) × (1 − 0.002)`. v0's
  adjudicated primary; strict carried in parallel on the T+1 outcome.
- **`limit_down_close`** — `close ≤ round(prev_close×(1−w), 2) × (1 + 0.002)`.
- **`连板 N`** — consecutive limit-up closes ending on the bar; any non-limit bar, including an
  excluded one, resets it to 0. Cohorts are **{1, 2, 3+}**.
- **`g` (the gap)** — `open[T+1] / close[T] − 1`. Known at the 09:25 auction, acted on at 09:30.
- **`unfillable open` (一字)** — `open[T+1] ≥ limit_price[T+1] × (1 − 0.002)`. The name is already
  sealed when continuous trading starts; there is no price at which a new entrant is filled.
  A stricter reading (the whole bar printed at the limit, `open == high == low == close`) is
  carried beside it as `strict_yizi`.
- **`T → T+1`** — the immediately following bar, which must be live and at most 10 calendar
  days later. Because the successor is always `i+1`, a usable chain is contiguous, which is
  what makes the multi-session exit walk exact rather than approximate.
- **Exclusions** — ST cohort (all dates); STAR/ChiNext first 5 sessions and pre-2014 listings'
  first session; ex-dividend suspects (`|open − prev_close| / prev_close > 1.5·w`); zero-volume
  bars; every ticker's first bar.

### The gap bands — and one disclosed deviation

| Band | Definition (10% board) | (20% board) |
|---|---|---|
| `g0` | g < −3% | same |
| `g1` | −3% ≤ g < 0 | same |
| `g2` | 0 ≤ g < +2% | same |
| `g3` | +2% ≤ g < +5% | same |
| `g4` | +5% ≤ g < 0.95·w → **< +9.5%** | **< +19%** |
| `g5` | 0.95·w ≤ g < limit → **+9.50%…+9.78%** | **+19.00%…+19.76%** |
| `g6` | **open ≥ limit×(1−0.002) — UNFILLABLE** | same |

**DEVIATION, disclosed:** the brief's list runs `[+5%, 0.95w)` straight into "opens at or above
the limit". Those two do not meet — on a 10% board 0.95·w is +9.50% and the unfillable threshold
is +9.78% — so a real slice of opens would have fallen through the partition and been silently
dropped. **`g5` is that hole**, added so the bands are exhaustive and every usable T+1 open lands
in exactly one of them. It is a small, interesting class in its own right (see below).

---

## PARITY GATE — is this v0's panel?

| Check | Result |
|---|---|
| Published ladder cells re-derived (main 1–6, chinext 1–6, star 1–3) | **15 / 15 match** |
| Max abs Δ in cell **n** | **0** |
| Max abs Δ in cell **rate** | **0.005 pp** (published to 2 dp; this is the rounding floor) |
| Unconditional next-bar limit-up | main 1.27 / chinext 1.14 / star 0.32 — all three reproduce |

Deliberately a comparison against v0's published **output** rather than a re-import of its code:
v0 lives on an unmerged branch, and a number that has survived adversarial review is the stronger
reference.

---

## C1 — OPEN-GAP CONDITIONING (primary)

**Main board, HOLDOUT (2021-11-26 → 2026-08-06).** Wilson 95%. `touch` = the board was reached
intraday whether or not it held; `↓limit` = closed at the *down* limit; `open→close` = the day-1
return of an entrant who bought the open and sold the close.

### N = 1 (first board) — cohort rate 15.94%, n = 13,735

| Band | n | **P(next board)** | Wilson 95% | touch | ↓limit | open→close mean / median |
|---|---|---|---|---|---|---|
| g0 g < −3% | 564 | **3.19%** | 2.03–4.99 | 7.09% | **12.06%** | **+1.482%** / +0.68% |
| g1 −3…0% | 2,999 | **3.63%** | 3.02–4.37 | 6.54% | 2.50% | +0.286% / +0.09% |
| g2 0…+2% | 4,646 | **5.94%** | 5.30–6.66 | 12.16% | 0.73% | +0.224% / −0.08% |
| g3 +2…+5% | 3,240 | **18.33%** | 17.04–19.70 | 30.59% | 0.71% | −0.155% / −0.50% |
| **g4 +5…+9.5%** | **1,251** | **41.57%** | **38.87–44.32** | 63.63% | 0.64% | **−1.009%** / +0.37% |
| g5 +9.5…+9.78% | 59 | 28.81% | 18.84–41.38 | 59.32% | 0.00% | −4.364% / −4.60% |
| **g6 UNFILLABLE** | 976 | **67.21%** | 64.21–70.09 | 100% | 0.00% | −1.579% / 0.00% |

### N = 2 — cohort 29.68%, n = 2,197 · N ≥ 3 — cohort 47.26%, n = 1,221

| Band | N=2 n | N=2 P | Wilson | N≥3 n | N≥3 P | Wilson | N≥3 ↓limit |
|---|---|---|---|---|---|---|---|
| g0 g < −3% | 200 | 4.50% | 2.39–8.33 | 142 | 14.08% | 9.31–20.76 | **50.00%** |
| g1 −3…0% | 398 | 8.79% | 6.39–11.98 | 134 | 12.69% | 8.07–19.38 | 23.88% |
| g2 0…+2% | 502 | 13.55% | 10.83–16.82 | 167 | 31.14% | 24.61–38.52 | 7.78% |
| g3 +2…+5% | 416 | 23.08% | 19.29–27.36 | 201 | 34.83% | 28.58–41.64 | 7.96% |
| **g4 +5…+9.5%** | 284 | **45.07%** | 39.39–50.88 | 192 | **54.17%** | 47.11–61.06 | 2.08% |
| g5 +9.5…+9.78% | 17 | 52.94% **THIN** | 30.96–73.84 | 16 | 81.25% **THIN** | 56.99–93.41 | 0.00% |
| g6 UNFILLABLE | 380 | 80.79% | 76.53–84.43 | 369 | 81.57% | 77.30–85.20 | 1.63% |

### Fit → holdout: the ordering is stable at every N

| Band | N=1 fit → hold | N=2 fit → hold | N≥3 fit → hold |
|---|---|---|---|
| g0 | 2.17 → 3.19 | 4.74 → 4.50 | 5.62 → 14.08 |
| g1 | 3.29 → 3.63 | 11.21 → 8.79 | 10.85 → 12.69 |
| g2 | 6.58 → 5.94 | 15.40 → 13.55 | 18.30 → 31.14 |
| g3 | 17.90 → 18.33 | 30.64 → 23.08 | 32.83 → 34.83 |
| **g4** | **41.25 → 41.57** | 52.17 → 45.07 | 51.86 → 54.17 |
| g6 | 81.23 → 67.21 | 83.77 → 80.79 | 93.34 → 81.57 |

**The g4 cell is the finding.** 41.25% on 2,075 fit observations, 41.57% on 1,251 fresh ones —
a 0.32 pp reproduction. Nothing else in this study is that stable.

### Main N = 1 by year — the conditioner survives every era

| Year | n | P(next board) | of which unfillable | **P \| fillable** | **g4 band P (n)** |
|---|---|---|---|---|---|
| 2011 | 769 | 7.93% | 2.7% | 6.15% | 35.85% (53) |
| 2012 | 996 | 11.75% | 5.4% | 8.49% | 27.71% (83) |
| 2013 | 1,426 | 13.25% | 6.0% | 8.96% | 34.40% (125) |
| 2014 | 1,706 | 16.47% | 8.1% | 10.40% | 33.33% (162) |
| **2015** | 6,240 | **24.18%** | 9.1% | 18.51% | **51.78%** (618) |
| 2016 | 1,894 | 12.99% | 6.3% | 8.23% | 27.20% (125) |
| 2017 | 1,140 | 18.60% | 12.5% | 8.42% | 36.99% (73) |
| **2018** | 1,202 | **8.15%** | 4.2% | 5.04% | **19.67%** (61) |
| 2019 | 2,047 | 15.53% | 6.4% | 11.32% | 42.62% (183) |
| 2020 | 3,170 | 17.32% | 6.3% | 12.86% | 42.86% (315) |
| 2021 | 4,349 | 13.68% | 3.5% | 11.39% | 40.74% (297) |
| 2022 | 2,835 | 13.62% | 4.3% | 10.54% | 40.50% (200) |
| 2023 | 1,727 | 11.99% | 3.6% | 9.73% | 36.13% (155) |
| 2024 | 2,838 | 22.20% | **18.0%** | 14.48% | 42.47% (292) |
| 2025 | 3,008 | 15.96% | 5.1% | 12.75% | 45.25% (305) |
| 2026 | 2,943 | 14.88% | 3.9% | 12.38% | 39.78% (279) |

The cohort rate swings 3× (8.15% in 2018 to 24.18% in 2015). The **g4 conditional swings far
less and never breaks** — 19.7% at its worst, 27–46% in 12 of 16 years. Note 2024: the
unfillable share triples to 18.0%, so its impressive 22.20% headline is the year the tax bit
hardest.

### Other boards, holdout (never pooled with main)

| Board | N | n | P(next board) | Wilson | g4 band | g6 UNFILLABLE |
|---|---|---|---|---|---|---|
| chinext | 1 | 1,125 | 10.67% | 8.99–12.61 | **19.11%** (n=246) | 96.77% (n=62) |
| chinext | 2 | 121 | 19.83% | 13.71–27.82 | 32.00% (n=25) **THIN** | 80.00% (n=15) **THIN** |
| chinext | 3+ | 45 | 46.67% | 32.93–60.92 | 44.44% (n=9) **THIN** | 94.44% (n=18) **THIN** |
| star | 1 | 663 | 10.26% | 8.17–12.80 | **16.10%** (n=118) | 80.00% (n=45) |
| star | 2 | 67 | 13.43% | 7.23–23.60 | 25.00% (n=8) **THIN** | 100% (n=6) **THIN** |
| star | 3+ | 19 | 52.63% | 31.71–72.67 | 40.00% (n=5) **THIN** | 100% (n=6) **THIN** |

The band ordering holds on both, but ChiNext's holdout is a ±20% market and its fit is not —
these are not comparable to its own fit cells, and STAR is thin everywhere.

---

## THE FILLABILITY TAX — the continuation you cannot buy

`TAX` = share of **realised** next-day boards whose T+1 open was unfillable. `entry avail` =
share of board-days that offered a fillable open at all. `P | fillable` = the only version of
the ladder a trader can act on.

| Board | N | board-days | published P(next board) | **TAX** | strict 一字 | entry avail | **P \| fillable** | buyable P |
|---|---|---|---|---|---|---|---|---|
| main | 1 | 38,290 | 16.50% | **31.6%** | 20.2% | 93.2% | **12.12%** | 11.29% |
| main | 2 | 6,257 | 36.61% | **49.9%** | 33.6% | 78.0% | **23.53%** | 18.35% |
| main | 3+ | 5,315 | 58.51% | **75.0%** | 63.7% | **52.1%** | **28.06%** | 14.62% |
| main | all | 49,862 | 23.50% | **46.7%** | 34.4% | 86.9% | 14.42% | 12.53% |
| chinext | 1 | 6,587 | 16.76% | 41.3% | 27.1% | 91.9% | 10.70% | 9.84% |
| chinext | 2 | 1,094 | 39.12% | 59.8% | 43.7% | 72.9% | 21.58% | 15.72% |
| chinext | 3+ | 1,242 | 66.83% | **83.1%** | 75.1% | **40.9%** | **27.56%** | 11.27% |
| star | 1 | 773 | 10.09% | 50.0% | 7.7% | 93.7% | 5.39% | 5.05% |
| star | all | 872 | 11.47% | 51.0% | 15.0% | 92.9% | 6.05% | 5.62% |

**Read the N ≥ 3 row twice.** The published ladder says a 3-board name continues 58.5% of the
time on the main board. Three quarters of those continuations open unbuyable, and nearly half
its board-days offer no entry at all. What is left — **P(next board | you could enter) =
28.06%** — is less than half the headline, and only **14.62%** of board-days deliver a board you
could actually have owned. **This is the single number this lane exists to produce.**

---

## C2 — THE FILLABILITY-HONEST ENTRY BOOK

**Entry:** buy at the open of T+1, **only** where `open[T+1] < limit_price[T+1] × (1 − 0.002)`.
Unfillable opens are refused, not modelled as fills.

**Exits, all on daily bars:**
- **E1 board-fail** — sell at the next open after the first session that fails to close limit-up.
- **E2 first down-close** — sell at the next open after the first session closing below its open.
- **E3 time stop** — sell at the open of T+4, unconditionally.

**LOCKED-EXIT HONESTY.** A scheduled exit bar whose open is at or below its own limit-down price
cannot be sold — the book is one-sided. The exit rolls to the next usable bar's open, up to 10
sessions; if the chain breaks or the cap is exhausted the position closes at the last available
**close** and is flagged. Without this the book sells the unsellable at a price that never
traded, which is the single largest way a 打板 backtest lies.

> **Worked example — `603887.SS`, board day 2022-01-25** (close 10.88 = the limit exactly).
> T+1 opens 11.10, below the 11.97 limit → fillable, entry at **11.10**. It closes 10.20, below
> its open, so E2 schedules a sale at the next open: **9.18 on 01-27 — which is that bar's exact
> limit-down price.** No fill. Roll. **8.26 on 01-28 — limit-down again.** No fill. Roll. Sold at
> **7.52 on 02-07**. A naive book marks this trade at 9.18/11.10 − 1 = **−17.3%**. It actually
> cost **−32.3%**. The roll alone was **−18.1%**.

### Main board, HOLDOUT, all bands (gross; `net` applies a 15 bp round trip)

| Rule | N | n | win% | **mean** | median | p10 | p90 | worst | hold | roll% | net |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E1 | ALL | 15,428 | 41.11 | **−0.384%** | −1.00% | −7.35% | +6.39% | −37.4% | 1.22 | 1.67 | −0.534% |
| E1 | 1 | 12,759 | 41.89 | **−0.255%** | −0.84% | −6.44% | +5.92% | −32.3% | 1.17 | 0.89 | −0.404% |
| E1 | 2 | 1,817 | 37.37 | −0.799% | −2.09% | −9.36% | +8.03% | −28.7% | 1.33 | 3.30 | −0.948% |
| E1 | 3+ | 852 | 37.44 | −1.441% | −2.79% | −13.41% | +11.71% | −37.4% | 1.66 | **9.98** | −1.588% |
| E2 | ALL | 15,428 | 33.32 | **−0.341%** | −1.88% | −7.89% | +8.49% | −37.4% | 2.01 | 1.66 | −0.490% |
| E2 | 1 | 12,759 | 33.88 | −0.190% | −1.69% | −7.00% | +7.95% | −36.2% | 1.99 | 0.90 | −0.340% |
| E2 | 3+ | 852 | 31.57 | −1.356% | −4.46% | −15.19% | +16.49% | −37.4% | 2.32 | 9.98 | −1.504% |
| E3 | ALL | 15,428 | 43.99 | **−0.209%** | −1.06% | −10.90% | +11.11% | −39.3% | 2.95 | 0.73 | −0.359% |
| E3 | 1 | 12,759 | 44.73 | **−0.026%** | −0.85% | −9.72% | +10.38% | −32.6% | 2.95 | 0.39 | −0.176% |
| E3 | 2 | 1,817 | 40.34 | −1.002% | −2.68% | −13.68% | +14.16% | −31.8% | 2.93 | 1.38 | −1.150% |
| E3 | 3+ | 852 | 40.73 | −1.268% | −3.11% | −18.84% | +20.41% | −39.3% | 3.01 | 4.46 | −1.416% |

Fit window, same cells: E1 **−0.431%**, E2 **−0.589%**, E3 **−0.277%**. **The null is
era-stable.** ChiNext holdout: E1 −0.561%, E2 −0.007%, E3 −0.653%. STAR holdout: −0.117% /
−0.356% / −1.211%.

### The anti-monotone result — main, N = 1, HOLDOUT

| Band | P(next board) | open→close mean | **E1 mean** | **E3 mean** |
|---|---|---|---|---|
| g0 g < −3% | 3.19% | +1.482% | **+0.462%** | **+0.453%** |
| g1 −3…0% | 3.63% | +0.286% | −0.232% | −0.009% |
| g2 0…+2% | 5.94% | +0.224% | −0.114% | **+0.047%** |
| g3 +2…+5% | 18.33% | −0.155% | −0.408% | −0.050% |
| g4 +5…+9.5% | **41.57%** | **−1.009%** | **−0.570%** | **−0.338%** |

**Probability climbs 13×, expectancy falls.** The 09:25 auction is where the continuation
information is paid for; by 09:30 there is nothing left of it. The two positive cells in the g0
row are a *reversal* trade, not a continuation one — and they are not stable (E3 g0 fit
**−0.709%** → holdout **+0.453%**; E1 g0 fit **+0.001%**, i.e. nothing).

### The positive cells, censused rather than curated

Cherry-picking the winners is how a book like this lies to its author, so the whole filter is
printed instead of a shortlist.

| Filter | Cells surviving |
|---|---|
| Holdout mean > 0 with n ≥ 100 | **35** |
| …and fit mean also > 0 (sign-stable) | **15** |
| …and n ≥ 500 in **both** windows | **2** |

Ten of the 15 sign-stable cells are STAR, whose **fit** windows hold 7–38 trades; three are
ChiNext, whose fit/holdout pair straddles the ±10% → ±20% band change and is not like-for-like.
That leaves exactly two cells standing on real samples in both eras:

| Cell | fit mean (n) | holdout mean (n) | after 15 bp |
|---|---|---|---|
| main E1 N=1 **g0** (gap < −3%) | +0.001% (876) | +0.462% (564) | +0.311% |
| main E3 N=1 **g2** (gap 0…+2%) | +0.062% (8,110) | **+0.047% (4,646)** | **−0.103%** |

The first has a fit window of **exactly zero**. The second is the most-populated cell in the
study and is worth four basis points before costs and less than nothing after them. **That is
the whole positive result of the entry book**, and it is not one.

For contrast, the largest positive holdout numbers — star E3 N=1 g4 **+2.219%** (n = 118, fit
n = **26**) and chinext E2 g3 **+1.829%** (n = 248, fit **−1.174%** on 1,821) — are exactly what
the census exists to disqualify.

---

## C3 — THE CONFIRMED-LADDER VARIANT

Same book, same exits, same fillability rule; N ≥ 2 at T against N = 1. **Holdout:**

| Board | Rule | N=1 mean (n) | N≥2 mean (n) | Δ mean | Δ win rate |
|---|---|---|---|---|---|
| main | E1 | −0.255% (12,759) | −1.004% (2,669) | **−0.749 pp** | −4.50 pp |
| main | E2 | −0.190% (12,759) | −1.063% (2,669) | **−0.873 pp** | −3.23 pp |
| main | E3 | −0.026% (12,759) | −1.087% (2,669) | **−1.061 pp** | −4.27 pp |
| chinext | E1 | −0.503% (1,063) | −1.027% (133) | −0.524 pp | +7.67 pp |
| chinext | E3 | −0.294% (1,063) | −3.523% (133) | −3.229 pp | −13.20 pp |
| star | E1 | −0.202% (618) | +0.590% (74) **THIN** | +0.792 pp | +11.01 pp |
| star | E3 | −0.721% (618) | −5.308% (74) **THIN** | −4.587 pp | −14.39 pp |

**The confirmed ladder is worse on every main-board rule and on 8 of the 9 board×rule cells**, despite
roughly double the continuation rate. The mechanism is measured, not guessed: 75% of its
realised boards open unbuyable, only 52% of its board-days offer any entry, its roll rate is 11×
higher (9.98% vs 0.89%), and its loss tail is roughly double (E3 p10 −18.84% vs −9.72%). **What
you can buy at N ≥ 3 is the subset that did not gap away — which is adverse selection, priced.**

---

## C4 — DAY OF WEEK / FERMENTATION

**Collinearity first, because it decides how to read everything else.** Weekday of T and the
T→T+1 calendar gap are the same variable:

| | 1-day | 2–3 day (weekend) | 4+ day (holiday) |
|---|---|---|---|
| Mon | 13,285 | 0 | 549 |
| Tue | 11,953 | 37 | 59 |
| Wed | 11,539 | 0 | 201 |
| Thu | 10,870 | 0 | 303 |
| **Fri** | **0** | **10,294** | 567 |

So the two tables below are **one test presented twice**, not two independent tests.

### Continuation by break length — main, holdout

| N | Break | n | P(next board) | Wilson | share unfillable |
|---|---|---|---|---|---|
| 1 | 1 day | 10,646 | 14.19% | 13.54–14.87 | 4.5% |
| 1 | weekend | 2,407 | **18.86%** | 17.35–20.47 | 6.1% |
| 1 | holiday | 682 | **32.99%** | 29.57–36.61 | **51.9%** |
| 2 | 1 day | 1,794 | 27.37% | 25.36–29.48 | 14.9% |
| 2 | weekend | 328 | 36.89% | 31.85–42.24 | 21.3% |
| 2 | holiday | 75 | 53.33% | 42.16–64.18 | 57.3% |
| 3+ | 1 day | 962 | 46.99% | 43.85–50.15 | 28.0% |
| 3+ | weekend | 216 | 49.07% | 42.48–55.70 | 35.2% |
| 3+ | holiday | 43 | 44.19% | 30.43–58.89 | 55.8% |

Monotone in break length at N = 1 and N = 2. **The holiday cell is a mirage for a trader**:
51.9% of holiday boards open unfillable, so the extra continuation is mostly unbuyable.

### Friday vs Tue/Wed/Thu — uncontrolled, then controlled

| Era | Board | N | Friday | Midweek | Δ | intervals overlap? |
|---|---|---|---|---|---|---|
| fit | main | 1 | 19.69% (4,174) | 16.71% (14,655) | **+2.98** | **No** |
| holdout | main | 1 | 19.12% (2,579) | 14.64% (7,936) | **+4.48** | **No** |
| fit | main | 2 | 58.84% (1,069) | 34.94% (2,178) | +23.90 | No |
| holdout | main | 2 | 37.17% (339) | 27.58% (1,374) | +9.59 | No |
| fit | chinext | 1 | 20.91% (942) | 16.85% (3,247) | +4.06 | No |
| holdout | chinext | 1 | 11.95% (226) | 5.56% (594) | +6.39 | No |

**Now inside each gap band — main N = 1, holdout:**

| Band | Friday | Midweek | Δ | overlap? |
|---|---|---|---|---|
| g0 g < −3% | 2.52% (119) | 3.64% (357) | −1.12 | Yes |
| g1 −3…0% | 3.88% (515) | 3.69% (1,868) | **+0.19** | Yes |
| g2 0…+2% | 6.66% (781) | 6.21% (2,800) | **+0.45** | Yes |
| g3 +2…+5% | 19.18% (657) | 18.96% (1,888) | **+0.22** | Yes |
| g4 +5…+9.5% | 45.56% (338) | 41.59% (666) | +3.97 | Yes |
| g6 unfillable | 84.52% (155) | 77.88% (339) | +6.64 | Yes |

**Every band overlaps, and the deltas collapse from +4.48 pp to +0.2–0.5 pp in the three
best-populated bands.** The mechanism is visible in one number: Friday boards gap **+2.20%** on
average against **+1.52…+1.68%** midweek. **Friday's edge is the gap.** (The fit window's
enormous N = 2 within-band Fridays — +36.0 pp at g3, +38.9 pp at g4, both disjoint — do not
survive: holdout gives −3.03 pp and +9.04 pp, both overlapping. Printed as an example of what a
fit-window-only weekday effect looks like.)

### Weekday expectancy — main, entry book

| Rule | Era | Mon | Tue | Wed | Thu | **Fri** |
|---|---|---|---|---|---|---|
| E1 | fit | −0.744% | −0.807% | −0.832% | **+0.549%** | −0.196% |
| E1 | holdout | −0.687% | −0.116% | −0.340% | **−0.533%** | −0.229% |
| E3 | fit | −0.385% | −0.055% | −0.580% | **+0.409%** | −0.760% |
| E3 | holdout | −0.375% | −0.283% | −0.028% | −0.334% | **−0.006%** |

Friday is mid-pack and negative in both eras. **The fermentation effect converts to no
expectancy.** Note Thursday: the fit window's best weekday by a distance (+0.549% / +0.409%)
becomes ordinary out of sample (−0.533% / −0.334%). That sign flip is what a weekday expectancy
split is actually made of.

**WEEKEND VERDICT.** The effect is **real as a probability observation and era-stable**; it is
**not independent information** (fully absorbed by the gap band); and it is **worth nothing in
the entry book**. The operator's hypothesis is confirmed in its observable and refuted in its
mechanism — as far as *this* construction can see it. §ORE LEDGER: overnight message-board
volume, the actual proposed mechanism, is not held by this repo and was not tested.

---

## C5 — THE GAP-CONTINUOUS SHAPE (main, N = 1)

20 quantile bins on the **values** of g, so ties share a bin and the realised bin count and
sizes are printed rather than assumed equal.

### Holdout, fillable opens only — 19 realised bins

| bin | g range | n | P(next board) | Wilson | ↓limit | open→close mean |
|---|---|---|---|---|---|---|
| 0 | −10.24…−2.82% | 638 | 3.92% | 2.67–5.72 | **11.76%** | **+1.454%** |
| 1 | −2.82…−1.83% | 638 | 3.92% | 2.67–5.72 | 2.98% | +0.872% |
| 2 | −1.82…−1.14% | 638 | 3.92% | 2.67–5.72 | 3.29% | +0.351% |
| 3 | −1.14…−0.66% | 638 | 3.13% | 2.04–4.79 | 2.35% | −0.133% |
| 4 | −0.66…−0.21% | 638 | 2.82% | 1.79–4.42 | 1.88% | +0.088% |
| 5 | −0.21…0.00% | 1,287 | 3.34% | 2.49–4.47 | 0.47% | −0.012% |
| 6 | 0.01…+0.31% | 627 | 4.78% | 3.37–6.75 | 0.48% | +0.535% |
| 7 | +0.31…+0.67% | 638 | 4.39% | 3.05–6.27 | 1.10% | +0.122% |
| 8 | +0.67…+1.02% | 638 | 5.33% | 3.84–7.35 | 1.57% | +0.270% |
| **9** | **+1.02…+1.41%** | 638 | **7.69%** | 5.87–10.02 | 0.47% | +0.350% |
| 10 | +1.41…+1.76% | 638 | 7.37% | 5.58–9.66 | 0.47% | +0.160% |
| 11 | +1.76…+2.04% | 638 | 10.34% | 8.21–12.95 | 0.47% | +0.236% |
| 12 | +2.04…+2.53% | 638 | 11.76% | 9.48–14.49 | 0.78% | +0.065% |
| 13 | +2.53…+2.98% | 638 | 14.42% | 11.91–17.36 | 0.78% | +0.094% |
| 14 | +2.98…+3.53% | 638 | 18.50% | 15.67–21.69 | 0.31% | −0.199% |
| 15 | +3.53…+4.23% | 638 | 21.16% | 18.17–24.50 | 0.78% | −0.255% |
| 16 | +4.23…+5.04% | 638 | 28.21% | 24.86–31.83 | 0.94% | −0.503% |
| 17 | +5.04…+6.50% | 638 | 36.21% | 32.57–40.01 | 0.94% | −0.567% |
| **18** | **+6.50…+9.88%** | 638 | **45.92%** | 42.09–49.80 | 0.31% | **−1.797%** |

**Shape verdict, all six curves (3 eras × all-opens / fillable-only):**

| | adjacent decreases | **with disjoint Wilson** | down-gap floor | elbow (first bin at 2× floor) | peak | **rolls over?** |
|---|---|---|---|---|---|---|
| holdout, fillable | 4 | **0** | 3.63% | g = +1.02% (7.69%) | last bin, 45.92% | **No** |
| holdout, all opens | 5 | **0** | 3.50% | g = +0.93% (7.71%) | last bin, 68.08% | **No** |
| fit, fillable | 4 | **0** | 3.40% | g = +0.83% (6.98%) | last bin, 45.03% | **No** |
| fit, all opens | 2 | **0** | 3.58% | g = +1.03% (7.49%) | last bin, 82.82% | **No** |
| all, fillable | 3 | **0** | 3.29% | g = +1.11% (8.13%) | last bin, 45.24% | **No** |
| all, all opens | 2 | **0** | 3.45% | g = +1.00% (7.37%) | last bin, 77.53% | **No** |

**Answer to the brief's question: monotone, not humped.** A bare "is every step up?" test reads
False, but every one of those steps down is a sub-1 pp wobble inside the flat floor whose Wilson
intervals overlap; **there is not a single Wilson-disjoint decrease in any of the six curves**,
and the peak is the top bin in all six. The structure is a **floor, an elbow, and a ramp**: any
gap below zero is worth the same 3.3–3.6%, the curve lifts off at **g ≈ +1%**, and it climbs
without turning over.

**And the companion column is the whole study in one line.** `open→close mean` runs
**+1.454% → −1.797%** monotonically down as P(next board) runs 3.9% → 45.9% up. The bins that
board are the bins that give the day back.

---

## PRICE BASIS — a measured correction to an inherited description

An A-share close is always a whole number of 0.01 ticks, so a non-2-decimal close is proof of an
applied adjustment factor. Measured over all 4,843,576 live bars:

| Year | share of closes on the 0.01 tick | | Year | share |
|---|---|---|---|---|
| 2011 | **36.4%** | | 2019 | 72.1% |
| 2013 | 43.6% | | 2021 | 78.1% |
| 2015 | 51.8% | | 2023 | 86.6% |
| 2017 | 63.1% | | 2025 | 93.7% |
| 2018 | 67.3% | | **2026** | **96.6%** |

609 of 1,836 names are on-tick for their entire history; for the rest the last off-tick bar has
median **2019-06-18**. That monotone rise toward the present, with a per-name boundary, **is the
back-adjustment signature**. `data/china_stocks_raw` is back-adjusted, not nominal — v0's header
description of it is wrong and should be corrected in the CN data-plane docs.

**This explains v0's definition adjudication rather than overturning it.** Rounding a *scaled*
price to a 0.01 tick is precisely why `close ≥ round(prev_close×(1+w), 2)` is brittle against
its own inputs, and why a cushion was needed. What matters here is whether 0.002 is a big
enough cushion, and it is: the tick-rounding error on the limit price is p50 **0.016%**, p90
**0.065%**, p99 **0.150%**, p99.9 **0.297%**, max 1.608%; **18,162 of 4,843,576 bars (0.375%)**
exceed the tolerance. **Returns are unaffected** — adjustment preserves them — so every gap,
every open→close and every trade return in this document is untouched by this. Only the
round-to-tick step is.

---

## WHAT THIS DOES NOT ESTABLISH

- **No significance claim beyond Wilson intervals.** Limit moves cluster hard in time and
  cross-section; a naive binomial interval understates the true uncertainty. Every entry-book
  cell carries `n_dates` and `top5_name_share_pct` in the JSON so the clustering is visible
  (main E1 holdout: 15,428 trades over 1,134 dates). The tests used are **out-of-sample sign
  stability** and **interval disjointness**, not p-values.
- **The entry book is not a strategy.** No sizing, no capital constraint, no concurrency cap,
  no cross-trade correlation. It is a mean-per-trade measurement. A day with 200 simultaneous
  signals and a day with one are weighted identically.
- **Slippage is not modelled.** Fills are assumed at the printed open, which is optimistic for
  exactly these names. The 15 bp cost column is stamp duty plus commission only. The true book
  is worse than the one printed here, in the same direction as the null.
- **The negative expectancy is a statement about THESE THREE EXITS at THIS ENTRY.** It is not a
  statement about the 打板 game, which is played intraday. See §ORE LEDGER.
- **The g0 reversal cells are not a finding.** They are the only positive main-board cells with
  real n and they flip sign across the split in two of three rules.
- **The limit-down cells are survivors-only** and therefore optimistic — the terminal down-limit
  runs of delisted names are simply absent from this store.
- **ChiNext fit and holdout are different markets** (±10% vs ±20%). Their cells must not be
  compared to each other, and STAR is thin throughout.
- **Fillability is modelled as a binary at the open.** A name that opens 0.1% below the limit is
  treated as fully fillable; in practice the book there is nearly as thin as a sealed one. This
  makes the entry book *optimistic*, again in the direction of the null.
- **Nothing is promoted.** Display/audit tier; the gauntlet applies at promotion, and nothing
  here is being promoted.

---

## ORE LEDGER — untested variants

**THE ORE LAW: a null closes the construction tested, never the hypothesis.** §C2's negative
expectancy closes *one* entry (the T+1 open) with *three* exits on *daily* bars. It says nothing
about any of the following, none of which was tested and none of which is refuted by anything
above.

| # | Untested variant | Blocked by | Why it matters |
|---|---|---|---|
| 1 | **Intraday pullback entries** — the first dip after a strong open, or the 09:35 / 10:00 print instead of the open | needs minute bars | The gap bands here are entry-*timed* but entry-*priced* only at the open. The g4 band's −1.009% mean open→close with a **+0.372% median** is a left-tail story: most g4 days are fine and a minority collapse. A pullback entry or an intraday stop addresses exactly that shape and **is not tested here.** This is the single highest-value next construction. |
| 2 | **Seal-break (开板) re-entry** — buy when a sealed board breaks and re-seals | needs intraday first-touch times and seal-break counts (v0 collector #3) | The most-used discretionary 打板 entry, entirely invisible in a daily bar where a 09:31 seal and a 14:55 seal are one row. |
| 3 | **Closing-auction imbalance at T** (14:57–15:00 集合竞价) | v0 collector #2 — not collected | The mechanism the gap is a downstream proxy for. If the imbalance is the real conditioner, the gap bands are a lossy shadow of it. |
| 4 | **封单量 conditioning** (resting order-wall volume at the limit) | held 2026-06-15 forward only, no history | Without it "limit-up" pools a ~100× range of demand into one flag; the practitioner's primary conviction measure. |
| 5 | **Regime-gate interaction** — does the rider only work in hot tape? | deliberately out of scope: this is the Wave-2 cross with the L2 market-state lane | The by-year table shows a 3× era swing in the cohort base rate. A market-state gate is the obvious conditioner and is **not** tested here. |
| 6 | **Stop-loss exit family** — fixed %, ATR, trailing, intraday | an intraday stop is unmeasurable on daily bars without assuming a path; a close-based stop was not in the pre-registered exit set | The p10 and worst-trade columns are where a stop would bind. Three exits is not the exit space. |
| 7 | **Per-N and per-band exit tuning** | not run by design, so the cohort comparison stays like-for-like | An E3 tuned per cohort is an obvious improvement and an obvious overfit; it needs its own holdout discipline. |
| 8 | **ST universe (5% band) and BSE (30%)** | ST dropped wholesale (no membership history); the store carries **zero** BSE names | The 打板 game lives disproportionately in small-cap and ST names. This study cannot see them at all. |
| 9 | **Replication on the zt_pool universe** (the vendor's whole-market limit-up pool) | zt_pool covers 2026-06-15 forward only | Only 29% of the names that hit the vendor's pool exist in our universe. The largest single limitation of every number here. |
| 10 | **Overnight discussion volume** — the actual proposed fermentation mechanism | no such store in this repo | §C4 shows Friday's *observable* (a bigger gap) and shows it carries no information beyond the gap. It does **not** test whether after-hours discussion causes the gap. |
| 11 | **Short side / limit-down riding** | A-share retail shorting is largely unavailable; the store is survivors-only | The limit-down cells printed here are survivor-biased upward and must **not** be read as a short opportunity. |
| 12 | **Sector / theme cohort conditioning** — is the rider a theme-wave artifact? | not run in this lane; v0's f4 sector-heat feature is the nearest probe | The clustering receipt shows trades arrive in waves. Whether the gap edge survives *within* a wave is untested. |

**What a kill here would and would not mean.** Nothing above is killed. The measured statements
are: *(a)* the open gap is a strong, era-stable, entry-timed conditioner of continuation
probability — **kept**; *(b)* roughly half the published continuation is unbuyable — **kept**;
*(c)* the open-entry / daily-exit construction converts (a) into no expectancy — **that specific
construction is null**; *(d)* weekday fermentation adds nothing beyond the gap — **that specific
construction is null**. "Not found at the open on daily bars" is not "does not exist".

---

## REPRODUCE

```
cd <repo root>
TZ=UTC python3 research/cn_prophet_audit/continuation_rider_v1.py
```

Fully deterministic (ticker-sorted; the only subsampling is the disclosed every-500th-bar
tick-error sample in the price-basis audit). Runtime **10.6 s**. Writes
`research/cn_prophet_audit/CONTINUATION_RIDER_V1_2026-08-08.json`, which carries every cell in
this document plus the full band tables for all three eras, the complete 20-bin curves, the
per-cell clustering receipts, and the v0 parity gate.
