# PSS-SR3 — synchronized participation recovery

The construction and decision law were committed before forward outcomes in `research/PSS_SR3_PARTICIPATION_RECOVERY_PREREG.md`. Positive effects always mean SR3 is better than the nested level-recovered control.

SR3 is research/display-only. Historical qualification could authorize only a prospective frozen shadow, never entry, rank, size, gate, or alert authority.

## Construction audit

- Anchor: subject fresh prior-60 close low during a shifted-q80 ex-self sector new-low breadth extreme.
- Subject action: first three-session recovery hold; each close >= +0.50 frozen ATR, each low >= -0.50 ATR, final close in [+1.00,+1.75] ATR.
- Passive peer qualification: on all three action-window closes, at least half of peers are >=+0.50 own frozen ATR above their own formation lows.
- Treatment: on all three closes, at least half of those same peers also close above their own five-session-prior close.
- Primary control: identical subject path and passive majority peer recovery, but active breadth remains below half.
- Inference: keep-first name-month; exact sector x month x anchor severity x delay strata; within-stratum permutation primary.

## DEV

| group | paths | names | names >=3 | MAE63 | prox | W5 | called | tail<=-10 | tdt | rebound8 first | breach first | unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sr3 | 981 | 575 | 93 | -8.56% | +7.84% | +29.7% | +7.5% | +41.4% | +5.0td | +44.0% | +55.1% | +0.9% |
| level_control | 1323 | 662 | 181 | -8.40% | +7.06% | +35.1% | +10.6% | +40.7% | +7.5td | +44.3% | +54.5% | +1.2% |
| weak_level | 555 | 419 | 16 | -7.59% | +7.27% | +34.3% | +9.7% | +39.9% | +5.5td | +53.9% | +45.1% | +1.0% |

### Frozen-geometry and execution audit

| group | delay | close/ref | anchor breadth | formation peer peak | passive breadth | active breadth | next-open gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| sr3 | +6.0td | +1.40 ATR | +0.264 | +0.335 | +0.850 | +0.690 | -0.000% |
| level_control | +4.5td | +1.42 ATR | +0.271 | +0.360 | +0.739 | +0.283 | +0.087% |
| weak_level | +6.0td | +1.36 ATR | +0.232 | +0.340 | +0.364 | +0.161 | +0.091% |

### SR3 minus level-recovered control

| metric | effect | 95% 3-month-block CI | permutation p | informative strata | retained events |
|---|---:|---:|---:|---:|---:|
| mae | -1.39 | [-2.81, -0.47] | 0.9875 | 91 | 1320 |
| tail10 | -6.39 | [-12.48, +1.87] | 0.9775 | 91 | 1320 |
| w5 | -6.15 | [-12.98, +3.62] | 0.9880 | 91 | 1320 |
| called | -2.12 | [-4.88, +1.67] | 0.8516 | 91 | 1320 |
| rebound8_first | -10.76 | [-15.26, -5.62] | 0.9995 | 91 | 1320 |

Inference-tape accounting: 2,304 raw primary paths; 19 repeated name-month paths dropped; 2,285 de-duplicated; 965 outside informative strata; 1,320 retained across 91 strata.

## VAL

| group | paths | names | names >=3 | MAE63 | prox | W5 | called | tail<=-10 | tdt | rebound8 first | breach first | unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sr3 | 561 | 399 | 27 | -6.43% | +7.27% | +34.8% | +6.3% | +29.0% | +3.0td | +47.4% | +51.5% | +1.1% |
| level_control | 948 | 547 | 88 | -6.09% | +6.04% | +46.3% | +9.7% | +30.5% | +5.0td | +50.3% | +48.6% | +1.2% |
| weak_level | 426 | 337 | 9 | -6.44% | +7.24% | +35.6% | +9.1% | +29.7% | +9.0td | +37.8% | +61.5% | +0.7% |

### Frozen-geometry and execution audit

| group | delay | close/ref | anchor breadth | formation peer peak | passive breadth | active breadth | next-open gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| sr3 | +6.0td | +1.41 ATR | +0.242 | +0.280 | +0.829 | +0.659 | +0.089% |
| level_control | +4.0td | +1.39 ATR | +0.244 | +0.288 | +0.682 | +0.271 | +0.110% |
| weak_level | +6.0td | +1.37 ATR | +0.225 | +0.287 | +0.370 | +0.167 | +0.183% |

### SR3 minus level-recovered control

| metric | effect | 95% 3-month-block CI | permutation p | informative strata | retained events |
|---|---:|---:|---:|---:|---:|
| mae | -1.28 | [-2.40, +0.24] | 0.8946 | 55 | 599 |
| tail10 | -2.13 | [-9.17, +5.83] | 0.6817 | 55 | 599 |
| w5 | -11.83 | [-21.55, -3.18] | 0.9945 | 55 | 599 |
| called | -1.89 | [-5.65, +3.19] | 0.8241 | 55 | 599 |
| rebound8_first | -13.20 | [-21.38, -3.54] | 0.9995 | 55 | 599 |

Inference-tape accounting: 1,509 raw primary paths; 18 repeated name-month paths dropped; 1,491 de-duplicated; 892 outside informative strata; 599 retained across 55 strata.

## FWD

| group | paths | names | names >=3 | MAE63 | prox | W5 | called | tail<=-10 | tdt | rebound8 first | breach first | unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sr3 | 523 | 388 | 28 | -7.91% | +8.03% | +31.1% | +7.0% | +42.1% | +3.0td | +48.9% | +49.7% | +1.4% |
| level_control | 645 | 455 | 30 | -7.27% | +7.48% | +40.2% | +11.4% | +37.7% | +5.0td | +51.8% | +48.0% | +0.2% |
| weak_level | 332 | 284 | 0 | -8.84% | +8.40% | +28.5% | +7.4% | +44.7% | +4.0td | +50.4% | +48.9% | +0.7% |

### Frozen-geometry and execution audit

| group | delay | close/ref | anchor breadth | formation peer peak | passive breadth | active breadth | next-open gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| sr3 | +6.0td | +1.39 ATR | +0.256 | +0.289 | +0.835 | +0.655 | -0.026% |
| level_control | +4.0td | +1.41 ATR | +0.275 | +0.329 | +0.760 | +0.277 | +0.027% |
| weak_level | +7.0td | +1.36 ATR | +0.232 | +0.280 | +0.371 | +0.181 | -0.112% |

### SR3 minus level-recovered control

| metric | effect | 95% 3-month-block CI | permutation p | informative strata | retained events |
|---|---:|---:|---:|---:|---:|
| mae | -2.17 | [-3.63, -0.86] | 0.9990 | 53 | 626 |
| tail10 | -7.42 | [-14.44, -2.92] | 0.9690 | 53 | 626 |
| w5 | -18.20 | [-32.51, -9.34] | 1.0000 | 53 | 626 |
| called | -4.08 | [-8.35, +1.06] | 0.9440 | 53 | 626 |
| rebound8_first | -7.94 | [-14.67, +0.45] | 0.9605 | 53 | 626 |

