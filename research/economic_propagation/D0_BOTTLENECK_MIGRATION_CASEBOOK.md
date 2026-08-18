# D0 — Bottleneck migration casebook

**Authority:** research taxonomy + historical examples. Not a live enum. Not a GMI edge write.  
**SHA:** `3d12412e561ef77c0a9618c9d9b18871d7344209`.

A bottleneck is a **node in a value chain whose capacity binds the throughput of other nodes**. It is not a theme, not a residual correlation, and not “the stock that went up.”

---

## 1. Taxonomy

States are mutually exclusive **as of a dated observation**. Default is `INSUFFICIENT_EVIDENCE`.

| State | Meaning | What would flip it | Illegal inference |
|---|---|---|---|
| **NORMAL** | Capacity covers current + guided demand with slack | utilization, lead times, inventories in a normal band | “no news ⇒ normal” |
| **TIGHTENING** | Slack shrinking; lead times or language accelerating; not yet sold-out | cap-U / backlog / “allocation” language rising | a price spike alone |
| **BINDING** | Throughput of downstream nodes is limited by this node | sold-out / allocation / named wait-time; downstream citing this input | theme membership |
| **RELIEVING** | Incremental capacity, process yield, or substitution is raising effective supply | guided capacity adds converting; lead times falling | an announced fab that is years out |
| **EXCESS_CAPACITY** | Supply overshoots; utilization and pricing power fall | inventory/sales up; impairments; customers switch | a single weak print |
| **INSUFFICIENT_EVIDENCE** | Cannot classify without look-ahead or missing facts | more dated evidence | converting missing to zero |

These states are **node-local**. The interesting object is the **migration**: the binding node moving along the chain.

---

## 2. Map onto existing house objects

| Taxonomy state | Nearest live object | Gap |
|---|---|---|
| all six | none as a typed field | do not write onto `theme_graph.edges.v1` in this lane |
| TIGHTENING / BINDING | `engine/bottleneck.py` legs 1–4 together + leg6 language | NAICS legs shared across unlike businesses (MU/WDC vs AMAT/LRCX) |
| BINDING | GMI `BOTTLENECK_OF` reserved | not emitted |
| BINDING | Defense D10 Industrial Bottleneck Atlas | SPEC_ONLY; DLA “bottleneck” DEFER |
| EXCESS_CAPACITY | Falsifier field-book US Silica | one documented supplier glut |
| INSUFFICIENT_EVIDENCE | GR3 counterparties = 0; reserved exposure axes; Bio partnership economics unbuilt | default |

Foresight bottleneck is a **physical nowcast**, not a firm-to-firm edge. A tight cap-U z is not `BOTTLENECK_OF` ticker A→B.

---

## 3. Migration examples (in-repo first)

Each row: where scarcity sat **before** → **after**, and what evidence this tree already has.

| ID | Chain | Before | After | States | Evidence | Status |
|---|---|---|---|---|---|---|
| B01 | HBM / DRAM 2024–25 | GPU/accelerator attention | HBM packaging + DRAM substitution | TIGHTENING → BINDING at HBM; DRAM at risk of EXCESS or BINDING depending on conversion | June-2024 13D quotes in `THEMATIC_FORESIGHT_DESK.md`; `engine/bottleneck.py` header uses this as the template | IN_REPO_EVIDENCED (language); tape not rebuilt |
| B02 | NVDA 2023-05-24 → cooling | GPU demand BINDING | power/cooling TIGHTENING then converting (VRT orders) | BINDING at accelerators → TIGHTENING at power train | `VRT_2023.md` | IN_REPO_EVIDENCED |
| B03 | same print → interconnect | GPU demand BINDING | CRDO still company-offset (rev −40.9% seq) | BINDING upstream, **NORMAL/offset** at this node | `CRDO_2023.md` | IN_REPO_EVIDENCED |
| B04 | 24/7 power 2024 | GPU/IT load | nuclear / IPP scarce 24/7 (CEG PPA prices VST) | BINDING migrates from chips to megawatts | `VST_2024.md`, `TLN_2024.md`, `NRG_2024.md` | IN_REPO_EVIDENCED |
| B05 | Optics 2025 | GPU / 800G | silicon photonics + optical CM | BINDING at interconnect/optics | `LITE_2025.md`, `FN_2025.md` | IN_REPO_EVIDENCED |
| B06 | LOI power campus 2024 | narrative BINDING | unsigned lease + ATM | INSUFFICIENT_EVIDENCE misread as BINDING | `APLD_2024.md` | IN_REPO_EVIDENCED |
| B07 | Northern White frac sand 2017–20 | sand BINDING in the boom | in-basin substitution → EXCESS_CAPACITY + impairments | BINDING → EXCESS_CAPACITY | `FALSIFIER_FIELD_BOOK_FOR_FABLE.md` CY-TB-2 | IN_REPO_EVIDENCED |
| B08 | Memory cycle 2017–18 | DRAM BINDING (MU GM 25%→51%) | 2018 duration/cycle reverse | BINDING → RELIEVING / EXCESS | `MU_2017.md` | IN_REPO_EVIDENCED |
| B09 | Lithium 2020–23 | chemical BINDING (forward) | later glut (not fully taped here) | TIGHTENING (2020 SQM) → later EXCESS (UNKNOWN in this book) | `SQM_2020.md` start only | partial |
| B10 | Korea memory unwind 2026-06/07 | HBM BINDING narrative | HBM4 shortfall + price **down** | BINDING language + residual-market unwind can coexist | CSP + 07-16 postmortem | IN_REPO_EVIDENCED (tape hop); do not call it “constraint ended” |
| B11 | GOOGL 2026-07-22 capex raise | spend BINDING | spender multiple compressed; hardware did **not** relieve | BINDING at spenders ≠ BINDING at suppliers that day | 07-22 postmortem | IN_REPO_EVIDENCED |
| B12 | Gold/miners 2026-08 | real-rate restriction | bullion/miners led the **instrument** | not a capacity bottleneck; included so TXI is not mistaken for one | gold case study | IN_REPO_EVIDENCED |

