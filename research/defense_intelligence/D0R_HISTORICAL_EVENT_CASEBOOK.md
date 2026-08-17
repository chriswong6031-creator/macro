# D0R Workstream D — Historical market behavior and event casebook

**Authority:** research hypotheses, not a production model. No scores. No “validated alpha.”  
**Selection law:** mix of positive, negative, ambiguous, correction, and *non-material* controls. Famous winners are not the sampling frame. Live golden row HC101319C0006 / IRDM is in the book as a **late-discovery incremental fund**, not as a war trade.

PIT legend: `replay-safe` = official timestamped primary (DoD PDF, EDGAR accession, USAspending action_date); `current-vintage` = today’s revised series; `forward-only` = would not have been knowable; `unavailable`; `ambiguous`.

## D2. Academic review (primary papers, architecture implications)

| Paper | Sample / method / outcome | Architecture implication | Does **not** justify |
|---|---|---|---|
| Schneider & Troeger 2006, *J. Conflict Resolution* — war vs world indices 1990–2000 | Broad equity indices; conflict often **negative** or null for CAC/DJ/FTSE | War is not a market-wide bull; do not map “conflict up” to SPX | Defense-name alpha |
| Martins et al. 2024, *JES* — Ukraine invasion, top 100 defense firms | Short-window event study; **positive** AR, larger for higher defense-sales weight and R&D/capex | Weight of defense sales is a first-class feature; pure-play ≠ diversified | Holding-period returns or earnings |
| Martins 2024, *IMEFM* — Ukraine, Taiwan Strait, Hamas | Positive short-term AR around three threats; same defense-sales / R&D pattern | Regional wars still move the global defense list, but size of move is not uniform | Treating Taiwan headlines as a US munitions print |
| Gurdgiev & Henrichsen / related “budgets of wars” 2022, *Int. Rev. Econ. Finance* — US MIC 1990–2019 | Budget announcements **complex**; direct conflict positive then **mean-reverts** | Budget *changes* and surprise matter more than the level; do not treat conflict as a permanent multiple | “Republican president” as a trading rule |
| SEF 2024 Wagner coup event study (European defense) | Invasion +CAAR; Wagner coup **negative** next session (~−1% AAR in that paper) | De-escalation / regime-fragility can reverse the war bid **the next session** | Ignoring de-escalation as a first-class adverse event |
| Apergis et al. 2017 GPR → defense returns/vol (nonparametric) | GPR predicts **volatility** more reliably than signed returns | Geopolitics is often a vol/attention event, not a cash-flow event | Using GPR as a ranker |
| CMC thesis 2024 (Claremont) Ukraine vs Israel-Hamas on 9 US names | Ukraine AR significant; Hamas mixed/regional | Match **geography and US involvement** to archetype (munitions vs homeland vs nothing) | One war-beta for all names |

**Honest limit:** these papers are short-window ARs, survivorship-heavy, and usually **current-vintage prices**. They support *heterogeneity* and *mean-reversion of conflict spikes*. They do not support a Prophet member, a “defense score,” or “war is always bullish.”

## D4. How cases were selected

1. Seed families from the D0R handoff (war, program charge, FMS, legal, capacity, budget).  
2. Forced negatives: de-escalation, FP charges, protest, CR, civil-aero swamp, non-material option.  
3. Forced live: IRDM P00032 (May obligation, August known_at).  
4. No case is included solely because the stock went up.  
5. Returns below are **qualitative market memory**, not a PIT study. D7 evaluation must rebuild with PIT prices before any promotion.

## D3. Casebook (≥60)

