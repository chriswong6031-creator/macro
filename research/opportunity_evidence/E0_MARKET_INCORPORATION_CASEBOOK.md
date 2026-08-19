# E0 Market Incorporation Casebook

**Question:** once evidence existed, how far had the market already gone — anticipation, immediate abnormal response, estimate revision, options repricing, attention, peer response, persistence/rejection?

**PIT law:** “knowable at t0” means published on or before the named decision date in the cited artifact. Later rungs are labeled **ex post**. Options legs before 2026-06 are **unavailable**, not zero. Analyst-target history is **not in-repo**.

**Sources:** `research/winners/cases/*.md` (`winner_case.v1`, 154 parsed this session) · `research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md` · DRL latest.json (example only).

No scores. Incorporation is a **state vector**, not a grade.

---

## 1. Incorporation legs (research enum)

| Leg | Observable in-estate? | Notes |
|---|---|---|
| I1 Pre-event anticipation | PARTIAL | Pre-t0 residual / relative return if bars exist. 13F cannot speak. |
| I2 Immediate abnormal price response | YES | Winner-case local tape + DRL resid_z on event day |
| I3 Estimate revisions | ACCRUING from 2026-06-16 only | Yahoo snapshot archive. Pre-June 2026: unlicensed_absent |
| I4 Options repricing | ACCRUING from 2026-06-15 | Else unavailable |
| I5 Attention | PARTIAL | Quiver/Hot Tape/context-vector; historically thin |
| I6 Peer / linked-name response | PARTIAL | Benchmark excess in winner cases; group_earnings sympathy; DRL peer_ret |
| I7 Persistence vs rejection | YES if horizon matured | Winner vs `failed_breakaway`; mechanical census excess |

---

## 2. Cases

Each row: decision date = case `t0_hypothesis` unless noted. “Dominated” here means the cited artifact’s own relative-breakaway / failed_breakaway label plus named excess vs the case benchmark — **not** a new outcome model.

### 2.1 Strong catalyst, immediately incorporated

| ID | Name / t0 | Theme | Knowable at t0 | I2 immediate | I3 revisions | I4 options | I6 peers | I7 later | Receipt |
|---|---|---|---|---|---|---|---|---|---|
| INC-01 | NVDA 2023-05-25 | AI accelerators | FY24 Q1 print + Q2 ~$11B guide 2023-05-24 (issuer PR) | Gap +26.15% held 3/5/10d; $58.5B $vol z60 6.63 | **UNAVAILABLE** in-repo | **UNAVAILABLE** | +24.10pp / 42d vs SMH by 2023-06-30 | Persisted through Q2/Q3 confirms (ex post) | `research/winners/cases/NVDA_2023.md` **PRIMARY SOURCE VERIFIED** (issuer URLs in file) |
| INC-02 | MRNA 2026-01-20 → 06-18 ladder | mRNA platform | 5y KEYNOTE-942 data 2026-01-20; VRBPAC 9-0 on 2026-06-18 | 21d +49.16pp vs XBI (prices to 2026-07-02) | Repo revisions exist in 2026 but **not joined in the case**. External: avg target 45.85 vs spot 81.80 on 2026-07-06 (case cites StockAnalysis — **not PIT-safe as a house series**) | GEX 2026-07-04 IV30 96.73 — **after** the vertical, chase/coil not cause | XBI/XLV lagged | Persisted into July 2026 (case window) | `MRNA_2026.md` |
| INC-03 | CCJ 2025-05-09 | Uranium / nuclear fuel | Q1 2025-05-01: realized contract price up while spot −30%; 34.5% drawdown 21 sessions earlier | +23.80pp / 21d vs SPY; 63d high on t0 | **UNAVAILABLE** in-repo | **UNAVAILABLE** (GEX starts 2026-06) | XME proxy +17.45pp / 21d; **full-year CCJ lagged XME −4.93pp** (limit) | Second rung 2025-06-06 and 2025-10-28 are **ex post** | `CCJ_2025.md` |
| INC-04 | VRT 2023-04-26 | Data-center power | Case: platform/cycle re-underwriting vs XLI | Relative breakaway labeled present in YAML | UNAVAILABLE | UNAVAILABLE | XLI benchmark | Winner | `VRT_2023.md` YAML **CODE VERIFIED** |
| INC-05 | CRWD 2023-11-29 | Cyber | Case platform_rerating vs XLK | Immediate relative move in case tape | UNAVAILABLE | UNAVAILABLE | XLK | Winner | `CRWD_2023.md` |

