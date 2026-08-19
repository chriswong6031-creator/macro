# D0 — Propagation casebook

**Authority:** research hypotheses. No scores. No “validated.” No Prophet member.  
**Honesty rule (copied from Defense D0R Gate 5):** this close does **not** invent 40 pinned primaries. Rows are `IN_REPO_EVIDENCED` or `RESEARCH_CANDIDATE`. PIT prices are not rebuilt here.  
**SHA:** `3d12412e561ef77c0a9618c9d9b18871d7344209`.  
**Sparse:** winner-case tapes that cite `data/massive_stock_day/` were not re-read from parquet this session; the claim is the markdown already in-repo.

### Status meanings

| Status | Meaning |
|---|---|
| **IN_REPO_EVIDENCED** | This tree already pins dates, names, and a hop or a statistical family, with a file path. Not a new primary opened this session. |
| **RESEARCH_CANDIDATE** | Architecture-useful. Qualitative or cited-from-D0R. Not a pinned primary this close. |
| **DO_NOT_USE** | Mentioned in-repo but is not a transfer episode (see §C). |

### Outcome classes (commission)

`success_fundamental` · `delayed_market` · `immediate_incorporation` · `no_transfer` · `false_common_factor` · `company_offset`

A row may carry two classes (e.g. instrument delayed + tape success).

### Family codes

`ME` mega-cap earnings → smaller name · `DEF` defense demand → contractors · `COM` commodity → producers/equipment · `AI` AI capex → networking/power/cooling/memory · `CLIN` clinical/regulatory → peers · `MACRO` driver → terminal asset (TXI-shaped) · `STAT` pre-registered family, not a single story

Defense already has 67 rows in `research/defense_intelligence/D0R_HISTORICAL_EVENT_CASEBOOK.md` (6 `VERIFIED_CASE`, 61 `RESEARCH_CANDIDATE`). This book **cites** that file. It does not re-verify it.

---

## A. Named episodes in this repository (24)