Inference-tape accounting: 1,168 raw primary paths; 4 repeated name-month paths dropped; 1,164 de-duplicated; 538 outside informative strata; 626 retained across 53 strata.

## Frozen decision law

| check | pass | evidence |
|---|:---:|---|
| DEV mae clears | NO | effect=-1.39, CI=[-2.81,-0.47], p=0.9875 |
| DEV tail10 clears | NO | effect=-6.39, CI=[-12.48,+1.87], p=0.9775 |
| DEV timing and rebound-first improve | NO | W5=-6.15, called=-2.12, rebound8=-10.76 |
| VAL mae clears | NO | effect=-1.28, CI=[-2.40,+0.24], p=0.8946 |
| VAL tail10 clears | NO | effect=-2.13, CI=[-9.17,+5.83], p=0.6817 |
| VAL timing and rebound-first improve | NO | W5=-11.83, called=-1.89, rebound8=-13.20 |
| Coverage and informative-strata floor | YES | names=733, names≥3=380, strata={'DEV': 91, 'VAL': 55} |
| H1 active share at least 15pp below Sep-Nov | YES | H1=35.7%, Sep-Nov=67.9%, gap=32.2pp |
| DEV no safe-late distance confound | YES | stratified treatment-control=-0.02 ATR |
| VAL no safe-late distance confound | YES | stratified treatment-control=+0.02 ATR |
| Sector robustness and ≤25% concentration | NO | DEV-mae min=-1.83, DEV-tail10 min=-7.84, VAL-mae min=-1.76, VAL-tail10 min=-5.38, max share=20.7% |
| No FWD primary reversal | NO | MAE=-2.17, tail=-7.42 |

**Verdict: KILLED**.

## Containment and topology

- H1-2022 primary opportunity / treatment density: 174.0 / 62.2 per month.
- Sep-Nov 2022 primary opportunity / treatment density: 100.7 / 68.3 per month.
- Conditional treatment share: H1 35.7% vs Sep-Nov 67.9%.

Treatment paths by sector:

- Financials: 427
- Information Technology: 309
- Industrials: 275
- Consumer Discretionary: 248
- Health Care: 201
- Materials: 136
- Real Estate: 135
- Consumer Staples: 111
- Energy: 99
- Utilities: 65
- Communication Services: 59

### Primary path counts by era

| era | SR3 | level control | total |
|---|---:|---:|---:|
| DEV | 981 | 1323 | 2304 |
| FWD | 523 | 645 | 1168 |
| VAL | 561 | 948 | 1509 |

### Primary path counts by sector

| sector | SR3 | level control | total |
|---|---:|---:|---:|
| Communication Services | 59 | 91 | 150 |
| Consumer Discretionary | 248 | 395 | 643 |
| Consumer Staples | 111 | 167 | 278 |
| Energy | 99 | 172 | 271 |
| Financials | 427 | 585 | 1012 |
| Health Care | 201 | 318 | 519 |
| Industrials | 275 | 424 | 699 |
| Information Technology | 309 | 400 | 709 |
| Materials | 136 | 144 | 280 |
| Real Estate | 135 | 143 | 278 |
| Utilities | 65 | 77 | 142 |

### Primary path counts by action month

| month | SR3 | level control | total |
|---|---:|---:|---:|
| 2020-09 | 34 | 53 | 87 |
| 2020-10 | 22 | 17 | 39 |
| 2020-11 | 35 | 34 | 69 |
| 2020-12 | 3 | 0 | 3 |
| 2021-01 | 1 | 1 | 2 |
| 2021-03 | 22 | 21 | 43 |
| 2021-04 | 1 | 1 | 2 |
| 2021-05 | 4 | 11 | 15 |
| 2021-06 | 20 | 47 | 67 |
| 2021-07 | 30 | 91 | 121 |
| 2021-08 | 43 | 41 | 84 |
| 2021-09 | 34 | 38 | 72 |
| 2021-10 | 32 | 49 | 81 |
| 2021-11 | 4 | 3 | 7 |
| 2021-12 | 52 | 85 | 137 |
| 2022-01 | 2 | 31 | 33 |
| 2022-02 | 86 | 86 | 172 |
| 2022-03 | 74 | 161 | 235 |
| 2022-04 | 34 | 58 | 92 |
| 2022-05 | 40 | 173 | 213 |
| 2022-06 | 137 | 162 | 299 |
| 2022-07 | 61 | 62 | 123 |
| 2022-08 | 5 | 1 | 6 |
| 2022-09 | 13 | 20 | 33 |
| 2022-10 | 180 | 59 | 239 |
| 2022-11 | 12 | 18 | 30 |
| 2023-01 | 1 | 4 | 5 |
| 2023-02 | 0 | 8 | 8 |
| 2023-03 | 37 | 137 | 174 |
| 2023-04 | 23 | 39 | 62 |
| 2023-05 | 35 | 89 | 124 |
| 2023-06 | 50 | 27 | 77 |
| 2023-07 | 15 | 9 | 24 |
| 2023-08 | 9 | 7 | 16 |
| 2023-09 | 2 | 35 | 37 |
| 2023-10 | 31 | 97 | 128 |
| 2023-11 | 103 | 60 | 163 |
| 2023-12 | 9 | 3 | 12 |
| 2024-01 | 8 | 16 | 24 |
| 2024-02 | 2 | 9 | 11 |
| 2024-03 | 3 | 7 | 10 |
| 2024-04 | 47 | 41 | 88 |
| 2024-05 | 25 | 28 | 53 |
| 2024-06 | 47 | 72 | 119 |
| 2024-07 | 23 | 20 | 43 |
| 2024-08 | 49 | 64 | 113 |
| 2024-09 | 7 | 22 | 29 |
| 2024-10 | 3 | 11 | 14 |
| 2024-11 | 23 | 32 | 55 |
| 2024-12 | 9 | 111 | 120 |
| 2025-01 | 60 | 16 | 76 |
| 2025-02 | 7 | 47 | 54 |
| 2025-03 | 64 | 99 | 163 |
| 2025-04 | 70 | 136 | 206 |
| 2025-05 | 22 | 14 | 36 |
| 2025-06 | 0 | 3 | 3 |
| 2025-07 | 9 | 5 | 14 |
| 2025-08 | 36 | 28 | 64 |
| 2025-09 | 2 | 9 | 11 |
| 2025-10 | 32 | 79 | 111 |
| 2025-11 | 62 | 61 | 123 |
| 2025-12 | 45 | 36 | 81 |
| 2026-01 | 4 | 14 | 18 |
| 2026-02 | 9 | 18 | 27 |
| 2026-03 | 31 | 32 | 63 |
| 2026-04 | 70 | 48 | 118 |

