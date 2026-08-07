# §7 signal_quality absolute session anchor — blast radius

Era `sq-abs-session-2026-08-06` · ruling `research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md`

Generated 2026-08-06T12:16Z · store as-of dates are per-universe (read from the stores, never the wall clock).


Every number below is measured END-TO-END through `signal_gate.gate()` — the path a board, a chart and a ledger actually read — with the pre-repair `signal_frame`/`_bucket_last_session` frozen verbatim in this script and monkeypatched in for the OLD pass.


## 1. Old → new, per production loader

| universe | graded | last-marker DATE moved | last-marker IDENTITY moved | ticks flips | eligible / buyable flips | open-take re-keys | store as-of |
|---|---:|---:|---:|---:|---:|---:|---|
| data/stocks | 238 | 188 (78.99%) | 80 (33.61%) | 79 (33.19%) | 8 / 5 | 56 | 2026-08-05 |
| data/baskets/ohlcv | 2707 | 2363 (87.29%) | 861 (31.81%) | 887 (32.77%) | 111 / 60 | 709 | 2026-08-05 |

- **data/stocks** — the deep US loader (1960s-2000s starts)

- **data/baskets/ohlcv** — the 2014-start US loader
  - not graded: 68 ({'under signal_frame floor': 68})

### Marker-count delta (new − old), by universe


- **data/stocks**: {'-64': 1, '-60': 1, '-57': 1, '-54': 1, '-47': 1, '-46': 1, '-44': 1, '-40': 1, '-38': 1, '-37': 4, '-36': 1, '-34': 2, '-33': 1, '-32': 1, '-31': 1, '-29': 1, '-27': 4, '-26': 2, '-25': 2, '-24': 2, '-23': 2, '-21': 5, '-20': 4, '-19': 3, '-18': 12, '-17': 6, '-16': 10, '-15': 4, '-14': 5, '-13': 11, '-12': 7, '-11': 9, '-10': 9, '-9': 5, '-8': 6, '-7': 9, '-6': 5, '-5': 9, '-4': 3, '-3': 11, '-2': 11, '-1': 7, '0': 5, '1': 8, '2': 2, '3': 5, '4': 4, '5': 4, '6': 3, '7': 3, '8': 2, '9': 4, '10': 2, '11': 2, '12': 2, '13': 1, '14': 2, '15': 1, '17': 1, '25': 1, '27': 1, '29': 1, '31': 1}

- **data/baskets/ohlcv**: {'-34': 1, '-25': 1, '-23': 2, '-22': 3, '-21': 7, '-20': 4, '-19': 10, '-18': 14, '-17': 10, '-16': 19, '-15': 30, '-14': 29, '-13': 39, '-12': 62, '-11': 62, '-10': 73, '-9': 87, '-8': 94, '-7': 129, '-6': 154, '-5': 145, '-4': 145, '-3': 177, '-2': 187, '-1': 190, '0': 188, '1': 155, '2': 151, '3': 112, '4': 92, '5': 90, '6': 70, '7': 50, '8': 32, '9': 28, '10': 16, '11': 14, '12': 7, '13': 7, '14': 8, '15': 3, '16': 4, '17': 2, '18': 2, '19': 2}

A non-zero delta is R-SQ4's disclosed re-draw: a cross can appear or vanish where a 3D bucket's close changed. It is NOT a filter-semantics change — `_buy_filter`/`_confirm_legs`/`_bear_div` are byte-identical.


## 2. stocks/ vs baskets/ohlcv/ — the defect's live symptom, §7 layer

237 shared names, aligned to each pair's shared last date (store as-of 2026-08-05).

| field | disagreements BEFORE | disagreements AFTER |
|---|---:|---:|
| last_date | 168 | 1 |
| last_type | 52 | 0 |
| last_quality | 70 | 0 |
| n_markers | 214 | 214  ← DEPTH, not anchor |
| asof | 168 | 0 |
| eligible | 4 | 0 |
| tier_cascade | 3 | 0 |
| ticks | 74 | 1 |
| buyable | 1 | 0 |

`n_markers` is expected to disagree in BOTH eras and is not a defect: the deep loader carries decades the 2014-start loader never saw, so it has more markers by construction. Every other field is what the two loaders should have agreed on all along — the anchor is what makes them.


The residual AFTER is named rather than rounded to zero:


- **CSCO** (['last_date']) — the two stores' PRICES differ on their shared dates (max |Δclose| 0.484512), so this is a data disagreement between the loaders, not a grid one. The anchor guarantees one GRID per name; it cannot make two stores agree about what a close was.

