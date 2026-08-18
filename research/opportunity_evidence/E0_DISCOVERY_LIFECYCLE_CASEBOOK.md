# E0 Discovery / Attention Lifecycle Casebook

**Stages (commissioned vocabulary):**  
NEGLECTED → EVIDENCE_ACCUMULATING → CATALYST_IGNITION → INSTITUTIONALIZING → CROWD_SATURATION → DISTRIBUTION → UNRESOLVED

**This is a labeling language, not a Markov model and not a score.** A name may skip stages or occupy two at once (Radar P-5 analog: multiple lanes). If attention data are missing, the stage is **UNRESOLVED**, not NEGLECTED.

**PIT:** stage at `t0` may use only evidence dated ≤ t0. Later stage is labeled `ex_post`.

---

## 1. Stage definitions (observable tests)

| Stage | Observable test (any one sufficient; missing data → do not assign) | Must not infer from |
|---|---|---|
| NEGLECTED | Low coverage (`n_covering` small or null **and** no theme leadership **and** no 13F breadth) **known at t** | Price being down |
| EVIDENCE_ACCUMULATING | ≥1 material public rung (filing, print, trial, contract) **without** a relative-breakaway label yet | Analyst notes after the move |
| CATALYST_IGNITION | Winner-case t0 / DRL shock / first 63d high **on a dated public rung** | A random gap |
| INSTITUTIONALIZING | Repeated institutional-capacity $volume (case language) **or** 13F mapped-holder increase **after** +45d (ex post only) | Same-day 13F fantasy |
| CROWD_SATURATION | Vertical extension + research targets ≤ spot + high attention/IV (when those series exist) | “It went up a lot” alone |
| DISTRIBUTION | failed_breakaway **or** mechanical blow_off after saturation evidence | Any pullback |
| UNRESOLVED | Conflicting legs, missing attention/options/revisions, or instrument vs tape disagreement | — |

House attention history is thin. **Most pre-2026 cases cannot support NEGLECTED vs EVIDENCE_ACCUMULATING as a data claim** — only as a narrative in the winner file. Those rows are tagged `INFERRED from case prose` or `UNRESOLVED`.

---

## 2. Lifecycle rows