| ID | Date (event) | Names (archetype) | Family | What happened | Mechanism | Horizon | Sign | PIT inputs | Why included | Source class |
|---|---|---|---|---|---|---|---|---|---|---|
| E01 | 2001-09-11 | LMT, NOC, GD (1,3) | demand shock | 9/11 | Homeland + DoD demand reset | years | + / mixed (BA civil −) | replay-safe news; current-vintage prices | Dual-use trap | official/news |
| E02 | 2003-03 | LMT, NOC (1) | Iraq invasion | OIF | Expected ops + munitions | months–years | + short | current-vintage | War ≠ perpetual | news |
| E03 | 2011-05 | BA (10) | program | Tanker award to BA (KC-46) after protest era | Access win | years | + then − charges | replay-safe DoD | Win then FP pain | DoD/SEC |
| E04 | 2013-03 | primes | budget | Sequester / BCA | Demand cut | years | − | replay-safe | Budget level can dominate war | budget |
| E05 | 2014-03 | EU names (11) | Crimea | Russia annexes Crimea | NATO discourse, slow spend | years | delayed + | current-vintage | Threat ≠ appropriation | news |
| E06 | 2016 | BA (1,10) | charge | KC-46 charges begin recurring | FP development | years | − | replay-safe 8-K | Charge series > award | SEC |
| E07 | 2017-12 | NOC (1,3) | M&A | NOC-Orbital ATK | Munitions + SRM | years | mixed | replay-safe | Identity change | SEC |
| E08 | 2018 | LMT (2) | FMS | Saudi Patriot/THAAD cluster (notifications) | Notification ≠ funded | months | + then fade | replay-safe DSCA | FMS stage | DSCA |
| E09 | 2019 | HII (4) | schedule | Carrier/sub cadence commentary | Yard throughput | years | mixed | company | Hull slip is FCF | IR |
| E10 | 2020-03 | diversified (10) | COVID | Civil aero collapse | Civil swamp defense | months | − | current-vintage | Archetype 10 | prices |
| E11 | 2021-08 | none specific | de-escalation | Afghanistan withdrawal | Ops demand down | months | mixed/− services | news | War end | news |
| E12 | 2021 | BA (1) | quality | 737 MAX civil still dominates BA | Dual-use | years | − | SEC | Don’t tag BA as war stock | SEC |
| E13 | 2022-02-24 | RHM, SAAB, LDO, LMT, RTX (2,11) | Ukraine invasion | Full-scale invasion | Expected replenishment | days–years | + short AR | papers above; current-vintage | Motivating exemplar | news+papers |
| E14 | 2022-03 | RTX, LMT (2) | replenishment | Javelin/Stinger/HIMARS drawdown | Inventory restock | years | + | DoD/IR | Capacity lag | DoD |
| E15 | 2022-05 | US A&D | supplemental | Ukraine supplemental | Funded demand | year | + | replay-safe Congress | Appropriation is the cash-flow event | Congress |
| E16 | 2022-08 | TSM/geo | Taiwan Strait | Pelosi visit | Discourse; not US ammo print | days | mixed | Martins 2024 | Regional vs product | news |
| E17 | 2022 | BA (1,10) | charge | Defense charges alongside civil | FP + dual-use | years | − | 8-K | Negative control for “award=good” | SEC |
| E18 | 2022 | GD (4) | ship | EB/NNS labor & schedule | Capacity | years | mixed/− | IR/GAO | Bottleneck | GAO |
| E19 | 2022 | HII (4) | schedule | Ingalls/NNS guidance | Delivery | years | mixed | IR | | IR |
| E20 | 2023-02 | EU (11) | budget | German/EU rearmament laws | Home FY | years | + | official | National champion | MoD |
| E21 | 2023-06-23 | EU defense (11) | Wagner | Coup attempt | De-escalation/fragility | days | − next session (paper) | event study | Must have de-escalation cases | paper |
| E22 | 2023-10-07 | LMT, RTX, IHI/Israel-exposed (2,7) | Hamas | Regional war | Missile defense vs US primes | days | mixed US; + local | thesis 2024 | Geography | news |
| E23 | 2023 | NOC (1,7) | program | Sentinel / GBSD cost growth | ICBM FP risk | years | − | GAO/DoD | Nunn-McCurdy path | GAO |
| E24 | 2023 | RTX (2,3) | charge / TOC | Raytheon charges / quality | Execution | year | − | 8-K | Negative | SEC |
| E25 | 2023 | LMT (1) | F-35 | Lot pricing / engine | Franchise friction | year | mixed | IR | Prime ≠ smooth | IR |
| E26 | 2023 | AVAV / drones (8) | UON | Ukraine UAV demand | Attritable | year | + then competitive | IR | OTA≠franchise | IR |
| E27 | 2023 | KTOS (8) | autonomy | Replicator discourse | Policy | months | + attention | news | Attention lag | news |
| E28 | 2023 | LMT (2) | Patriot | GEM-T / capacity adds | Line rate | years | + if not already guided | IR/DoD | | DoD |
| E29 | 2024 | NOC (7) | space | OPIR / space force mix | Classified limits | years | ambiguous | IR | Classified economics | IR |
| E30 | 2024 | BA (1) | NGAD / F/A-XX pause discourse | Access/doctrine | years | −/mixed | DoD | Program pause | DoD |
| E31 | 2024 | HII (4) | Constellation FFG | FP ship risk | years | − | Navy/GAO | Repeat of LCS lesson | GAO |
| E32 | 2024 | GD (4) | Columbia | SSBN cadence | years | mixed | Navy | Nuclear yard | Navy |
| E33 | 2024 | LHX (3) | C4ISR | Vehicle/task orders | quarters | mixed | awards | IDIQ ceiling trap | USAspending |
| E34 | 2024 | CACI/SAIC (5) | recompete | Services vehicle | year | ± | SAM | Recompete is the event | SAM |
| E35 | 2024 | TDG/HWM (6) | aftermarket | Aero content | year | civil-driven | IR | Dual-use | IR |
| E36 | 2024 | MP/critical (9) | materials | DPA / magnet narrative | years | mixed | DPA | Bottleneck without offtake | official |
| E37 | 2024-10 | US names | Israel/Iran strike windows | Vol/attention | days | mixed | prices | Options often first | market |
| E38 | 2025 | LMT/RTX (2) | Golden Dome discourse | Policy theme | years | + attention | White House/DoD | Theme ≠ issuer alpha | official |
| E39 | 2025 | space names (7) | SDA tranche awards | Proliferated space | year | + winners / − losers | SDA | Winner-take-tranche | official |
| E40 | 2025 | IRDM (7) | SATCOM | Service mods | year | small | USAspending | **Live golden** | USAspending |
| E41 | 2026-05-12 | IRDM (7) | P00032 | $18.4M FUNDING ONLY on HC101319C0006 | Incremental service fund | none as catalyst | **non-material** vs mkt cap | replay-safe action_date; known_at 2026-08-12 | Late discovery; not August news | USAspending + GovRev |
| E42 | 2026-08-12 | IRDM (7) | late discovery | Collector first-seen | Attention lag | days (if any) | ambiguous | known_at replay-safe | Do not title as new award | GovRev |
| E43 | 2010s | LCS program | GD/HII/LMT mix (4,1) | Truncated class | FP + requirements | years | − | GAO | Famous loser | GAO |
| E44 | 2010s | Zumwalt | GD (4) | Quantity collapse | Requirements | years | − | Navy | | Navy |
| E45 | 1986 | Challenger | contractors | Contagion | Quality/safety | weeks | − peers | news | Contagion case | news |
| E46 | 2010s | A-12 / historical FP | primes | Cancellation | FP development | years | − | historical | Cancellation | historical |
| E47 | 2019 | CSRA/GDIT (5) | M&A | Services identity | year | identity | SEC | Atlas case | SEC |
| E48 | 2023 | L3Harris-Aerojet (2,9) | M&A | SRM bottleneck ownership | years | + bottleneck | SEC | Bottleneck via deal | SEC |
| E49 | 2024 | GE split (10,6) | identity | GE Aerospace listing | identity | n/a | SEC | Dual-class/listing | SEC |
| E50 | 2022 | BWXT (4,9) | nuclear | Naval nuclear components | years | + with fleet | IR | Graph coverage gap vs filmstrip | IR |
| E51 | 2023 | protest example | incumbent vs challenger | GAO sustain | Access | months | − winner delayed | GAO | Protest | GAO |
| E52 | 2023 | CR / shutdown threat | services (5) | Continuing resolution | Timing | quarter | − delayed funding | Congress | CR | Congress |
| E53 | 2024 | quality escape | RTX/others | Cyber/quality | year | − | 8-K | Adverse | SEC |
| E54 | 2024 | legal settlement | prime | Pricing/False Claims | year | often **immaterial** | 8-K | Negative control | SEC |
| E55 | 2024 | structural legal | export/ITAR | License | years | − | official | Structural vs settlement | official |
| E56 | 2015 | HII (4) | routine option | Expected year funding | none | **non-material** | award | Control: expected option | USAspending |
| E57 | 2022 | PLTR (5,8) | Army software | Attention vs earnings | year | mixed | IR | Crowding | IR |
| E58 | 2023 | Anduril (private) | OTA | Private mark | n/a | n/a | news | Public-market analog only | news |
| E59 | 2024 | AUKUS | GD/HII/BAE (4,11) | Pillar 1 subs | decade | + long | treaty/Navy | Export + yard | official |
| E60 | 2024 | FMS Taiwan | LMT/NOC (1,2) | Notifications | years | + if converted | DSCA | Stage labels | DSCA |
| E61 | 2023 | 155mm / SRM | munitions (2,9) | Capacity projects | years | + bottleneck | DoD | Industrial | DoD |
| E62 | 2022 | book-to-bill miss | prime | Guidance vs awards | quarter | − | IR | Gov vs company | IR |
| E63 | 2024 | classified charge | prime | Undisclosed program | year | − | 8-K limited | Classified economics | SEC |
| E64 | 2025 | ceasefire discourse | munitions (2) | Inventory fill risk | year | − if believed | news | De-escalation | news |
| E65 | 2018-03-22 | none on row (HII sibling exists) | deobligation | N0002415C2114 AZ0010 −$5.94M | Late collector 2026-08-08 | none as ticker event | **negative official $** | replay-safe action + known_at | Live negative lineage L2 | USAspending + HEAD workspace |
| E66 | (effective ≪ known) | HII (4) | late discovery | N0002415C2114 award_discovered_late `govws-b19836e22bc86b6144fd410a` | Collector lag | n/a | identity+clock | replay-safe | Live HII clock case | HEAD workspace |
| E67 | 2025-12-08 | SPR → BA (6,10) | identity / M&A | Boeing completed Spirit acquisition; NYSE halt SPR | Listing ends | n/a | identity | replay-safe 8-K | SPR is not a live issuer | SEC 8-K |

