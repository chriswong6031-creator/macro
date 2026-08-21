# G0 Post-Event Casebook

**N:** 8 estate-native rows + 60 historical rows = **68**.  
**Historical library:** `research/winners/cases/*.md` (`winner_case.v1`, 154 YAML blocks parsed this session). G0 **does not own** that corpus; it maps earnings-relevant rows onto G0 archetypes.

**PIT law:** CEI `event_workspace` does not join reaction. Frontier columns below are `UNKNOWN` in CEI unless tagged otherwise. Winner-case tape is CODE VERIFIED **in that file**. Options before 2026-06 are **unavailable**, not zero. Analyst-target history is not in-repo.

**Archetype column** is a **candidate label** (INFERRED from `case_type` + mechanism + earnings/gap/guidance hints). It is not a legal beat/miss and not a CEI verdict.

Frontier codes: `U` unknown in CEI · `P` present in named artifact · `A` typed absence / unlicensed · `X` unavailable (options pre-2026-06).

---

## A. Estate-native (Earnings OS)

| ID | Event | Archetype candidate | PRE | HEAD | REL | PREP | QA | FILING | CLOSE | REV | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E-01 | AAPL FY2026 Q3 `evt_cik0000320193_2026q3_results` call 2026-07-30 | basis mismatch / no legal beat-miss | U | U | **P** Exhibit 99.1 | **P** tx body | **A** `qa_exchanges: []` | **P** 8-K accession only | **A** `reaction_not_joined` | **A** unlicensed | PRODUCTION VERIFIED live generation `f709a0a6ec514282d5769e7d`. Clocks collapsed to `2026-07-30T20:30:28Z`. `basis_match=false`. |
| E-02 | SNOW latest (golden universe) | growth-KPI / no fake GAAP | U | U | U | U | U | U | U | A | SPEC — E0 golden universe #2. Not bound as workspace. |
| E-03 | CAT amendment `CIE-GC-0025` | correction replay (not a tape archetype) | U | U | U | U | U | U | U | U | CODE VERIFIED as corpus class `amendment`. Bodies synthetic. |
| E-04 | BAC `CIE-GC-0113` | basis mismatch (NII/CET1 ≠ EPS) | U | U | U | U | U | U | U | A | CODE VERIFIED corpus `bank_basis`. Freeze: refuse cross-basis beat/miss. |
| E-05 | GOOGL Q2 FY2026 `cie_e7b4b160257b99936851ece0` | dual-class identity, not two events | U | U | U | U | U | U | U | A | CODE VERIFIED freeze: GOOG must not mint a second issuer. CI 200 GOOGL / 404 GOOG as of E0. |
| E-06 | NET `CIE-GC-0147` | missing transcript | U | U | P? | **A** | **A** | U | U | U | CODE VERIFIED corpus `missing_transcript` → typed absence. |
| E-07 | UAL `CIE-GC-0187` | changed slide family | U | U | U | U | U | U | U | U | CODE VERIFIED corpus `changed_slide_family`. Slides SPEC_ONLY in production. |
| E-08 | XOM `CIE-GC-0199` | speaker-role / Q&A pressure | U | U | U | P fixture | P fixture | U | U | U | CODE VERIFIED freeze worked example. Synthetic body. |

IEX Q2 FY2026 and LMND Q2 FY2026 are **control** Wire records (E0 §5), not G0 geometry. LMND Wire Q2 vs CI Q1 is the freshness-split diagnostic, not a fade.

Golden corpus 234 events / 17 classes remain identity/citation fixtures. They are **not** 234 market-reaction cases (`research_only`, synthetic bodies).

---

## B. Historical rows (winner-case library)

Receipt for every row: `research/winners/cases/<FILE>`. Tape numbers, if any, live there. CEI frontier = `U` except where noted. Options `X` unless t0 ≥ 2026-06.

### B1. Positive gap / hold (reaction-confirmed candidates)