### Primary path counts by name

| sym | SR3 | level control | total |
|---|---:|---:|---:|
| A | 3 | 5 | 8 |
| AAL | 4 | 4 | 8 |
| AAP | 4 | 5 | 9 |
| AAPL | 4 | 4 | 8 |
| AAT | 2 | 7 | 9 |
| ABBV | 2 | 2 | 4 |
| ABCB | 1 | 6 | 7 |
| ABG | 6 | 3 | 9 |
| ABM | 3 | 3 | 6 |
| ABR | 2 | 2 | 4 |
| ABT | 2 | 4 | 6 |
| ACAD | 2 | 2 | 4 |
| ACGL | 0 | 1 | 1 |
| ACHC | 3 | 5 | 8 |
| ACIW | 1 | 7 | 8 |
| ACLS | 3 | 6 | 9 |
| ACN | 1 | 5 | 6 |
| ADBE | 3 | 9 | 12 |
| ADEA | 3 | 5 | 8 |
| ADI | 2 | 3 | 5 |
| ADM | 1 | 4 | 5 |
| ADMA | 3 | 1 | 4 |
| ADP | 0 | 2 | 2 |
| ADSK | 2 | 5 | 7 |
| ADUS | 1 | 4 | 5 |
| AEE | 3 | 3 | 6 |
| AES | 1 | 5 | 6 |
| AFL | 1 | 1 | 2 |
| AGX | 2 | 1 | 3 |
| AIG | 2 | 2 | 4 |
| AIN | 1 | 4 | 5 |
| AIR | 0 | 2 | 2 |
| AIT | 3 | 3 | 6 |
| AIZ | 4 | 1 | 5 |
| AJG | 0 | 2 | 2 |
| AKAM | 3 | 2 | 5 |
| ALB | 2 | 4 | 6 |
| ALGN | 3 | 0 | 3 |
| ALGT | 1 | 3 | 4 |
| ALKS | 2 | 3 | 5 |
| ALL | 1 | 4 | 5 |
| ALLE | 4 | 5 | 9 |
| AMCR | 4 | 0 | 4 |
| AMD | 3 | 6 | 9 |
| AME | 5 | 1 | 6 |
| AMGN | 2 | 2 | 4 |
| AMN | 1 | 5 | 6 |
| AMP | 2 | 5 | 7 |
| AMPH | 4 | 4 | 8 |
| AMSF | 1 | 6 | 7 |
| AMT | 5 | 4 | 9 |
| AMZN | 0 | 3 | 3 |
| ANDE | 3 | 3 | 6 |
| ANET | 4 | 2 | 6 |
| ANIP | 1 | 1 | 2 |
| AON | 1 | 1 | 2 |
| AORT | 1 | 2 | 3 |
| AOS | 2 | 7 | 9 |
| AOSL | 2 | 5 | 7 |
| APA | 1 | 7 | 8 |
| APAM | 6 | 5 | 11 |
| APD | 4 | 4 | 8 |
| APH | 3 | 5 | 8 |
| APO | 3 | 3 | 6 |
| APOG | 2 | 5 | 7 |
| APTV | 1 | 6 | 7 |
| ARCB | 2 | 3 | 5 |
| ARE | 3 | 4 | 7 |
| ARI | 1 | 3 | 4 |
| AROC | 0 | 4 | 4 |
| ARR | 1 | 4 | 5 |
| ARWR | 4 | 1 | 5 |
| ASB | 1 | 3 | 4 |
| ASH | 3 | 2 | 5 |
| ASTE | 2 | 2 | 4 |
| ASTH | 0 | 8 | 8 |
| ATEN | 4 | 4 | 8 |
| AVA | 5 | 1 | 6 |
| AVB | 1 | 4 | 5 |
| AVGO | 2 | 1 | 3 |
| AVNT | 2 | 7 | 9 |
| AVY | 3 | 5 | 8 |
| AWR | 4 | 2 | 6 |
| AX | 5 | 5 | 10 |
| AXP | 2 | 3 | 5 |
| AZO | 0 | 2 | 2 |
| AZTA | 3 | 5 | 8 |
| BA | 2 | 4 | 6 |
| BAC | 2 | 3 | 5 |
| BALL | 2 | 2 | 4 |
| BANC | 4 | 5 | 9 |
| BANF | 5 | 2 | 7 |
| BANR | 3 | 6 | 9 |
| BAX | 5 | 5 | 10 |
| BBT | 1 | 4 | 5 |
| BCC | 5 | 1 | 6 |
| BCPC | 2 | 1 | 3 |
| BDC | 4 | 2 | 6 |
| BDX | 6 | 4 | 10 |
| BEN | 7 | 5 | 12 |
| BF-B | 6 | 4 | 10 |
| BFH | 2 | 4 | 6 |
| BFS | 3 | 2 | 5 |
| BG | 2 | 3 | 5 |
| BGC | 2 | 5 | 7 |
| BHE | 3 | 2 | 5 |
| BIIB | 1 | 7 | 8 |
| BJRI | 6 | 3 | 9 |
| BKE | 0 | 5 | 5 |
| BKR | 0 | 5 | 5 |
| BKU | 3 | 4 | 7 |
| BLDR | 2 | 2 | 4 |
| BLK | 6 | 1 | 7 |
| BLKB | 1 | 3 | 4 |
| BMI | 2 | 2 | 4 |
| BMY | 3 | 1 | 4 |
| BNY | 1 | 3 | 4 |
| BOH | 5 | 5 | 10 |
| BR | 1 | 3 | 4 |
| BRK-B | 2 | 2 | 4 |
| BRO | 1 | 2 | 3 |
| BSX | 2 | 2 | 4 |
| BURL | 3 | 2 | 5 |
| BX | 2 | 3 | 5 |
| BXP | 3 | 5 | 8 |
| BYD | 0 | 5 | 5 |
| C | 3 | 4 | 7 |
| CAG | 4 | 6 | 10 |
| CAKE | 3 | 4 | 7 |
| CALM | 0 | 2 | 2 |
| CALX | 3 | 4 | 7 |
| CALY | 4 | 3 | 7 |
| CASH | 0 | 5 | 5 |
| CASY | 1 | 1 | 2 |
| CAT | 3 | 4 | 7 |
| CATY | 2 | 7 | 9 |
| CBOE | 4 | 1 | 5 |
| CBRE | 2 | 2 | 4 |
| CBRL | 3 | 7 | 10 |
| CBT | 5 | 1 | 6 |
| CBU | 3 | 6 | 9 |
| CCI | 1 | 6 | 7 |
| CCL | 1 | 6 | 7 |
| CDE | 4 | 3 | 7 |
| CDNS | 3 | 2 | 5 |
| CDW | 3 | 4 | 7 |
| CENT | 1 | 4 | 5 |
| CENTA | 2 | 3 | 5 |
| CF | 2 | 3 | 5 |
| CFFN | 5 | 3 | 8 |
| CFR | 2 | 5 | 7 |
| CGNX | 3 | 1 | 4 |
| CHCO | 1 | 4 | 5 |
| CHD | 3 | 4 | 7 |
| CHEF | 0 | 3 | 3 |
| CHRW | 3 | 2 | 5 |
| CI | 1 | 5 | 6 |
| CIEN | 2 | 4 | 6 |
| CINF | 5 | 2 | 7 |
| CL | 3 | 4 | 7 |
| CLB | 2 | 7 | 9 |
| CLX | 2 | 5 | 7 |
| CMCSA | 5 | 2 | 7 |
| CME | 1 | 1 | 2 |
| CMG | 1 | 4 | 5 |
| CMI | 2 | 5 | 7 |
| CNC | 1 | 5 | 6 |
| CNK | 2 | 4 | 6 |
| CNO | 2 | 3 | 5 |
| CNXN | 1 | 4 | 5 |
| COF | 2 | 5 | 7 |
| COHR | 5 | 5 | 10 |
| COHU | 5 | 5 | 10 |
| COLB | 4 | 4 | 8 |
| COO | 4 | 2 | 6 |
| COP | 5 | 3 | 8 |
| COR | 4 | 2 | 6 |
| COST | 0 | 1 | 1 |
| COTY | 4 | 4 | 8 |
| CPAY | 2 | 3 | 5 |
| CPF | 3 | 4 | 7 |
| CPK | 2 | 5 | 7 |
| CPRI | 0 | 5 | 5 |
| CPRT | 0 | 5 | 5 |
| CPRX | 0 | 3 | 3 |
| CPT | 4 | 1 | 5 |
| CRH | 1 | 3 | 4 |
| CRI | 2 | 4 | 6 |
| CRK | 3 | 5 | 8 |
| CRL | 6 | 3 | 9 |
| CRM | 5 | 5 | 10 |
| CRVL | 3 | 1 | 4 |
| CSCO | 2 | 3 | 5 |
| CSGP | 1 | 4 | 5 |
| CSX | 2 | 3 | 5 |
| CTAS | 0 | 3 | 3 |
| CTS | 3 | 1 | 4 |
| CUBI | 2 | 2 | 4 |
| CVBF | 2 | 2 | 4 |
| CVLT | 1 | 4 | 5 |
| CVS | 1 | 4 | 5 |
| CVX | 3 | 5 | 8 |
| CXT | 4 | 3 | 7 |
| CXW | 4 | 4 | 8 |
| DAL | 2 | 2 | 4 |
| DAN | 2 | 5 | 7 |
| DCH | 4 | 6 | 10 |
| DCOM | 3 | 5 | 8 |
| DD | 3 | 3 | 6 |
| DE | 1 | 2 | 3 |
| DECK | 2 | 3 | 5 |
| DEI | 2 | 4 | 6 |
| DG | 3 | 3 | 6 |
| DGII | 0 | 2 | 2 |
| DGX | 0 | 2 | 2 |
| DHI | 1 | 8 | 9 |
| DHR | 2 | 6 | 8 |
| DINO | 3 | 8 | 11 |
| DKS | 2 | 2 | 4 |
| DLR | 2 | 3 | 5 |
| DLTR | 2 | 3 | 5 |
| DLX | 5 | 4 | 9 |
| DNOW | 0 | 7 | 7 |
| DOC | 2 | 3 | 5 |
| DORM | 4 | 1 | 5 |
| DOV | 2 | 3 | 5 |
| DPZ | 1 | 5 | 6 |
| DRH | 3 | 3 | 6 |
| DRI | 3 | 4 | 7 |
| DVA | 1 | 3 | 4 |
| DXC | 1 | 7 | 8 |
| DXCM | 2 | 3 | 5 |
| DXPE | 3 | 3 | 6 |
| DY | 1 | 3 | 4 |
| EA | 1 | 3 | 4 |
| EAT | 4 | 3 | 7 |
| ECHO | 3 | 2 | 5 |
| ECL | 2 | 3 | 5 |
| ECPG | 5 | 2 | 7 |
| ED | 4 | 3 | 7 |
| EFOR | 1 | 3 | 4 |
| EFX | 0 | 5 | 5 |
| EG | 1 | 0 | 1 |
| EGBN | 4 | 3 | 7 |
| EIX | 1 | 4 | 5 |
| EL | 5 | 2 | 7 |
| ELV | 1 | 4 | 5 |
| EME | 3 | 5 | 8 |
| EMR | 1 | 4 | 5 |
| ENOV | 5 | 7 | 12 |
| ENS | 4 | 1 | 5 |
| ENSG | 3 | 2 | 5 |
| EOG | 4 | 5 | 9 |
| EPAC | 3 | 2 | 5 |
| EPC | 2 | 4 | 6 |
| EQIX | 1 | 3 | 4 |
| EQR | 2 | 6 | 8 |
| EQT | 3 | 3 | 6 |
| ERIE | 2 | 6 | 8 |
| ESE | 0 | 1 | 1 |
| ESNT | 1 | 3 | 4 |
| ESS | 5 | 3 | 8 |
| ETD | 3 | 0 | 3 |
| ETN | 2 | 4 | 6 |
| EVTC | 4 | 6 | 10 |
| EW | 3 | 2 | 5 |
| EWBC | 5 | 3 | 8 |
| EXC | 2 | 1 | 3 |
| EXPD | 3 | 4 | 7 |
| EXPO | 5 | 3 | 8 |
| F | 2 | 7 | 9 |
| FANG | 1 | 5 | 6 |
| FAST | 4 | 2 | 6 |
| FBIN | 4 | 6 | 10 |
| FBP | 1 | 4 | 5 |
| FCF | 4 | 5 | 9 |
| FCFS | 0 | 2 | 2 |
| FCX | 2 | 5 | 7 |
| FDS | 2 | 0 | 2 |
| FDX | 2 | 1 | 3 |
| FE | 2 | 4 | 6 |
| FELE | 2 | 5 | 7 |
| FFBC | 3 | 7 | 10 |
| FFIN | 4 | 5 | 9 |
| FI | 1 | 3 | 4 |
| FIBK | 3 | 4 | 7 |
| FICO | 0 | 1 | 1 |
| FIS | 4 | 3 | 7 |
| FIVE | 0 | 4 | 4 |
| FIZZ | 4 | 4 | 8 |
| FLEX | 0 | 5 | 5 |
| FLG | 1 | 5 | 6 |
| FLO | 5 | 5 | 10 |
| FMC | 2 | 2 | 4 |
| FN | 3 | 3 | 6 |
| FORM | 6 | 7 | 13 |
| FOXF | 5 | 4 | 9 |
| FRT | 3 | 5 | 8 |
| FSLR | 5 | 3 | 8 |
| FTNT | 1 | 1 | 2 |
| FUL | 2 | 4 | 6 |
| FULT | 2 | 6 | 8 |
| FUN | 3 | 2 | 5 |
| FWRD | 2 | 3 | 5 |
| GATX | 2 | 5 | 7 |
| GBCI | 3 | 5 | 8 |
| GBX | 1 | 7 | 8 |
| GD | 1 | 2 | 3 |
| GE | 1 | 5 | 6 |
| GEF | 5 | 5 | 10 |
| GEN | 2 | 4 | 6 |
| GEO | 0 | 4 | 4 |
| GFF | 3 | 5 | 8 |
| GHC | 0 | 3 | 3 |
| GIII | 3 | 5 | 8 |
| GIS | 2 | 4 | 6 |
| GL | 2 | 2 | 4 |
| GLW | 1 | 4 | 5 |
| GM | 2 | 5 | 7 |
| GNRC | 1 | 2 | 3 |
| GNW | 2 | 5 | 7 |
| GOGO | 1 | 5 | 6 |
| GOOG | 1 | 4 | 5 |
| GOOGL | 1 | 4 | 5 |
| GPC | 1 | 3 | 4 |
| GPI | 2 | 4 | 6 |
| GPN | 5 | 2 | 7 |
| GRBK | 1 | 6 | 7 |
| GS | 3 | 6 | 9 |
| GT | 5 | 2 | 7 |
| GTLS | 1 | 1 | 2 |
| GTY | 2 | 2 | 4 |
| GVA | 1 | 3 | 4 |
| GWW | 1 | 1 | 2 |
| H | 2 | 6 | 8 |
| HAE | 0 | 3 | 3 |
| HAFC | 1 | 3 | 4 |
| HAL | 2 | 11 | 13 |
| HASI | 2 | 1 | 3 |
| HBAN | 5 | 6 | 11 |
| HCA | 0 | 3 | 3 |
| HD | 1 | 9 | 10 |
| HE | 1 | 4 | 5 |
| HFWA | 0 | 4 | 4 |
| HIG | 2 | 5 | 7 |
| HII | 1 | 4 | 5 |
| HIW | 8 | 2 | 10 |
| HL | 2 | 4 | 6 |
| HLIT | 2 | 4 | 6 |
| HLX | 5 | 7 | 12 |
| HMN | 5 | 2 | 7 |
| HNI | 4 | 4 | 8 |
| HOG | 3 | 5 | 8 |
| HOMB | 2 | 7 | 9 |
| HON | 4 | 3 | 7 |
| HOPE | 6 | 1 | 7 |
| HP | 2 | 7 | 9 |
| HPQ | 1 | 6 | 7 |
| HRL | 1 | 7 | 8 |
| HSIC | 2 | 5 | 7 |
| HST | 4 | 3 | 7 |
| HSTM | 3 | 3 | 6 |
| HSY | 1 | 3 | 4 |
| HTH | 4 | 4 | 8 |
| HTLD | 2 | 5 | 7 |
| HTO | 4 | 6 | 10 |
| HUBB | 2 | 2 | 4 |
| HUBG | 4 | 3 | 7 |
| HUM | 1 | 1 | 2 |
| HWC | 2 | 5 | 7 |
| HWKN | 1 | 0 | 1 |
| HZO | 4 | 4 | 8 |
| IART | 2 | 5 | 7 |
| IBKR | 0 | 4 | 4 |
| IBM | 2 | 5 | 7 |
| IBOC | 2 | 5 | 7 |
| ICE | 2 | 3 | 5 |
| ICUI | 3 | 5 | 8 |
| IDXX | 3 | 6 | 9 |
| IEX | 2 | 6 | 8 |
| IFF | 5 | 2 | 7 |
| INDB | 2 | 4 | 6 |
| INTC | 5 | 7 | 12 |
| INVA | 2 | 2 | 4 |
| IOSP | 5 | 5 | 10 |
| IP | 3 | 4 | 7 |
| IPAR | 2 | 3 | 5 |
| IQV | 3 | 4 | 7 |
| IRM | 3 | 2 | 5 |
| IT | 3 | 6 | 9 |
| ITGR | 3 | 4 | 7 |
| ITW | 2 | 2 | 4 |
| IVZ | 2 | 6 | 8 |
| J | 1 | 3 | 4 |
| JBHT | 2 | 5 | 7 |
| JBL | 2 | 4 | 6 |
| JBLU | 3 | 2 | 5 |
| JBSS | 2 | 2 | 4 |
| JBTM | 2 | 1 | 3 |
| JCI | 1 | 4 | 5 |
| JJSF | 2 | 3 | 5 |
| JKHY | 2 | 1 | 3 |
| JNJ | 1 | 3 | 4 |
| JOE | 3 | 1 | 4 |
| JPM | 3 | 4 | 7 |
| KAI | 3 | 3 | 6 |
| KALU | 4 | 4 | 8 |
| KDP | 3 | 4 | 7 |
| KEY | 4 | 7 | 11 |
| KFY | 4 | 3 | 7 |
| KLAC | 7 | 3 | 10 |
| KLIC | 1 | 5 | 6 |
| KMB | 4 | 5 | 9 |
| KMI | 2 | 2 | 4 |
| KMPR | 2 | 8 | 10 |
| KMT | 3 | 2 | 5 |
| KN | 5 | 3 | 8 |
| KO | 0 | 1 | 1 |
| KR | 3 | 2 | 5 |
| KSS | 3 | 8 | 11 |
| KTOS | 1 | 2 | 3 |
| KWR | 4 | 5 | 9 |
| L | 4 | 1 | 5 |
| LCII | 3 | 5 | 8 |
| LDOS | 1 | 5 | 6 |
| LEG | 6 | 5 | 11 |
| LEN | 1 | 8 | 9 |
| LGIH | 3 | 4 | 7 |
| LH | 4 | 4 | 8 |
| LHX | 0 | 2 | 2 |
| LII | 2 | 6 | 8 |
| LKFN | 1 | 8 | 9 |
| LLY | 1 | 4 | 5 |
| LMAT | 2 | 2 | 4 |
| LMT | 2 | 2 | 4 |
| LNN | 2 | 6 | 8 |
| LNT | 2 | 4 | 6 |
| LOW | 3 | 8 | 11 |
| LQDT | 1 | 2 | 3 |
| LRCX | 5 | 4 | 9 |
| LTC | 4 | 1 | 5 |
| LULU | 4 | 2 | 6 |
| LUMN | 0 | 6 | 6 |
| LUV | 1 | 3 | 4 |
| LXP | 2 | 1 | 3 |
| LYB | 5 | 2 | 7 |
| LYV | 1 | 8 | 9 |
| LZB | 2 | 5 | 7 |
| MA | 5 | 2 | 7 |
| MAR | 4 | 2 | 6 |
| MAS | 4 | 5 | 9 |
| MATW | 3 | 4 | 7 |
| MATX | 1 | 2 | 3 |
| MC | 6 | 4 | 10 |
| MCD | 1 | 2 | 3 |
| MCHP | 6 | 6 | 12 |
| MCO | 2 | 3 | 5 |
| MCY | 3 | 4 | 7 |
| MD | 5 | 3 | 8 |
| MDLZ | 1 | 3 | 4 |
| MDT | 3 | 7 | 10 |
| MET | 4 | 3 | 7 |
| MHK | 5 | 7 | 12 |
| MKC | 4 | 5 | 9 |
| MKSI | 3 | 8 | 11 |
| MLM | 2 | 4 | 6 |
| MMI | 1 | 2 | 3 |
| MMM | 3 | 4 | 7 |
| MMS | 4 | 0 | 4 |
| MMSI | 6 | 5 | 11 |
| MNRO | 7 | 0 | 7 |
| MNST | 3 | 2 | 5 |
| MO | 0 | 2 | 2 |
| MOG-A | 0 | 2 | 2 |
| MOH | 1 | 3 | 4 |
| MOS | 3 | 2 | 5 |
| MPC | 2 | 5 | 7 |
| MPWR | 3 | 4 | 7 |
| MRCY | 1 | 2 | 3 |
| MRK | 0 | 3 | 3 |
| MRVL | 3 | 6 | 9 |
| MSCI | 3 | 2 | 5 |
| MSEX | 3 | 5 | 8 |
| MSFT | 4 | 6 | 10 |
| MSM | 1 | 4 | 5 |
| MTB | 2 | 7 | 9 |
| MTD | 2 | 6 | 8 |
| MTH | 5 | 2 | 7 |
| MTRN | 3 | 4 | 7 |
| MTUS | 3 | 3 | 6 |
| MTX | 5 | 4 | 9 |
| MUR | 6 | 7 | 13 |
| MWA | 3 | 2 | 5 |
| MXL | 2 | 3 | 5 |
| MYRG | 2 | 3 | 5 |
| MZTI | 0 | 3 | 3 |
| NBHC | 2 | 4 | 6 |
| NBTB | 2 | 3 | 5 |
| NCLH | 3 | 4 | 7 |
| NDAQ | 1 | 2 | 3 |
| NDSN | 4 | 2 | 6 |
| NEE | 3 | 2 | 5 |
| NEM | 5 | 2 | 7 |
| NEO | 1 | 5 | 6 |
| NFLX | 2 | 2 | 4 |
| NHC | 0 | 3 | 3 |
| NI | 0 | 1 | 1 |
| NJR | 2 | 1 | 3 |
| NKE | 2 | 5 | 7 |
| NMIH | 0 | 6 | 6 |
| NOC | 0 | 2 | 2 |
| NOG | 4 | 5 | 9 |
| NOVT | 3 | 5 | 8 |
| NOW | 5 | 2 | 7 |
| NPK | 1 | 2 | 3 |
| NPO | 0 | 3 | 3 |
| NRG | 2 | 0 | 2 |
| NSC | 4 | 5 | 9 |
| NSIT | 2 | 8 | 10 |
| NSP | 1 | 1 | 2 |
| NTAP | 0 | 3 | 3 |
| NUE | 2 | 3 | 5 |
| NWBI | 3 | 5 | 8 |
| NWE | 2 | 4 | 6 |
| NWL | 3 | 5 | 8 |
| NWN | 2 | 5 | 7 |
| NX | 5 | 3 | 8 |
| O | 2 | 4 | 6 |
| OI | 4 | 5 | 9 |
| OII | 2 | 6 | 8 |
| OKE | 4 | 1 | 5 |
| OMCL | 1 | 3 | 4 |
| ON | 4 | 5 | 9 |
| ONB | 4 | 3 | 7 |
| ORA | 3 | 1 | 4 |
| ORCL | 2 | 4 | 6 |
| ORLY | 1 | 2 | 3 |
| OTTR | 1 | 4 | 5 |
| OUT | 4 | 4 | 8 |
| OXM | 2 | 4 | 6 |
| OXY | 4 | 5 | 9 |
| PAHC | 3 | 3 | 6 |
| PANW | 3 | 1 | 4 |
| PATK | 3 | 3 | 6 |
| PAYX | 4 | 3 | 7 |
| PBF | 2 | 6 | 8 |
| PBH | 1 | 3 | 4 |
| PCAR | 2 | 3 | 5 |
| PCRX | 0 | 2 | 2 |
| PDFS | 6 | 1 | 7 |
| PEB | 3 | 3 | 6 |
| PEG | 3 | 1 | 4 |
| PENN | 5 | 6 | 11 |
| PEP | 2 | 3 | 5 |
| PFBC | 3 | 5 | 8 |
| PFE | 1 | 2 | 3 |
| PFG | 3 | 6 | 9 |
| PFS | 2 | 7 | 9 |
| PGR | 0 | 1 | 1 |
| PH | 2 | 4 | 6 |
| PII | 2 | 3 | 5 |
| PIPR | 2 | 3 | 5 |
| PKG | 4 | 2 | 6 |
| PLAB | 2 | 3 | 5 |
| PLD | 4 | 1 | 5 |
| PLUS | 3 | 2 | 5 |
| PLXS | 3 | 1 | 4 |
| PM | 2 | 4 | 6 |
| PMT | 3 | 2 | 5 |
| PNC | 5 | 3 | 8 |
| PNW | 5 | 1 | 6 |
| POOL | 5 | 4 | 9 |
| PPG | 7 | 4 | 11 |
| PRAA | 2 | 2 | 4 |
| PRDO | 3 | 3 | 6 |
| PRG | 8 | 2 | 10 |
| PRGS | 1 | 4 | 5 |
| PRK | 3 | 4 | 7 |
| PRKS | 1 | 7 | 8 |
| PRLB | 4 | 2 | 6 |
| PRSU | 4 | 5 | 9 |
| PRU | 3 | 4 | 7 |
| PSA | 2 | 5 | 7 |
| PSKY | 3 | 6 | 9 |
| PSX | 4 | 6 | 10 |
| PTC | 2 | 6 | 8 |
| PTCT | 5 | 1 | 6 |
| PTEN | 8 | 12 | 20 |
| PWR | 2 | 2 | 4 |
| PZZA | 4 | 7 | 11 |
| QCOM | 3 | 5 | 8 |
| QDEL | 1 | 4 | 5 |
| QLYS | 3 | 3 | 6 |
| QNST | 5 | 2 | 7 |
| QTWO | 4 | 5 | 9 |
| RAMP | 3 | 5 | 8 |
| RCL | 2 | 2 | 4 |
| RDN | 1 | 4 | 5 |
| RDNT | 3 | 4 | 7 |
| REG | 3 | 3 | 6 |
| REGN | 3 | 3 | 6 |
| RES | 5 | 6 | 11 |
| REX | 1 | 3 | 4 |
| RF | 4 | 6 | 10 |
| RH | 3 | 6 | 9 |
| RHP | 4 | 4 | 8 |
| RJF | 2 | 5 | 7 |
| RL | 2 | 6 | 8 |
| RMBS | 4 | 4 | 8 |
| RNST | 2 | 6 | 8 |
| ROCK | 2 | 4 | 6 |
| ROG | 2 | 4 | 6 |
| ROK | 2 | 5 | 7 |
| ROL | 0 | 1 | 1 |
| ROP | 2 | 4 | 6 |
| ROST | 0 | 6 | 6 |
| RSG | 0 | 1 | 1 |
| RTX | 2 | 4 | 6 |
| RUSHA | 2 | 3 | 5 |
| RVTY | 5 | 6 | 11 |
| RWT | 1 | 4 | 5 |
| SAFE | 5 | 4 | 9 |
| SAFT | 3 | 3 | 6 |
| SAH | 0 | 6 | 6 |
| SAM | 4 | 4 | 8 |
| SANM | 2 | 2 | 4 |
| SBAC | 5 | 1 | 6 |
| SBCF | 4 | 8 | 12 |
| SBH | 4 | 3 | 7 |
| SBRA | 1 | 1 | 2 |
| SBSI | 3 | 7 | 10 |
| SBUX | 3 | 2 | 5 |
| SCHL | 4 | 0 | 4 |
| SCHW | 1 | 3 | 4 |
| SCL | 6 | 5 | 11 |
| SCSC | 4 | 2 | 6 |
| SEM | 2 | 5 | 7 |
| SFBS | 4 | 2 | 6 |
| SFNC | 0 | 7 | 7 |
| SHEN | 3 | 2 | 5 |
| SHO | 5 | 4 | 9 |
| SHOO | 5 | 4 | 9 |
| SHW | 1 | 5 | 6 |
| SIG | 2 | 5 | 7 |
| SIGI | 4 | 2 | 6 |
| SJM | 0 | 6 | 6 |
| SKYW | 1 | 2 | 3 |
| SLAB | 5 | 6 | 11 |
| SLB | 4 | 5 | 9 |
| SLG | 2 | 5 | 7 |
| SM | 1 | 4 | 5 |
| SMP | 4 | 1 | 5 |
| SMTC | 6 | 4 | 10 |
| SNA | 3 | 1 | 4 |
| SNEX | 1 | 1 | 2 |
| SNPS | 0 | 8 | 8 |
| SO | 0 | 3 | 3 |
| SPNT | 4 | 1 | 5 |
| SPSC | 4 | 6 | 10 |
| SPXC | 2 | 2 | 4 |
| SR | 2 | 3 | 5 |
| SRPT | 2 | 3 | 5 |
| SSB | 6 | 3 | 9 |
| STBA | 3 | 5 | 8 |
| STE | 0 | 4 | 4 |
| STLD | 4 | 1 | 5 |
| STRA | 4 | 1 | 5 |
| STRL | 1 | 2 | 3 |
| STX | 4 | 4 | 8 |
| STZ | 4 | 3 | 7 |
| SUPN | 1 | 6 | 7 |
| SW | 3 | 2 | 5 |
| SWX | 2 | 1 | 3 |
| SXI | 1 | 1 | 2 |
| SXT | 1 | 4 | 5 |
| SYK | 0 | 1 | 1 |
| SYNA | 5 | 4 | 9 |
| T | 3 | 2 | 5 |
| TAP | 1 | 4 | 5 |
| TCBI | 0 | 6 | 6 |
| TDC | 2 | 5 | 7 |
| TDS | 2 | 2 | 4 |
| TDY | 4 | 3 | 7 |
| TECH | 2 | 3 | 5 |
| TER | 6 | 6 | 12 |
| TFC | 1 | 5 | 6 |
| TGT | 3 | 3 | 6 |
| THRM | 4 | 5 | 9 |
| TILE | 4 | 4 | 8 |
| TJX | 0 | 4 | 4 |
| TMO | 2 | 5 | 7 |
| TMP | 2 | 3 | 5 |
| TMUS | 2 | 2 | 4 |
| TNC | 4 | 5 | 9 |
| TNDM | 3 | 4 | 7 |
| TPL | 5 | 1 | 6 |
| TPR | 1 | 4 | 5 |
| TR | 1 | 2 | 3 |
| TRGP | 1 | 3 | 4 |
| TRIP | 3 | 6 | 9 |
| TRMK | 2 | 3 | 5 |
| TRN | 3 | 5 | 8 |
| TRNO | 4 | 2 | 6 |
| TROW | 2 | 3 | 5 |
| TRST | 2 | 6 | 8 |
| TRV | 1 | 0 | 1 |
| TSCO | 4 | 4 | 8 |
| TSLA | 3 | 2 | 5 |
| TSN | 3 | 3 | 6 |
| TT | 2 | 2 | 4 |
| TTMI | 4 | 2 | 6 |
| TTWO | 3 | 3 | 6 |
| TWO | 2 | 4 | 6 |
| TXN | 3 | 4 | 7 |
| TXT | 4 | 6 | 10 |
| TYL | 3 | 4 | 7 |
| UAA | 3 | 5 | 8 |
| UAL | 1 | 5 | 6 |
| UBSI | 5 | 4 | 9 |
| UCB | 4 | 7 | 11 |
| UCTT | 6 | 5 | 11 |
| UDR | 4 | 4 | 8 |
| UFCS | 1 | 4 | 5 |
| UFPI | 6 | 3 | 9 |
| UHS | 3 | 4 | 7 |
| ULTA | 1 | 3 | 4 |
| UMBF | 6 | 4 | 10 |
| UNFI | 4 | 5 | 9 |
| UNH | 1 | 2 | 3 |
| UNP | 1 | 3 | 4 |
| UPS | 4 | 4 | 8 |
| URBN | 4 | 3 | 7 |
| USB | 7 | 2 | 9 |
| USPH | 2 | 3 | 5 |
| UTI | 1 | 5 | 6 |
| UTL | 4 | 3 | 7 |
| UVV | 1 | 5 | 6 |
| V | 1 | 2 | 3 |
| VC | 3 | 9 | 12 |
| VCEL | 4 | 1 | 5 |
| VCYT | 3 | 5 | 8 |
| VIAV | 5 | 4 | 9 |
| VICR | 2 | 0 | 2 |
| VLO | 2 | 5 | 7 |
| VLY | 9 | 4 | 13 |
| VMC | 2 | 5 | 7 |
| VRSK | 1 | 2 | 3 |
| VRSN | 2 | 6 | 8 |
| VRTS | 7 | 5 | 12 |
| VRTX | 1 | 1 | 2 |
| VSAT | 0 | 2 | 2 |
| VSH | 4 | 1 | 5 |
| VTOL | 2 | 2 | 4 |
| VTR | 3 | 2 | 5 |
| VYX | 8 | 1 | 9 |
| VZ | 3 | 4 | 7 |
| WAB | 1 | 2 | 3 |
| WABC | 2 | 3 | 5 |
| WAFD | 1 | 3 | 4 |
| WAL | 4 | 5 | 9 |
| WAT | 2 | 5 | 7 |
| WBD | 5 | 7 | 12 |
| WCC | 1 | 3 | 4 |
| WD | 4 | 2 | 6 |
| WDAY | 4 | 5 | 9 |
| WDC | 5 | 2 | 7 |
| WDFC | 4 | 2 | 6 |
| WEN | 3 | 8 | 11 |
| WERN | 0 | 5 | 5 |
| WFC | 2 | 5 | 7 |
| WINA | 1 | 0 | 1 |
| WKC | 3 | 3 | 6 |
| WLY | 3 | 4 | 7 |
| WM | 0 | 3 | 3 |
| WMT | 1 | 2 | 3 |
| WOR | 1 | 3 | 4 |
| WRLD | 2 | 3 | 5 |
| WSFS | 1 | 4 | 5 |
| WSM | 3 | 4 | 7 |
| WSO | 3 | 3 | 6 |
| WSR | 6 | 0 | 6 |
| WST | 1 | 4 | 5 |
| WTFC | 5 | 4 | 9 |
| WTS | 1 | 3 | 4 |
| WTW | 1 | 1 | 2 |
| WU | 4 | 3 | 7 |
| WWW | 4 | 4 | 8 |
| XNCR | 1 | 1 | 2 |
| XOM | 3 | 3 | 6 |
| XRAY | 1 | 5 | 6 |
| XYL | 0 | 5 | 5 |
| YELP | 5 | 6 | 11 |
| YUM | 3 | 4 | 7 |
| ZBH | 5 | 3 | 8 |
| ZBRA | 4 | 4 | 8 |
| ZD | 2 | 5 | 7 |
| ZTS | 3 | 2 | 5 |
| ZWS | 1 | 4 | 5 |

