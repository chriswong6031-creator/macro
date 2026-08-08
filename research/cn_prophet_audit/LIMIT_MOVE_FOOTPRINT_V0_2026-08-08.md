# CN LIMIT-MOVE FOOTPRINT v0 — event catalog, base rates, pre-registered features

**Charter:** `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(f), ANTICIPATION program.
**Instrument:** `research/cn_prophet_audit/limit_move_footprint_v0.py` ·
**Frozen numbers:** `LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json` · **Runtime:** ~40s ·
**Window:** 2011-01-01 → 2026-08-07 · **Basis:** `data/china_stocks_raw` (nominal OHLCV).

**Tier: display / audit. MEASUREMENT ONLY.** Nothing here ranks, sizes, gates, admits or
promotes anything. No LLM is involved at any point. There is **no pooled top-line across board
types** anywhere in this document: a ±10% main-board name and a ±20% ChiNext name do not share
a base rate, and averaging them would invent a number that describes no market.

---

## DECISION SUMMARY

1. **The event catalog exists and is trustworthy.** 31,897 limit-up closes, 13,308 limit-down
   closes and 30,417 near-limit closes over 4.98M ticker-days / 1,836 names / 15.6 years.
   The vectorised detector reproduces **100% of the events** the repo's own
   `engine.china_microstructure._detect_limit_events` emits (656/656, 25-ticker sample) at
   **99.85% precision** — the one extra event is `002428.SZ` on 2011-01-04, and it is the
   module's artifact, not this instrument's: the module resolves its IPO window *after* its own
   date filter, so it mistakes that ticker's first in-window bar for an IPO bar and drops it.
   Independently, **97.2% of names (1,465/1,507) match the committed house tape exactly**.
2. **THE BINDING CAVEAT — the universe is curated, not the market.** `data/china_stocks_raw`
   holds 1,842 names against a listed A-share market of roughly 5,400. Two store-measured
   probes of the hole: only **1 of 100** current ST names is present, and of the 1,770 names that hit
   the limit-up pool in `data/china_zt_pool`'s 47-session window only **514 (29%)** exist here
   — **24.7%** of that store's rows find a match. The 打板 game lives disproportionately in
   exactly the small-cap and ST names this universe omits. **Every number below describes a
   curated large/mid-cap universe. None of them is a market-wide statistic.**
3. **The single strongest conditioner is the event itself, not any feature.** Main board: the
   unconditional chance that a name closes at the limit on any given next bar is **0.67%**.
   Given it just closed at its first limit-up, that becomes **10.86%** — a **16× lift**, free,
   before a single feature is computed. The best pre-registered feature's top decile reaches
   only ~2.5%. **The 连板 state is roughly 4× stronger than the best of the eight features.**
4. **The 连板 ladder is monotone on both boards that have the sample to show it.** Main
   10.86% → 22.72% → 28.65% → 32.48% → 34.69% for N = 1…5. ChiNext 11.83% → 24.53% → 35.90% →
   39.02%. Beyond N=5 every cell is thin (n < 20) and is labelled as such rather than smoothed.
5. **But the base rate is an era artifact, not a constant.** The main-board first-board →
   second-board rate ranges **4.99% (2011) to 17.53% (2017)** — a 3.5× swing across years. The
   pooled 10.86% is an average over eras that genuinely differ. Anyone quoting one number is
   quoting the wrong kind of object.
6. **ChiNext's band change is visible in the data as a 10× collapse.** After the ±10% → ±20%
   move on 2020-08-24, ChiNext first-board continuation falls from 16.25% (2015) / 13.58%
   (2019) to **1.52% (2022) and 2.04% (2026)**, and limit-up counts fall from 521 (2020) to 139
   (2021). A wider band is a genuinely different game; ChiNext pre- and post-2020-08-24 must
   never be pooled.
7. **Seven of the eight pre-registered features are sign-stable on the holdout, on all three
   boards.** Main-board holdout top-decile lifts: f5 near-limit-prev **15.0×**, f3 5-session
   run-up **3.81×**, f7 distance-from-52w-low **3.25×**, f6 gap **3.00×**, f1 volume z **2.54×**,
   f8 consecutive up-days **2.25×**, f4 sector heat **2.08×**. Zero features printed UNSTABLE.
8. **They are NOT one thing measured seven ways** — and this was tested, not assumed, because
   "everything works" is the signature of a false discovery. Max off-diagonal Spearman among
   the seven is **0.375** (run-up vs consecutive-up-days); most pairs sit under 0.15. Removing
   every row f5 already flags costs the other six only 5–12% of their lift (f3 3.81 → 3.38).
   Seven low-correlation axes, each surviving the other's removal.
9. **Sign-stable does not mean magnitude-stable.** Under the ChiNext band-era control (re-split
   inside the ±20% era so fit and holdout are the same game), every sign holds but the levels
   compress hard: f5 53.4× → 19.9×, f4 3.07× → 1.32×, f8 3.27× → 1.55×. Read the direction as
   the finding and the magnitude as unstable.
10. **f2 turnover ratio is a printed NULL — not measurable on this basis.** No CN store carries
    per-date shares outstanding or free float. The pre-registered set stays at eight; no ninth
    feature was substituted. The swap is precisely the move this design exists to block.
11. **Absolute probabilities stay small.** A 3.8× lift on a 0.65% base rate is 2.5%. Every
    feature cell in Stage 3 describes an event that still does not happen ~97% of the time.
12. **Side finding, reported not acted on:** the committed
    `data/china_microstructure/limit_events.parquet` is **missing pre-2026-07 history for 34
    names — 14 of them absent from the tape entirely** — carrying 1,059 of the 1,065-event
    aggregate delta. Its own `backfill` flag reads `True`
    for all 3,751 market-days, so the flag does not surface the hole. Consistent with a raw-price
    repair landing after the one-time historical backfill, with the nightly appender only ever
    adding new dates. Handed to the CN data-plane owner; this instrument does not touch the tape.

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Price basis | `data/china_stocks_raw` — nominal/unadjusted. The adjusted twin `data/china_stocks` would fabricate limit misses (adjustment breaks `round(prev_close×(1+w),2)` equality). |
| Names in store | 1,842 · kept 1,836. (For scale: the listed A-share market is roughly 5,400 names — an external reference figure, not one our stores measure. The two store-measured gap probes are the next two rows.) |
| ST names present | **1 of 100** current ST names |
| zt_pool overlap | 514 of 1,770 names (29%) · 24.7% of rows |
| Ticker-days | 4,981,168 · usable after exclusions 4,843,576 |
| Boards | main 1,243 · chinext 351 · star 242 · **bse 0** |
| Sector coverage | 93.68% (`data/china_search/members.parquet`, CURRENT mapping applied to 15y of history) |
| Excluded bars | zero-volume/suspension 133,781 · ex-div suspect 621 · IPO window 2,793 |
| Pairs dropped | 22,205 T→T+1 pairs where the bars are > 10 calendar days apart (suspensions) |
| 2015 concentration | 18% of all main-board limit-ups and **38%** of all main-board limit-downs fall in 2015 alone. The fit window contains it entirely; the holdout has no comparable event. |
| Survivorship | The store holds the CURRENT listed universe. Delisted names are absent, which biases the **limit-down** numbers most — the terminal down-limit runs of delisted names are simply not here. Read every limit-down cell as survivors-only. |
| ST residual | Names that WERE ST historically but are not today remain at a 10% band. Not fixable with the stores we hold; not patched over. |

---

## DEFINITIONS (stated inline, as required)

- **`w` (limit width)** — `engine.china_microstructure.limit_width_for_date`, **imported, not
  reimplemented**: STAR 20%; ChiNext 20% on/after `CHINEXT_WIDE_DATE` 2020-08-24 else 10%;
  main 10%; BSE 30%; ST 5% on main only. Board from `_board_from_ticker` (688/689 → star,
  300/301/302 → chinext, 8/4/92 → bse, else main).
- **`limit_up_close` (PRIMARY, strict)** — `close ≥ round(prev_close × (1+w), 2)`.
- **`limit_up_close` (tolerant)** — `close ≥ limit_price × (1 − 0.002)`, the build charter's
  "at or within 0.2%" wording. Carried as a full parallel column, **not** used as the headline —
  see *Deviations*.
- **`near_limit_up`** — return ≥ 0.95 × w (9.5% on a 10% board, 19% on a 20% board) **and** not
  a strict limit close.
- **`连板 N`** — consecutive strict limit-up closes ending on the bar. Any non-limit bar,
  including an excluded one, resets it to 0. **`first_board`** = N is 1; **`continuation`** = N ≥ 2.
- **`T → T+1`** — the name's next usable bar, at most 10 calendar days later.
- **Exclusions** — ST cohort (all dates); STAR/ChiNext first 5 sessions and pre-2014 listings'
  first session (44%-cap IPO regime, per the module's own windows); ex-dividend suspects
  (`|open − prev_close| / prev_close > 1.5 × w`); zero-volume bars. Every ticker's first bar is
  independently unusable (no prev_close).

---

## STAGE 1 — EVENT CATALOG

### By board (2011-01-01 → 2026-08-07, strict)

| Board | Names | Ticker-days | Limit-up | rate | Limit-down | rate | Near-limit-up | Near-limit-down | tolerant/strict | First board | Cont. 2+ | max 连板 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main | 1,243 | 3,817,967 | **26,682** | 0.699% | **11,154** | 0.292% | 25,317 | 15,727 | 1.89× | 23,365 | 3,317 | 9 |
| chinext | 351 | 757,341 | **4,776** | 0.631% | **2,105** | 0.278% | 4,593 | 3,008 | 1.88× | 4,108 | 668 | 7 |
| star | 242 | 268,268 | **439** | 0.164% | **49** | 0.018% | 507 | 82 | 2.00× | 422 | 17 | 2 |

**STAR barely plays this game at all** — a 20%-band board of large, institutionally-held tech
names produces 0.16% limit-up days and 49 limit-down days in six years.

### 连板 distribution (count of limit-up days at each N)

| Board | N=1 | 2 | 3 | 4 | 5 | 6 | 7 | 8+ |
|---|---|---|---|---|---|---|---|---|
| main | 23,365 | 2,514 | 565 | 159 | 51 | 17 | 6 | 5 |
| chinext | 4,108 | 483 | 117 | 42 | 16 | 8 | 2 | — |
| star | 422 | 17 | — | — | — | — | — | — |

### Main board by year — the era story

| Year | Names | Limit-up | Limit-down | Near-limit-up | LU per 1k ticker-days |
|---|---|---|---|---|---|
| 2011 | 811 | 463 | 154 | 457 | 2.54 |
| 2012 | 833 | 617 | 143 | 597 | 3.16 |
| 2013 | 842 | 950 | 176 | 887 | 4.92 |
| 2014 | 873 | 1,190 | 174 | 1,161 | 6.05 |
| **2015** | 916 | **4,769** | **4,248** | 4,991 | **24.86** |
| 2016 | 958 | 1,342 | 1,027 | 1,263 | 6.37 |
| 2017 | 1,031 | 998 | 223 | 934 | 4.34 |
| 2018 | 1,074 | 827 | 608 | 641 | 3.36 |
| 2019 | 1,116 | 1,473 | 682 | 1,311 | 5.58 |
| 2020 | 1,156 | 2,359 | 849 | 2,120 | 8.58 |
| 2021 | 1,184 | 2,844 | 569 | 2,601 | 10.02 |
| 2022 | 1,199 | 1,910 | 484 | 1,644 | 6.63 |
| 2023 | 1,212 | 1,089 | 201 | 1,007 | 3.73 |
| 2024 | 1,219 | 1,946 | 455 | 2,138 | 6.64 |
| 2025 | 1,235 | 2,021 | 640 | 1,775 | 6.79 |
| 2026 (partial) | 1,243 | 1,884 | 521 | 1,790 | 10.57 |

ChiNext limit-ups by year: 29 · 74 · 227 · 205 · **1,233** · 384 · 342 · 360 · 585 · 521 ·
**139** · 67 · 104 · 252 · 152 · 102 — the 2021 cliff is the ±20% band arriving, not a market event.
STAR (2019→): 2 · 36 · 28 · 24 · 41 · 122 · 82 · 104.

### Sector distribution (share of that board's limit-ups)

| Board | Top sectors |
|---|---|
| main | Industrials 21.3% · Basic Materials 18.3% · Technology 17.2% · Consumer Cyclical 8.8% · *UNKNOWN 6.9%* · Healthcare 5.9% |
| chinext | **Technology 44.8%** · Industrials 21.4% · Healthcare 10.1% · Basic Materials 8.7% · *UNKNOWN 7.1%* |
| star | **Technology 57.2%** · Industrials 15.5% · *UNKNOWN 11.9%* · Basic Materials 7.3% · Healthcare 6.8% |

*UNKNOWN* is the 6.3% of names with no row in the sector map — printed, not dropped.

---

## STAGE 2 — BASE RATES (no features)

**P(limit-up close at T+1 | 连板 = N at T).** Pooled beside per-name-first. Wilson 95%.
Cells with n < 20 labelled **THIN**.

| Board | N | n | P(next board) | Wilson 95% | per-name median (names) |
|---|---|---|---|---|---|
| main | 1 | 23,098 | **10.86%** | 10.46–11.27 | 9.52% (953) |
| main | 2 | 2,487 | **22.72%** | 21.11–24.41 | 31.82% (4) |
| main | 3 | 555 | **28.65%** | 25.04–32.55 | — (0) |
| main | 4 | 157 | **32.48%** | 25.65–40.15 | — (0) |
| main | 5 | 49 | **34.69%** | 22.92–48.69 | — (0) |
| main | 6 | 17 | 35.29% | 17.31–58.70 | **THIN** |
| main | 7 | 5 | 80.00% | 37.55–96.38 | **THIN** |
| main | 8+ | 5 | 20.00% | 3.62–62.45 | **THIN** |
| chinext | 1 | 4,082 | **11.83%** | 10.88–12.86 | 11.65% (174) |
| chinext | 2 | 477 | **24.53%** | 20.88–28.58 | 20.00% (2) |
| chinext | 3 | 117 | **35.90%** | 27.78–44.91 | — (0) |
| chinext | 4 | 41 | **39.02%** | 25.66–54.27 | — (0) |
| chinext | 5 | 16 | 50.00% | 28.00–72.00 | **THIN** |
| chinext | 6 | 8 | 25.00% | 7.15–59.07 | **THIN** |
| chinext | 7 | 2 | 0.00% | 0.00–65.76 | **THIN** |
| star | 1 | 420 | **4.05%** | 2.54–6.39 | 0.00% (1) |
| star | 2 | 16 | 0.00% | 0.00–19.36 | **THIN** |

**Unconditional next-bar limit-up:** main **0.67%** · chinext **0.61%** · star **0.16%**.
So a first board multiplies the next-bar odds by **16×** (main), **19×** (chinext), **25×** (star).

**Limit-down mirror** — continuation is much weaker than on the up-side:

| Board | N | n | P(next down-limit) | Wilson 95% |
|---|---|---|---|---|
| main | 1 | 10,130 | **7.55%** | 7.05–8.08 |
| main | 2 | 750 | **12.53%** | 10.35–15.10 |
| main | 3 | 92 | **25.00%** | 17.28–34.73 |
| main | 4 | 17 | 29.41% | 13.28–53.13 **THIN** |
| main | 5 | 4 | 0.00% | 0.00–48.99 **THIN** |
| chinext | 1 | 1,926 | **6.91%** | 5.86–8.13 |
| chinext | 2 | 131 | **13.74%** | 8.87–20.68 |
| chinext | 3 | 15 | 6.67% | 1.19–29.82 **THIN** |
| star | 1 | 49 | **0.00%** | 0.00–7.27 |

Unconditional next-bar limit-down: main 0.27% · chinext 0.26% · star 0.01%.
STAR's 0/49 is a printed null, not an omission.

### P(second board | first board) by year — the base rate is not a constant

| Year | main n | main rate | chinext n | chinext rate |
|---|---|---|---|---|
| 2011 | 421 | 4.99% | 29 | 0.00% |
| 2012 | 558 | 7.17% | 66 | 7.58% |
| 2013 | 846 | 8.16% | 209 | 6.70% |
| 2014 | 1,025 | 10.24% | 183 | 9.29% |
| 2015 | 3,891 | 15.83% | 997 | 16.25% |
| 2016 | 1,138 | 10.98% | 312 | 14.42% |
| 2017 | 770 | **17.53%** | 267 | 16.85% |
| 2018 | 757 | **5.94%** | 313 | 12.46% |
| 2019 | 1,249 | 10.89% | 486 | 13.58% |
| 2020 | 2,011 | 12.53% | 465 | 9.68% |
| 2021 | 2,545 | 9.27% | 129 | 7.75% |
| 2022 | 1,733 | 8.42% | 66 | **1.52%** |
| 2023 | 1,002 | 6.19% | 94 | 5.32% |
| 2024 | 1,649 | 12.07% | 223 | 9.87% |
| 2025 | 1,783 | 10.94% | 145 | 3.45% |
| 2026 | 1,720 | 7.33% | 98 | **2.04%** |

**Two reading rules, both load-bearing:**

- **The ladder is conditioned-on-reaching, not a survival curve.** A run that reached 8 boards
  contributes a row at N = 1…7, every one of which continued. Read a cell as *"a day inside an
  N-board run is followed by another board X% of the time"* — never as *"the Nth board continues
  X% of the time"*.
- **The per-name column thins out fast by construction.** A name needs ≥ 10 conditioning events
  in the *same* cell to contribute. Only N=1 clears that for a meaningful count (953 main names);
  at N ≥ 2 the qualifying names are, by construction, the serial-limit names, so those medians are
  a selected sub-population and are **not** a check on the pooled number. Printed with their name
  count so the thinness is visible rather than inferred.

---

## STAGE 3 — PRE-REGISTERED FOOTPRINT SET

**Eight features, named in the charter before any of this ran.** Measured at the T-1 close,
predicting a strict limit-up close at T. **Fit / inspect on the first 70% of trading dates
(2011-01-05 → 2021-11-25, 2,646 dates, 2.86M rows); REPORTED on the last 30% holdout only
(2021-11-26 → 2026-08-06, 1,135 dates, 1.96M rows).**

| # | Feature | Status |
|---|---|---|
| f1 | volume z-score of the T-1 bar vs its own prior 20 bars | measured |
| f2 | turnover ratio (volume / shares outstanding) | **NULL — not measurable** |
| f3 | 5-session run-up, `close[T-1]/close[T-6] − 1` | measured |
| f4 | same-day sector limit-up count at T-1, **leave-one-out** | measured |
| f5 | prior-session near-limit flag (near-limit-up at T-1) | measured |
| f6 | gap at the T-1 open, `open[T-1]/close[T-2] − 1` | measured |
| f7 | distance from 52w low, `close[T-1]/min(low, 252) − 1` | measured |
| f8 | consecutive up-close days ending at T-1 | measured |

### HOLDOUT decile lift — main board (holdout base rate 0.654%)

| Feature | fit top-decile lift | **holdout top-decile lift** | holdout bottom | top/bottom spread | verdict | per-name median lift (names > 1×) |
|---|---|---|---|---|---|---|
| f5 near-limit-prev | 18.68× | **15.01×** | 0.913 | 16.4 | stable-sign | 7.01× (263/363) |
| f3 run-up 5d | 3.77× | **3.81×** | 1.349 | 2.8 | stable-sign | 3.32× (353/363) |
| f7 dist 52w low | 2.94× | **3.25×** | 0.329 | 9.9 | stable-sign | 1.99× (280/360) |
| f6 gap % | 3.41× | **3.00×** | 1.905 | 1.6 | stable-sign | 2.71× (327/363) |
| f1 volume z20 | 2.40× | **2.54×** | 0.715 | 3.6 | stable-sign | 2.27× (309/362) |
| f8 consec up-days | 2.26× | **2.25×** | 0.683 | 3.3 | stable-sign | 2.09× (280/363) |
| f4 sector heat | 2.53× | **2.08×** | 0.785 | 2.7 | stable-sign | 1.66× (243/335) |

**Zero features printed UNSTABLE.** Every sign survives the time split, and the per-name-first
column confirms it holds *within* names, not merely across them — 243–353 of ~363 qualifying
names show a top-decile lift above 1×.

### HOLDOUT top-decile lift — chinext and star

| Feature | chinext (base 0.185%) | star (base 0.159%) |
|---|---|---|
| f5 near-limit-prev | 39.92× | 46.11× |
| f3 run-up 5d | 4.53× | 4.52× |
| f6 gap % | 3.39× | 4.00× |
| f1 volume z20 | 3.11× | 3.34× |
| f8 consec up-days | 2.81× | 2.93× |
| f4 sector heat | 2.46× | 3.05× |
| f7 dist 52w low | 2.34× | 3.03× |

All sign-stable. **The per-name-first column is a MEASURED null on both boards** (0 of 351 and
0 of 242 names qualify): at a 0.16–0.19% base rate a name accumulates a median of **1** limit-up
in the entire holdout — far under the 10-positive floor. Rarity, not a bug.

### Is this seven findings, or one finding measured seven times?

**Tested, not assumed** — "everything works" is the signature of a false discovery.

Spearman correlation among the seven, main-board holdout (every 6th row, 228,899 of 1,373,390):

| | f1 | f3 | f4 | f5 | f6 | f7 | f8 |
|---|---|---|---|---|---|---|---|
| **f1** vol z | 1.00 | 0.33 | 0.10 | 0.09 | 0.07 | 0.02 | 0.23 |
| **f3** run-up | 0.33 | 1.00 | 0.13 | 0.11 | 0.10 | 0.18 | **0.375** |
| **f4** sector heat | 0.10 | 0.13 | 1.00 | 0.05 | 0.05 | 0.18 | 0.17 |
| **f5** near-limit | 0.09 | 0.11 | 0.05 | 1.00 | 0.06 | 0.08 | 0.10 |
| **f6** gap | 0.07 | 0.10 | 0.05 | 0.06 | 1.00 | −0.01 | 0.22 |
| **f7** dist 52w low | 0.02 | 0.18 | 0.18 | 0.08 | −0.01 | 1.00 | 0.10 |
| **f8** consec up | 0.23 | 0.375 | 0.17 | 0.10 | 0.22 | 0.10 | 1.00 |

**Max off-diagonal |ρ| = 0.375.** Most pairs sit below 0.15. And removing every row f5 already
flags (1.36M rows remain, base 0.596%) costs the other six only 5–12% of their lift:

| | f1 | f3 | f4 | f6 | f7 | f8 |
|---|---|---|---|---|---|---|
| unconditional | 2.54 | 3.81 | 2.08 | 3.00 | 3.25 | 2.25 |
| **f5-excluded** | 2.36 | 3.38 | 1.96 | 2.64 | 3.17 | 2.00 |

So: seven low-correlation axes, each surviving the strongest one's removal. Contrary to the
prior this check was written to test, they are **not** one thing.

### ChiNext band-era control

The global 70/30 split lands at 2021-11-26 — **after** ChiNext's 2020-08-24 move to a ±20% band.
So ChiNext's fit window is mostly a 10%-band market and its holdout is entirely a 20%-band market
(fit base 0.992% vs holdout 0.185%, a 5× gap that is a rule change, not a signal). Re-split inside
the ±20% era only (438,042 rows, split 2024-10-25; fit base 0.183% vs holdout 0.204% — now
like-for-like):

| Feature | fit top-lift | holdout top-lift | verdict |
|---|---|---|---|
| f5 near-limit-prev | 53.35× | **19.88×** | stable-sign |
| f3 run-up 5d | 4.88× | **3.33×** | stable-sign |
| f6 gap % | 3.71× | **2.31×** | stable-sign |
| f1 volume z20 | 3.54× | **2.20×** | stable-sign |
| f7 dist 52w low | 2.26× | **1.91×** | stable-sign |
| f8 consec up-days | 3.27× | **1.55×** | stable-sign |
| f4 sector heat | 3.07× | **1.32×** | stable-sign |

**Every sign holds; every magnitude compresses**, f4 and f8 by more than half. Direction is the
finding here. Magnitude is not.

### f2 turnover ratio — printed NULL

**Not measurable on this basis.** A turnover ratio needs shares outstanding (or free float) *per
date*. No CN store carries one: `china_stocks_raw` is OHLCV only; `china_fundamentals/
fundamentals.parquet` is a 4-asof payload blob with no share-count series; `china_search/
members.parquet` carries a single **current** `mktcap_yi`; `china_participation/tape.parquet` is
market-level. Applying a current share count to a 2013 bar is a knowingly wrong denominator —
A-share counts grow materially through placements and conversions — so **no proxy was
substituted and the set stays at eight**. (`china_zt_pool` does carry `turnover_pct`, but only
for limit-up names from 2026-06-15 — a sample conditioned on the outcome, unusable as a T-1
predictor.) The collector that would unblock it is Stage 4 #2.

### What Stage 3 does NOT establish

- **No significance claim is made.** Limit-ups cluster hard in both time and cross-section, so a
  naive binomial interval on a decile cell would be badly understated. The test used here is
  **sign stability across an independent time block**, not a p-value — and 2015 alone carries
  18% of main-board limit-ups, entirely inside the fit window.
- **Lift is not probability.** 3.8× on a 0.65% base is **2.5%**. Every cell above describes an
  event that still does not happen ~97% of the time.
- **Nothing is promoted.** These are display/audit-tier measurements. Per the epistemics law the
  gauntlet applies at promotion, and nothing here is being promoted.

---

## STAGE 4 — DATA-GAP RECEIPT (COLLECTOR PROPOSALS ONLY — nothing built)

What the daily basis structurally cannot see, ranked by expected discriminative value.

1. **封单量 — resting order-wall volume at the limit price.** *Highest value.* The single most-
   watched 打板 number in the market and the one input every practitioner conditions on. Without
   it, "limit-up" pools a ~100× range of conviction into one flag. We hold it for **47 dates**
   (`china_zt_pool.seal_fund_yi`) and for no date before 2026-06-15.
   **Proposal:** persist the *existing* zt_pool scrape (`seal_fund_yi`, `failed_seals`,
   `turnover_pct`) as an append-only daily tape, and backfill from any vendor with history.
   Storage change to a scrape that already runs — the cheapest item on this list.
2. **Closing-auction order imbalance (14:57–15:00 集合竞价).** *High.* The seal that holds into
   the close is decided in the closing auction; a daily bar records the outcome and destroys the
   mechanism. A name sealed with a thin queue and one sealed with a wall are the same row here.
   **Proposal:** per-ticker closing-auction matched volume + unmatched imbalance (direction and
   size) at 15:00, daily snapshot, ~5k rows/day. Directly addresses the T+1 continuation
   question Stage 2 measures and cannot explain.
3. **Intraday first-touch time and seal stability.** *Medium-high.* A 09:31 seal that never
   breaks and a 14:55 seal are the same daily row; Stage 1's near-limit class — and the house
   tape's separate failed-seal rows, which this catalog deliberately does not duplicate (its
   charter is limit closes plus the return-based near-limit class) — are the crudest possible
   proxy for a continuous distinction. The standard practitioner split
   (一字/秒板 vs 尾盘板) is currently entirely invisible to us.
   **Proposal:** per-limit-event intraday summary — first-touch timestamp, seal-break count,
   cumulative minutes sealed, final seal time. Needs minute bars for limit names only
   (~50–300/day), not the whole universe.
4. **T+0 intraday turnover composition (order-size-bucketed flow).** *Medium, ranked last
   deliberately.* A-share T+1 settlement means the day's buyers cannot sell until tomorrow, so
   the Stage 2 continuation rates are a direct function of who is locked in; 大单/中单/小单 net
   flow is the standard decomposition and we hold none of it per name per day. Plausibly the
   mechanism behind f4, but the most vendor-dependent and least verifiable of the four.
   **Proposal:** per-ticker daily order-size-bucketed net flow. `data/china_lhb` (龙虎榜) already
   lands a related disclosure for a small qualifying subset — this is the universe-wide daily
   version, not a re-scrape of LHB.

Plus one that is not a collector but a repair: **`data/china_st` has a single `asof`
(2026-07-06) and no membership history**, which is why the ST cohort is dropped wholesale rather
than banded at 5%. An append-only ST membership tape would make historical ST limit events
recoverable. And the universe gap in the coverage receipt (1,842 of ~5,400 names) is the largest
single limitation of this entire study.

---

## DEVIATIONS FROM THE BRIEF (all disclosed, none silent)

1. **The charter's 0.2% limit-close tolerance was measured to be a widening, not a rounding
   cushion, so STRICT is the headline and tolerant rides beside it.** On a 10% board the
   tolerance admits every close from ~+9.78% to +10.00% — **1.89× the strict event count** — and
   it swallows most of the near-limit class the same charter asks us to count separately
   (main-board near-limit-up would collapse from 25,317 to 1,578, starving pre-registered feature
   f5). Both definitions run through Stage 1 and Stage 2 in full and are in the JSON; Stage 3
   uses strict with a tolerant-target robustness column. Under the tolerant definition the
   ladder reads main 16.50% → 36.61% → 45.52%, chinext 16.76% → 39.12% → 52.48%.
2. **Three controls were added that the brief did not name.** None adds a feature: the
   collinearity matrix, the f5-excluded conditional lift, and the ChiNext band-era re-split. All
   three exist to *attack* the Stage 3 result rather than extend it — the first two because a
   uniform "all seven work" is the false-discovery signature, the third because ChiNext's split
   straddles a rule change.
3. **The IPO window is resolved from each ticker's full history**, where the module resolves it
   after its own date filter (so the module drops the first bar of 2011 for every pre-2014
   listing, and the first 5 for every pre-2011 ChiNext/STAR listing, as if they were IPO bars).
   **Zero-volume suspension bars are additionally excluded.** This is the entire content of the
   parity gate's single mismatch (`002428.SZ` 2011-01-04) and it runs in this instrument's
   favour; both differences are named in the tape cross-check.
4. **The 连板 tail bucket is 8+, not 5+**, so the mid-ladder cells are readable rather than pooled.
5. **Not done, flagged instead:** the `limit_events.parquet` history hole (Summary #12) is a CN
   data-plane repair, out of scope here.

---

## REPRODUCE

```
cd <repo root>
TZ=UTC python3 research/cn_prophet_audit/limit_move_footprint_v0.py
```

Deterministic (ticker-sorted, no sampling except the disclosed every-k-th-row Spearman
subsample). Runtime ~40s (39-41s observed across runs). Writes `research/cn_prophet_audit/LIMIT_MOVE_FOOTPRINT_V0_2026-08-08.json`,
which carries every cell in this document plus the full holdout decile tables, the by-year
tolerant-definition ladders, and the per-ticker tape reconciliation.