| ID | Family | Episode | Hop claimed in-repo | Outcome | Status | Source |
|---|---|---|---|---|---|---|
| P01 | MACRO | 2026-07-31 DFII10 2.47 → 08-05–09 gold +5.8%/22d, NEM +15% | real-rate extreme → bullion/miners; peak-chain **FAILED** (63d +49bp) while terminal passed | `delayed_market` (instrument) + `success_fundamental` (operator tape) | IN_REPO_EVIDENCED | `research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md` |
| P02 | MACRO | Five DFII10 peaks 2008–2025 | naive 63d falsifier stays red 7–36 sessions after a true peak | `delayed_market` (instrument) | IN_REPO_EVIDENCED | same file §3 |
| P03 | AI | June-2024 13D HBM/DRAM sold-out ~2y; SK Hynix/Samsung/Micron | supply constraint → later HBM/DRAM rerating; desk claims ~9 months early | `delayed_market` | IN_REPO_EVIDENCED (quotes); tape path not reconstructed here | `research/THEMATIC_FORESIGHT_DESK.md` |
| P04 | AI / ME | NVDA FY24 Q1 AI guide 2023-05-24 → VRT 2023-05-25 $544m z21 gap +12.68% held; own raises 04-26 and 08-02 | mega-cap guide → cooling/power supplier, then own fundamentals confirm | `immediate_incorporation` then `success_fundamental` | IN_REPO_EVIDENCED | `research/winners/cases/VRT_2023.md` (NVDA PR + Vertiv IR URLs pinned) |
| P05 | AI / ME | NVDA 2023-05-24 → CRDO 05-31 print (rev −40.9% seq); t0 06-12 after the peak | interconnect “AI recovery” pulled forward; lagged SOXX; −16%/42d | `no_transfer` / `company_offset` | IN_REPO_EVIDENCED | `research/winners/cases/CRDO_2023.md` |
| P06 | AI | CEG–MSFT 20y TMI-1 PPA 2024-09-20 → VST +16.33% same window | peer contract as public price of scarce 24/7 nuclear (VST is **not** the contracting party) | `immediate_incorporation` | IN_REPO_EVIDENCED | `research/winners/cases/VST_2024.md` |
| P07 | AI | 2024-03-04 AWS / Cumulus → TLN | hyperscaler customer → nuclear IPP | `success_fundamental` | IN_REPO_EVIDENCED | `research/winners/cases/TLN_2024.md` |
| P08 | AI | NRG 2024 cash-return rerating, then data-center load as second leg | AI electricity is the **second** mechanism, not the first | `success_fundamental` (year) / not 126d durable | IN_REPO_EVIDENCED | `research/winners/cases/NRG_2024.md` |
| P09 | ME / AI | 2026-07-22 AH GOOGL beat + FY26 capex $180–190B → $195–205B, **−4% AH**; AMZN/META/MSFT down; hardware not up | spender-pool capex bind; Cooper–Gulen–Schill cited (spender capex → negative spender returns) | `company_offset` (spenders) + `no_transfer` (hardware relief) | IN_REPO_EVIDENCED | `research/POSTMORTEM_20260722_CROSSOVERS_VS_CAPEX_BIND_BY_FABLE.md` |
| P10 | ME / AI | TSMC 2026-07 record profit + capex raise; semis kept falling; 07-16 AMD/INTC −4–6%, NBIS −14% | excellent foundry news, no positive price response | `no_transfer` | IN_REPO_EVIDENCED | `research/MAG7_Q2_2026_EARNINGS_CAPEX_DILEMMA_AND_TAPE_SCENARIOS.md`; `POSTMORTEM_20260716_DEFENSIVE_ROTATION_MISS_BY_FABLE.md` |
| P11 | AI | 2026-06-25 Hynix/MU top → 07-01/02 MU/SNDK −10%+ → Hynix/Samsung/KOSPI → 07-13 HBM4 note + KOSPI breaker → 07-16 TSMC guide; US 07-16 **narrow** (only Tech/Comms down; 358/503 SPX green) | Korea memory → tech hop is real; “index crash” is not | `success_fundamental` as dated hop; `false_common_factor` if used as SPX crash | IN_REPO_EVIDENCED | CSP masterplan §0–1; `POSTMORTEM_20260716` |
| P12 | COM | GDX 2016-02-04 breakaway; trough-to-peak +151%; −33% peak-to-YE | gold + operating leverage, then USD/yields/election reverse | `success_fundamental` then reversal | IN_REPO_EVIDENCED | `research/winners/cases/GDX_2016.md` |
| P13 | COM | FCX t0 2020-11-24; copper ~7y high + Grasberg | commodity deck + company torque; +62pp vs XLB / 126d | `success_fundamental` | IN_REPO_EVIDENCED | `research/winners/cases/FCX_2020.md` |
| P14 | COM | SQM t0 2020-11-09; earnings still trough | next-cycle lithium capitalized forward | `delayed_market` / `success_fundamental` (hold, not durable_winner) | IN_REPO_EVIDENCED | `research/winners/cases/SQM_2020.md` |
| P15 | COM | USDA 2020-09-30 corn stocks −10% YoY → CF t0 2020-11-23 | crop/nitrogen while Q3 still weak | `delayed_market` | IN_REPO_EVIDENCED | `research/winners/cases/CF_2020.md` |
| P16 | COM | Scotiabank 2009-05-20 U3O8 $41.63→$51 → CCJ | sector-wide uranium repricing, not CCJ-exclusive | `success_fundamental` mixed with sector beta | IN_REPO_EVIDENCED | `research/winners/cases/CCJ_2009.md` |
| P17 | COM | CCJ 2025-05-09 onset; later ≥$80B Westinghouse framework | policy/reactor demand → scarce public vehicle; FY CCJ +75.7% **trailed** XME +80.7% | `success_fundamental` vs SPY; `no_transfer` as sector alpha | IN_REPO_EVIDENCED | `research/winners/cases/CCJ_2025.md` |
| P18 | AI / COM | MU FY Q4 2017-09-26; GM 25.5%→50.7%; XLK-relative alpha failed by 2018-09 | memory-cycle leverage then duration reversal | `success_fundamental` then `company_offset` | IN_REPO_EVIDENCED | `research/winners/cases/MU_2017.md` |
| P19 | AI | 2025-03-18 NVIDIA silicon-photonics partner; LITE 06-03 guide raise | AI optics bottleneck + named customer ecosystem | `success_fundamental` | IN_REPO_EVIDENCED | `research/winners/cases/LITE_2025.md` |
| P20 | AI | FN 2025-06-20; Rosenblatt 06-12 800G/1.6T/Blackwell production bridge | scarce optical CM | `success_fundamental` | IN_REPO_EVIDENCED | `research/winners/cases/FN_2025.md` |
| P21 | AI | APH 2025 own prints 41% organic | AI/datacom converting in **issuer** results (no named mega-cap print day) | `success_fundamental` at 126d; 252d excess later −6.27pp | IN_REPO_EVIDENCED | `research/winners/cases/APH_2025.md` |
| P22 | AI | APLD Together AI / Blackwell / 400MW LOI; lease unsigned; 2024-07-09 $125m ATM | narrative outran contracts; −25%/21d, −41%/42d | `no_transfer` / failed breakaway | IN_REPO_EVIDENCED | `research/winners/cases/APLD_2024.md` |
| P23 | CLIN | Akeso HARMONi-2 2024-05-30 → SMMT more than tripled; WCLC 09-08 | clinical event → **US licensee**, not a peer basket | `immediate_incorporation` + `success_fundamental` | IN_REPO_EVIDENCED | `research/winners/cases/SMMT_2024.md` |
| P24 | COM | US Silica FY17 capex 26–28% of sales; customers left Northern White; impairments $266m then $364m | commodity/customer-shift → supplier glut | `company_offset` | IN_REPO_EVIDENCED | `research/FALSIFIER_FIELD_BOOK_FOR_FABLE.md` CY-TB-2 (8-K accessions) |