### Leave-one-sector-out primary effects

| era | omitted sector | MAE effect | tail effect |
|---|---|---:|---:|
| DEV | Communication Services | -1.01 | -4.90 |
| DEV | Consumer Discretionary | -1.27 | -4.93 |
| DEV | Consumer Staples | -1.31 | -6.05 |
| DEV | Energy | -1.38 | -6.09 |
| DEV | Financials | -1.55 | -5.92 |
| DEV | Health Care | -1.12 | -6.28 |
| DEV | Industrials | -1.83 | -7.84 |
| DEV | Information Technology | -1.28 | -7.66 |
| DEV | Materials | -1.50 | -7.15 |
| DEV | Real Estate | -1.59 | -6.32 |
| DEV | Utilities | -1.44 | -7.28 |
| VAL | Communication Services | -1.37 | -2.17 |
| VAL | Consumer Discretionary | -1.07 | -1.04 |
| VAL | Consumer Staples | -1.73 | -5.38 |
| VAL | Energy | -1.76 | -4.13 |
| VAL | Financials | -0.84 | +0.08 |
| VAL | Health Care | -1.27 | -3.48 |
| VAL | Industrials | -1.22 | +1.06 |
| VAL | Information Technology | -1.25 | -3.32 |
| VAL | Materials | -1.11 | -1.66 |
| VAL | Real Estate | -1.21 | -1.26 |
| VAL | Utilities | -1.28 | -2.13 |

