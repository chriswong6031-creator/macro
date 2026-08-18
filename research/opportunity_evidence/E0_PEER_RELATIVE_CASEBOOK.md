# E0 Peer-Relative Casebook

**Unit of comparison:** same theme or same mechanism, **not** absolute attractiveness.  
**Outcome used:** the house `winner_case.v1` label plus the case’s own excess vs its stated benchmark or sibling episode. This session did **not** recompute a new matched-pair backtest.  
**PIT:** “knowable at decision time” is taken from the cited case’s catalyst ladder and bottom line. Present-day knowledge of who “won the decade” is marked **ex post** and is not a t0 input.

Parsed library this session: **154** cases (108 winner / 46 failed_breakaway). **CODE VERIFIED** YAML blocks under `research/winners/cases/`.

Archetype coverage:

| Required archetype | Rows below | Honest hole |
|---|---|---|
| Sector/factor washout, company evidence intact | PR-01, PR-02, PR-40, PR-41 | Residual attribution not re-run; washout is from case drawdown + intact filings |
| Company-impairment washout | PR-20, PR-21, PR-22 | — |
| High-attention crowded leader | PR-03, PR-08, PR-16, PR-28, PR-35 | Attention often inferred from case prose |
| Evidence-before-attention discovery | PR-04, PR-06, PR-23, PR-37 | Pre-2026 attention tape missing — “discovery” is case-narrative, tagged |
| Strong catalyst already reflected | PR-09, PR-10, PR-11, PR-24, PR-32 | — |
| Weak catalyst, strong price | PR-12, PR-13, PR-14, PR-17, PR-29 | — |
| Capital-supply overhang | PR-15, PR-18, PR-19, PR-25, PR-33 | Dilution is case-stated, not `dilution_events.parquet` joined |

---

## 1. Comparisons (42)

