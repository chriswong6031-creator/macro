# Absolute session anchor — blast radius

Era `abs-session-2026-08-06` · ruling `research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`

Generated 2026-08-06T11:06Z · store as-of dates are per-universe (read from the stores, never the wall clock).


## 1. Old → new, per production loader

| universe | graded | tier flips | veto flips | eligible | store as-of |
|---|---:|---:|---:|---|---|
| data/stocks | 238 | 13 (5.46%) | 19 (7.98%) | 13 → 14 (+1) | 2026-08-05 |
| data/baskets/ohlcv | 2743 | 152 (5.54%) | 271 (9.88%) | 163 → 168 (+5) | 2026-08-05 |
| data/stocks @345 bars | 238 | 9 (3.78%) | 16 (6.72%) | 10 → 9 (-1) | 2026-08-05 |
| data/stocks @777 bars | 238 | 13 (5.46%) | 16 (6.72%) | 15 → 14 (-1) | 2026-08-05 |
| massive_stock_day (scan tier) | 3886 | 179 (4.61%) | 276 (7.1%) | 287 → 278 (-9) | 2026-08-05 |
| CN china_search panel | 1765 | 59 (3.34%) | 87 (4.93%) | 111 → 146 (+35) | 2026-08-05 |
| HK stores | 2 | 0 (0.0%) | 0 (0.0%) | 0 → 0 (+0) | 2026-08-05 |

- **data/stocks** — the deep US loader (1960s-2000s starts)

- **data/baskets/ohlcv** — the 2014-start US loader
  - not graded: 32 ({'under MIN_HISTORY': 32})

- **data/stocks @345 bars** — stocks/ truncated to the trailing 345 bars (a production cache depth)

- **data/stocks @777 bars** — stocks/ truncated to the trailing 777 bars (a production cache depth)

- **massive_stock_day (scan tier)** — floor + listing rule from engine.us_scan_universe.resolve

- **CN china_search panel** — old era = the market-BLIND business-day resample every market used to get; new era = the Shanghai reference calendar. That IS the shipped CN delta.
  - not graded: 29 ({'under MIN_HISTORY': 29})

- **HK stores** — data/hk/*.HK.parquet, market=HK

## 2. Tier transition matrices (changed cells only)


**data/stocks** — {'None->T2': 4, 'None->T4': 2, 'T2->None': 5, 'T2->T4': 1, 'T4->T2': 1}

**data/baskets/ohlcv** — {'None->T2': 57, 'None->T3': 6, 'None->T4': 11, 'T2->None': 59, 'T2->T3': 1, 'T2->T4': 5, 'T3->None': 8, 'T3->T2': 1, 'T3->T4': 1, 'T4->None': 2, 'T4->T3': 1}

**data/stocks @345 bars** — {'None->T2': 1, 'None->T4': 3, 'T2->None': 5}

**data/stocks @777 bars** — {'None->T2': 3, 'None->T4': 2, 'T2->None': 6, 'T2->T4': 1, 'T4->T2': 1}

**massive_stock_day (scan tier)** — {'None->T2': 63, 'None->T3': 4, 'None->T4': 8, 'T2->None': 67, 'T2->T3': 6, 'T2->T4': 6, 'T3->None': 14, 'T3->T2': 3, 'T3->T4': 3, 'T4->None': 3, 'T4->T2': 2}

**CN china_search panel** — {'None->T2': 45, 'None->T3': 1, 'None->T4': 1, 'T2->None': 11, 'T3->None': 1}

**HK stores** — no tier changed

## 3. stocks/ vs baskets/ohlcv/ — the defect's live symptom

237 shared names, aligned to each pair's shared last date (store as-of 2026-08-05).

| field | disagreements BEFORE | disagreements AFTER |
|---|---:|---:|
| tier | 4 | 0 |
| not_topped | 18 | 0 |
| eligible | 4 | 0 |

### The audit quintet

| name | bars stocks / ohlcv | BEFORE stocks | BEFORE ohlcv | AFTER stocks | AFTER ohlcv |
|---|---|---|---|---|---|
| NUE | 11691 / 3166 | None/nt=True/e=False | None/nt=True/e=False | None/nt=True/e=False | None/nt=True/e=False |
| PEP | 13657 / 3166 | None/nt=False/e=False | None/nt=True/e=False | None/nt=False/e=False | None/nt=False/e=False |
| ECL | 13477 / 3166 | T2/nt=True/e=True | T2/nt=True/e=True | None/nt=False/e=False | None/nt=False/e=False |
| SW | 4562 / 3166 | None/nt=False/e=False | None/nt=True/e=False | None/nt=False/e=False | None/nt=False/e=False |
| WMT | 13597 / 3166 | None/nt=True/e=False | None/nt=True/e=False | None/nt=True/e=False | None/nt=True/e=False |

## 4. Start-invariance re-run on real data (NEW anchor)

`cascade(c)` vs `cascade(c.iloc[3:])` over 238 data/stocks names: **0 tier flips, 0 veto flips, 0 eligibility flips**.

## 5. Depth residual (honest, NOT an anchor effect)


- **345-bar view**: 5 of 238 names differ from full depth under the NEW anchor — by reason {'wbull-arm (weekly confirm not yet knowable)': 5}. A shallower window genuinely cannot compute the deeper legs; every one is disclosed in `null_legs` (R8 keeps this a depth effect, not something the anchor fixes).

- **777-bar view**: 0 of 238 names differ from full depth under the NEW anchor — by reason {}. A shallower window genuinely cannot compute the deeper legs; every one is disclosed in `null_legs` (R8 keeps this a depth effect, not something the anchor fixes).