## Exclusion and path census

- `eligible`: 799 names
- `missing_sector_map`: 501 names

Aggregate primary groups:

- treatment: 2,065
- level-recovered control: 2,916
- weak-level diagnostic: 1,313
- complete outcome paths: 6,294
- incomplete outcome paths dropped: 0

## Post-kill diagnostic partition

These slices were read only after the frozen verdict. They diagnose the failure mechanism and cannot rescue, reverse, or retune SR3. Each value remains an equal-weight effect across the same exact primary strata; sparse one-stratum cells are printed, not promoted.

| era | partition | cell | strata | MAE | tail | W5 | rebound8 first |
|---|---|---|---:|---:|---:|---:|---:|
| DEV | delay | d1 | 81 | -1.36 | -5.19 | -5.71 | -11.64 |
| DEV | delay | d2 | 10 | -1.79 | -15.33 | -9.00 | -3.67 |
| DEV | delay | d3 | 0 | — | — | — | — |
| DEV | anchor severity | p1 | 46 | -1.49 | -2.23 | -3.13 | -4.65 |
| DEV | anchor severity | p2 | 33 | -1.23 | -6.62 | -9.55 | -11.82 |
| DEV | anchor severity | p3 | 12 | -1.57 | -21.92 | -7.60 | -30.51 |
| VAL | delay | d1 | 46 | -1.19 | -1.86 | -9.79 | -14.67 |
| VAL | delay | d2 | 8 | -3.89 | -15.21 | -24.58 | -14.79 |
| VAL | delay | d3 | 1 | +18.17 | +100.00 | +0.00 | +50.00 |
| VAL | anchor severity | p1 | 35 | -1.17 | -1.17 | -8.43 | -14.58 |
| VAL | anchor severity | p2 | 14 | -2.00 | -8.91 | -18.71 | -15.45 |
| VAL | anchor severity | p3 | 6 | +0.52 | +8.91 | -12.48 | -1.65 |
| FWD | delay | d1 | 44 | -2.58 | -7.79 | -20.29 | -8.86 |
| FWD | delay | d2 | 8 | -2.79 | -7.85 | -7.78 | -8.19 |
| FWD | delay | d3 | 1 | +5.09 | +0.00 | +0.00 | +25.00 |
| FWD | anchor severity | p1 | 28 | -3.43 | -18.97 | -26.75 | -11.56 |
| FWD | anchor severity | p2 | 14 | -2.01 | +5.28 | -9.80 | -6.24 |
| FWD | anchor severity | p3 | 11 | -0.59 | +4.68 | -6.26 | -1.75 |

## Interpretation

At least one frozen requirement failed. This exact SR3 construction is not usable and cannot be rescued by threshold retiming, removing the nested control, or replacing active participation with another absence-of-weakness label after outcomes.

Inference: 2,000 within-stratum permutations (base seed 20260806); 1,000 circular three-month moving-block bootstraps (base seed 20260807).