### 2.2 Strong catalyst already broadly reflected (late t0 / rejection)

| ID | Name / t0 | Knowable at t0 | Incorporation read | I7 | Receipt |
|---|---|---|---|---|---|
| INC-06 | TMDX 2021-03-02 | FDA de-risking **already** public; commercial ramp not yet in numbers | I1 high / I2 present / I7 reject — “approvals arrived months before revenue” | failed_breakaway | `TMDX_2021.md` |
| INC-07 | TMDX 2022-08-25 | Approvals now a commercialization story but **onset after model extended** | Late incorporation | failed_breakaway | `TMDX_2022.md` |
| INC-08 | GTLB 2022-08-05 | Exceptional growth already known; t0 = stale-catalyst local-high continuation | I1 high, I2 weak liquidity confirmation | failed_breakaway | `GTLB_2022.md` |
| INC-09 | NVDA 2000-06-16 | GPU/Xbox re-rating **over-anticipated**; peaked 3 sessions after breakaway | I1 high → I7 reject | failed_breakaway | `NVDA_2000.md` |
| INC-10 | TSM 2000-02-03 | Record utilization / scarce capacity already in the tape | Cycle peak already priced | failed_breakaway | `TSM_2000.md` |
| INC-11 | PINS 2024-05-06 | Post-Q1 signal **after** the print; Q2 guide showed growth decelerating toward expense growth | Late / rejected | failed_breakaway | `PINS_2024.md` |
| INC-12 | SMMT 2025-04-24 | Single-asset clinical re-rating **expectation-saturated before publication**; HARMONi PFS strong but non-OS | Anticipation then reject | failed_breakaway | `SMMT_2025.md` |
| INC-13 | VKTX 2023-04-03 | Early VK2735 / VK2809 data; price outran confirmatory evidence | Immediate pop, later reject | failed_breakaway | `VKTX_2023.md` |
| INC-14 | HIMS 2024-06-04 | Delayed June signal **after** GLP-1 shock, no fresh liquidity | Late, failed 63d hold (later 2025 platform growth is a different episode) | failed_breakaway | `HIMS_2024.md` |

### 2.3 Weak / conditional catalyst, strong price (attention or financing)

| ID | Name / t0 | Catalyst quality at t0 | Price | Incorporation read | Receipt |
|---|---|---|---|---|---|
| INC-15 | SOUN 2024-02-26 | Delayed Nvidia **ownership disclosure** + AI narrative + SI; margins/losses not repaired | Vertical | I5/I2 high, I3/fundamentals weak | `SOUN_2024.md` failed_breakaway |
| INC-16 | NNE 2024-10-16 | Hyperscaler nuclear **optionality**; no 2024 revenue / licensing / operations | Liquid scarcity re-rate | I2 high, company evidence thin | `NNE_2024.md` failed_breakaway |
| INC-17 | QUBT 2024-12-06 | Quantum-theme scarcity + $50M financing + NASA application | Vertical then fail | Financing + theme, not earnings | `QUBT_2024.md` failed_breakaway |
| INC-18 | APLD 2024-07-01 | Unsigned hyperscaler lease + **conditional equity-linked financing** | AI-infra re-rate then fail | Supply overhang + uncontracted demand | `APLD_2024.md` failed_breakaway |
| INC-19 | NBIS 2025-01-24 | Strategic financing + GPU-cloud **plan**; thin operating proof, short listing history | Forward-ARR re-rate | I1/I2 on financing, not prints | `NBIS_2025.md` failed_breakaway |
| INC-20 | TEM 2025-01-21 | Platform + Ambry; late mechanical trigger, failed peak gaps | Attention-amplified vertical | I5 high | `TEM_2025.md` failed_breakaway |
| INC-21 | HIMS 2021-01-28 | Recent-SPAC + ARK attention + research vacuum | High-growth narrative pop | I5 high, operating proof later | `HIMS_2021.md` failed_breakaway |

### 2.4 Sector / factor washout, company evidence intact (incorporation delayed)