- **EA** (['ticks']) — the two stores' PRICES differ on their shared dates (max |Δclose| 0.038818), so this is a data disagreement between the loaders, not a grid one. The anchor guarantees one GRID per name; it cannot make two stores agree about what a close was.

### The audit quintet

| name | bars stocks / ohlcv | BEFORE stocks | BEFORE ohlcv | AFTER stocks | AFTER ohlcv |
|---|---|---|---|---|---|
| NUE | 11691 / 3166 | 2026-06-16 sell/None · t=1 · e=False · buy=False | 2026-06-17 sell/None · t=1 · e=False · buy=False | 2026-06-17 sell/None · t=1 · e=False · buy=False | 2026-06-17 sell/None · t=1 · e=False · buy=False |
| PEP | 13657 / 3166 | 2026-07-06 buy/block · t=8 · e=False · buy=False | 2026-07-13 cut/None · t=5 · e=False · buy=False | 2026-07-15 buy/block · t=6 · e=False · buy=False | 2026-07-15 buy/block · t=6 · e=False · buy=False |
| ECL | 13477 / 3166 | 2026-06-02 buy/block · t=16 · e=False · buy=False | 2026-07-24 rebuy/block · t=4 · e=False · buy=False | 2026-06-01 buy/block · t=16 · e=False · buy=False | 2026-06-01 buy/block · t=16 · e=False · buy=False |
| SW | 4562 / 3166 | 2026-03-03 sell/None · t=16 · e=False · buy=False | 2026-07-24 rebuy/block · t=4 · e=False · buy=False | 2026-03-05 sell/None · t=16 · e=False · buy=False | 2026-03-05 sell/None · t=16 · e=False · buy=False |
| WMT | 13597 / 3166 | 2026-07-28 buy/block · t=3 · e=False · buy=False | 2026-07-29 buy/pending · t=3 · e=False · buy=False | 2026-07-31 buy/pending · t=2 · e=True · buy=True | 2026-07-31 buy/pending · t=2 · e=True · buy=True |

## 3. Start-invariance re-run on real data (NEW anchor)

`gate(c)` vs `gate(c.iloc[3:])` over 238 data/stocks names: **0 movers** on the §7 fields ['last_date', 'last_type', 'last_quality', 'asof', 'eligible', 'tier_cascade', 'ticks', 'buyable'].

Zero — every field a board, a chart or a ledger reads is now a function of the price history alone. Before the repair the same run moved 238/238 last-marker dates and flipped 11 eligibilities.

### The one residual, named rather than hidden: the warm-up head

190 of 238 marker streams are IDENTICAL end to end. The other 48 differ only at the HEAD of the stream: the truncation eats the leading 3D bucket outright, and near the 60-bucket RSI-MACD warm-up (plus the StochRSI flat-band NaN that drops rows out of the frame at all) the two windows can differ by a marker or two. The most recent such disagreement anywhere in the universe is **2024-04-09**, and the table below is sorted by exactly that — read it as the residual's ceiling. Each row's disagreement sits in that name's OWN first weeks, so a recent date there means a recent LISTING, not a recent defect (the worst case is a 2023 IPO whose warm-up head is 2024; the deep names' residuals are decades old). This is EWM memory, the residual the cascade's own battery names too; it is a different animal from the bucket-phase defect, which was structural, unbounded, and reached the last bar.

| name | markers old / new | identical tail | last disagreement |
|---|---|---:|---|
| KVUE | 11 / 10 | 10 | 2024-04-09 |
| HOOD | 23 / 23 | 20 | 2022-10-18 |
| APP | 24 / 23 | 23 | 2022-03-18 |
| CVNA | 48 / 48 | 44 | 2019-01-09 |
| ANET | 69 / 71 | 66 | 2015-11-05 |
| PANW | 91 / 89 | 86 | 2013-11-18 |
| FANG | 89 / 88 | 88 | 2013-09-19 |
| PSX | 97 / 98 | 94 | 2013-08-20 |
| TSLA | 92 / 94 | 91 | 2011-07-14 |
| DG | 96 / 97 | 96 | 2010-10-21 |

## 4. Ledger re-key surface (R-SQ4)

`open-take re-keys` above counts names CURRENTLY holding a §7 entry (buy/rebuy, take or pending) whose marker date moved — i.e. every forward row keyed on that date needs the era fence. No backfill, no retro-edit: rows logged pre-era keep their dates and `anchor_era` is the cohort boundary (`track_record.SQ_ANCHOR_ERA_FLOOR` enforces it at ingestion).