| ID | Ticker | t0 | File | Candidate | Notes (from case; not CEI) |
|---|---|---|---|---|---|
| H-01 | NVDA | 2023-05-25 | `NVDA_2023.md` | guidance reinterpretation + reaction confirmed | FY24 Q1 + Q2 ~$11B guide 2023-05-24 issuer PR. Gap +26.15% held 3/5/10d. PRIMARY SOURCE URL in file. Options X. Revisions not in-repo. |
| H-02 | APP | 2024-11-07 | `APP_2024.md` | positive gap / hold | Q3 2024 earnings gap +36.46% held 3/5/10d. Issuer PR URLs in file. |
| H-03 | ANET | 2020-11-03 | `ANET_2020.md` | positive gap + guidance | earnings/gap/guidance hints |
| H-04 | APH | 2025-05-30 | `APH_2025.md` | positive gap + guidance | |
| H-05 | ATI | 2025-05-02 | `ATI_2025.md` | positive gap + guidance | |
| H-06 | AVGO | 2025-05-30 | `AVGO_2025.md` | positive gap + guidance | AI-infra peer to NVDA wave (E0 golden wave names AVGO) |
| H-07 | AXON | 2024-08-07 | `AXON_2024.md` | positive gap + guidance | |
| H-08 | BROS | 2024-11-07 | `BROS_2024.md` | positive gap + guidance | |
| H-09 | CAVA | 2023-12-13 | `CAVA_2023.md` | positive gap + guidance | |
| H-10 | CRWD | 2023-11-29 | `CRWD_2023.md` | positive gap + guidance | E0 incorporation INC-05 |
| H-11 | CVNA | 2023-07-19 | `CVNA_2023.md` | turnaround print | |
| H-12 | DUOL | 2024-09-16 | `DUOL_2024.md` | positive gap + guidance | |
| H-13 | EME | 2024-02-28 | `EME_2024.md` | positive gap + guidance | |
| H-14 | FICO | 2024-08-06 | `FICO_2024.md` | positive gap + guidance | |
| H-15 | FN | 2025-06-20 | `FN_2025.md` | positive gap + guidance | |
| H-16 | FSLR | 2022-07-28 | `FSLR_2022.md` | policy + earnings gap | |
| H-17 | HOOD | 2025-06-03 | `HOOD_2025.md` | positive gap | |
| H-18 | ILMN | 2025-06-20 | `ILMN_2025.md` | turnaround + guidance | |
| H-19 | LITE | 2025-06-04 | `LITE_2025.md` | turnaround + guidance | |
| H-20 | NET | 2021-06-08 | `NET_2021.md` | positive gap + guidance | Same issuer as corpus missing-transcript class — **different year** |
| H-21 | NRG | 2024-03-14 | `NRG_2024.md` | turnaround + guidance | |
| H-22 | NVDA | 2017-05-10 | `NVDA_2017.md` | earlier GPU rerating | Do not mix with 2023 episode |
| H-23 | NVDA | 2015-09-29 | `NVDA_2015.md` | platform rerating | Distinct episode |
| H-24 | PLTR | 2024-02-06 | `PLTR_2024.md` | positive gap + guidance | |
| H-25 | RDDT | 2024-10-14 | `RDDT_2024.md` | positive gap + guidance | |
| H-26 | RDDT | 2025-06-17 | `RDDT_2025.md` | later confirm | Distinct episode |
| H-27 | RBRK | 2024-11-21 | `RBRK_2024.md` | positive gap + guidance | |
| H-28 | SMCI | 2024-01-19 | `SMCI_2024.md` | positive gap + guidance | Later accounting-attention risk is **ex post** to t0 — do not silently import |
| H-29 | SPOT | 2023-01-20 | `SPOT_2023.md` | turnaround + guidance | |
| H-30 | TWLO | 2024-10-31 | `TWLO_2024.md` | turnaround + guidance | |
| H-31 | VRT | 2023-04-26 | `VRT_2023.md` | positive gap + guidance | E0 incorporation INC-04 |
| H-32 | VST | 2024-09-20 | `VST_2024.md` | cycle + guidance | |
| H-33 | XPEV | 2024-09-19 | `XPEV_2024.md` | cycle + guidance | |
| H-34 | SE | 2024-09-23 | `SE_2024.md` | turnaround + guidance | |
| H-35 | OSCR | 2024-01-08 | `OSCR_2024.md` | turnaround + guidance | |

### B2. Negative gap / recovery or turnaround-after-reset

| ID | Ticker | t0 | File | Candidate | Notes |
|---|---|---|---|---|---|
| H-36 | AMD | 2003-08-18 | `AMD_2003.md` | negative-era turnaround | earnings/gap |
| H-37 | BA | 2025-04-23 | `BA_2025.md` | turnaround print | |
| H-38 | CCJ | 2025-05-09 | `CCJ_2025.md` | delayed incorporation after washout | E0 INC-03/INC-22: Q1 2025-05-01 intact; spot fear vs contract book |
| H-39 | CHWY | 2022-07-08 | `CHWY_2022.md` | mixed: Mar 2022 negative 8-K then Jun recovery then Aug guide disappoint | 8-K acceptance times in file. Opens **null**. Later fail = reaction rejected on a **later** rung |
| H-40 | EDU | 2023-10-25 | `EDU_2023.md` | turnaround | |
| H-41 | NIO | 2020-06-01 | `NIO_2020.md` | turnaround + guidance | |
| H-42 | NVDA | 2004-11-05 | `NVDA_2004.md` | turnaround | Distinct from 2023 |
| H-43 | A | 2003-06-02 | `A_2003.md` | turnaround | |