| ID | Name / t0 | Statistical hint (from case, not a new residual run) | Company evidence at t0 | Incorporation | Receipt |
|---|---|---|---|---|---|
| INC-22 | CCJ 2025-05-09 | −34.5% from 252d high; 126d ret −0.84% at t0; uranium **spot** down, **realized contract** up | Q1 2025-05-01 intact | Market had incorporated spot-price fear, not contract book | `CCJ_2025.md` |
| INC-23 | AFRM 2022-08-03 | Deep compression vs ARKF | Rebound failed: credit + funding + opex | Washout **with** impairment — not this cell | `AFRM_2022.md` failed |
| INC-24 | CHWY 2022-07-08 | Depressed consumer-discretionary | Better-than-feared print + squeeze; thin ladder | Partial repair, then fail | `CHWY_2022.md` failed |
| INC-25 | Gold / real-rate 2026-07-22..08-09 | Engine **chain FAILED** (63d Δ) while gold +5.8%/22d and NEM +15% on 08-09 tape | Prophet CN miners + NEM US Prophet 07-22 already long | **Instrument verdict ≠ market incorporation.** Market incorporated the peak **before** DFII10 63d window certified it | `CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md` **PRIMARY SOURCE VERIFIED** (FRED DFII10 + chain receipts cited) |

### 2.5 Company-impairment washout (do not call dislocation)

| ID | Name / t0 | Impairment knowable at t0 | Price | Receipt |
|---|---|---|---|---|
| INC-26 | U 2021-11-11 | Monetization-stack flaw + guidance reset (Q3/Weta) | Gap then fail | `U_2021.md` failed |
| INC-27 | RBLX 2021-11-09 | Bookings / MPU decelerating faster than recognized revenue | Q3 gap fail | `RBLX_2021.md` failed |
| INC-28 | A 2000-02-24 | Communications demand real, then **cycle + scarce float** failed when demand did | Vertical then fail | `A_2000.md` failed |
| INC-29 | SEDG 2016-02-04 | 57% pre-t0 run; largest-customer concentration | Fail | `SEDG_2016.md` failed |

### 2.6 Research echo / revision lag (I3)

House **has no PIT target-price series**. Cases that document research catching **after** price:

| ID | Name | Echo | PIT caveat | Receipt |
|---|---|---|---|---|
| INC-30 | CCJ 2025 | GS to $78 from $65 on 2025-06-10 **after** Jun-9 close $66.70; NBC C$110 vs C$108.06 on 2025-07-24 | External news citations, not `data/revisions` | `CCJ_2025.md` §7 |
| INC-31 | MRNA 2026 | Piper to 77 from 69 after Science Day; **average target still far below spot** | External | `MRNA_2026.md` §5 |
| INC-32 | NVDA 2023 | Guide forced published DC estimates to move; consensus-vs-spot qualitative only | No in-repo targets | `NVDA_2023.md` §7 |

`data/revisions/history.parquet` can support I3 **only** for names/dates ≥ 2026-06-16. MRNA’s June–July 2026 ladder is in that window but **this session did not join the parquet to the case** — I3 for MRNA remains **UNVERIFIED in-house**.

### 2.7 Options (I4) — only post-2026-06

| ID | Name | What exists | What must not be claimed |
|---|---|---|---|
| INC-33 | MRNA Jul 2026 | `site/gex/MRNA.json` 2026-07-04 IV30 96.73, call wall 80 | That options **caused** the June move |
| INC-34 | CCJ current-only | GEX from 2026-06-21; 2025 episode **null** | Any 2025 dealer story |
| INC-35 | NVDA 2023 | Current GEX only | Any 2023 skew/IV claim |

---

## 3. Pattern (descriptive, not a model)

From the labeled cases above, without weights:

- **Immediate incorporation of a first-order print** (NVDA 2023, MRNA 2026 rungs) can persist if later rungs confirm. That is a description of those episodes, not a base rate. Winner census is **blow_off-dominated ~5.5:1** (`FINGERPRINT_CENSUS_W3.md`) — persistence is the minority label.  
- **Late mechanical t0** after a vertical (GTLB 2022, TMDX 2022, HIMS 2024, NVDA 2000) is the common failed_breakaway shape.  
- **Conditional contracts + equity financing** (APLD, NBIS, LUNR, QUBT) often print I2 without I7.  
- **Gold 2026** is the load-bearing house lesson: a display-tier chain can read “failed” while the terminal asset has already incorporated the view.

---

## 4. Gaps

- No house event-study joining `data/revisions` to winner t0 yet.  
- I5 attention has no 2020–2025 PIT tape.  
- I4 cannot be used on 108 of 154 cases (pre-2026-06).  
- Peer response is usually a **sector ETF**, not a matched same-mechanism name (see peer casebook).