| ID | Name | t0 | Theme | Stage at t0 | Later stage (ex post) | What was knowable at t0 | PIT risk | Receipt |
|---|---|---|---|---|---|---|---|---|
| LC-01 | NVDA 2023 | 2023-05-25 | AI GPU | CATALYST_IGNITION (guide) | INSTITUTIONALIZING then CROWD_SATURATION (2023–24, **ex post**) | Q1 + Q2 guide | Low on ignition; high if we back-label “neglected” — NVDA was already a leader | `NVDA_2023.md` |
| LC-02 | SMCI 2024 | 2024-01-19 | AI servers | CATALYST_IGNITION / crowding **INFERRED** | DISTRIBUTION later is **UNKNOWN in this case file** (type=winner; no fail file) | AI-server demand already public via NVDA 2023 | Medium — winner file does not prove neglected | `SMCI_2024.md` |
| LC-03 | CRDO 2023 | 2023-05-25 | AI interconnect | CATALYST_IGNITION same **week** as NVDA | DISTRIBUTION (failed_breakaway: price pulled future AEC too far) | Plausible AEC demand | Low | `CRDO_2023.md` |
| LC-04 | MRNA 2026 | 2026-01-20 | mRNA | EVIDENCE_ACCUMULATING (5y data) | CATALYST_IGNITION 2026-06-18 VRBPAC; research still below spot in July | COVID decay + Hold consensus (external) | Medium on “neglected” (still a mega-cap biotech) | `MRNA_2026.md` |
| LC-05 | VKTX 2023 | 2023-04-03 | Obesity | CATALYST_IGNITION | DISTRIBUTION (failed) | Early VK2735 data | Low | `VKTX_2023.md` |
| LC-06 | VKTX 2024 | 2024-02-27 | Obesity | EVIDENCE_ACCUMULATING → IGNITION | Winner (later confirmatory path) | 2023 fail was knowable | Low | `VKTX_2024.md` |
| LC-07 | SMMT 2024 | 2024-05-30 | Biotech single-asset | IGNITION | Winner | Clinical rung | Low | `SMMT_2024.md` |
| LC-08 | SMMT 2025 | 2025-04-24 | Same name | CROWD_SATURATION | DISTRIBUTION | Prior winner + pre-event expectation | Low | `SMMT_2025.md` |
| LC-09 | HIMS 2021 | 2021-01-28 | Telehealth SPAC | CROWD_SATURATION (ARK/SPAC) | DISTRIBUTION | Research vacuum + recent SPAC | Medium (attention inferred from case) | `HIMS_2021.md` |
| LC-10 | HIMS 2024 | 2024-06-04 | GLP-1 adjacency | Late IGNITION | DISTRIBUTION (63d hold fail) | GLP-1 shock already public | Low | `HIMS_2024.md` |
| LC-11 | HIMS 2025 | 2025-02-13 | GLP-1 platform | IGNITION / SATURATION mix | DISTRIBUTION (temp) | Real growth + attention | Medium | `HIMS_2025.md` |
| LC-12 | CCJ 2025 | 2025-05-09 | Uranium | EVIDENCE_ACCUMULATING (Q1 book) after washout | IGNITION t0; INSTITUTIONALIZING Jun/Oct **ex post** | Contract book vs spot | Low | `CCJ_2025.md` |
| LC-13 | OKLO 2024 | 2024-10-15 | Advanced nuclear | IGNITION (policy/theme) | UNRESOLVED / winner label | Policy + NLR theme | Medium | `OKLO_2024.md` |
| LC-14 | NNE 2024 | 2024-10-16 | Nuclear optionality | CROWD_SATURATION without revenue | DISTRIBUTION | No 2024 revenue | Low | `NNE_2024.md` |
| LC-15 | LEU 2025 | 2025-05-23 | Enrichment policy | IGNITION (policy) | Winner | Same May 2025 US nuclear orders as CCJ | Low | `LEU_2025.md` |
| LC-16 | UEC 2023 | 2023-09-11 | Uranium miner | Cycle IGNITION | Winner vs URA | Miner cycle | Medium neglected? **UNRESOLVED** | `UEC_2023.md` |
| LC-17 | IREN 2023 | 2023-12-21 | BTC miner / AI pivot | SATURATION (already vertical) | DISTRIBUTION | Capacity+AI story after the move | Low | `IREN_2023.md` |
| LC-18 | IREN 2025 | 2025-06-06 | Same name | IGNITION on later rung | Winner | 2023 fail was knowable | Low | `IREN_2025.md` |
| LC-19 | MARA 2020 | 2020-11-20 | BTC miner | IGNITION (cycle) | Winner | BTC cycle | Medium | `MARA_2020.md` |
| LC-20 | MARA 2021 | 2021-03-31 | BTC proxy | SATURATION | DISTRIBUTION | After vertical, priced on future fleet | Low | `MARA_2021.md` |
| LC-21 | MARA 2022 | 2022-07-08 | BTC proxy | Repair IGNITION | DISTRIBUTION | Compression + restored hosting | Low | `MARA_2022.md` |
| LC-22 | CLSK 2020 | 2020-09-21 | Microgrid → BTC | IGNITION then identity change | DISTRIBUTION (capital raise) | Low-base growth | Low | `CLSK_2020.md` |
| LC-23 | CIFR 2024 | 2024-11-06 | BTC + DC optionality | Election IGNITION | DISTRIBUTION | Weak mining economics + capital needs | Low | `CIFR_2024.md` |
| LC-24 | MSTR 2020 | 2020-11-10 | BTC balance-sheet | IGNITION | Winner | Policy/treasury strategy public | Medium | `MSTR_2020.md` |
| LC-25 | APLD 2024 | 2024-07-01 | AI infra / HPC | SATURATION on unsigned lease | DISTRIBUTION | Financing conditional | Low | `APLD_2024.md` |
| LC-26 | VRT 2023 | 2023-04-26 | Power for compute | EVIDENCE → IGNITION | Winner / later crowd **UNKNOWN** | Data-center power demand emerging | Medium | `VRT_2023.md` |
| LC-27 | VST 2024 | 2024-09-20 | Merchant power | Cycle IGNITION | Winner | Power tightness | Medium | `VST_2024.md` |
| LC-28 | TLN 2024 | 2024-03-27 | Independent power | IGNITION | Winner | Same complex as VST/NRG | Medium | `TLN_2024.md` |
| LC-29 | NRG 2024 | 2024-03-14 | Power turnaround | IGNITION | Winner | Contrast NRG 2017 | Low | `NRG_2024.md` |
| LC-30 | PLTR 2024 | 2024-02-06 | Software / AI | IGNITION | Winner | Already famous — **not NEGLECTED** | Low | `PLTR_2024.md` |
| LC-31 | APP 2024 | 2024-11-07 | Adtech | IGNITION | Winner | Peer PINS already failing | Medium | `APP_2024.md` |
| LC-32 | RDDT 2024 | 2024-10-14 | Social IPO | IGNITION | Winner | Post-IPO | Medium | `RDDT_2024.md` |
| LC-33 | ASTS 2024 | 2024-05-15 | Space / sat | IGNITION | Winner | Theme UFO/space | Medium | `ASTS_2024.md` |
| LC-34 | LUNR 2024 | 2024-12-24 | Space | IGNITION on flight/NASA | DISTRIBUTION (IDIQ + financing runway) | Awards real, ceilings not revenue | Low | `LUNR_2024.md` |
| LC-35 | QBTS 2025 | 2025-03-17 | Quantum | IGNITION on milestone | DISTRIBUTION | Scientific + first sale + equity raise | Low | `QBTS_2025.md` |
| LC-36 | QUBT 2024 | 2024-12-06 | Quantum | SATURATION | DISTRIBUTION | Theme scarcity | Low | `QUBT_2024.md` |
| LC-37 | PDD 2019 | 2019-08-16 | China commerce | EVIDENCE → IGNITION | Winner vs KWEB | Platform proof | Medium | `PDD_2019.md` |
| LC-38 | JD 2023 | 2023-01-04 | China reopening | Cohort IGNITION | DISTRIBUTION | Reopening + regulatory-risk re-rate, weak RS | Low | `JD_2023.md` |
| LC-39 | EDU 2023 | 2023-10-25 | China education | Turnaround IGNITION | Winner | Contrast EDU 2017/2019 | Low | `EDU_2023.md` |
| LC-40 | FSLR 2022 | 2022-07-28 | Solar policy | Policy IGNITION | Winner vs TAN | IRA / policy | Medium | `FSLR_2022.md` |
| LC-41 | SEDG 2016 | 2016-02-04 | Solar hardware | SATURATION | DISTRIBUTION | 57% pre-t0 + customer concentration | Low | `SEDG_2016.md` |
| LC-42 | MP 2025 | 2025-06-12 | Rare earths policy | Policy IGNITION | Winner | Contrast MP 2020 | Medium | `MP_2025.md` |
| LC-43 | Gold miners 2026-07 | 2026-07-22 NEM Prophet admit | Real-rate / gold | EVIDENCE_ACCUMULATING (CN Prophet + SI Buy Now) | Tape INSTITUTIONALIZING while **chain UNRESOLVED/failed** | DFII10 extreme 07-31 is **after** first miner buys | Low on dual-read | Gold case study |
| LC-44 | SOUN 2024 | 2024-02-26 | AI voice | CROWD_SATURATION | DISTRIBUTION | Disclosure + SI + narrative | Low | `SOUN_2024.md` |
| LC-45 | GTLB 2022 | 2022-08-05 | DevTools | SATURATION | DISTRIBUTION | Growth already known | Low | `GTLB_2022.md` |
| LC-46 | NET 2020 | 2020-10-09 | Edge/cloud | IGNITION | Winner | Contrast NET 2021 later | Medium | `NET_2020.md` |
| LC-47 | BA 2025 | 2025-04-23 | Aero turnaround | EVIDENCE_ACCUMULATING / IGNITION | Winner | Operational repair public | Medium | `BA_2025.md` |
| LC-48 | CVNA 2023 | 2023-07-19 | Consumer turnaround | IGNITION from deep discount | Winner | Credit/survival narrative | Medium | `CVNA_2023.md` |

