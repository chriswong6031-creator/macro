# D0 — Three-graph separation map

**Prior art (do not reinvent):** `research/EARNINGS_NEURAL_GRAPH_READTHROUGH_AND_CATALYST_ARCHITECTURE_2026-08-16.md` §1.  
**Law:** the three graphs may join through a read-through object. They must not be flattened into one opaque edge or magic score.  
**SHA:** `3d12412e561ef77c0a9618c9d9b18871d7344209`.

This file maps **currently existing objects** onto the three graphs. It does not create a fourth graph.

---

## 1. The three graphs

### Graph 1 — Economic relationship

**Question:** why could information transfer?

Disclosed or strongly evidenced business structure:

- customer / supplier / partner / competitor / distributor / license
- common customer or common supplier
- product / end-market / geography / regulation exposure
- prime–sub, program, facility, bottleneck node
- ownership only when it changes cash-flow rights (JV, sub, parent)

**Why-transfer is not:** “these names are in the same basket,” “they correlate,” “ChatGPT says they are peers.”

### Graph 2 — Fundamental / narrative similarity

**Question:** what operating information is comparable?

- shared products, KPIs, Q&A topics, guidance drivers
- similar segment mix or demand/cost mechanism
- narrative co-acceleration
- theme membership as **vocabulary**, not as a cash-flow edge
- trial-protocol comparability (same indication/endpoint), which is **not** a commercial peer

### Graph 3 — Residual market

**Question:** how is the market treating the names *right now*?

- residual correlation, group pulse, participation, breadth
- sympathy around another member’s print
- leader/centrality, incorporation state
- contagion / leadership-crack / deterioration-cascade
- options-implied move, volume, attention

Graph 3 can fire with no Graph 1 path (common factor). Graph 1 can exist with no Graph 3 move (delayed or no transfer).

---

## 2. Object → graph assignment

| Object | Graph | Status | Forbidden collapse |
|---|---|---|---|
| GMI `MEMBER_OF` company→basket / `ltheme` | **2** (source claims this name belongs to a concept) | live W1b/W3A | do not treat as supplier or beneficiary |
| GMI `EXPRESSES` basket→theme | **2** (vocabulary) | live | do not compose into company→theme as a stored fact (contract §3) |
| GMI `TRACKS` etf→basket | **3** (tradable proxy) mixed with **2** | live | do not use as economic exposure weight (axes reserved-null) |
| GMI `SUPPLIES` / `ENABLES` / `BOTTLENECK_OF` / `BENEFITS_FROM` | **1** | reserved enum, not emitted | do not backfill from co-movement (`source_class=co_movement` exists in the enum and is a trap) |
| GMI `CATALYST_OF` | **1** (event→name) | planned W4 from GovRev | do not mint from a theme tag |
| GMI `SAME_AS` / `TRANSLATES_TO` / `PARENT_OF` / `RELATED` | **2** (vocab / hierarchy) | reserved / partial | `RELATED` is the flatten-word; do not use it as the join |
| TIL `theme_pathways` beneficiary/loser | **2** compiled, displayed as if **1** | live config | TI-R5: no runtime shock-to-beneficiary. Pathways are curated theme-level, not filing-backed firm edges |
| Demand Desk `ai_datacenter` / `housing` | **1** (hardcoded spender→beneficiary lists) | live | lists are not a graph; `ai_datacenter` scored theses must not become EP authority |
| Foresight `bottleneck.py` | physical tightness, **not** a firm graph | live shadow | a tight NAICS cap-U is not `BOTTLENECK_OF` ticker A→B |
| GR baskets | **2** (curated peer set) + input to **3** | live | membership ≠ economic edge |
| `group_pulse.v1` | **3** | live | do not invert pulse into “these supply each other” |
| `group_earnings_pulse.v1` sympathy | **3** (earnings-day co-move) | live | sympathy ratio is not a hypothesis object |
| `group_linked_outsiders.v1` | **1-candidate** (disclosed agreement, role unknown) | code live, yield 0 | never upgrade `supply_agreement` to customer/supplier |
| EI fact pack / claim graph / event_workspace | source facts for a later hypothesis | live substrate | not a graph |
| `earnings_readthrough_hypothesis/v1` | **join object** across 1+2+3 | **not built** | the only lawful join |
| `earnings_market_incorporation/v1` | **3** | not built | “not incorporated” ≠ “price didn’t go up” |
| GovRev `defense19-v1` | **1-identity** (legal/ownership), not customer | live | do not call ownership an economic relationship graph |
| GovRev IDV / subaward | **1-award-vehicle** | artifacts exist; live unproven | subaward ≠ supplier BOM |
| GovRev budget program graph | **1-budget** | schema, no committed file | `economic_weight` is required-null |
| Defense D5/D10 | **1** program / bottleneck | spec only | do not start in D1 |
| Bio `trial_peer_set.v1` | **2** (protocol comparability) | live | contract forbids commercial-peer inference |
| Bio ontology fixture | **2** (asset–indication–trial) | fixture | no competitor / MOA / customer |
| Bio sponsor map | identity, not graph | live | `parent_of_subsidiary_sponsor` ≠ customer |
| TXI chains | macro mechanism path; **not** firm Graph 1 | live | do not attach a chain `expressed` to a supplier ticker as a transfer |
| CHF frontier | research cells | live | `DNR:KILL-CAUSAL-DAG-ALPHA` |
| Neural Web synapses | bus, not a market graph | live | A7: no originated edges |
| CSP / `contagion.py` / leadership_crack | **3** | live | 2026-07 Korea unwind is residual-market contagion, not customer transfer |
| C1 commodity→sector studies | **3** tests of a **1-ish** thesis | reports | gold→XGD NO-GO shows Graph 1 intuition ≠ Graph 3 fact |