---

## B. Pre-registered statistical families (13)

These are episode-honest or lead-lag **families**, not one-off stories. They exist so the book is not only famous winners.

| ID | Family | What was tested | Outcome | Status | Source |
|---|---|---|---|---|---|
| S01 | COM | oil `CL_F` bull flip → `XEG.TO` +1.87%/4w, n=32 non-overlap | `delayed_market` (absent at 2w; builds 4–8w) | IN_REPO_EVIDENCED | `reports/c1-commodity-sector-phase0.md` |
| S02 | COM | gold → `XGD.TO` −0.04%, sign-flip | `no_transfer` | IN_REPO_EVIDENCED | same |
| S03 | COM | copper → `XBM.TO` −0.65%; `XMA.TO` −0.20% | `no_transfer` | IN_REPO_EVIDENCED | same |
| S04 | COM | oil bear flip → XEG −1.16%/4w | `delayed_market` (symmetric de-rate) | IN_REPO_EVIDENCED | `reports/c1b-commodity-flip-protective-phase0.md` |
| S05 | COM | gold bear flip → XGD **+1.85%** | `false_common_factor` / `no_transfer` | IN_REPO_EVIDENCED | C1 exploratory |
| S06 | AI | SMH+SOXX+TSM 4w mom → next-week `ths_cpo` t 3.27 / pre-2024 3.03 | `success_fundamental` (stat lead) | IN_REPO_EVIDENCED | `reports/china-global-theme.md` |
| S07 | AI | same → `ths_pcb` weaker | mixed | IN_REPO_EVIDENCED | same |
| S08 | AI | storage / adv_pkg / liquid_cool leads mostly **2024+ only** | possible `false_common_factor` in the AI era | IN_REPO_EVIDENCED | same |
| S09 | CLIN | XLV 4w mom → Shenwan pharma 801150 t −0.48 (semis→CPO control live) | `no_transfer` | IN_REPO_EVIDENCED | `reports/c-hc-readthrough-phase0.md` |
| S10 | AI | TSM–ASML–SMH lag-0 HAC t +15.9 corr +0.82; lag-1 t −1.67; kill=True | `false_common_factor` (co-membership, not a lead) | IN_REPO_EVIDENCED | `reports/intl-semi-readthrough-phase0.md` |
| S11 | ME | LVMUY/luxury → FXI contemporaneous only; lag-1 wrong-signed | `no_transfer` (lead) | IN_REPO_EVIDENCED | `reports/intl-luxury-readthrough-phase0.md` |
| S12 | ME | CN ≥2 deep-discount blocks → non-blocked peers vs CSI300 | `no_transfer` | IN_REPO_EVIDENCED | `reports/f501-block-sector-readthrough-phase0.md` |
| S13 | ME | GR first-night sympathy: regional_banks **1.23×** (n=102); mag7 **0.93×** | mixed (banks yes / mag7 no) | IN_REPO_EVIDENCED | `research/GROUP_READS_SESSION2_HANDOFF_2026-08-09.md` |

Conflict to preserve: **S02 gold→XGD is NO-GO** while P01/P12 are real gold episodes. Different constructions (C1 slope_z 4w excess vs a confluence cycle). Do not reconcile them into “gold transmits.”

---

## C. Defense citations (not re-verified here)