| ID | Theme / mechanism | A (candidate) | B (peer / sibling) | Decision date | Knowable then | Who subsequently dominated | PIT risk | Receipt |
|---|---|---|---|---|---|---|---|---|
| PR-01 | Uranium / nuclear fuel vs miner beta | CCJ 2025-05-09 | XME proxy; UEC 2023 cycle | 2025-05-09 | Q1: realized contract price up, spot −30%; 34.5% drawdown; Westinghouse already owned | CCJ vs SPY +23.80pp/21d. **Full-year CCJ lagged XME −4.93pp** — do not call 2025 “sector alpha.” vs UEC: different year; not a same-t0 pair | Low on CCJ tape; high if compared to 2023 UEC as if simultaneous | `CCJ_2025.md`; `UEC_2023.md` |
| PR-02 | Same May-2025 US nuclear policy | CCJ 2025-05-09 | LEU 2025-05-23 | 2025-05 | Four US nuclear EOs 2025-05-23 are **sector-wide** (CCJ case). LEU t0 **is** that policy date | Both labeled winner. **Relative winner UNKNOWN** — this session did not compute CCJ vs LEU excess after 2025-05-23 | Medium | `CCJ_2025.md`; `LEU_2025.md` |
| PR-03 | Advanced nuclear optionality | OKLO 2024-10-15 | NNE 2024-10-16 | 2024-10 | Policy/hyperscaler nuclear narrative public for both. NNE: **no 2024 revenue/licensing/ops**. OKLO: policy_beneficiary vs NLR | OKLO winner; NNE failed_breakaway | Low | `OKLO_2024.md`; `NNE_2024.md` |
| PR-04 | Obesity / GLP-1 pipeline | VKTX 2024-02-27 | VKTX 2023-04-03 (same name prior) | 2024-02-27 | 2023 early-data pop and fail were public | 2024 winner vs 2023 fail | Low | `VKTX_2024.md`; `VKTX_2023.md` |
| PR-05 | Single-asset biotech | SMMT 2024-05-30 | SMMT 2025-04-24 | 2025-04-24 | 2024 winner + HARMONi approaching; case: expectation-saturated **before** publication | 2024 winner dominated the *first* print; 2025 fail on non-OS | Low | `SMMT_2024.md`; `SMMT_2025.md` |
| PR-06 | mRNA / XBI | MRNA 2026-01-20..06-18 | XBI / XLV | 2026-06-18 | 5y melanoma data (Jan), VRBPAC 9-0 (Jun 18), Science Day (Jun 25). Consensus Hold / target << spot (external) | MRNA +49.16pp/21d vs XBI | Medium on target-price (external) | `MRNA_2026.md` |
| PR-07 | RNAi / XBI | ALNY 2024-06-24 | XBI | 2024-06-24 | Platform_rerating YAML | ALNY winner vs XBI (case) | Medium — this session did not re-read ALNY tape | `ALNY_2024.md` YAML |
| PR-08 | Telehealth / GLP-1 retail | HIMS 2025-02-13 | HIMS 2024-06-04; HIMS 2021-01-28 | 2025-02 | Prior SPAC crowd and 2024 late fail knowable; 2025: real growth + GLP-1 attention, price outran margin/regulatory proof | None of the three is a durable peer-relative winner across episodes; 2024/2025 failed; 2021 failed | Low | `HIMS_*.md` |
| PR-09 | Medical device too-early vs too-late | TMDX 2021-03-02 | TMDX 2022-08-25 | both | FDA de-risking public by 2021; 2022 commercialization already extended | **Neither** dominated — both failed_breakaway | Low | `TMDX_2021.md`; `TMDX_2022.md` |
| PR-10 | Pump / diabetes devices | TNDM 2024-05-03 | TNDM 2018-06-04 | 2024-05 | Mobi + beat; still-negative opex | 2018 winner vs 2024 fail — **different mechanisms**; not a same-t0 pair | Medium | `TNDM_*.md` |
| PR-11 | AI GPU vs interconnect same week | NVDA 2023-05-25 | CRDO 2023-05-25 | 2023-05-25 | NVDA $11B guide; CRDO AEC demand plausible | NVDA winner (+24pp/42d vs SMH); CRDO failed (pulled future demand too far) | Low | `NVDA_2023.md`; `CRDO_2023.md` |
| PR-12 | AI servers vs GPU leader | SMCI 2024-01-19 | NVDA 2023 (already re-rated) | 2024-01 | NVDA 2023 guide was 7 months old; AI server demand public | SMCI labeled winner vs XLK. Whether it *dominated NVDA in 2024* is **UNKNOWN here** (no pair tape) | High if used as “SMCI > NVDA” | `SMCI_2024.md`; `NVDA_2023.md` |
| PR-13 | AI custom silicon / XLK | AVGO 2025-05-30 | XLK; APH 2025-05-30 | 2025-05-30 | Both platform_rerating same t0 vs XLK | **Relative winner UNKNOWN** (same-day pair, no excess computed this session) | Medium | `AVGO_2025.md`; `APH_2025.md` |
| PR-14 | Foundry cycle | TSM 2025-06-24 | TSM 2000-02-03 | 2025-06 | 2000 fail is history; 2025 cycle vs SOXX | 2025 winner; 2000 fail | Low as sequence; not same-t0 | `TSM_2025.md`; `TSM_2000.md` |
| PR-15 | AI infra / lease + equity | APLD 2024-07-01 | VRT 2023-04-26 | 2024-07 | VRT already re-rated on power equipment; APLD: **unsigned** lease + conditional equity-linked financing | VRT winner; APLD fail | Low | `APLD_2024.md`; `VRT_2023.md` |
| PR-16 | GPU cloud / short history | NBIS 2025-01-24 | APLD 2024 | 2025-01 | Financing + capacity **plan**, thin ops, short listing | Both failed_breakaway — **neither dominated** | Low | `NBIS_2025.md`; `APLD_2024.md` |
| PR-17 | Power for AI / IPPs | VST 2024-09-20 | TLN 2024-03-27; NRG 2024-03-14 | 2024 | Merchant tightness / turnaround public | All three labeled winner. **Who dominated whom UNKNOWN** without pair excess | Medium | `VST_2024.md`; `TLN_2024.md`; `NRG_2024.md` |
| PR-18 | BTC miner 2020 identity | MARA 2020-11-20 | CLSK 2020-09-21 | 2020-Q4 | BTC cycle; CLSK capital raise + late identity change | MARA winner; CLSK fail | Low | `MARA_2020.md`; `CLSK_2020.md` |
| PR-19 | BTC miner after vertical | MARA 2021-03-31 | MARA 2020 | 2021-03 | 2020 winner already vertical; 2021 priced on future fleet | 2020 dominated 2021 (2021 fail) | Low | `MARA_2021.md` |
| PR-20 | BTC miner + AI pivot | IREN 2025-06-06 | IREN 2023-12-21 | 2025-06 | 2023 fail after vertical/equity-funded AI story knowable | 2025 winner vs 2023 fail | Low | `IREN_2025.md`; `IREN_2023.md` |
| PR-21 | BTC miner vs WGMI 2023 | HUT 2023-06-20 | IREN 2023-12-21 | 2023 | Miner-cycle beta + optionality | Both failed_breakaway | Low | `HUT_2023.md`; `IREN_2023.md` |
| PR-22 | BTC + data-center optionality | CIFR 2024-11-06 | IREN 2025 | 2024-11 | Election beta + DC optionality; weak mining economics + capital needs | CIFR fail; IREN 2025 later win is **ex post** to Nov-2024 | Medium | `CIFR_2024.md` |
| PR-23 | BTC treasury vs miner | MSTR 2020-11-10 | MARA 2020-11-20 | 2020-11 | Both BTC-cycle; different claim on cash flows | Both winners. Relative **UNKNOWN** | Medium | `MSTR_2020.md`; `MARA_2020.md` |
| PR-24 | Cyber / XLK | CRWD 2023-11-29 | GTLB 2022-08-05 | different years | GTLB: growth already in price, weak liquidity. CRWD: later platform rung | CRWD winner; GTLB fail — **not same-t0** | Medium | `CRWD_2023.md`; `GTLB_2022.md` |
| PR-25 | Edge / cloud software | NET 2020-10-09 | NET 2021-06-08 | 2021-06 | 2020 winner knowable; 2021 is a second episode (winner YAML) | Both winners — relative **UNKNOWN** | Medium | `NET_2020.md`; `NET_2021.md` |
| PR-26 | Adtech / social | APP 2024-11-07 | PINS 2024-05-06 | 2024 | PINS Q2 guide deceleration already a fail by May; APP Nov earnings rung | APP winner; PINS fail | Low | `APP_2024.md`; `PINS_2024.md` |
| PR-27 | Social IPO | RDDT 2024-10-14 | RDDT 2025-06-17 | 2025-06 | 2024 winner knowable | Both winners — relative **UNKNOWN** | Medium | `RDDT_*.md` |
| PR-28 | Fintech / high beta | HOOD 2025-06-03 | AFRM 2022-08-03 | different years | AFRM: GMV vs credit/funding impairment. HOOD: platform_rerating vs XLF | HOOD winner; AFRM fail — **not same-t0** | High if treated as a 2025 pair | `HOOD_2025.md`; `AFRM_2022.md` |
| PR-29 | AI voice / narrative | SOUN 2024-02-26 | NVDA ownership disclosure (case) | 2024-02 | Delayed NVDA stake disclosure + SI + narrative; losses intact | SOUN failed_breakaway — **peer NVDA is not a same-mechanism loser**; this is crowded-leader **on SOUN** | Low on SOUN fail | `SOUN_2024.md` |
| PR-30 | Space / NASA | ASTS 2024-05-15 | LUNR 2024-12-24 | 2024 | Flight/awards vs IDIQ ceilings + financing | ASTS winner; LUNR fail | Low | `ASTS_2024.md`; `LUNR_2024.md` |
| PR-31 | Space / defense optionality | RDW 2025-06-05 | ASTS 2024 | 2025-06 | Edge Autonomy + Golden Dome; cleared only local overhead before acquisition-risk | RDW fail vs ASTS prior winner — **ex post** to use ASTS as 2025 peer | Medium | `RDW_2025.md` |
| PR-32 | Quantum scarcity | QBTS 2025-03-17 | QUBT 2024-12-06 | 2024-12 / 2025-03 | Both: milestone + financing + thin revenue | **Both failed** — theme did not produce a house winner in this pair | Low | `QBTS_2025.md`; `QUBT_2024.md` |
| PR-33 | China commerce | PDD 2019-08-16 / 2020-11-03 | JD 2023-01-04; BIDU 2006-05-10 | various | PDD platform proof vs JD reopening cohort beta vs BIDU one-day monetization pop | PDD winners; JD fail; BIDU fail | Medium (years differ) | `PDD_*.md`; `JD_2023.md`; `BIDU_2006.md` |
| PR-34 | China education | EDU 2023-10-25 | EDU 2017-04-24 / 2019-01-22 | 2023-10 | Crackdown + turnaround vs earlier platform rerates | 2023 turnaround winner; 2017/2019 also winners — **mechanism change**, not one champion | Medium | `EDU_*.md` |
| PR-35 | China EV | XPEV 2024-09-19 | NIO 2020-06-01 | different years | Different cycle points | Both winners in their files — relative **UNKNOWN** | High | `XPEV_2024.md`; `NIO_2020.md` |
| PR-36 | Solar policy vs hardware | FSLR 2022-07-28 | SEDG 2016-02-04; TAN 2020-08-04 | various | FSLR policy_beneficiary vs TAN; SEDG customer-concentration fail | FSLR 2022 winner; SEDG fail | Medium (years) | `FSLR_2022.md`; `SEDG_2016.md`; `TAN_2020.md` |
| PR-37 | Rare earths policy | MP 2025-06-12 | MP 2020-11-18 | 2025-06 | 2020 policy winner knowable; 2025 another policy rung vs XLB | Both winners | Medium | `MP_*.md` |
| PR-38 | Aluminum cycle vs policy | CENX 2010-09-24 | CENX 2024-04-19 | 2024-04 | 2024: conditional federal support + commodity scarcity **before** recurring ops | 2010 cycle winner; 2024 policy fail | Low | `CENX_*.md` |
| PR-39 | Gold / real-rate 2026 | NEM (US Prophet 2026-07-22) + CN miners | Engine peak-chain “FAILED” 08-05/08-07 | 2026-07-22..08-09 | Prophet CN buys from 07-08; NEM admit 07-22 entry 94.72; SI Gold Miners Buy Now. DFII10 high 07-31 **after** first buys | **Tape dominated the instrument:** gold +5.8%/22d; NEM +15% on 08-09; miners +20% unlevered by operator receipt. Chain windows failed | Low | `CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md` |
| PR-40 | Gold 2016 | GDX 2016-02-04 | GDXJ | 2016-02 | Cycle_upswing YAML | GDX winner vs GDXJ (case benchmark) | Medium — file not fully re-read | `GDX_2016.md` |
| PR-41 | Fertilizer / XLB | CF 2021-09-23 | CF 2020-11-23 | 2021-09 | 2020 cycle winner knowable | Both cycle_upswing winners | Medium | `CF_*.md` |
| PR-42 | Genomics / XLV | ILMN 2025-06-20 | ILMN 2014-01-16 / 2007-06-14 | 2025-06 | Long platform history; 2025 is **turnaround** | 2007/2014 winners + 2025 turnaround winner — not one domination | Medium | `ILMN_*.md` |

