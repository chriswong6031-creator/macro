# coiled + mtf_upturn absolute session anchor — blast radius

Era `coiled-mtf-abs-session-2026-08-06` · ruling `research/SIGNAL_QUALITY_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md` §Sibling triage chip (2)

Generated 2026-08-07T07:21Z · store as-of dates are per-universe (read from the stores, never the wall clock).


OLD = the pre-repair `resample("3B"/"2B")` constructions frozen verbatim in `scripts/measure_coiled_mtf_anchor_blast_radius.py` (market-blind, as production was); NEW = the modules as they ship.


## 1. Old → new, per production loader

| universe | graded | bull_div flips | fire flips | fire_ticks moved | d3 pos flips | d3 bars_since_cross moved | store as-of |
|---|---:|---:|---:|---:|---:|---:|---|
| data/stocks (deep US) | 238 | 16 (6.7%) | 20 (8.4%) | 132 (55.5%) | 11 (4.6%) | 157 (66.0%) | 2026-08-06 |
| baskets/ohlcv (2014-start) | 2753 | 168 (6.1%) | 286 (10.4%) | 1550 (56.3%) | 120 (4.4%) | 2180 (79.2%) | 2026-08-06 |
| stocks tail-345 (depth view) | 238 | 11 (4.6%) | 8 (3.4%) | 116 (48.7%) | 11 (4.6%) | 160 (67.2%) | 2026-08-06 |
| stocks tail-777 (depth view) | 238 | 10 (4.2%) | 9 (3.8%) | 90 (37.8%) | 11 (4.6%) | 160 (67.2%) | 2026-08-06 |
| breadth cache (native rolling window) | 501 | 20 (4.0%) | 21 (4.2%) | 266 (53.1%) | 18 (3.6%) | 293 (58.5%) | 2026-08-06 |
| smallcap_breadth cache (native rolling window) | 601 | 27 (4.5%) | 35 (5.8%) | 255 (42.4%) | 23 (3.8%) | 455 (75.7%) | 2026-08-06 |
| midcap_breadth cache (native rolling window) | 400 | 23 (5.8%) | 27 (6.8%) | 155 (38.8%) | 9 (2.2%) | 288 (72.0%) | 2026-08-06 |
| russell_breadth cache (native rolling window) | — | — | — | — | — | — | **not measured** |
| china_search panel (CN, market=CN) | 1773 | 103 (5.8%) | 121 (6.8%) | 835 (47.1%) | 32 (1.8%) | 884 (49.9%) | 2026-08-06 |

- **data/stocks (deep US)** — the deep-history loader (1960s starts) — the standout board's primary store
  - div_flips: AMD, AVGO, AZO, BA, CL, CMI, ELV, EXR, MNST, MRVL, ORCL, ORLY
  - fire_flips: ABNB, ADI, AMAT, AMZN, CRH, CVNA, DE, ECL, EQIX, ETN, EXR, GILD
  - d3_flips: AMT, ATO, COST, DVN, KR, LYV, PGR, SLB, STLD, UBER, VRTX

- **baskets/ohlcv (2014-start)** — the 2014-start loader — mtf_upturn's PRIMARY store (ohlcv → stocks → yahoo)
  - not graded: 22 (22× under 120 bars)
  - div_flips: ABCB, ADEA, ADI, AESI, AGNT, AIR, ALLO, ALM, ALNY, AMD, APD, ARE
  - fire_flips: AAP, AARD, ABEO, ABNB, ABOS, ACCO, ACMR, ADAM, ADI, AFCG, AFRM, AIG
  - d3_flips: AG, AGI, ALEC, AMT, ARWR, ASC, ATO, BALY, BANF, BBSI, BEEP, BIIB

- **stocks tail-345 (depth view)** — stocks/ truncated to the trailing 345 bars — the breadth/smallcap cache depth class
  - div_flips: AMD, APD, AVGO, BA, CL, ISRG, MNST, MRVL, PEP, SNDK, WMT
  - fire_flips: AMAT, CRH, CVNA, NWSA, SATS, SBAC, TT, VMC
  - d3_flips: AMT, ATO, COST, DVN, ES, KR, LYV, NVDA, PGR, SLB, STLD