Pulled as `RESEARCH_CANDIDATE` from D0R so the book covers `DEF`. Full table stays in the Defense file. Verified set there is E40–E42, E65–E67 only.

| ID | D0R | Episode | Outcome (D0R qualitative) | Status |
|---|---|---|---|---|
| D01 | E13 | 2022-02-24 Ukraine → RHM/SAAB/LDO/LMT/RTX short AR | `immediate_incorporation`; papers are short-window ARs, current-vintage prices | RESEARCH_CANDIDATE |
| D02 | E14 | 2022-03 Javelin/Stinger/HIMARS drawdown → replenishment | `delayed_market` (capacity lag) | RESEARCH_CANDIDATE |
| D03 | E48 | 2023 L3Harris–Aerojet SRM bottleneck ownership | `success_fundamental` (bottleneck via deal) | RESEARCH_CANDIDATE |
| D04 | E61 | 2023 155mm / SRM capacity projects | `delayed_market` / tightening | RESEARCH_CANDIDATE |
| D05 | E21 | 2023-06-23 Wagner coup → EU defense next-session − | de-escalation reverse; `false_common_factor` if “war = bid” | RESEARCH_CANDIDATE |
| D06 | E41 | 2026-05-12 IRDM P00032 $18.4M FUNDING ONLY | **non-material**; relationship exists, no transfer | D0R VERIFIED_CASE (cite, do not restamp) |

Same-issuer rows **not counted** as contractor-graph hops: BA F-47 (`research/winners/cases/BA_2025.md`), ATI Airbus/Boeing (`ATI_2025.md`). Promote only if a later charter allows intra-name customer conversion.

---

## D. Coverage vs the commission’s five families

| Family | In-repo named | Families | Defense cites | Honest hole |
|---|---:|---:|---:|---|
| mega-cap earnings → smaller name | P04, P05, P09, P10 | S11–S13 | — | almost no **peer-adjusted residual** study except VRT/CRDO around one NVDA print |
| defense demand → contractors | 0 in winners-as-hops | — | D01–D06 | D0R is the book; do not invent 60 primaries |
| commodity → producers/equipment | P12–P17, P24 | S01–S05 | — | equipment hop is thin (Silica is the glut counterexample) |
| AI capex → net/power/cooling/memory | P03–P11, P18–P22 | S06–S08, S10 | — | strongest family in this tree |
| clinical/regulatory → **peers** | P23 is **licensee**, not peers | S09 is **no-transfer** | — | **empty peer basket**. ALNY/VKTX/HIMS are own-name (DO_NOT_USE) |

**Count:** 24 named + 13 families + 6 defense cites = **43 rows**.  
**IN_REPO_EVIDENCED:** 37. **RESEARCH_CANDIDATE / cite-only:** 6.  
**New primaries opened this session:** 0.

---

## E. DO_NOT_USE (do not pad the 40 with these)

| File | Why it is not a transfer case |
|---|---|
| `research/AVGO_NVDA_ALIGNMENT.md` | scoring/PEG/13F bug, not a hop |
| `research/winners/cases/AVGO_2025.md` | own-name AI/custom-silicon |
| `research/winners/cases/SMCI_2024.md` | own guide + index inclusion |
| `research/winners/cases/EME_2024.md` | repo says not explained by a data-center headline alone |
| `research/winners/cases/ALNY_2024.md` / `VKTX_2023.md` / `HIMS_2024.md` | own clinical/launch, no peer tape |
| `research/winners/cases/LDOS_2019.md` / `AXON_2024.md` | own execution |
| `research/winners/cases/JD_2023.md` | Ant sector read-through; JD lagged KWEB |
| `research/winners/cases/SG_2023.md` | IPO sympathy; failed |
| `research/POSTMORTEM_20260714_ROTATION_MISS_BY_FABLE.md` | same-day XLV dump; no clinical mechanism |
| Theme-graph 商品联动 chain examples | display idiom, not an episode |
| `linked_outsiders` 1,902 edges | n_confirming 0/49; no CS labels |

---

## F. What a later PIT rebuild must do before any promotion

1. Rebuild RESEARCH_CANDIDATE and winner-case tapes with as-of prices, not current-vintage.
2. Report **episode N**, not fire-dates (adjudication coverage gate).
3. Name the missing panel (survivorship / delistings) before any cohort mean.
4. Run the rule on the motivating live exemplars **and** the current regime.
5. Keep S02/S03/S09/S10/S12 as first-class negatives so the book cannot be sampled as “transfers work.”
