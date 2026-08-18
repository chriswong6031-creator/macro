# D0 — Ownership and graph census

**Program candidate:** Economic Propagation (not a registered `mastermind_programs.yml` key).  
**SHA audited:** `3d12412e561ef77c0a9618c9d9b18871d7344209` (`origin/main` as of 2026-08-18).  
**Lane:** read-only research. No graph rewrite. No alpha score. No Prophet change.  
**Sparse checkout:** `data/`, `site/`, `mockups/`, `verify_shots/` omitted. Production row counts are from `git show`/`git ls-tree` or module-measured dates, never from a live VPS probe this session.

Evidence tags used below: **CODE VERIFIED**, **PRODUCTION VERIFIED** (not claimed this session), **PRIMARY SOURCE VERIFIED**, **INFERRED**, **UNKNOWN**.

---

## Return packet

### MISSION

Audit the current graph / mechanism / read-through estate and produce the research casebook required before any Economic Propagation build.

### WHAT I VERIFIED

- There is **no** registered program named Economic Propagation. Creating one would be a later DEC, not this census.
- The **three-graph law already exists** as architecture (not a live store) in `research/EARNINGS_NEURAL_GRAPH_READTHROUGH_AND_CATALYST_ARCHITECTURE_2026-08-16.md` §1. CODE VERIFIED.
- **Evidence Mesh has not landed.** Zero matches under that name in this repo or Mastermind. CODE VERIFIED absence (name grep).
- Live objects that look like “graphs” are **not one graph**. They are at least: GMI membership spine, TIL pathway config, Group Reads baskets + empty 8-K outsiders, GovRev identity/ownership, Bio trial-peer comparison, TXI macro chains, Neural Web synapse bus, Demand Desk hardcoded spender→beneficiary lists, CSP contagion wiring.
- **No live firm-level customer/supplier/bottleneck economic-relationship graph** exists in Defense or BioCatalyst. CODE VERIFIED (defense scout + `defense19-v1` relationships = `issuer_legal_entity` / `wholly_owned` only).
- Theme-graph edge enum already reserves `SUPPLIES`, `ENABLES`, `BOTTLENECK_OF`, `BENEFITS_FROM`, `CATALYST_OF`. W1b emits only `MEMBER_OF`, `EXPRESSES`, `TRACKS`. CODE VERIFIED (`contracts/theme_graph/edges.v1.schema.json`, `config/synapse.yml` notes at `theme-graph-edges`).
- Group Reads **refuses** Customer / Supplier / Partner / Competitor labels. CODE VERIFIED (`engine/group_linked_outsiders.py`).
- CHF is `research_only` / display-tier. `DNR:KILL-CAUSAL-DAG-ALPHA` and `DNR:KILL-LLM-CONFIDENCE` remain in force.

### WHAT I COULD NOT VERIFY

- Live `data/theme_graph/*.parquet` row counts and which reserved edge types, if any, have ever been written (sparse omit).
- Whether a later nightly populated `data/edgar/material_8k_events.parquet` counterparties after the 2026-08-08 measured zero.
- Production liveness of GovRev IDV / subaward / budget graph on the VPS.
- Whether Evidence Mesh exists under a different name (search bounds: `evidence_mesh`, `EvidenceMesh`, `EVIDENCE_MESH`, `Evidence Mesh` in Macro + Mastermind).

### CODE / SOURCE RECEIPTS

Cited inline. Load-bearing: `config/mastermind_programs.yml`, `contracts/theme_graph/`, `engine/group_{pulse,earnings,linked_outsiders}.py`, `engine/transmission_chains.py`, `engine/neuralweb/{causal_frontier,theme_pathways}.py`, `engine/demand_chain.py`, `engine/bottleneck.py`, `engine/biocatalyst/{peer_matrix,sponsor_identity}.py`, `research/defense_intelligence/D0R_*`, `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`, `WS:GMI-THEME-GRAPH`, `WS:DEFENSE-PROCUREMENT-V3`.

### OUTPUT ARTIFACTS

All under `research/economic_propagation/`:

- `D0_OWNERSHIP_AND_GRAPH_CENSUS.md` (this file)
- `D0_THREE_GRAPH_SEPARATION_MAP.md`
- `D0_MECHANISM_VOCABULARY_CROSSWALK_DRAFT.md`
- `D0_PROPAGATION_CASEBOOK.md`
- `D0_BOTTLENECK_MIGRATION_CASEBOOK.md`
- `D0_COMMON_CAUSE_FAILURES.md`
- `D0_OPEN_QUESTIONS.md`