- **stocks tail-777 (depth view)** — stocks/ truncated to the trailing 777 bars — the breadth/smallcap cache depth class
  - div_flips: AMD, AVGO, BA, CL, ISRG, MNST, MRVL, PEP, SNDK, WMT
  - fire_flips: ADI, AMAT, CRH, CVNA, ECL, SBAC, SHW, SYY, VMC
  - d3_flips: AMT, ATO, COST, DVN, ES, KR, LYV, NVDA, PGR, SLB, STLD

- **breadth cache (native rolling window)** — the ROLLING ~3y cache whose window start creeps forward every refresh — the build-to-build re-phase surface
  - not graded: 9 (9× under 120 bars)
  - div_flips: BAX, CL, CMI, COHR, EVRG, EW, HPE, HBAN, ICE, KEYS, KMI, MNST
  - fire_flips: AMZN, APH, BIIB, CCI, CEG, CRH, CRWD, DECK, DELL, DHI, GLW, ETN
  - d3_flips: AES, ARE, AVGO, BIIB, CINF, CL, DAL, DVN, FANG, KR, LYV, META

- **smallcap_breadth cache (native rolling window)** — the ROLLING ~3y cache whose window start creeps forward every refresh — the build-to-build re-phase surface
  - not graded: 33 (33× under 120 bars)
  - div_flips: ADEA, ADUS, ANIP, AOSL, BMI, BXMT, CBU, CWK, ENVA, HCSG, KALU, MTCH
  - fire_flips: AAP, ABR, ADAM, BANR, BOOT, BTU, CC, CLSK, CNS, CRVL, CZR, DV
  - d3_flips: ADNT, CATY, CWST, CXW, DAVE, HP, HUBG, KMT, KNTK, LFST, LQDT, MMI

- **midcap_breadth cache (native rolling window)** — the ROLLING ~3y cache whose window start creeps forward every refresh — the build-to-build re-phase surface
  - not graded: 12 (12× under 120 bars)
  - div_flips: AA, AEIS, AGCO, APG, CART, CBT, CLF, DLB, DY, ENS, GBCI, GMED
  - fire_flips: AA, ACI, AFG, APPF, CART, CHDN, CRBG, DOCU, ESAB, EXP, FNB, HIMS
  - d3_flips: ALV, CNM, CROX, FNB, NOV, OKTA, SWX, WCC, ZION

- **russell_breadth cache (native rolling window)** — data/russell_breadth/_closes_cache.parquet absent from this checkout

- **china_search panel (CN, market=CN)** — CN lane: OLD was market-blind bdate bins; NEW cuts on the Shanghai reference calendar — a calendar change plus a phase change
  - not graded: 21 (21× under 120 bars)
  - div_flips: 688981.SS, 601088.SS, 002080.SZ, 300014.SZ, 688396.SS, 600673.SS, 000408.SZ, 002466.SZ, 001389.SZ, 300757.SZ, 688048.SS, 601825.SS
  - fire_flips: 300408.SZ, 301308.SZ, 688525.SS, 601898.SS, 688766.SS, 000021.SZ, 301396.SZ, 688387.SS, 688141.SS, 301269.SZ, 688047.SS, 600895.SS
  - d3_flips: 300750.SZ, 601985.SS, 000792.SZ, 600089.SS, 600893.SS, 601233.SS, 688796.SS, 688336.SS, 603699.SS, 000921.SZ, 600157.SS, 002779.SZ

## 2. The rank input — STAR/bonus on the production union universe

Union universe 1505 names (1458 with sectors) · coiled tonight: 194 (ACIW, ACMR, ACN, ADBE, ADI, ADSK, AEIS, AGYS, AKAM, ALGM, AMAT, AMD, AMKR, ANET, AOSL, APH, APP, APPF, ARLO, AVGO, BDC, BILL, BL, BMI, BOX, BSY, CALX, CARG, CCOI, CDNS, CDW, CGNX, CHTR, CIEN, CLSK, CMCSA, CNK, CNXN, COHR, COHU, CRM, CRSR, CRUS, CRWD, CTS, CTSH, CVLT, CXM, CXT, DBD, DBX, DDOG, DIOD, DIS, DLB, DOCN, DOCU, DT, DV, DXC, ECHO, EFOR, ENPH, ENTG, EPAM, EXTR, FFIV, FICO, FN, FORM, FOX, FOXA, FSLR, GDDY, GEN, GLW, GOOG, GOOGL, GTM, GWRE, HLIT, HPQ, IBM, ICHR, IDCC, INTC, INTU, IPGP, IT, ITRI, KD, KLAC, KLIC, LIF, LITE, LRCX, LSCC, LUMN, MANH, MARA, MCHP, META, MIR, MKSI, MPWR, MSFT, MSI, MTCH, MTSI, MU, MXL, NABL, NFLX, NOVT, NOW, NSSC, NTAP, NTNX, NVDA, NWS, NWSA, NXPI, NXST, NYT, OKTA, OLED, OMC, ON, ONTO, ORCL, OSIS, P, PANW, PATH, PEGA, PENG, PI, PINS, PLAB, PLTR, PLUS, PRGS, PSKY, PTC, QCOM, QLYS, QNST, QRVO, QTWO, RAMP, RMBS, RNG, ROP, SATS, SCSC, SEDG, SHEN, SITM, SMCI, SNDK, SNPS, SPSC, STX, SWKS, SYNA, T, TDC, TDS, TDY, TEL, TER, TKO, TMUS, TRIP, TRMB, TTD, TTMI, TTWO, TWLO, TXN, TYL, UCTT, VNT, VSAT, VSH, VYX, VZ, WDAY, WDC, WMG, YELP, YOU, ZBRA, ZD)