---

## 4. Defense / industrial (cite D0R; RESEARCH_CANDIDATE)

Do not invent primaries. See `research/defense_intelligence/D0R_HISTORICAL_EVENT_CASEBOOK.md`.

| ID | D0R | Migration | States | Notes |
|---|---|---|---|---|
| B13 | E14 / E61 | 2022 drawdown of Javelin/Stinger/HIMARS/155mm → plant rate, not stock | BINDING at energetics / 155mm / SRM | capacity lag is the hop |
| B14 | E48 | Aerojet SRM ownership via L3Harris deal | BINDING node changes **owner**, not tightness | Graph-1 identity change |
| B15 | E18 / E32 / E59 | shipyard labor / Columbia / AUKUS | BINDING at yards for a decade | do not treat a treaty as RELIEVING |
| B16 | E31 / E43 / E44 | Constellation / LCS / Zumwalt | TIGHTENING requirements → EXCESS or quantity collapse | FP + requirements, not “more war” |
| B17 | E36 | MP / critical materials DPA narrative | TIGHTENING without offtake | bottleneck without a customer |
| B18 | E03 / E06 | KC-46 award then charges | access win ≠ RELIEVING industrial constraint | company_offset |

D10 “Industrial Bottleneck Atlas” is the lawful future owner of B13–B17 as typed nodes. Economic Propagation may **read** it. It must not fork it.

---

## 5. How scarcity migrates (research pattern, not a model)

Observed pattern across B01–B05, B13:

1. Demand surprise hits the **visible** node (GPU, HIMARS, gold).
2. Market Graph 3 prices that node first (`immediate_incorporation`).
3. Physical Graph 1 constraint shows up one or two nodes **upstream or downstream** (HBM, cooling, 155mm, megawatts) with a lag (`delayed_market`).
4. A later node can become BINDING while the first node is already RELIEVING or in a residual unwind (B10).
5. Substitution can dump the old node into EXCESS_CAPACITY (B07) even if the end-market is still fine.

This is why the three graphs must stay distinct: Graph 3 can leave node 1 while Graph 1 is binding at node 3.

---

## 6. Classification rules for a later builder

1. Default `INSUFFICIENT_EVIDENCE`. Missing counterparties stay null (`group_linked_outsiders.py` discipline).
2. Do not classify from a same-day residual move (S10 TSM–ASML–SMH is the teaching case).
3. A reserved GMI `BOTTLENECK_OF` edge requires a dated filing/official receipt, not a nowcast z.
4. Foresight NAICS legs are industry-shared; they cannot pick between two members of the same code.
5. `RELIEVING` requires evidence the **effective** supply rose, not that someone announced a plant.
6. Company-specific offset (CRDO, APLD, Silica, KC-46 charges) is not a chain-wide RELIEVING.

---

## 7. Open measurement holes

- No in-repo dated CoWoS / TSMC advanced-packaging series with PIT capacity. Often spoken; not a row.
- No in-repo SRM unit-rate time series. D0R E48/E61 are qualitative.
- Lithium glut after P14 is not reconstructed here → B09 stays partial.
- Bio API / fill-finish / comparator-drug bottlenecks: **no object**.