### ASSUMPTIONS

- “Owner” means the registered program key in `config/mastermind_programs.yml` plus any DEC that explicitly overrides a stale `owns` clause. Code that exists without a program key is marked **UNREGISTERED IMPLEMENTATION**, not a new owner.
- `implementation: []` on `gmi-theme-graph` is treated as **stale registry text**, not as absence of `engine/theme_graph/` (W3A #5718).

### PIT RISKS

- Theme-graph `era=reconstruction` / `date_provenance=seed_constant` edges must never be used as historically known membership.
- GovRev `known_at` is collector time, not official `action_date`.
- `demand_chain.ai_datacenter` emits **scored ledger theses** (`engine/demand_chain.py`) while the rest of this estate is display/context. Absorbing it into Economic Propagation would silently import a scored path.
- Group Reads sympathy is basket co-move around prints, not a causal transfer.

### RIGHTS RISKS

- `DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS`: Theia is research-only; no adapter.
- GMI W3A: unresolved rights ⇒ internal-only for some local-theme planes (`engine/theme_graph/rights.py`).
- GovRev licensed sources (Janes / Aviation Week / Govini) are LICENSE in the D0R registry; DLA bottleneck DEFER; imagery REJECT.

### OPEN QUESTIONS

See `D0_OPEN_QUESTIONS.md`. Blocking: who owns Economic Propagation without minting a duplicate graph.

### RECOMMENDATIONS

1. Do **not** create a new graph store. Join through a `read-through hypothesis` object as already specified in the 2026-08-16 earnings architecture.
2. Treat GMI W4 (`SUPPLIES`/`ENABLES`/`BOTTLENECK_OF`) + GR3b (8-K name extraction) + Defense D5/D10 as the three existing build ramps. Economic Propagation is a **consumer and honesty layer**, not a fourth spine.
3. Heal the registry collision: `earnings-intelligence.owns` still says “read-through context”; DEC assigns group-grain read-through to `group-reads`.
4. Keep CHF / TXI / CSP off any firm-level economic edge.

### NO-BUILD / DO-NOT-INFER WARNINGS

- `DNR:KILL-CAUSAL-DAG-ALPHA` — no DAG→alpha.
- `DNR:KILL-LLM-CONFIDENCE` — no LLM numeric confidence.
- `DNR:KILL-THESIS-LOBE` — no new thesis lobe.
- `DNR:LAW-REVIEWED-MANIFEST-CENSUS` — do not treat `#5424` defense20-v1 as live.
- `DNR:KILL-PSS-SR3-PARTICIPATION` — participation is display-tier.
- Do not infer customer/supplier from 8-K Item 1.01, from theme co-membership, or from residual correlation.
- Do not invent 60 (or 40) `VERIFIED_CASE` primaries. Follow Defense D0R Gate 5 honesty.
- Do not collapse the three graphs into one edge.

---

## 1. Anti-duplication ownership map

Object types requested by the commission. One row per **current object**, not per wish.

| Object type | Current object | Owner | Contract | Producer | Reader | Temporal semantics | Authority | Maturity | Active PR collision |
|---|---|---|---|---|---|---|---|---|---|
| theme | TIL phase / thesis / crosswalk | `thematic-intelligence` | theme_crosswalk + `neuralweb.theme_*` | `build_thematic_state.py` nightly | NW, Prophet context | `computed_at`; phase-history PIT jsonl | context_only | operating | none specific |
| theme | GMI nodes (`theme:*`, `ltheme:*`, `co:*`, baskets, ETFs) | `gmi-theme-graph` | `theme_graph.nodes.v1` | `scripts/build_theme_graph.py` | synapse `consumers: []` | bitemporal `valid_*` + `belief_time` + `computed_at` | all six authority flags false | operating spine; ThemeState not built | #5894 identity bridge (GMI → Data OS) |
| mechanism | `earnings_mechanism_observation/v1` | **architecture only** (`earnings-intelligence` candidate) | specified in 2026-08-16 architecture; **no live schema file found** | none | none | designed `known_at` | context_only (spec) | research | WS:EARNINGS-INTELLIGENCE-OS is E2-scoped, not this object |
| mechanism | TXI chain hops (`knowledge/transmission/*.yaml`) | `policy-transmission-intelligence` | `transmission_chains.v1` | `engine/transmission_chains.py` nightly | NW `transmission_chains` lobe; site card | episode SM: dormant→arming→propagating→expressed\|failed\|expired; nightly ledger | display_only; DNR:KILL-CAUSAL-DAG-ALPHA | operating (hypothesis tier) | none |
| mechanism | CHF frontier cells | `causal-hypothesis-factory` | `neuralweb.causal_lab_state.v1` | `scripts/build_causal_frontier.py` | research workbenches | drift-only nightly | research_only; not_a_signal | operating research | none |
| economic relationship | GMI reserved edge types `SUPPLIES`/`ENABLES`/`BOTTLENECK_OF`/`BENEFITS_FROM`/`CATALYST_OF` | `gmi-theme-graph` (W4 planned) | `theme_graph.edges.v1` enum | not emitted in W1b | none | would inherit bitemporal law | display / zero authority | **reserved-null** | do not start W4 without ThemeState merge-order ruling |
| economic relationship | GR linked-outsider 8-K edges | `group-reads` | `group_linked_outsiders.v1` | `build_baskets.py` after pulse | entry_radar nominations; **no template fetch** | 24-month 8-K window; tape state is today | context_only; **no CS labels** | code live, **source-inert** (0 counterparties measured 2026-08-08) | GR3b not an open PR this census |
| economic relationship | GovRev recipient graph `defense19-v1` | `government-revenue-foresight` | `government_recipient_entity_graph.v1` | reviewed manifest | GovRev dossiers | ownership intervals `valid_from`/`valid_to` | context_only | **identity graph live**; not economic | **#5424 defense20-v1 OPEN, not live**; #5856 labels; #5882 defects |
| economic relationship | Bio ontology fixture | `biocatalyst` | `ontology.v1` fixture only | none in production | none | asset×indication×owner temporal unit | context_only | fixture / D0A forbids auto peers | #5821 BCI architecture; #5906 P0-C2; #5909 JV recon |
| customer/supplier | *no live object* | — | — | — | — | — | — | **MISSING** | do not mint under Defense D1 or Bio P0 |
| beneficiary/loser | TIL `theme_pathways` | `thematic-intelligence` | `neuralweb.theme_pathways.v1` | `build_thematic_state.py` | NW cortex | config-compiled + live legs | context_only; TI-R5 no shock-to-beneficiary | operating | none |
| beneficiary/loser | Demand Desk chains | Demand Desk (**UNREGISTERED as a program key in the slice read**) | none in GR/GMI set | `build_stock_library.py` / `demand_ledger.py` | stock-library panel | annual/quarter, mixed FYs | **housing display-only; `ai_datacenter` emits scored theses** | operating adjacent | HIGH authority leak if reused |
| bottleneck | Foresight `engine/bottleneck.py` | Thematic Foresight Desk (TIL-adjacent) | shadow bands | foresight nightly | foresight desk | FRED/XBRL nowcast; provisional cutoffs | display; Wave 3a backtest pending | operating shadow | none |
| bottleneck | Defense D10 Industrial Bottleneck Atlas | `government-revenue-foresight` | not built | — | — | — | — | SPEC_ONLY / D8+ | do not start D10 in D1 |
| propagation chain | TXI YAML library (7 chains) | `policy-transmission-intelligence` | `knowledge/transmission/SCHEMA.md` | `transmission_chains.py` | NW + site | hop lag windows; nightly episode ledger | display_only | operating hypothesis | none |
| propagation chain | CSP contagion hop (Korea→memory→tech) | CSP / `international-risk-intelligence` (wiring) + XSR organs | `contagion_state.v1` planned | `engine/contagion.py`, NW `contagion_regime` | NW brief, MM stub | coincident / nightly; not firm-level | context_only; `DNR:KILL-LLM-CONTAGION-TAGS` | operating wiring | not a firm graph |
| peer group | US curated baskets `data/baskets/membership.json` | consumed by `group-reads`; roster owner is the basket registry | membership JSON | membership pipeline | GR pulse/earnings/outsiders | PIT `added`/`removed` vs `as_of` | n/a (input) | operating | HIGH vs TIL themes / GMI `MEMBER_OF` |
| peer group | Bio `trial_peer_set.v1` | `biocatalyst` | `trial_peer_set.v1` | `engine/biocatalyst/peer_matrix.py` | Bio workbench | caller-supplied NCT list; `as_of` | source_fact; no rank | operating comparison API | **does not assert commercial peers** |
| market co-movement | `group_pulse.v1` + episodes | `group-reads` | in-module + tests (no `contracts/*.json`) | `build_baskets.py` | basket detail, baskets desk, sector_central, entry_radar | snapshot `as_of` = last member-tape session | context_only; no fused score | operating | name collision with `live/basket_pulse.json` |
| market co-movement | sympathy ledger | `group-reads` | `group_earnings_pulse.v1` sympathy block | nightly `append_sympathy_ledger` | basket detail GRE | 8-quarter window; floors; null below | context_only; **description not causal** | operating | registry drift vs EI “read-through context” |
| market co-movement | residual / contagion organs | CSP + XSR + IRD | various | nightly / fastpath | boards + NW | coincident | context_only | operating | residual **market** graph, not economic |
| read-through hypothesis | `earnings_readthrough_hypothesis/v1` | **architecture only** | 2026-08-16 §2.6 | none | none | designed timestamps | context_only (spec) | **not built** | do not park under GR or EI without a DEC |
| read-through hypothesis | GR sympathy + earnings pulse | `group-reads` | `group_earnings_pulse.v1` | `build_baskets.py` | basket detail | season 75 sessions | context_only | operating (group grain only) | DEC vs EI `owns` wording |

---

## 2. System-by-system audit

### 2.1 Thematic Intelligence / Theme Graph / GMI

**CODE VERIFIED.**

| | TIL | GMI Theme Graph |
|---|---|---|
| Program key | `thematic-intelligence` operating | `gmi-theme-graph` building |
| Owns | phase, lifecycle, evidence legs, falsifiers, crosswalk | entities, evidence edges, transmission context, cross-market composition |
| Does not own | basket participation, earnings read-through, GMI composition, Prophet | GR participation, TIL lifecycle, Prophet, a product surface |
| Implementation | `config/theme_crosswalk.yml`, `engine/neuralweb/theme_{thesis,pathways,asymmetry}.py`, `thematic_state.py` | `engine/theme_graph/*`, `contracts/theme_graph/*`, `scripts/build_theme_graph.py` |
| Registry lie | — | `implementation: []` and note “runtime roots are absent at the audited baseline” are **stale**. W3A #5718 shipped the engine. |
| Authority | context_only | synapse six-false; G0.11 recency/id order only |
| Next | not this census | W3B ThemeState **blocked on merge-order ruling** with Prophet V4 D-lane (`WS:GMI-THEME-GRAPH` TRANSMISSION wave; `research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md`) |

W1b emits membership/expression/track only. W4 is the first wave that would write economic edges, and it is supposed to start from GR linked-outsiders + XBRL fingerprints + GovRev `CATALYST_OF`. Those inputs are either empty (GR3) or identity-not-economic (GovRev).

### 2.2 Group Reads

**CODE VERIFIED.** Operating. `authority_class: context_only`.

Owns group-grain participation, sympathy, and linked-outsider **context**. Does not own issuer event/claim truth (`DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`).

Waves in-repo are GR0–GR4 / GR3b, not “W-C”. Memory of a W-C arc re-cut is account-local; the masterplan table is GR*.

Linked outsiders: closed vocab `merger_related|financing|license|collaboration|supply_agreement|purchase_agreement|disclosed_agreement`. Knowing two names signed a supply agreement does not say who supplies.

### 2.3 Transmission Intelligence

**CODE VERIFIED.** Program key `policy-transmission-intelligence`. Alias `transmission-intelligence` is `subprogram_of` that key.

This is **macro→asset staged cascades**, not firm-to-firm economic transfer. Library on HEAD:

- `real_rate_peak_gold_rerate` (rev 1; operator 2026-08 gold case)
- `real_rate_peak_crypto_rerate`
- `oil_slide_disinflation_duration_rerate`
- `oil_inflation_duration_derate`
- `credit_spreads_refinancing`
- `dollar_spike_em_multinational`
- `vol_regime_deleveraging`

Instrument verdict ≠ market verdict (`research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md`). A `failed` hop is a window miss.

### 2.4 Earnings read-through

Two grains, one wording collision:

1. **Group grain** — `group-reads` / `group_earnings_pulse.v1` / sympathy. Live.
2. **Issuer event grain** — `earnings-intelligence` evidence packets (`earnings.fact_pack/v1`, `claim_graph`, `event_workspace.v1`). Live substrate; E2 is the workspace render.
3. **Mechanism-specific hypothesis** — architecture only (`earnings_readthrough_hypothesis/v1`). Not built.

`earnings-intelligence.owns` still lists “read-through context” (`config/mastermind_programs.yml` ~2055). DEC says that clause is leftover wording. Treat DEC + GR `owns` as the ruling.

### 2.5 Defense graph / economics

Owner: `government-revenue-foresight`. Workstream `WS:DEFENSE-PROCUREMENT-V3`.

Live: reviewed **identity/ownership** graph `recipient-graph:reviewed:2026-08-08:defense19-v1` (19 companies, 101 legal, 101 ownership edges). CODE VERIFIED via `git show HEAD:data/government_revenue/recipient_entity_graph.json`.

Not live: program/mission/capability/product (D5), facility/supplier/bottleneck (D8+/D10), `#5424` defense20-v1.

D0R already froze contracts and a historical casebook. Economic Propagation must **cite**, not rewrite, `research/defense_intelligence/D0R_HISTORICAL_EVENT_CASEBOOK.md` and `D0R_GRAPH_AND_CONTRACT_FREEZE.md`.

### 2.6 BioCatalyst relationships

Owner: `biocatalyst` (building, context_only). No `WS-BIO*` workstream.

Live: trial protocol comparison (`trial_peer_set.v1` — caller supplies NCT IDs; contract text: does **not** assert a clinical or commercial peer) and sponsor map (`direct_issuer` | `parent_of_subsidiary_sponsor`).

Not live: competitive landscape, partnership economics, MOA graph. D0A forbids auto-generated peer/competitor cohorts.

### 2.7 Causal Hypothesis Factory

Owner: `causal-hypothesis-factory`. `authority_class: research_only`. Program, **not** a lobe (registry still has nine raw lobe-charter rows under this owner — named contradiction, not endorsed).

Produces frontier / surprise / lab state. Does not produce economic edges. `DNR:KILL-CAUSAL-DAG-ALPHA`.

### 2.8 Neural Web

Owner: `neural-web`. This is a **cognitive routing / synapse bus**, not an economic-relationship graph. It consumes TIL, CHF, macro-context-rail; it must not originate signals (A7).

Synapse rows for theme-graph currently list `consumers: []`. CSP contagion is a re-projection of already-computed organs into `world_state.contagion_regime`.

### 2.9 Evidence Mesh

**UNKNOWN / not found.** No code, contract, program key, or Agent OS record under that name. If a later session finds it under another title, supersede this row — do not mint a second mesh.

---

## 3. Active PR collisions (open on 2026-08-18)

| PR | Why it matters | Rule for this lane |
|---|---|---|
| #5894 V4-D2A identity authority bridge (GMI → Data OS) | identity plane Economic Propagation must reuse | do not mint a second company id |
| #5424 defense20-v1 recipient graph | would replace defense19-v1 | not live; `DNR:LAW-REVIEWED-MANIFEST-CENSUS` |
| #5856 GovRev PIT agency labels | D1 truth, not graph redesign | do not fold into a new graph |
| #5882 GovRev identity/ledger/gate defects | same | wait |
| #5821 BCI federated architecture freeze | Bio cycle OS, not commercial peers | do not invent Bio competitor graph |
| #5906 / #5909 BioCatalyst production / JV recon | identity/hydration | not relationship edges |
| #5910 alpha-intel PASS-0 | integration packet | read before any later program mint |

No open PR was found that already implements `earnings_readthrough_hypothesis/v1` or Evidence Mesh.

---

## 4. What Economic Propagation may consume vs must not own

**May consume (read):** GMI latest-belief membership, TIL pathways, GR pulse/sympathy/outsiders, EI fact packs, GovRev identity + award facts, Bio trial-peer sets, TXI chain **state** as macro context, NW contagion_regime as residual-market context, Foresight bottleneck nowcast as a physical tightness input.

**Must not own:** ticker identity (Stock Identity), theme lifecycle (TIL), basket participation (GR), issuer event truth (EI), reviewed recipient graph (GovRev), trial facts (Bio), Prophet rank/gate/size, CHF hypotheses, a second synapse bus.

**May eventually own, and only after a DEC:** the join object `read-through hypothesis` (architecture already named) plus its PIT grade ledger. That is a **record class**, not a graph rewrite.