- **STAR flips (rank input, ±0.15 bonus ≈ 0.3 cascade tier): 15** (AEIS, AMD, AOSL, AVGO, BMI, COHR, DLB, LSCC, MTCH, ORCL, QTWO, SNDK, TER, TTMI, ZD)
- fire chip flips among coiled: ADI, AMAT, APPF, CLSK, DOCU, DV, EXTR, GLW, LUMN, SEDG, TMUS, TTMI
- fire_ticks moves among coiled (the day-diffed field): ACN, ADI, ALGM, AMAT, APPF, AVGO, BILL, BOX, CIEN, CLSK, CNK, CRSR, CTSH, CVLT, CXT, DBD, DOCU, DV, ECHO, EFOR, ENPH, EPAM, EXTR, FICO, FN, FOX, FOXA, GDDY, GEN, GLW, GTM, HPQ, ICHR, INTU, LUMN, MSI, MTCH, NTAP, NTNX, NXST, OMC, ORCL, OSIS, PATH, QLYS, QNST, QRVO, RAMP, ROP, SCSC, SEDG, T, TDY, TMUS, TRIP, TTMI, TTWO, TYL, VNT, VZ, YELP, ZBRA

star = coiled ∧ div; coiled (washout ∧ cohort) carries no grid and cannot flip under the anchor — every rank-input move is ±0.15 (≈0.3 cascade tier) on a star flip, plus the display-only fire chip.


## 3. stocks/ vs baskets/ohlcv/ — the defect's live symptom

237 shared names.

| field | disagreements BEFORE | disagreements AFTER |
|---|---:|---:|
| div | 13 | 0 |
| fire | 10 | 0 |
| ticks | 81 | 3 |
| src | 36 | 0 |
| d3_pos | 8 | 0 |
| d3_bsc | 99 | 2 |

Residual AFTER (4 names) — named, not rounded to zero. Where the two stores' probe still differs, the stores' own DATA differs (depth or price revisions), not the grid:

- **CSCO** (ticks) — stocks 9183 bars to 2026-08-06, ohlcv 3167 bars to 2026-08-06
- **EA** (ticks,d3_bsc) — stocks 9275 bars to 2026-08-05, ohlcv 3165 bars to 2026-08-05
- **GD** (d3_bsc) — stocks 16257 bars to 2026-08-06, ohlcv 3167 bars to 2026-08-06
- **PCG** (ticks) — stocks 13658 bars to 2026-08-06, ohlcv 3167 bars to 2026-08-06

## 4. Start-invariance re-run under the NEW anchor (must be 0)

- k1: **0 movers** / 238 graded
- k3: **0 movers** / 238 graded

## 5. What this re-draw is

A one-time, era-stamped re-phase (the R-SQ4 pattern): the OLD chips were a function of each loader's window start — the breadth caches' start creeps forward every refresh, so 'flips' of this size were being minted build-to-build with zero price action, and the two US loaders disagreed about the same name the same night (§3 BEFORE column). Under the absolute anchor every window of a name reads one grid (§4: 0 movers), the flips above happen ONCE, and `anchor_era` on the persisted payloads (us_standouts coiled block, china_standouts coiled block, mtf_upturn artifacts) lets every grader and day-over-day differ fence the boundary. Semantics are byte-identical: thresholds, windows, K-of-N, hysteresis, W-FRI weekly legs and washout_ctx are untouched.