### B3. Positive gap / fade or reaction rejected

| ID | Ticker | t0 | File | Candidate | Notes |
|---|---|---|---|---|---|
| H-44 | AFRM | 2022-08-03 | `AFRM_2022.md` | reaction rejected | failed_breakaway; credit/funding impairment knowable |
| H-45 | GTLB | 2022-08-05 | `GTLB_2022.md` | positive gap / fade | E0 INC-08 stale-catalyst continuation |
| H-46 | PINS | 2024-05-06 | `PINS_2024.md` | headline print / fade | E0 INC-11: Q2 guide decelerating |
| H-47 | U | 2021-11-11 | `U_2021.md` | guidance reset / rejected | E0 INC-26 |
| H-48 | TMDX | 2022-08-25 | `TMDX_2022.md` | late catalyst / rejected | |
| H-49 | TNDM | 2024-05-03 | `TNDM_2024.md` | guidance / rejected | Distinct from 2018 winner |
| H-50 | SOUN | 2024-02-26 | `SOUN_2024.md` | attention > earnings quality | E0 INC-15 |
| H-51 | NBIS | 2025-01-24 | `NBIS_2025.md` | earnings hint but financing-led | E0 INC-19 |
| H-52 | TEM | 2025-01-21 | `TEM_2025.md` | attention-amplified | E0 INC-20 |
| H-53 | NVDA | 2000-06-16 | `NVDA_2000.md` | over-anticipated / rejected | E0 INC-09 |
| H-54 | A | 2000-02-24 | `A_2000.md` | gap + guidance, failed | |
| H-55 | BIDU | 2006-05-10 | `BIDU_2006.md` | earnings/guidance, failed | |
| H-56 | SEDG | 2016-02-04 | `SEDG_2016.md` | gap + guidance, failed | |
| H-57 | RBLX | 2021-11-09 | `RBLX_2021.md` | earnings gap, failed | |
| H-58 | SG | 2023-07-06 | `SG_2023.md` | earnings gap, failed | |
| H-59 | HIMS | 2024-06-04 | `HIMS_2024.md` | late GLP-1 print, failed | Distinct from 2021 and 2025 rows |
| H-60 | RDW | 2025-06-05 | `RDW_2025.md` | earnings/guidance, failed | |

---

## C. Archetype coverage (candidates, not grades)

| Commission archetype | Rows that can even be *candidates* | CEI-gradable now? |
|---|---|---|
| Negative gap / full recovery | H-36–H-43, CHWY first rung | No |
| Positive gap / fade | H-44–H-60 | No |
| Headline beat / deep weakness | **none legal** — consensus unlicensed | No |
| Headline miss / deep strength | **none legal** | No |
| Accounting contradiction | SMCI later attention is ex post; FIF-7 not built | No |
| Guidance reinterpretation | H-01 (NVDA guide), live AAPL one-shot range, CHWY Aug 2022 | Partial (item exists; history does not) |
| Q&A-driven reinterpretation | **zero** with structured exchanges | No |
| Basis mismatch / no legal beat-miss | E-01 live AAPL; E-04 BAC corpus | **Yes** (E-01) |
| Reaction confirmed | H-01–H-35 as research labels | No as CEI |
| Reaction rejected | H-44–H-60 as research labels | No as CEI |

Count of historical rows in §B: **60**. Estate-native §A: **8**. Total **68**.

---

## D. How a later session should fill frontier cells

For each `H-*` row, the cheapest honest fill is:

1. Issuer PR / 8-K URL already in the winner file → `FULL_RELEASE.source_available_at` if the page carries a timestamp (PRIMARY SOURCE).
2. Do not backfill `HEADLINE_AVAILABLE` from a newspaper lede.
3. Transcript chapter split → `PREPARED_REMARKS` / `QA_AVAILABLE` only with a body SHA.
4. 10-Q `accepted_at` via FIF / submissions → `FILING_RECONCILED` or `pit_ineligible`.
5. Bars from the case’s named parquet → G1/G2/G3; opens may be null.
6. Options/revisions: `X` / accruing per matrix.

Until those fills exist, leave `U`. Do not copy winner YAML `t0_hypothesis` into `source_available_at`. `t0` is a research decision date, often the **session after** the print (NVDA t0 2023-05-25 vs PR 2023-05-24).

---

## E. Rights

Winner-case files cite issuer IR URLs. This casebook cites those files; it does not copy transcript bodies. Golden-corpus rows are synthetic.