## D8. VERIFIED_CASE vs RESEARCH_CANDIDATE (Gate 5 honesty)

Gate 5 requires ≥60 **reviewed** events with pinned event/source/security/PIT. This close **does not invent 60 fake primary sources**. Rows E01–E64 remain in the book as the sampling frame. Status:

| Status | Meaning | IDs |
|---|---|---|
| **VERIFIED_CASE** | Primary artifact or official URL pinned this program (HEAD GovRev, USAspending action id, or SEC 8-K opened 2026-08-17) | **E40–E42, E65–E67** (6). PIT: official `action_date` + collector `known_at` on E41/E42/E65/E66; SEC accepted 8-K on E67 (`ba-20251208`, Spirit `tm2532915d1_8k.htm`). Securities: IRDM live on Stock Identity; HII live; SPR **not** in SI universe (historical). |
| **RESEARCH_CANDIDATE** | Architecture-useful, not a pinned primary this close. Qualitative market memory only. | **E01–E39, E43–E64** (61). |

**Count:** 64+3 = **67 rows** in the book; **6 VERIFIED_CASE**; **61 RESEARCH_CANDIDATE**; academic papers in D2 remain citations, not case rows.

**Selection disclosure:** verified set is biased toward *what the live tape actually contains* (USAspending award_change, late discovery, deobligation, one M&A identity close). It under-represents FMS, budget enactments, and EU home-FY events until those rails exist. That bias is why RESEARCH_CANDIDATE rows stay listed rather than deleted.

