# CN LIMIT-MOVE FOOTPRINT v0 — event catalog, base rates, pre-registered features

**Charter:** `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(f), ANTICIPATION program.
**Instrument:** `research/cn_prophet_audit/limit_move_footprint_v0.py` ·
**Frozen numbers:** `LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json` · **Runtime:** ~32s ·
**Window:** 2011-01-01 → 2026-08-07 · **Basis:** `data/china_stocks_raw` (nominal OHLCV).

**Tier: display / audit. MEASUREMENT ONLY.** Nothing here ranks, sizes, gates, admits or
promotes anything. No LLM is involved at any point. **No base rate, lift or share in this
document is pooled across board types** — a ±10% main-board name and a ±20% ChiNext name do not
share a base rate, and averaging them would invent a number that describes no market. (Where
whole-catalog *counts* appear, they are plain sums and are labelled as such.)

---

## DECISION SUMMARY

1. **The event catalog exists and is trustworthy.** 60,298 limit-up closes, 28,857 limit-down
   closes and 2,017 near-limit closes over 4.98M ticker-days / 1,836 names / 15.6 years (sums
   across boards; the per-board tables are the readable form). Two independent checks: the
   detector reproduces **100%** of the events `engine.china_microstructure._detect_limit_events`
   emits when run on the same strict rule (656/656, 25-ticker sample) at **99.85% precision**,
   and **97.2% of names (1,465/1,507) match the committed house tape exactly**.
2. **The definition question was decided by measurement, and it overturned this instrument's
   first answer.** An earlier draft treated the charter's "close at or within 0.2% of the limit"
   as a *widening* and made the strict test primary. That was wrong. Of the 28,401 marginal
   events — admitted by tolerant, rejected by strict — the median moved **exactly 100.000% of
   the band**, and **43.4% moved strictly MORE than the full band**, which is impossible for a
   real limit-up and is therefore direct evidence of price noise in this third-party feed rather
   than of near-limit closes being swept in. Independently, the vendor scrape in
   `data/china_zt_pool` agrees with the tolerant 连板 reconstruction on **99.8%** of matched rows
   versus **91.1%** for strict. **The charter's tolerance is a rounding cushion, exactly as
   specified; it is primary.** Strict is retained in full as a parallel column.
3. **THE BINDING CAVEAT — the universe is curated, not the market.** `data/china_stocks_raw`
   holds 1,842 names against a listed A-share market of roughly 5,400. Two store-measured
   probes: only **1 of 100** current ST names is present, and only **514 of the 1,770 names
   (29%)** that hit `china_zt_pool`'s limit-up pool exist here. The 打板 game lives
   disproportionately in exactly the small-cap and ST names this universe omits. **Every number
   below describes a curated large/mid-cap universe. None is a market-wide statistic.**
4. **The single strongest conditioner is the event itself, not any feature.** Main board: the
   unconditional chance a name closes at the limit on its next usable bar is **1.27%**. Given it
   just closed at its first limit-up, **16.50%** — a **13× lift**, free, before a single feature
   is computed. The best *stable* feature's top decile reaches 4.88%, so the 连板 state is
   **3.4× stronger than the best of the eight features**.
5. **The 连板 ladder is monotone on both boards with the sample to show it.** Main 16.50% →
   36.61% → 45.52% → 54.37% → 66.91% → 72.78% for N = 1…6. ChiNext 16.76% → 39.12% → 52.48% →
   63.47% → 78.83%. STAR runs out of sample at N=2.
6. **But the base rate is an era artifact, not a constant.** The main-board first-board →
   second-board rate ranges **7.93% (2011) to 24.18% (2015)** — a 3× swing. The pooled 16.50% is
   an average over eras that genuinely differ.
7. **ChiNext's 2020 band change is the largest single structural break in the data.** After the
   ±10% → ±20% move on 2020-08-24, ChiNext first-board continuation falls from 15.75% (2020) to
   **5.45% (2022) / 5.43% (2026)**, and limit-up counts fall from 973 (2020) to 257 (2021).
   ChiNext pre- and post-2020-08-24 must never be pooled — which is why Stage 3 carries a
   dedicated era control.
8. **Six of the eight pre-registered features are sign-stable on the holdout, on all three
   boards AND in the ChiNext band-era control.** Main-board holdout top-decile lifts: f3
   5-session run-up **3.93×**, f7 distance-from-52w-low **3.27×**, f6 gap **3.07×**, f1 volume z
   **2.58×**, f4 sector heat **2.39×**, f8 consecutive up-days **2.33×**.
9. **f5 prior-session near-limit is printed UNSTABLE — the pre-registration mechanism firing
   as designed.** It looks spectacular pooled on main (7.22×) and is not real: its class is
   **0.03% of rows** (378 holdout rows), its **per-name median lift is 0.00** with only 28 of
   208 names above 1×, it flips sign on STAR (fit 0.00 → holdout 75.7×), and it collapses in the
   ChiNext era control (fit 65.2× → holdout **0.00**). Printed, not averaged, not promoted.
10. **The six stable features are NOT one finding measured six times** — tested two ways, not
    assumed. Max off-diagonal Spearman is **0.375**; more to the point, since top-decile lift is
    a *tail* statistic, the max pairwise **Jaccard overlap between their top buckets is 0.216**.
    Different rows, different information.
11. **f2 turnover ratio is a printed NULL — not measurable on this basis.** No CN store carries
    per-date shares outstanding or free float. The pre-registered set stays at eight; **no ninth
    feature was substituted.** That swap is the exact move this design exists to block.
12. **Absolute probabilities stay small.** 3.93× on a 1.25% base rate is 4.88%. Every *stable*
    feature cell describes an event that still does not happen ~95% of the time.
13. **Side finding, flagged not acted on:** `data/china_microstructure/limit_events.parquet` is
    **missing pre-2026-07 history for 34 names** (14 absent entirely), carrying 1,059 of the
    1,065-event strict-basis delta — while its own `backfill` flag reads `True` for all 3,751
    market-days, so the flag does not surface the hole. CN data-plane repair, out of scope here.

---

## THE DEFINITION ADJUDICATION (why tolerant is primary)

Both definitions are computed everywhere; this is why the tolerant one leads.

| Marginal events (tolerant admits, strict rejects) | 28,401 |
|---|---|
| Move as a fraction of the full band — p25 / **p50** / p75 | 0.998 / **1.00000** / 1.001 |
| p90 / p99 / max | 1.003 / 1.010 / **1.047** |
| Share at or above 99.95% of the band | **60.0%** |
| **Share strictly ABOVE the full band** | **43.4%** |
| Share below 99.5% of the band | 9.7% |

A close cannot exceed the limit. That 43.4% of these events *appear* to is proof that the feed's
prices do not exactly reproduce exchange closes, so `close ≥ round(prev_close×(1+w), 2)` is
brittle against its own inputs. The 0.2% cushion absorbs that noise. It also absorbs a real
minority (~9.7%) of genuine near-limit closes — a real cost, and the reason the strict column is
kept in full rather than dropped.

**The corroboration matters more than the percentiles.** The house tape agrees with strict, but
it applies the strict rule to the same prices, so that agreement is *definitional*, not evidence.
The only outside check is `china_zt_pool`, an independently scraped vendor limit-up pool:

| 连板 agreement within matched rows | tolerant (primary) | strict |
|---|---|---|
| matched rows | 949 | 496 |
| **exact 连板 agreement** | **99.79%** (947) | **91.13%** (452) |

(The *match* rate — 24.7% / 12.9% of the vendor's rows — is a universe fact, not a detection
score: the vendor covers the whole market, our store covers a curated slice.)

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Price basis | `data/china_stocks_raw` — nominal/unadjusted. The adjusted twin `data/china_stocks` would fabricate limit misses (adjustment breaks the `round(prev_close×(1+w),2)` relation entirely). |
| Names in store | 1,842 · kept 1,836. For scale, the listed A-share market is roughly 5,400 names — an external reference figure, not one these stores measure. The two store-measured probes are the next two rows. |
| ST names present | **1 of 100** current ST names |
| zt_pool names present | **514 of 1,770 (29%)** |
| Ticker-days | 4,981,168 · usable after exclusions 4,843,576 |
| Boards | main 1,243 · chinext 351 · star 242 · **bse 0** |
| Sector coverage | 93.68% of ticker-days (`data/china_search/members.parquet`, CURRENT mapping applied to 15y of history) |
| Excluded bars | zero-volume/suspension 133,781 · ex-div suspect 621 · IPO window 2,793 |
| Pairs dropped | 22,205 total — **8,522** from the >10-calendar-day suspension rule, **13,683** from a next bar that exists but is itself excluded, plus each name's final in-window bar |
| Usability asymmetry | A bar's usability at T+1 is a property of T+1, so conditioning on it is a filter a trader at T could not apply. Applied uniformly to numerator and denominator, so lift ratios are essentially unaffected; the base rates are rates **among usable next bars**. |
| 2015 concentration | 18.6% of all main-board limit-ups and **38.5%** of all main-board limit-downs fall in 2015 alone — entirely inside the fit window; the holdout has no comparable event. |
| Survivorship | The store holds the CURRENT listed universe. Delisted names are absent, which biases the **limit-down** numbers most — the terminal down-limit runs of delisted names are simply not here. Read every limit-down cell as survivors-only. |
| ST residual | Names that WERE ST historically but are not today remain at a 10% band. Not fixable with the stores we hold; not patched over. |

---

## DEFINITIONS (stated inline, as required)

- **`w` (limit width)** — `engine.china_microstructure.limit_width_for_date`, **imported, not
  reimplemented**: STAR 20%; ChiNext 20% on/after `CHINEXT_WIDE_DATE` 2020-08-24 else 10%; main
  10%; BSE 30%; ST 5% on main only. Board from `_board_from_ticker` (688/689 → star, 300/301/302
  → chinext, 8/4/92 → bse, else main).
- **`limit_up_close` (PRIMARY)** — `close ≥ round(prev_close×(1+w), 2) × (1 − 0.002)`.
- **`limit_up_close` (strict)** — `close ≥ round(prev_close×(1+w), 2)`, the house tape's rule,
  carried as a full parallel column.
- **`near_limit_up`** — return ≥ 0.95 × w (9.5% on a 10% board, 19% on a 20% board) **and** not a
  limit close. Under the primary definition this is a deliberately narrow band (~9.5%→9.78% on a
  10% board), which is why it is a small class.
- **`连板 N`** — consecutive limit-up closes ending on the bar. Any non-limit bar, including an
  excluded one, resets it to 0. **`first_board`** = N is 1; **`continuation`** = N ≥ 2.
- **`T → T+1`** — the name's next usable bar, at most 10 calendar days later.
- **Exclusions** — ST cohort (all dates); STAR/ChiNext first 5 sessions and pre-2014 listings'
  first session (44%-cap IPO regime, the module's own windows); ex-dividend suspects
  (`|open − prev_close| / prev_close > 1.5 × w`); zero-volume bars. Every ticker's first bar is
  independently unusable (no prev_close).

---

## STAGE 1 — EVENT CATALOG

### By board (2011-01-01 → 2026-08-07)

| Board | Names | Ticker-days | Limit-up | rate | (strict) | ×strict | Limit-down | rate | Near-limit-up | max 连板 |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 1,243 | 3,817,967 | **50,421** | 1.321% | 26,682 | 1.89× | **24,111** | 0.632% | 1,578 | 25 |
| chinext | 351 | 757,341 | **8,999** | 1.188% | 4,776 | 1.88× | **4,636** | 0.612% | 371 | 25 |
| star | 242 | 268,268 | **878** | 0.327% | 439 | 2.00× | **110** | 0.041% | 68 | 10 |

**STAR barely plays this game** — a 20%-band board of large, institutionally-held tech names
produces 0.33% limit-up days and 110 limit-down days in six years.

### 连板 distribution (count of limit-up days at each N)

| Board | N=1 | 2 | 3 | 4 | 5 | 6 | 7 | 8+ |
|---|---|---|---|---|---|---|---|---|
| main | 38,684 | 6,331 | 2,293 | 1,028 | 555 | 366 | 262 | 902 |
| chinext | 6,636 | 1,105 | 428 | 222 | 139 | 108 | 80 | 281 |
| star | 778 | 78 | 10 | 5 | 2 | 1 | 1 | 3 |

### Main board by year — the era story

| Year | Names | Limit-up | Limit-down | Near-limit-up | LU per 1k ticker-days |
|---|---|---|---|---|---|
| 2011 | 811 | 882 | 338 | 38 | 4.85 |
| 2012 | 833 | 1,171 | 295 | 43 | 6.00 |
| 2013 | 842 | 1,757 | 386 | 80 | 9.09 |
| 2014 | 873 | 2,258 | 362 | 93 | 11.47 |
| **2015** | 916 | **9,368** | **9,279** | 392 | **48.83** |
| 2016 | 958 | 2,547 | 2,549 | 58 | 12.09 |
| 2017 | 1,031 | 1,891 | 516 | 41 | 8.22 |
| 2018 | 1,074 | 1,416 | 1,285 | 52 | 5.75 |
| 2019 | 1,116 | 2,702 | 978 | 82 | 10.23 |
| 2020 | 1,156 | 4,292 | 1,747 | 187 | 15.61 |
| 2021 | 1,184 | 5,316 | 1,296 | 129 | 18.72 |
| 2022 | 1,199 | 3,484 | 1,040 | 70 | 12.10 |
| 2023 | 1,212 | 2,062 | 473 | 34 | 7.07 |
| 2024 | 1,219 | 3,915 | 1,032 | 169 | 13.36 |
| 2025 | 1,235 | 3,745 | 1,364 | 51 | 12.59 |
| 2026 (partial) | 1,243 | 3,615 | 1,171 | 59 | 20.28 |

ChiNext limit-ups by year: 66 · 130 · 405 · 374 · **2,393** · 708 · 630 · 700 · 1,083 · 973 ·
**257** · 117 · 197 · 494 · 273 · 199 — the 2021 cliff coincides with the ±20% band arriving
(2020-08-24). The instrument does not test that attribution; it is the obvious candidate and is
offered as one, alongside the 2021 market context.
STAR (2019→): 5 · 58 · 61 · 61 · 78 · 252 · 169 · 194.

### Sector distribution (share of that board's limit-ups)

| Board | Top sectors |
|---|---|
| main | Industrials 21.3% · Basic Materials 18.5% · Technology 17.2% · Consumer Cyclical 8.9% · *UNKNOWN 7.1%* · Healthcare 5.6% |
| chinext | **Technology 44.7%** · Industrials 21.1% · Healthcare 9.9% · Basic Materials 8.6% · *UNKNOWN 7.3%* · Communication Services 4.0% |
| star | **Technology 57.1%** · Industrials 15.5% · *UNKNOWN 11.7%* · Healthcare 7.3% · Basic Materials 7.1% |

*UNKNOWN* is the share with no row in the sector map — printed, not dropped.

---

## STAGE 2 — BASE RATES (no features)

**P(limit-up close at T+1 | 连板 = N at T).** Pooled beside per-name-first. Wilson 95%. Cells
with n < 20 labelled **THIN**.

| Board | N | n | P(next board) | Wilson 95% | per-name median (names) |
|---|---|---|---|---|---|
| main | 1 | 38,290 | **16.50%** | 16.13–16.87 | 15.15% (1,090) |
| main | 2 | 6,257 | **36.61%** | 35.43–37.82 | 40.00% (170) |
| main | 3 | 2,254 | **45.52%** | 43.47–47.58 | 43.56% (4) |
| main | 4 | 1,019 | **54.37%** | 51.30–57.40 | — (0) |
| main | 5 | 547 | **66.91%** | 62.86–70.72 | — (0) |
| main | 6 | 360 | **72.78%** | 67.96–77.12 | — (0) |
| chinext | 1 | 6,587 | **16.76%** | 15.88–17.68 | 15.59% (212) |
| chinext | 2 | 1,094 | **39.12%** | 36.27–42.05 | 35.71% (17) |
| chinext | 3 | 423 | **52.48%** | 47.72–57.20 | — (0) |
| chinext | 4 | 219 | **63.47%** | 56.91–69.56 | — (0) |
| chinext | 5 | 137 | **78.83%** | 71.25–84.84 | — (0) |
| chinext | 6 | 105 | **76.19%** | 67.21–83.32 | — (0) |
| star | 1 | 773 | **10.09%** | 8.16–12.42 | 9.55% (10) |
| star | 2 | 77 | **12.99%** | 7.21–22.28 | — (0) |
| star | 3 | 10 | 50.00% | 23.66–76.34 | **THIN** |

**Unconditional next-bar limit-up:** main **1.27%** · chinext **1.14%** · star **0.32%**.
A first board multiplies the next-bar odds by **13×** (main), **15×** (chinext), **32×** (star).

**Limit-down mirror** — continuation is real here too, but the survivorship caveat bites hardest:

| Board | N | n | P(next down-limit) | Wilson 95% |
|---|---|---|---|---|
| main | 1 | 19,678 | **14.85%** | 14.36–15.36 |
| main | 2 | 2,886 | **26.65%** | 25.06–28.29 |
| main | 3 | 747 | **38.55%** | 35.13–42.09 |
| chinext | 1 | 3,847 | **13.54%** | 12.50–14.66 |
| chinext | 2 | 523 | **26.96%** | 23.33–30.92 |
| chinext | 3 | 136 | **34.56%** | 27.09–42.88 |
| star | 1 | 110 | **0.00%** | 0.00–3.37 |

Unconditional next-bar limit-down: main 0.60% · chinext 0.58% · star 0.03%. STAR's 0/110 is a
printed null, not an omission. (These are rates over *usable next bars*; the whole-catalog
limit-down rates over all live ticker-days in Stage 1 — 0.632% / 0.612% / 0.041% — use a
different denominator and are not the same statistic.)

### P(second board | first board) by year — the base rate is not a constant

| Year | main n | main rate | chinext n | chinext rate |
|---|---|---|---|---|
| 2011 | 769 | **7.93%** | 62 | 4.84% |
| 2012 | 996 | 11.75% | 107 | 13.08% |
| 2013 | 1,426 | 13.25% | 335 | 14.63% |
| 2014 | 1,706 | 16.47% | 308 | 12.01% |
| 2015 | 6,240 | **24.18%** | 1,524 | 24.80% |
| 2016 | 1,894 | 12.99% | 472 | 12.71% |
| 2017 | 1,140 | 18.60% | 375 | 19.20% |
| 2018 | 1,202 | 8.15% | 514 | 16.93% |
| 2019 | 2,047 | 15.53% | 793 | 18.03% |
| 2020 | 3,170 | 17.32% | 762 | 15.75% |
| 2021 | 4,349 | 13.68% | 229 | 9.61% |
| 2022 | 2,835 | 13.62% | 110 | **5.45%** |
| 2023 | 1,727 | 11.99% | 177 | 5.65% |
| 2024 | 2,838 | 22.20% | 381 | 20.21% |
| 2025 | 3,008 | 15.96% | 254 | 6.30% |
| 2026 | 2,943 | 14.88% | 184 | **5.43%** |

**Two reading rules, both load-bearing:**

- **The ladder is conditioned-on-reaching, not a survival curve.** A run that reached 8 boards
  contributes a row at N = 1…7, every one of which continued. Read a cell as *"a day inside an
  N-board run is followed by another board X% of the time"* — never as *"the Nth board continues
  X% of the time"*.
- **The per-name column thins out fast by construction.** A name needs ≥ 10 conditioning events
  in the *same* cell to contribute. Only N=1 clears that for a meaningful count (1,090 main
  names); at N ≥ 3 the qualifying names are, by construction, the serial-limit names, so those
  medians are a selected sub-population and are **not** a check on the pooled number.

---

## STAGE 3 — PRE-REGISTERED FOOTPRINT SET

**Eight features, named in the charter before any of this ran.** Measured at the T-1 close,
predicting a limit-up close at T. **Fit / inspect on the first 70% of trading dates (2011-01-05 →
2021-11-25, 2,646 dates, 2.86M rows); REPORTED on the last 30% holdout only (2021-11-26 →
2026-08-06, 1,135 dates, 1.96M rows).**

| # | Feature | Status |
|---|---|---|
| f1 | volume z-score of the T-1 bar vs its own prior 20 bars | measured |
| f2 | turnover ratio (volume / shares outstanding) | **NULL — not measurable** |
| f3 | 5-session run-up, `close[T-1]/close[T-6] − 1` | measured |
| f4 | same-day sector limit-up count at T-1, **leave-one-out** | measured |
| f5 | prior-session near-limit flag (near-limit-up at T-1) | measured → **UNSTABLE** |
| f6 | gap at the T-1 open, `open[T-1]/close[T-2] − 1` | measured |
| f7 | distance from 52w low, `close[T-1]/min(low, 252) − 1` | measured |
| f8 | consecutive up-close days ending at T-1 | measured |

### HOLDOUT lift — main board (holdout base rate 1.245%)

Buckets are quantile bins **on feature values**, so tied values share a bucket: only f1, f3, f6
and f7 realise a full ten. The realised bucket count and the top bucket's share of rows are
printed because "top decile" would otherwise be a false label.

| Feature | buckets | top bucket = % of rows | fit top lift | **holdout top lift** | holdout top rate | bottom | verdict |
|---|---|---|---|---|---|---|---|
| f3 run-up 5d | 10 | 10.0% | 3.76× | **3.93×** | 4.88% | 1.29 | stable-sign |
| f7 dist 52w low | 10 | 9.9% | 2.98× | **3.27×** | 4.02% | 0.34 | stable-sign |
| f6 gap % | 9 | 10.0% | 3.36× | **3.07×** | 3.82% | 1.90 | stable-sign |
| f1 volume z20 | 10 | 10.0% | 2.34× | **2.58×** | 3.20% | 0.71 | stable-sign |
| f4 sector heat | 5 | 7.8% | 2.86× | **2.39×** | 2.91% | 0.70 | stable-sign |
| f8 consec up-days | 3 | 9.8% | 2.92× | **2.33×** | 2.90% | 0.79 | stable-sign |
| **f5 near-limit-prev** | 2 | **0.03%** | 4.67× | 7.22× | 8.99% | 1.00 | **UNSTABLE — see below** |

Per-name-first (652 of 1,243 main names qualify), median top-bucket lift and the count of names
above 1×: f3 **3.48×** (624/650), f6 **2.67×** (609/652), f1 **2.34×** (595/648), f8 **2.13×**
(544/652), f4 **1.99×** (504/601), f7 **1.93×** (513/644). f5 is **0.00× (28/208)** — see below.

### Why f5 is printed UNSTABLE

This is the pre-registration mechanism doing its job on the one feature that most looks like a
discovery.

| Evidence | Reading |
|---|---|
| Top bucket = **378 rows**, 0.03% of the holdout | Not a decile; a rare flag |
| **Per-name median lift 0.00**, only **28 of 208** names above 1× | The pooled 7.22× is carried by a few names, not the population |
| STAR: fit 0.00× → holdout 75.7× (57 rows) | Sign flip; undefined in the fit window |
| ChiNext band-era control: fit 65.2× → holdout **0.00×** | Total collapse on a like-for-like split |

It is printed, not averaged into anything, and not promoted. Note the structural reason the class
is thin: under the primary definition the near-limit band is only ~9.5%→9.78% on a 10% board,
because the rest was correctly reclassified as limit closes (see the adjudication).

### HOLDOUT top-bucket lift — chinext and star

| Feature | chinext (base 0.350%) | star (base 0.324%) |
|---|---|---|
| f3 run-up 5d | 4.68× | 4.79× |
| f8 consec up-days | 4.17× | 4.31× |
| f6 gap % | 3.44× | 4.38× |
| f1 volume z20 | 3.28× | 3.40× |
| f4 sector heat | 2.83× | 3.78× |
| f7 dist 52w low | 2.55× | 2.90× |
| *f5 near-limit-prev* | *56.1× (n=56)* | *75.7× (n=57) — **UNSTABLE*** |

All six stable features sign-stable on both. **The per-name-first column is nearly empty here**
(19 of 351 chinext names, 7 of 242 star names qualify): at a ~0.33% base rate a name does not
accumulate enough holdout limit-ups to estimate its own curve. Rarity, not a bug.

### Is this six findings, or one finding measured six times?

**Tested two ways, not assumed** — a uniform "everything works" is the false-discovery signature.

Spearman correlation, main-board holdout (every 6th row, 228,899 of 1,373,390):

| | f1 | f3 | f4 | f5 | f6 | f7 | f8 |
|---|---|---|---|---|---|---|---|
| **f1** vol z | 1.00 | 0.33 | 0.11 | 0.02 | 0.07 | 0.02 | 0.23 |
| **f3** run-up | 0.33 | 1.00 | 0.14 | 0.02 | 0.10 | 0.18 | **0.38** |
| **f4** sector heat | 0.11 | 0.14 | 1.00 | 0.02 | 0.06 | 0.21 | 0.18 |
| **f5** near-limit | 0.02 | 0.02 | 0.02 | 1.00 | 0.01 | 0.01 | 0.02 |
| **f6** gap | 0.07 | 0.10 | 0.06 | 0.01 | 1.00 | −0.01 | 0.22 |
| **f7** dist 52w low | 0.02 | 0.18 | 0.21 | 0.01 | −0.01 | 1.00 | 0.10 |
| **f8** consec up | 0.23 | 0.38 | 0.18 | 0.02 | 0.22 | 0.10 | 1.00 |

But a global ρ answers *"are these the same variable"*, which is not the question a **top-decile**
lift raises — that is a tail statistic, and two features correlated at 0.10 overall could still
select nearly the same top rows. So the top buckets are compared directly:
**max pairwise Jaccard overlap = 0.216.** Different rows, different information.

A third control — recomputing every other feature's lift with all f5-flagged rows removed —
returns changes under 0.5% (f3 3.933 → 3.924). Under the primary definition that control is
**near-vacuous by construction**, because f5 flags only 0.03% of rows; it is reported for
completeness, and the Jaccard is what carries the claim.

### ChiNext band-era control

The global 70/30 split lands at 2021-11-26, **after** ChiNext's 2020-08-24 move to a ±20% band,
so ChiNext's fit window is mostly a 10%-band market and its holdout entirely a 20%-band one (fit
base 1.87% vs holdout 0.35% — a rule change, not a signal). Re-split inside the ±20% era only
(438,042 rows, split 2024-10-25; fit base 0.350% vs holdout 0.370% — now like-for-like):

| Feature | fit top-lift | holdout top-lift | verdict |
|---|---|---|---|
| f3 run-up 5d | 4.87× | **3.57×** | stable-sign |
| f6 gap % | 3.63× | **2.40×** | stable-sign |
| f7 dist 52w low | 2.33× | **2.29×** | stable-sign |
| f1 volume z20 | 3.70× | **2.26×** | stable-sign |
| f8 consec up-days | 4.63× | **1.92×** | stable-sign |
| f4 sector heat | 3.57× | **1.45×** | stable-sign |
| f5 near-limit-prev | 65.2× | **0.00×** | **UNSTABLE** |

**Every stable sign holds; every magnitude compresses**, f4 and f8 by more than half. Direction is
the finding. Magnitude is not.

### f2 turnover ratio — printed NULL

**Not measurable on this basis.** A turnover ratio needs shares outstanding (or free float) *per
date*. No CN store carries one: `china_stocks_raw` is OHLCV only; `china_fundamentals/
fundamentals.parquet` is a 4-asof payload blob with no share-count series; `china_search/
members.parquet` carries a single **current** `mktcap_yi`; `china_participation/tape.parquet` is
market-level. Applying a current share count to a 2013 bar is a knowingly wrong denominator —
A-share counts grow materially through placements and conversions — so **no proxy was substituted
and the set stays at eight**. (`china_zt_pool` carries `turnover_pct`, but only for limit-up names
from 2026-06-15 — a sample conditioned on the outcome, unusable as a T-1 predictor.) The collector
that would unblock it is Stage 4 #2.

### What Stage 3 does NOT establish

- **No significance claim is made.** Limit-ups cluster hard in time and cross-section, so a naive
  binomial interval on a bucket would be badly understated. The test used is **sign stability
  across an independent time block**, not a p-value — and 2015 alone carries 18.6% of main-board
  limit-ups, entirely inside the fit window.
- **Lift is not probability.** 3.93× on a 1.25% base is **4.88%**.
- **f4's effective sample is not its row count.** Sector heat takes one value per (date, sector),
  roughly 1,135 × 11 distinct values in the holdout, not 1.29M independent observations. Its
  2.39× is not peer to the per-name features.
- **The per-name-first column is itself selected.** Qualifying names are chosen by having ≥10
  holdout limit-ups — selection on the dependent variable. It answers "does this hold within
  active names", not "within all names".
- **Nothing is promoted.** Display/audit tier; the gauntlet applies at promotion, and nothing here
  is being promoted.

---

## STAGE 4 — DATA-GAP RECEIPT (COLLECTOR PROPOSALS ONLY — nothing built)

What the daily basis structurally cannot see, ranked by expected discriminative value.

1. **封单量 — resting order-wall volume at the limit price.** *Highest value.* The single
   most-watched 打板 number in the market and the one input every practitioner conditions on.
   Without it, "limit-up" pools a ~100× range of conviction into one flag. We hold it for **47
   dates** (`china_zt_pool.seal_fund_yi`) and for no date before 2026-06-15.
   **Proposal:** persist the *existing* zt_pool scrape (`seal_fund_yi`, `failed_seals`,
   `turnover_pct`) as an append-only daily tape, and backfill from any vendor with history.
   Storage change to a scrape that already runs — the cheapest item on this list.
2. **Closing-auction order imbalance (14:57–15:00 集合竞价).** *High.* The seal that holds into
   the close is decided in the closing auction; a daily bar records the outcome and destroys the
   mechanism. A name sealed with a thin queue and one sealed with a wall are the same row here.
   **Proposal:** per-ticker closing-auction matched volume + unmatched imbalance (direction and
   size) at 15:00, daily snapshot, ~5k rows/day. Directly addresses the T+1 continuation question
   Stage 2 measures and cannot explain.
3. **Intraday first-touch time and seal stability.** *Medium-high.* A 09:31 seal that never breaks
   and a 14:55 seal are the same daily row. Stage 1's near-limit class — and the house tape's
   separate failed-seal rows, which this catalog deliberately does not duplicate — are the crudest
   possible proxy for a continuous distinction. The standard practitioner split (一字/秒板 vs
   尾盘板) is entirely invisible to us.
   **Proposal:** per-limit-event intraday summary — first-touch timestamp, seal-break count,
   cumulative minutes sealed, final seal time. Needs minute bars for limit names only
   (~50–300/day), not the whole universe.
4. **T+0 intraday turnover composition (order-size-bucketed flow).** *Medium, ranked last
   deliberately.* A-share T+1 settlement means the day's buyers cannot sell until tomorrow, so the
   Stage 2 continuation rates are a direct function of who is locked in; 大单/中单/小单 net flow is
   the standard decomposition and we hold none of it per name per day. Plausibly the mechanism
   behind f4, but the most vendor-dependent and least verifiable of the four.
   **Proposal:** per-ticker daily order-size-bucketed net flow. `data/china_lhb` (龙虎榜) already
   lands a related disclosure for a small qualifying subset — this is the universe-wide daily
   version, not a re-scrape of LHB.

Two more that are repairs rather than collectors: **`data/china_st` has a single `asof`
(2026-07-06) and no membership history**, which is why the ST cohort is dropped wholesale rather
than banded at 5%; and **the price feed's precision** is what forced the definition adjudication
above — an exchange-sourced close would make the strict test exact and remove the ambiguity
entirely. The universe gap in the coverage receipt remains the largest single limitation of this
study.

---

## DEVIATIONS AND CORRECTIONS

1. **A mid-build reversal, recorded rather than tidied away.** This instrument first made the
   *strict* test primary, on the reasoning that the charter's 0.2% tolerance doubled the event
   count and must therefore be a widening. Adversarial review surfaced that the vendor cross-check
   disagreed, and the adjudication above settled it: the tolerance is a cushion for feed
   precision, exactly as the charter specified. **The charter was right and this instrument's
   first answer was wrong.** Every number in this document is on the corrected primary; the strict
   column is retained throughout so the earlier reading remains reproducible.
2. **Three controls were added that the brief did not name**, none of which adds a feature: the
   collinearity matrix, the top-bucket Jaccard overlap, and the ChiNext band-era re-split. All
   three exist to *attack* the Stage 3 result rather than extend it.
3. **Buckets are quantile bins on feature values, not forced deciles.** An earlier version binned
   the rank, which is unique by construction, so tied integer features were split into up to five
   "deciles" of the identical value — arbitrary ticker cohorts whose spread was cross-name base-
   rate variation. Realised bucket counts and top-bucket row shares are now printed.
4. **The IPO window is resolved from each ticker's full history**, where the module resolves it
   after its own date filter. **Zero-volume suspension bars are additionally excluded.** This is
   the entire content of the parity gate's single mismatch (`002428.SZ` 2011-01-04), and it runs
   in this instrument's favour.
5. **The 连板 tail bucket is 8+**, so mid-ladder cells stay readable.
6. **Not done, flagged instead:** the `limit_events.parquet` history hole (Summary #13).

---

## REPRODUCE

```
cd <repo root>
TZ=UTC python3 research/cn_prophet_audit/limit_move_footprint_v0.py
```

Deterministic (ticker-sorted; the only sampling is the disclosed every-k-th-row Spearman
subsample). Runtime ~32s. Writes `research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json`,
which carries every cell in this document plus the full bucket tables, both definitions' ladders
for every Stage-1 and Stage-2 cell, the definition adjudication, and the per-ticker tape
reconciliation.