---

## 3. Lawful joins (and the only join object)

From the 2026-08-16 architecture §4.3, a target universe is the **union** of generators, each tagged:

- Graph 1 generators: customer/supplier/partner/competitor, common customer/supplier, product/end-market
- Graph 2 generators: subindustry, curated peer set, narrative/topic, theme membership
- Graph 3 generators: residual co-movement group, historical transmission neighbor (neighbor ≠ cause)

**Record which generator admitted each target.** Semantic similarity alone must not assert an economic relationship.

The join record is `earnings_readthrough_hypothesis/v1` (or a later non-earnings generalization). Required legs already specified: source event, target, mechanism, predicted **operating** direction, evidence, relationship paths, narrative similarity, incorporation, alternatives, falsifiers, expiry, authority.

Economic Propagation, if chartered, owns **that record class** and its PIT grade. It does not own Graphs 1–3.

---

## 4. Collapse patterns already visible in this estate

| Collapse | Where it would happen | Why it is illegal here |
|---|---|---|
| Theme membership → supplier | GMI W4 temptation; 商品联动 display | W1b has no derived company→theme edge for this reason |
| 8-K agreement → customer | GR3 | module header forbids the four role words |
| Residual sympathy → transfer | GR2 sympathy printed as “read-through” | sympathy is Graph 3; EI registry wording already drifts this way |
| Ownership → customer | GovRev agency HHI labeled “customer concentration” | that metric is awarding-agency mix, not a customer node |
| Protocol peer → commercial peer | Bio peer matrix | contract text forbids it |
| TXI `expressed` → firm transfer | gold chain 2026-08 | instrument window ≠ miner cash-flow path |
| Contagion hop → economic chain | CSP Korea→memory→Mag7 | residual-market hop; 07-16 was not even a broad-index day |
| Hardcoded Demand Desk list → graph | `engine/demand_chain.py` | a list of six spenders is not PIT Graph 1 |
| `source_class=co_movement` on a `SUPPLIES` edge | theme-graph enum allows it | would bake Graph 3 into Graph 1 permanently |

---

## 5. Exposure axes (reserved, not a fourth graph)

`theme_graph.edges.v1` reserves three continuous quantities: `economic_share`, `trading_beta`, `attention_share`.

| Axis | Nearest graph | Status |
|---|---|---|
| `economic_share` | 1 | reserved-null; W2 probe |
| `trading_beta` | 3 | reserved-null; W2 probe |
| `attention_share` | 3 / attention | reserved-null; W2 probe |

Display enums are glance rounding, never inputs. Sorting members by any axis is a ranker (`G0.11`) and is forbidden.

---

## 6. What a later builder must freeze before writing edges

1. Which store is Graph 1 (GMI W4 vs a new table). Recommendation: **GMI edge types**, filled only from GR3b / XBRL / GovRev / reviewed Bio partnerships — not a parallel parquet.
2. Graph 2 stays TIL + GMI membership + Bio protocol + EI narrative. No new similarity graph.
3. Graph 3 stays GR pulse/sympathy + CSP/XSR residuals + (later) `earnings_market_incorporation/v1`.
4. The join is a hypothesis record with generator tags, not an edge type `RELATED`.