**Balanced outcomes in the verified set:** E41 non-material positive obligation; E65 official negative dollars with **no ticker**; E66 late identity; E67 listing termination. Famous Ukraine winners are **not** in the verified set.

D7 evaluation must still rebuild RESEARCH_CANDIDATE rows with PIT prices before any promotion. Gate 5 is **honest-labeled, not fake-closed**.

## D6. Hypothesis registry (preregistration candidates, not results)

| Key | Claim to test later | Falsifier | PIT need |
|---|---|---|---|
| H-novelty | Award headlines already in guidance do not move the name | AR≈0 when 8-K already quantified | filings + prices |
| H-funding | Obligation/mod > ceiling/IDIQ for earnings relevance | Ceiling-only events AR≈0 | USAspending action type |
| H-contract | FP development charges dominate award wins on 1y FCF | Charge 8-K AR more persistent than award AR | SEC |
| H-capacity | Munitions AR fade when line-rate already maxed | AR only when CAPEX/DPA announced | IR + DoD |
| H-divergence | Company backlog walk disagrees with award tape → next print surprise | Forecast error sign matches divergence | IR + tape |
| H-attention | Late collector discovery does not equal a new official event | AR on known_at ≈0 if action_date old | GovRev clocks |
| H-underreaction | Task-order rate on new IDIQ under-reacts vs ceiling print | Delayed AR as orders post | awards |
| H-selloff | Quality/charge selloff recovers only if EAC stable next two prints | No recovery if second charge | SEC |
| H-options | Short-dated IV up on war headlines without cash-flow names | IV↑, spot AR≈0 on diversified | options owner |
| H-theme | Golden Dome tape does not imply issuer alpha | Theme residual ≠ name residual | Prophet residual owner |
| H-wagner | De-escalation days reverse invasion-bid names | Negative AR on coup/ceasefire | prices |
| H-fms | 36(b) notification AR fades unless LOA implemented | Stage-conditioned AR | DSCA |

## D7. What D1–D4 may use

- Clocks: `action_date` vs `known_at` vs print date vs first tradable.  
- IRDM P00032 is the **non-material late-discovery** acceptance case, not a war exemplar.  
- Do not promote any H-* until a PIT study with honest N (episodes, not fires) covers the motivating names **and** the current regime.