---

## 3. Same-name sequences (lifecycle, not a trading rule)

These are the cleanest house examples of stage travel **with a second dated episode**:

| Name | Episode 1 | Episode 2 | Read |
|---|---|---|---|
| VKTX | 2023 fail (ignition without confirm) | 2024 winner | Evidence can re-ignite after a rejected first print |
| SMMT | 2024 winner | 2025 fail | Winner → saturation → distribution on the next binary |
| HIMS | 2021 SPAC crowd → 2024 late fail → 2025 growth/attention fail | Crowd can re-form on a new mechanism (GLP-1) without becoming “neglected” |
| IREN | 2023 fail after vertical | 2025 winner | Same theme, later rung |
| MARA | 2020 win → 2021/2022 fails → 2023 win | Cycle names recycle; stage is not identity |
| TMDX | 2021 fail (too early) → 2022 fail (too late) | Both sides of incorporation miss |
| NRG | 2017 turnaround win → 2024 turnaround win | Recurring mechanism |
| MP | 2020 policy win → 2025 policy win | Policy beneficiary, not discovery |
| EDU | 2017/2019 platform → 2023 turnaround | Mechanism change after China education crackdown |
| CCJ | 2009 cycle → 2025 platform/policy | Mechanism change (miner → fuel+Westinghouse) |

---

## 4. What the house cannot yet stage

- **NEGLECTED as a data state** before 2026-06 revisions + Quiver attention join. Do not label 2016–2022 names NEGLECTED from price alone.  
- **INSTITUTIONALIZING via 13F** at t0 (45d lag). Winner cases already treat 13F as context-only.  
- **Hot Tape 5-min attention** historically (no `data/` artifact).  
- Radar live lifecycle (`ARMED`/`TURNING`/`CANDIDATE`) is a **different object** (`WAITING_FOR_LIVE_SOURCE` as of 2026-08-18). Do not mix Radar cycle words with this discovery vocabulary.

---

## 5. No-build warnings

- Do not assign a numeric “lifecycle score.”  
- Do not treat UNRESOLVED as middle-of-the-road.  
- Do not use present-day fame (NVDA, PLTR) to rewrite  t0 neglect.