**Count:** 42 numbered comparisons. 40+ required. Several rows honestly say **relative winner UNKNOWN** where both are winners or years differ. That is the correct state, not a silent pick.

---

## 2. How to read these later (no weights)

A later Opportunity Evidence Vector, if assembled, should store **per pair**:

- `theme_id` / `mechanism`  
- `t0`  
- `knowable_set` (dated citations)  
- `unknowable_set` (options pre-2026-06, 13F inside 45d, licensed consensus)  
- `outcome_source` = `winner_case.v1` + benchmark, not a new utility  

It should **not** store a pair score.

---

## 3. Survivorship / panel integrity

- Library is **winner-autopsy selected**, then filled with failed_breakaways (~30%). It is not a random same-theme panel.  
- Blow_off:kept_going ≈ 5.5:1 on the **mechanical census**, not on this 42-row judgment sample (`FINGERPRINT_CENSUS_W3.md`).  
- Many “peers” are sector ETFs, not matched names. DRL peer_basis is market 47% of the time — same-theme ≠ same-residual.  
- Canadian/FPI names (CCJ) miss US EDGAR fundamentals — do not treat missing filings as missing operations.

---

## 4. No-build warnings

- Do not promote “NVDA beat CRDO in May 2023” into a rule that GPU > interconnect. n=1 week.  
- Do not use 2026 knowledge of NVDA’s later cap to score 2023 SMH peers.  
- Do not fill UNKNOWN relative winners with narrative.
