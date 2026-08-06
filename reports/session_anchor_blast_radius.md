# Absolute session anchor — blast radius

Era `abs-session-2026-08-06` · ruling `research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`

Generated 2026-08-06T09:58Z · store as-of dates are per-universe (read from the stores, never the wall clock).


## 1. Old → new, per production loader

| universe | graded | tier flips | veto flips | eligible | store as-of |
|---|---:|---:|---:|---|---|
| data/stocks | 235 | 12 (5.11%) | 17 (7.23%) | 14 → 6 (-8) | 2026-07-31 |
| data/baskets/ohlcv | 2737 | 89 (3.25%) | 255 (9.32%) | 107 → 79 (-28) | 2026-08-04 |
| data/stocks @345 bars | 235 | 2 (0.85%) | 20 (8.51%) | 6 → 4 (-2) | 2026-07-31 |
| data/stocks @777 bars | 235 | 8 (3.4%) | 21 (8.94%) | 10 → 6 (-4) | 2026-07-31 |
| massive_stock_day (scan tier) | — | — | — | — | **not measured** |
| CN china_search panel | 1765 | 59 (3.34%) | 87 (4.93%) | 111 → 146 (+35) | 2026-08-05 |
| HK stores | 2 | 0 (0.0%) | 0 (0.0%) | 0 → 0 (+0) | 2026-08-05 |

- **data/stocks** — the deep US loader (1960s-2000s starts)

- **data/baskets/ohlcv** — the 2014-start US loader
  - not graded: 32 ({'under MIN_HISTORY': 32})

- **data/stocks @345 bars** — stocks/ truncated to the trailing 345 bars (a production cache depth)

- **data/stocks @777 bars** — stocks/ truncated to the trailing 777 bars (a production cache depth)

- **massive_stock_day (scan tier)** — ABSENT: data/massive_stock_day holds 0 per-ticker parquets (R2-canonical; restored only in a lane that pulls it). The scan-tier delta is UNMEASURED here — run this script in a restored lane.

- **CN china_search panel** — old era = the market-BLIND business-day resample every market used to get; new era = the Shanghai reference calendar. That IS the shipped CN delta.
  - not graded: 29 ({'under MIN_HISTORY': 29})

- **HK stores** — data/hk/*.HK.parquet, market=HK

## 2. Tier transition matrices (changed cells only)


**data/stocks** — {'None->T2': 2, 'T2->None': 8, 'T3->None': 2}

**data/baskets/ohlcv** — {'None->T2': 22, 'None->T3': 3, 'None->T4': 3, 'T2->None': 50, 'T2->T3': 1, 'T2->T4': 1, 'T3->None': 4, 'T3->T2': 1, 'T4->None': 2, 'T4->T2': 2}

**data/stocks @345 bars** — {'T2->None': 2}

**data/stocks @777 bars** — {'None->T2': 2, 'T2->None': 5, 'T3->None': 1}

**CN china_search panel** — {'None->T2': 45, 'None->T3': 1, 'None->T4': 1, 'T2->None': 11, 'T3->None': 1}

**HK stores** — no tier changed

## 3. stocks/ vs baskets/ohlcv/ — the defect's live symptom

234 shared names, aligned to each pair's shared last date (store as-of 2026-07-31).

| field | disagreements BEFORE | disagreements AFTER |
|---|---:|---:|
| tier | 5 | 0 |
| not_topped | 19 | 0 |
| eligible | 5 | 0 |

### The audit quintet

| name | bars stocks / ohlcv | BEFORE stocks | BEFORE ohlcv | AFTER stocks | AFTER ohlcv |
|---|---|---|---|---|---|
| NUE | 11688 / 3163 | T2/nt=True/e=True | None/nt=False/e=False | None/nt=False/e=False | None/nt=False/e=False |
| PEP | 13654 / 3163 | T2/nt=True/e=True | None/nt=True/e=False | None/nt=False/e=False | None/nt=False/e=False |
| ECL | 13474 / 3163 | None/nt=True/e=False | T3/nt=True/e=True | T2/nt=True/e=True | T2/nt=True/e=True |
| SW | 4559 / 3163 | None/nt=False/e=False | T2/nt=True/e=True | None/nt=False/e=False | None/nt=False/e=False |
| WMT | 13594 / 3163 | T2/nt=True/e=True | None/nt=True/e=False | None/nt=False/e=False | None/nt=False/e=False |

## 4. Start-invariance re-run on real data (NEW anchor)

`cascade(c)` vs `cascade(c.iloc[3:])` over 235 data/stocks names: **0 tier flips, 0 veto flips, 0 eligibility flips**.

## 5. Depth residual (honest, NOT an anchor effect)


- **345-bar view**: 5 of 235 names differ from full depth under the NEW anchor — by reason {'wbull-arm (weekly confirm not yet knowable)': 5}. A shallower window genuinely cannot compute the deeper legs; every one is disclosed in `null_legs` (R8 keeps this a depth effect, not something the anchor fixes).

- **777-bar view**: 0 of 235 names differ from full depth under the NEW anchor — by reason {}. A shallower window genuinely cannot compute the deeper legs; every one is disclosed in `null_legs` (R8 keeps this a depth effect, not something the anchor fixes).
