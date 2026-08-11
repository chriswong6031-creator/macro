# Global Market Intelligence (GMI) — Theme Graph program: adjudication + masterplan

**Status:** PHASE-0 ADJUDICATION — charter for a multi-session program; no wave beyond W0 is authorized until its own session opens with this doc's gates inline
**Date:** 2026-08-10 (session 0)
**Owner program:** `gmi-theme-graph`
**Method:** operator-commissioned external brainstorm (ChatGPT, no codebase access; 445 sections, committed at `research/theme_graph/SOURCE_MEMO_GLOBAL_MARKET_INTELLIGENCE_ORGANISM_FINAL_2026-08-10.md`) → 3-lane Sonnet digestion (`research/theme_graph/MEMO_DIGEST_PART{1,2,3}_*.md`) + 4-lane Sonnet codebase/registry census + 同花顺 screenshot study → this Fable adjudication → Opus red-team (§11).
**Sibling sources committed:** `research/theme_graph/SOURCE_V1_THS_MEMO_2026-08-10.md`, `research/theme_graph/SOURCE_V1_DYNAMIC_THEME_GRAPH_MEMO_2026-08-10.md`. Screenshot reference index in Appendix B (files remain in operator Downloads until the design wave copies its selections to `mockups/refs/theme_graph/`).

---

## §0 — ACCEPTANCE GATES (bind every wave; a wave PR that violates one is not done)

- **G0.1 Tier law.** Every GMI artifact ships display-tier: synapse-registered (`config/synapse.yml`) with `tier: display`, `weights: none`, `scored_path_surfaces: []`, and all five authority booleans (`can_rank/can_size/can_gate/can_originate_signal/can_escalate`) literal `false`. No fused composite anywhere (`DNR:KILL-FUSED-COMPOSITE` class): theme readings are printed as named legs; state/lifecycle labels come only from deterministic thresholds baked once from history (the TOPA threshold-baking pattern), never from a weighted blend, never from an LLM.
- **G0.2 Point-in-time law.** Every graph edge is bitemporal (`evidence_time`, `belief_time`, `valid_from/valid_to`; `effective_time` where the underlying reality lags publication — memo §206, adopted). Reconstructed history is era-labeled (`era="reconstruction"`) and is never promotion evidence, matching the Konseki authenticated-vs-reconstruction distinction and DRL's gap-era rule. **Semantic-leakage law (new, named):** an LLM-assisted edge may cite only dated evidence documents; membership backfilled from a model's general knowledge (undatable) is forbidden — that is look-ahead smuggled through language (memo §190, §103). No historical theme claim ships while the membership snapshot cadence is stalled (§2.6 defect).
- **G0.3 No-parallel-organ law.** Named owners keep their territory: Group Reads (basket participation/earnings reads), Contagion Sensing (attention/propagation keys), TOPA + Short-Side docket (top/fragility species), DRL `engine/price_pressure/` (residual shocks), CN limit-alpha (limit ecology, auction, Tushare spine), `china_*` collectors/engines (CN participants/flows/intel), Konseki Market Memory (memory/salience/cortex machinery), Prophet (pick authority), TIL/Thematic Foresight Desk assets (§2.5). GMI extends owners through their own pipelines via the §5 contracts; it never re-detects, re-scores, or re-surfaces what an owner already emits (`DNR:KILL-ROTATION-SCHEDULE`, `DNR:KILL-PROPHET-POP-MERGE` precedent class).
- **G0.4 CN data law.** CN price/limit truth comes only from authorized planes (unadjusted TuShare spine, `china_stocks_raw`, receipted collectors). The adjusted-price limit tape is permanently closed (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`). THS concept scrapes keep their complete-or-fail receipts. No architecture may assume real-time Northbound flow (dead since 2024 — memo §33/§432; historical aggregates only, availability re-verified at build time).
- **G0.5 Forward-claim law.** Theme expectations accrue in an internal graded ledger first. No user-facing "which theme ignites next" or ranked forward surface until ≥30 graded calls + printed honest-null + operator ruling (`DNR:HOLD-IGNITION-SURFACES` is the standing cautionary precedent; `DNR:KILL-FORCED-CALLS` binds). Falsifier/refutation language never front-facing (operator 2026-07-27): user surfaces show windows and "what we're watching", full verdicts live on the Calibration Lab.
- **G0.6 LLM law.** Constitution Article 1 / A7 is absolute: no LLM-originated signal, score, weight, confidence, escalation, or narrative tag into any organ (`DNR:KILL-LLM-ORIGINATION`, `DNR:KILL-LLM-CONFIDENCE`, `DNR:KILL-LLM-FRAME-TAGS`, `DNR:KILL-LLM-CONTAGION-TAGS`). LLM roles in GMI are exactly three, all display-tier, provenance-stamped, curation-gated: (1) propose candidate taxonomy (names/merges/splits) into a probation queue a human ratifies; (2) disambiguate collisions between existing vocabulary entries; (3) de-escalate per A3. Deterministic math computes every number.
- **G0.7 Ship law.** Session-chain program (context economy): one wave per session, durable state in this doc's §11 execution record + a continuation handoff; each wave lands commit → push → PR → merge-on-green → live verification. Graph compute runs in the nightly collect lane, never the render path; heavy artifacts go to R2. Nightly remains the sole advancer of forward ledgers.
- **G0.8 Design law.** Any user-facing surface goes through the design lane (DESIGN_DOCTRINE.md + frontend-design skill; opus `designer` chooses, `builder` implements a pinned spec): glance tier = state + plain-word stance, technicals demoted to Tier-2 receipts, zh copy laws (红涨绿跌; zh authored, not translated), no third nav family, `docs/site_semantics/` rows for every new stat.
- **G0.9 Vocabulary honesty.** GMI's crosswalk unifies the existing theme vocabularies; it must never become vocabulary N+1 with its own drift. Every GMI theme node must resolve (via `expresses`/`same_as` edges) to the vocabularies users already see, and `DNR:KILL-PARALLEL-KNOWLEDGE-BASE` binds: the graph is a product data artifact (like `data/group_pulse/`), not a second hand-curated knowledge store parallel to the Macro Context Index.
- **G0.10 Instrument-verdict law.** A theme state label, window expiry, or chain-failed expectation is an instrument verdict, never a market verdict (operator 2026-08-09): syntheses lead with the dual-read against the tape; scope-limited phrasing ("no broadening within the declared window", never "theme dead").

---

## §1 — Provenance and how to read this program

The source memo is a deliberately expansive research notebook — its own handoff directive (§351) sorts its 445 sections into **architectural principles** (strong recommendations), **research hypotheses** (deserve empirical testing), and **creative metaphors** (stimulation, not features), and warns: "Do not accidentally promote the third category into production because the name sounds cool." This masterplan honors that sort: §3 adjudicates category 1 into architecture, §6 turns category 2 into a preregistered research queue, and Appendix C parks category 3 in an ore ledger where the names survive without becoming features. Per the operator's direct instruction, the creative reasoning is preserved: nothing is silently dropped — every load-bearing memo concept appears in §3, §6, §9, or Appendix C with a disposition and a reason.

Reading order for future sessions: this doc §0–§2 → the digest for the part you're working → the source memo section itself (always open the primary source before acting on a digest claim).

---

## §2 — Ground truth: what actually exists (census, 2026-08-10, HEAD `565450418c`)

The memo was written blind to the codebase and systematically underestimates it. The census verdict in one line: **almost every organ the memo proposes exists in some form; what does not exist anywhere is the connective tissue — a point-in-time, evidence-backed, cross-market semantic topology.**

### 2.1 Theme assets today

| Family | What exists | Freshness / defect |
|---|---|---|
| US baskets | 49 curated baskets (`data/baskets/membership.json`), `engine/baskets.py`, folded into Sector Central | curated 2026-08-07 (fresh) |
| US theme analytics | `engine/theme_scoring.py` (0–100 + lifecycle labels + ENTER/AVOID), `theme_flow_rollup.py` (ETF-holdings flow), `theme_crowding.py`, `group_flow.py` stages, `theme_tape.py`, `themes_heatmap.py` | live nightly; **nothing grades theme_scoring's calls** |
| US theme discovery | `engine/theme_discovery.py` (co-movement), `theme_emergence.py` (EDGAR scarcity clusters), `theme_fingerprint.py` (XBRL physical reads) | display-only, human-curated-in — the lawful LLM/discovery pattern already exists |
| Group Reads (live program) | `engine/group_pulse.py` / `group_earnings.py` / `group_linked_outsiders.py`; `data/group_pulse/*.parquet` (episodes/sympathy/linked-outsider edges); READ bands on basket pages | as_of 2026-08-10; CN/HK twin = GR4 backlog |
| CN themes | 237 THS concept baskets, 3,532 member-rows (`data/baskets_china_ths/`), `collectors/china_ths_concepts.py` (373 concepts, receipted scraper), `engine/baskets_china.py`, `cn_theme_tape.py` (heat × Prophet why-not), `narrative_radar.py` surface | membership curated 2026-06-30; **only 2 PIT snapshots ever taken (2026-06-30, 2026-07-08) — PIT history stalled** |
| CN legacy | 22 hand-curated baskets | dead (stub page) — do not revive |
| Regional | Canada 16 / HK 14 / Intl 17 baskets | curated mid-June |
| Taxonomy | US GICS map (`data/breadth/ticker_sectors.parquet` + S&P-1500 PIT membership); CN has THS's own categories only | **no US↔CN bridge of any kind** |
| Foresight desk | 18-theme desk with stage machine, thesis monitor, graded ledger (45 rows), demand desk (40 theses), divergence radar + IC harness (113 theses / 3,860 snapshots) | see §2.5 TIL |

### 2.2 Cognition assets (Konseki Clean Room Market Memory — the operator's "Cognitive Architecture", frontier ≈ W4A→W5)

Shipped: W0 current-context surface + typed temporal contract; W1A immutable bitemporal capture spine; W1B trusted source receipts + actual-output canaries; W2 sealed Forecast/OutcomeRecords + proper-score kernel (no production callsite yet); W3A playback-catalog scaffolding; W4A exact-distance episodic retrieval with purge/embargo (synthetic coordinates only). Specified, unbuilt: W5 Operating Cortex (salience/surprise), W6 research factory, W7 gated feature promotion. Latent/learned encoders parked to 2027 by standing ruling.

**Consequence for GMI:** the memo's PERSISTENT WORLD MODEL / MEMORY / SALIENCE / EXPECTATION→SURPRISE layers (§338 boxes 4–6, 9–10) are Konseki's chartered territory with real shipped substrate. GMI builds none of that machinery. GMI's job is to make themes **first-class citizens** of it: theme-level Forecast/OutcomeRecords, theme events into the playback catalog, theme-state coordinates for analog retrieval once real (each through Konseki's own gates).

### 2.3 Neural Web, constitution, chat

128 lobes; `config/synapse.yml` registry (+ `config/lobe_charters.yml`, 109 charters); `engine/neuralweb/constitution.py` — Article 1 origination ban (A7 refused unconditionally), Article 2 scored-path perimeter, Article 3 evidence floor (Wilson CI lower-bound lift > 1.25 + freshness, lapses on staleness). Chat integration is a solved two-tier pattern: `mastermind_context.py` (`external_consumers` tag or `LOBE_SUMMARIZERS`) + `market_packet.py` fail-soft blocks reading product artifacts only (CXI-R23). The lobe-shipping checklist (12 steps, DRL as reference) is §7's template.

### 2.4 Owner map for territory the memo proposes

| Memo proposal | Existing owner | GMI relationship |
|---|---|---|
| Dislocation intelligence (Part IV) | DRL `engine/price_pressure/` + `engine/dislocation.py` (macro gauge) + `options_dislocation.py`; `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` closed the OHLCV classifier | consume + annotate (§5.5) |
| Top recognition / fragility (Part V) | TOPA (`top_anatomy_p0`, AVOID-not-SHORT per `DNR:KILL-DIRECTIONAL-SHORTING`) + `froth_fragility.py` (index-level, import-locked) + Short-Side docket species inventory | file constructions through their preregs (§5.6) |
| Market state / world model (Parts VI, IX) | `engine/market_state.py` hero, `data/regime/latest.json`, NW `world_state.py`, breadth/vol suites; AQM adjudication REJECTED deep world models; "duplicate world models" = named failure mode | consume; a third plane is refused (§9) |
| Historical memory / replay (Part VII) | Konseki W2–W4A; future-lobes docket R1 replay rail (rule-experiment registry, trial budgets) + `LAW-ERA-SPLIT`, `LAW-TIME-CLUSTERED-CI` | populate; replay questions register through R1's governor when chartered (§5.3) |
| Attention / narrative propagation | Contagion Sensing program (engine-originated contagion key + glance chip live; Ignition Radar suspended = cautionary tale) | consume as attention legs (§5.4) |
| CN limit ecology / auction / participants | CN limit-alpha (W1–W3 priced several families dead; fillability tax measured), `china_lhb/connect/flows/participation/crowding/intel_hub` | consume; its kills bind any CN entry-flavored claim (§5.7) |
| Policy → funding ladder (memo §110) | GovRev Foresight rails (announcement→award→spend separation already load-bearing) | catalyst edges consume GovRev artifacts (§5.8) |
| Prophet as output organ (§340) | Prophet US+CN with two ratified lobe-integration templates: GovRev ruling (lobe owns the WHY; byte-identical on/off proof; preregistered grader = only promotion path) and CN-alpha §10 (re-rank already-selected picks) | §5.2 adopts both templates verbatim |

### 2.5 TIL reconciliation — ⟨PENDING-TIL-CENSUS: this section is being completed from a live census of `research/THEMATIC_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` build state; the ruling slot below is reserved⟩

The Thematic Intelligence Layer (ratified 2026-07-09, build dispatched) diagnosed the same disease this program targets — "three uncoordinated theme vocabularies with no crosswalk… no theme-level thesis objects… no persisted phase-state history… no generalized beneficiary/loser graph… no NW citizenship" — and ruled "TIL is connective tissue plus honesty machinery, not new signals." GMI must either (a) absorb TIL's unshipped charter as its own W1–W4 with explicit supersession, or (b) position as TIL-phase-2 over shipped TIL substrate. The census determines which. Either way: TIL's diagnosis is adopted as prior art, its fences inherited, and its "investigation packet, never a stock pick" product target is retained verbatim as GMI's product north star.

### 2.6 The true gap list (what GMI actually builds)

1. **The graph substrate** — typed, evidence-backed, bitemporal edges over themes/companies/catalysts/supply-chain/ETFs/policies/markets. Today: flat curated lists, one hardcoded beneficiary chain.
2. **PIT membership rigor** — the memo's §405 "hindsight chart" warning describes a live defect: CN THS snapshots stalled at 2; US membership has curation dates but no edge-interval history.
3. **The vocabulary crosswalk** — foresight-18 ∪ baskets-49 ∪ THS-237 ∪ finviz taxonomies ∪ GICS, resolved into one join layer with nothing deleted.
4. **Exposure decomposition** — economic/narrative/trading axes per edge (memo §8, Tier-A3), currently binary curated membership.
5. **Graded theme expectations** — theme_scoring emits ungraded labels; no theme-level forward ledger exists; Konseki has no theme population.
6. **Cross-market translation** — global theme nodes with per-market local expressions and empirical (never hardcoded) lead-lag (memo §66–69).
7. **CN analytics parity where lawful** — Group-Reads-class reads over THS baskets (coordinated with GR4, not parallel).

---

## §3 — Adjudication of the memo (the challenge layer)

Answering the memo's own §352 challenge questions with codebase truth. Format: **ruling** — reasoning.

### 3.1 The central reframe

**Ruling: adopt the memo's §338 stack as an orientation map, reject it as a build plan.** Ten of its eleven boxes map onto live programs (§2.4). The genuinely missing box is the third: DYNAMIC THEME GRAPH — semantic topology. The memo is right that without it "the Neural Web has many sensors but fewer structured relationships" (§339), and right that Prophet should read as an output organ over shared understanding (§340) — a reframe our GovRev/CN-alpha Prophet contracts already implement in miniature. GMI = build the missing box, wire it into the ten that exist.

### 3.2 Tier-A rulings (memo §281)

- **A1 Dynamic multi-label Theme Graph — ADOPT, as a deterministic rail.** Learned/dynamic graph structure is closed until at least 2027-01-15 (`DNR:KILL-CAUSAL-DAG-ALPHA`, `DNR:HOLD-STRUCTURE-LEARNERS`); the lawful construction is exactly what the memo's Tier A actually needs: explicit typed edges with evidence, deterministic edge math, append-only history. The AQM adjudication's salvage path ("deterministic edge-outcome ledger, display-tier") is this program's W3.
- **A2 Point-in-time edges — ADOPT + HARDEN.** Real defect found (§2.6.2). Edge schema is bitemporal from day one; Konseki's typed temporal contract is the house pattern to reuse; memo §206's `effective_time` is adopted as a fifth field where reality lags publication (e.g. a filing's period-end vs filing date). This is the program's hardest engineering problem, as the memo predicts (§358).
- **A3 Economic/Narrative/Trading separation — ADOPT as evidence axes; PROBE before trusting.** The three-realities decomposition (§8) is architecturally sound and maps to evidence sources we own (XBRL/filings via `theme_fingerprint` + EDGAR; attention/contagion keys; co-movement/factor behavior). But whether the axes measurably disagree in stable, decision-relevant ways on OUR data is an empirical question — W2 runs it on a pilot universe before the full build (§352.9's pilot instruction; house ore law).
- **A4 Persistent Theme State — ADAPT: legs, not a score.** The §22/§147 ThemeState object ships as named legs (price/breadth/leadership/flow/attention/catalyst-recency/crowding + lifecycle label). The memo's own §360 ("ThemeComposite = 0.7127" is not the product) and §123 (no intuition-built scores) agree with house law. Strength-vs-health (§148) survives as two *leg families*, never two numbers.
- **A5 Universal world-state interface — ADAPT: consume, don't build.** ThemeState rows carry regime context read from `data/regime/latest.json` + `world_state` keys (advisory). A GMI-owned market-state plane is refused (§9.3).
- **A6 Historical theme factors — ADOPT with era discipline.** Theme factor/residual families (§45–46) compute over PIT membership only; era-labeled reconstruction never feeds promotion; `LAW-ERA-SPLIT` + `LAW-TIME-CLUSTERED-CI` bind every historical claim.
- **A7 Eventization — ADAPT: emit into existing streams.** Theme state transitions become typed events consumed by Konseki's playback catalog and the existing event surfaces. No new event bus; no new salience engine (Konseki W5's charter).
- **A8 Expectation→Surprise→Outcome — ADOPT via population, not machinery.** Every meaningful state transition emits expected-consequence windows (§355 — "perhaps the single most important instruction") into a graded theme ledger (closure-tolerant forward chains per CN-alpha law), sealed as Konseki W2 records. Surprise/salience computation stays in Konseki.

### 3.3 Tier-B (research hypotheses) — chartered as §6's preregistered queue, not built

Each Tier-B idea (lifecycle transitions, leadership renewal, breadth acceleration, hidden beneficiaries, narrative/economic disagreement, catalyst elasticity, attention acceleration, theme market share, cross-market transmission, dislocation resolution, theme fragility) enters §6 with an owner-pipeline note where territory exists — e.g. leadership renewal must reconcile with TOPA's measured wrong-sign ore body (topped episodes are YOUNGER/HOTTER — the theme-level sibling hypothesis inherits that finding as a prior); theme fragility files through the Short-Side docket's species prereg ladder; dislocation resolution consumes DRL's resolved ledger.

### 3.4 Tier-C (metaphors) — PARKED in Appendix C's ore ledger

Narrative Rₙ, Theme Gravity/Entropy/Pressure/Potential-Energy, Attention Efficiency, Narrative-Capital/Capital-Price Conversion, Theme Frontier: preserved as named research vocabulary with the memo's own definition pointers. None may appear in code, schemas, or user copy. A Tier-C name may graduate only by passing through §6 as a preregistered construction under a plain descriptive name.

### 3.5 Tier-D (later-stage) — REFUSED-FOR-NOW, aligned with standing rulings

Autonomous theme discovery, Research-Cortex self-expansion, large-scale causal graph learning, full participant behavioral inference, continuous counterfactual simulation: the memo itself says wait; house rulings agree and add teeth (structure learners held to 2027; Konseki W6 owns the research-factory slot; replay questions go through the R1 rule-experiment registry when that rail is chartered).

### 3.6 Corrections to the memo's beliefs about Mastermind

The memo names "Risk Radar, Rotation Engine, Short/Top Recognition, Fundamental Forensics, Alternative Data Network" as existing systems (§107, Part VIII). Census truth: Risk Radar exists (caps the hero verdict); rotation lives in `theme_scoring` + RRG subsector rotation (not one "Rotation Engine"); short/top = TOPA + froth_fragility + docket (display-only, AVOID-not-SHORT — the memo's occasional short-alpha framing is unlawful here); "Fundamental Forensics" ≈ qualitative-intelligence organs + `theme_fingerprint`; "Alternative Data Network" is not a system — it is assets (GovRev SAM, Citrini institutional feed, THS scrapes, EDGAR/XBRL). Part VIII's wiring prescriptions are therefore re-derived in §5 from real seams, not adopted from the memo.

### 3.7 What makes this smarter than the memo (§361's demand)

1. **Bitemporal edges ride Konseki's proven contract pattern** instead of the memo's from-scratch five-way time model — adopting only `effective_time` as net-new.
2. **Evidence objects are receipts**, the discipline this house already runs (Konseki source receipts, GovRev append-only ledgers, THS complete-or-fail scrapes) — the memo's §204 "evidence as first-class nodes" is a schema alignment, not an invention.
3. **The supply-chain graph starts from data we already own**: `group_linked_outsiders` 8-K counterparty edges + `theme_fingerprint` XBRL physical reads give evidence-backed SUPPLIES/ENABLES edges on day one — the memo assumed this required new licensing.
4. **The catalyst ladder is already built**: GovRev's announcement→authorization→appropriation→award→spend rails ARE memo §110; GMI links, not builds.
5. **Fragility hypotheses inherit TOPA's measured surprise** (young/hot tops) and CN claims inherit CN-alpha's measured fillability tax — the memo's enthusiasm for seal-quality/entry signals meets a house that has already priced several of those families to null at daily resolution.
6. **Licensing tags (§211) become synapse-entry metadata convention**, not a new system; datum-level provenance rides the evidence refs.
7. **The product layer inherits a proven native pattern the memo never saw**: 同花顺's per-module AI 解读 one-liner is our glance-tier plain-word stance law already shipped across the site — GMI surfaces extend it rather than inventing legibility.

### 3.8 同花顺 lessons — adopt / refuse (screenshot study, Appendix B)

**Adopt at product layer:** information-density-over-chrome (§39's "copy the ontology, not the UI"); progressive disclosure ≈ our Tier-2 hover/receipt law; the 商品联动 rendered causal-chain table (futures → sector → instrument, each hop showing its own tape) as the display idiom for graph edges — the best product expression of "edges with evidence" observed anywhere in the study; theme chips on news surfaces as lightweight vocabulary exposure; 涨跌停对比/昨日涨停表现 compact cohort tiles as CN speculation-ecology legs (data via CN-alpha planes).
**Refuse:** UI cloning; any 景气度-style proprietary composite (fused score, would violate G0.1 — though its per-sector→instrument disclosure pattern is adopted); a 冲刺涨停 prediction card (that territory is CN-alpha's Prophet-propensity charter, and `DNR:KILL-FORCED-CALLS` binds); sentiment-gauge-as-oracle (our CN sentiment organs stay separate-axis, §15's direction/quality split is adopted as legs).

---

## §4 — Architecture (the substrate)

### 4.1 Object model (contracts before code; schemas land as `contracts/theme_graph/*.schema.json` in W1)

**Nodes** (`data/theme_graph/nodes.parquet`): `node_id` (stable slug), `kind` ∈ {theme, company, etf, catalyst, policy_program, commodity, participant_class, market}, `names` {en, zh}, `market_scope` ∈ {US, CN, GLOBAL, …}, `tier` ∈ {macro_category, theme, micro_theme}, `status` ∈ {candidate, canonical, retired, merged→target}, birth/retire dates + provenance. Themes die and merge; dead themes are retained (theme-level survivorship law — memo §189).

**Edges** (`data/theme_graph/edges.parquet`, append-only): `edge_id`, `src`, `dst`, `type` ∈ {MEMBER_OF, EXPRESSES, SAME_AS, TRANSLATES_TO, PARENT_OF, RELATED, SUPPLIES, ENABLES, BOTTLENECK_OF, BENEFITS_FROM, CATALYST_OF, TRACKS, HEDGES}, exposure axes where applicable (`economic`, `narrative`, `trading` — each a small enum {none, weak, core} + evidence refs, never a free float), `evidence` (list of receipt refs), `source_class` ∈ {curated, filing, co_movement, scrape, llm_proposed_ratified}, bitemporal fields per G0.2, `confidence_basis` (deterministic formula id, never a bare number without basis).

**Evidence** (`data/theme_graph/evidence.parquet`): receipt rows — `evidence_id`, `kind` (filing/xbrl/8k_counterparty/scrape_receipt/comovement_stat/news_item/operator_curation), `published_at`, `effective_at`, `source_ref` (path/accession/url-hash), `licensing` tags (`internal_ok/display_ok/redistribution_ok/retention` — memo §211). Contradictory evidence coexists as separate rows; nothing nets (memo §205).

**ThemeState** (`data/theme_graph/state/YYYY-MM-DD.parquet` + `latest.json` for surfaces): per canonical theme per session: price legs (theme factor return, residual vs market/sector — `peer_basis` disclosed per DRL's law), breadth legs (from group_pulse where a basket expresses the theme), leadership legs, flow legs (`theme_flow_rollup`), attention legs (contagion keys; THS 热度 where receipted), catalyst-recency legs (event refs), crowding legs (`theme_crowding`), regime context (read-only), `lifecycle_state` (deterministic label), `data_coverage` chip (which legs are null and why — nulls printed, never hidden).

**Expectation ledger** (`data/theme_graph/expectations.parquet`, nightly-advanced only): on qualifying state transitions, emit typed windows (`expected_consequence`, `horizon_sessions`, `declared_at`, closure-tolerant chain rules, grade fields). Sealed into Konseki Forecast/OutcomeRecords via §5.3. Honest-N = distinct episodes, never fires.

### 4.2 Namespace & registration

`engine/theme_graph/` (new; "theme_graph" collides with nothing — `engine/theme_*.py` singles stay untouched), `scripts/build_theme_graph.py`, `data/theme_graph/`, `contracts/theme_graph/`, synapse entries `theme-graph-{nodes,edges,state,expectations}` (display, booleans false), lobe charter row, `tests/test_theme_graph*.py`. Nightly step in `daily.yml` collect lane, non-fatal, `COLLECT_LANE=nightly`-gated ledger writes.

### 4.3 The crosswalk ⟨PENDING-TIL-CENSUS: final vocabulary inventory and whether a partial crosswalk shipped under TIL⟩

Every existing vocabulary keeps living exactly where it lives (foresight-desk themes, 49 US baskets, 237 THS concepts, finviz taxonomies, GICS, Group Reads' basket ids). GMI adds `EXPRESSES`/`SAME_AS`/`TRANSLATES_TO` edges resolving them to canonical theme nodes. The crosswalk is judged by G0.9: if a surface can't resolve its vocabulary through the graph, the crosswalk failed; if GMI mints names users never see elsewhere, it failed the other way.

### 4.4 LLM roles + the semantic-leakage law

Per G0.6. Implementation detail that makes it enforceable: LLM-proposed taxonomy writes only to a probation queue (`data/theme_graph/probation/`) with `source_class=llm_proposed`; ratification (operator or explicitly delegated curation session) flips nodes to canonical with the ratifier recorded. Every LLM-assisted edge lists ≥1 dated evidence ref; a CI check refuses `llm_proposed_ratified` edges whose evidence list is empty or undated. Historical backfill jobs run with the LLM disabled entirely — reconstruction edges come only from dated documents and deterministic co-movement, era-labeled.

### 4.5 Rail vs lobe classification (future-lobes docket §1 taxonomy) ⟨PENDING-TIL-CENSUS: confirm against TIL's self-classification⟩

Honest sort: the **substrate (nodes/edges/evidence/crosswalk) is a RAIL** — it serves every lobe and has no objective function of its own. The **graded expectation organ is a thin LOBE** (own objective: do declared theme-state windows verify?; own FDR family; own falsifiers). The **sensorium items are WAVES on existing organs** (CN reads → GR4 coordination; attention → Contagion; fragility → TOPA/docket). Misfiling all of this as "one big new lobe" is exactly the sprawl the docket warns about, and the memo's own organism framing survives intact across the sort.

---

## §5 — Integration contracts (the "deeply integrate into the entire system" deliverable)

Each contract names: what flows, in which direction, with what authority, and its proof obligation.

1. **Group Reads (basket reads; GR4 CN twin).** GMI consumes `data/group_pulse/` + `site/basketdata/*.json` as breadth/participation/earnings legs wherever a basket `EXPRESSES` a theme. GMI's CN membership spine (W1) is built as the substrate GR4 needs, coordinated in GR's masterplan before any CN read ships — GMI never computes participation itself. Proof: zero duplicated stat names; `docs/site_semantics/` rows disambiguate.
2. **Prophet (both markets).** GovRev-template annotation: theme context (which canonical themes a pick expresses; those themes' state legs) attaches post-selection; byte-identical board on/off proof required; GMI can neither source nor veto a pick. Any future re-ranking use rides CN-alpha's §10 pattern behind its own preregistered gauntlet. Prophet hierarchical context (memo §341–342: was the miss theme-level or expression-level?) lands as autopsy annotation in the existing postmortem stores, display-only.
3. **Konseki Market Memory.** GMI populates: theme Forecast/OutcomeRecords (sealed, proper-scored), theme transition events into the playback catalog, and — once ThemeState history is real (not reconstruction) — theme coordinates for W4A analog retrieval. All through Konseki's contracts and G-gates; GMI builds no memory machinery. Direction: GMI→Konseki writes via Konseki's capture spine; GMI reads analogs back only for display with era/effective-N disclosures.
4. **Contagion Sensing.** Contagion/attention keys are consumed as ThemeState attention legs via the crosswalk. GMI adds no attention detector; any "attention leads price" claim grades contagion's existing keys at theme level in §6. Ignition-surface law (G0.5) inherited.
5. **DRL (price pressure).** DRL events gain a display-only `theme_cohort` context axis (which themes the shocked name expresses; whether the residual is theme-wide or idiosyncratic — memo §71's price-vs-theme type). DRL's masterplan already fenced "basket residual = context axis only"; GMI rides that fence. The LSR fence stays LSR-pure; GMI never classifies shock causes.
6. **TOPA + Short-Side docket.** Theme-level maturation/fragility constructions (leadership renewal, breadth divergence, §77's state machine states) are offered as candidate species THROUGH the docket's prereg ladder with TOPA's inversion finding as prior. GMI ships only display legs meanwhile. AVOID-not-SHORT absolute.
7. **CN limit-alpha.** GMI consumes zt-pool/limit-tape (authorized planes) for CN speculation-ecology legs (昨日涨停 cohort by theme, board-aware normalized). Auction/fillability kills bind: no CN theme surface may imply an entry edge at daily resolution. The 冲刺涨停-class prediction stays in CN-alpha's Prophet-propensity charter.
8. **GovRev Foresight.** Policy catalyst edges (`CATALYST_OF` policy_program→theme) consume GovRev's rails/artifacts with their funding-stage semantics intact (announcement ≠ cash — §110). No timing predictions (`DNR:KILL-POLICY-TIMING-PREDICTOR`).
9. **Mastermind chat.** One `LOBE_SUMMARIZERS["theme_graph"]` entry + a THEMES block in `market_packet.py` reading `latest.json`/`site` artifacts only (CXI-R23): answers "why is X moving" with graph neighborhood + state legs + provenance, in plain words. This is memo §178's product surface at near-zero marginal cost once artifacts exist. Leak-screen sentinels inherited; nothing chat outputs persists into GMI state (NAR-R4).
10. **Site surfaces.** Extend existing families first: Sector Central flyout, basket detail pages (theme chips + graph context band), `state_of_themes.html`, `narrative_radar.html`, cn theme pages. New pages only via the design lane after W3, and none may become a rotation-schedule surface (`DNR:KILL-ROTATION-SCHEDULE`).

---

## §6 — Research program (hypotheses before software; each row = future prereg, none authorized here)

Pilot rule (memo §352.9): every probe runs first on a pilot universe of 3–5 themes per market chosen for contrast (one mature/broad, one young/narrow, one cross-market, one CN-only speculative, one US-only institutional). Every prereg carries: episode-level honest-N, era-split, time-clustered CIs, survivorship statement (dead themes included), and the coverage-floor law for nullable inputs.

| # | Hypothesis (memo §) | Data readiness | Honest clock |
|---|---|---|---|
| R1 | The three exposure axes disagree measurably & stably (§8, §42) | filings/XBRL + co-movement + attention keys: ready on pilot | short — cross-sectional |
| R2 | Breadth acceleration leads continuation vs exhaustion (§23, §77) | group_pulse + baskets history: partial | needs PIT accrual for theme-level; basket-level proxy sooner |
| R3 | Leadership renewal distinguishes rotation from distribution (§49, §167) | prices ready; TOPA prior binds | medium |
| R4 | Attention → price lead (contagion keys graded at theme level) (§23, §436) | contagion history: check depth | medium |
| R5 | Exposure-disagreement episodes resolve directionally (hidden-beneficiary/optionality-excess/dislocation triage) (§319, §363) | needs R1 first | long |
| R6 | Lifecycle transition hazards conditioned on regime (§58–59) | needs accrued PIT state history | LONG — start accrual early; this is why W1 precedes everything |
| R7 | Cross-market transmission via TRANSLATES_TO edges (empirical lead-lag) (§66–69, §174) | THS + US planes ready at basket grain | medium |
| R8 | Catalyst response elasticity (good-news response as state read) (§10, §437) | GovRev + earnings events partial | medium |
| R9 | Theme-cohort context improves DRL/TOPA readings (annotation value, not new signal) (§71, §77) | after W4 edges | medium |

Ore ledger discipline: a null closes the specific construction tested, never the search space; every null prints; Tier-C names may only enter through this table under plain names.

---

## §7 — Wave plan ⟨PENDING-TIL-CENSUS: W1 scope finalizes against what TIL already shipped⟩

Session-chain: one wave per session; each session opens with §0 inline in its prompt, closes with §11 append + continuation handoff. Model routing per house law: Fable = this adjudication + wave charters + merges; opus `builder` = all code; opus `reviewer` = every make-or-break prereg/ruling; opus `designer` = W6 surfaces; sonnet = census/mechanical fan-out only.

- **W0 (this session):** charter + provenance + red-team + ship. Done when this doc is merged and the program memory file exists.
- **W1 — PIT membership spine + crosswalk seed.** One bitemporal edge store unifying the five membership families (US 49, THS 237, regional, foresight-18, finviz map); revive THS snapshot cadence (nightly diff, append-only, receipted); US membership snapshotting; era-labeled seed backfill from the 2 existing THS snapshots + curation dates; crosswalk seed for the pilot universe. CI: edge-schema validation + semantic-leakage check + snapshot-freshness tripwire (a stalled cadence goes loud, never silent — the Marketing-publisher lesson).
- **W2 — Exposure-decomposition probe (R1) on the pilot universe.** Research session through an opus reviewer; verdict appends here; a null narrows W4's edge types, it does not kill the rail (ore law).
- **W3 — ThemeState nightly + expectation ledger.** Legs assembled from owner artifacts (contracts §5.1/5.4/5.7); deterministic lifecycle labels baked from history; graded windows begin accruing (internal only, G0.5); Konseki population contract (§5.3) opens.
- **W4 — Edges beyond membership.** SUPPLIES/ENABLES from linked-outsiders + XBRL; CATALYST_OF from GovRev; TRANSLATES_TO pilot pairs; PARENT_OF hierarchy from existing taxonomies. Every edge evidenced; the 商品联动-style chain display becomes renderable data.
- **W5 — Sensorium legs.** CN speculation-ecology legs (cohorts by theme, board-aware) + US organ legs (ETF flow extension, options state where entitled) — each as waves through owner contracts.
- **W6 — Surfaces + chat.** Design-lane session(s): basket-page graph bands, theme detail Tier-2, packet THEMES block, "what changed" diff view (KILL-ROTATION-SCHEDULE-aware). Screenshot refs copied to `mockups/refs/theme_graph/` in this wave's PR.
- **W7+ — Research queue (§6) + participant-graph probe** (LHB fingerprints as probabilistic display-tier through `china_participation`, identity never asserted — memo §28 agrees) + analog population + GR4 coordination completion.

Render-budget note: all GMI computation lands in the nightly collect lane; render only reads committed artifacts (regime-recompute precedent).

---

## §8 — Product doctrine

North star retained from TIL: **an investigation packet, never a stock pick** — theme, phase, mechanism, evidence, contradictions, crowding, falsifier-free "what we're watching", and what data would change the view. The maturity ladder for copy is memo §441 (state → context → experience → self-awareness) expressed through our glance/Tier-2 system: glance = state + plain-word stance ("Broadening; participation improved while attention cooled — watch, don't chase"), Tier-2 = legs + receipts + honest nulls, Calibration Lab = graded windows. The four memo surfaces (§177–180) map: "what changed" → nightly diff band; "why is this moving" → chat contract §5.9; "what's moving before price" → attention/flow legs (display, G0.5-capped); "what's breaking" → expectation-window outcomes on the Lab. Bilingual from W6 day one; zh authored under zh copy laws, theme names carry canonical zh from the THS vocabulary where a crosswalk edge exists.

---

## §9 — Refusals register (deliberate, with reasons — nothing silently dropped)

1. **Learned/dynamic graph structure** (memo Part XLI's embedding-clustering as production discovery; any graph transformer) — `DNR:HOLD-STRUCTURE-LEARNERS` clock + `DNR:KILL-CAUSAL-DAG-ALPHA`; deterministic rail instead; revisit only through the hold's own unblock condition.
2. **A GMI market-state/world-model plane** (memo Parts VI/IX) — duplicate world models is a named failure mode; consume `regime`/`world_state`/hero instead.
3. **New memory/salience/cortex machinery** (Parts VII, XXIV masterbrain session) — Konseki's charter; GMI populates. The "daily masterbrain session" idea survives as: Konseki W5 + chat over GMI artifacts, not a new orchestrator.
4. **Fused composites of any kind** — G0.1; includes Theme Strength "scores", 景气度-style boom indices, market-quality 0–100s.
5. **LLM narrative/frame tagging into organs; LLM-scored membership** — G0.6 kills; taxonomy-probation is the lawful residue.
6. **"Which theme ignites next" surface** pre-gauntlet — G0.5 (HOLD-IGNITION-SURFACES precedent).
7. **Directional shorting expression of fragility** — `DNR:KILL-DIRECTIONAL-SHORTING`; AVOID-not-SHORT.
8. **OHLCV shock-cause classification** rebadged as theme dislocation — `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`; DRL displays measured truths; GMI annotates cohort context only.
9. **Real-time Northbound architecture** — dead feed (§33/§432).
10. **同花顺 UI cloning; a second sentiment oracle; a limit-up prediction card** — §3.8; CN-alpha owns propensity.
11. **A seventh basket-construction suite as separate product surfaces** (memo §394–408's seven per-theme baskets) — ADAPTED instead: purity/optionality/bottleneck/laggard become edge attributes + state legs queryable through the graph; standing basket products stay the 49+237 the users know (G0.9). New tradeable-basket products are a design-lane/business decision deferred to operator.
12. **The "even larger unified vision document" the source session proposed** — refused as a deliverable: it would duplicate five live charters. This masterplan + the committed source memo + digests ARE the unified vision, bound to reality; the creative layer survives in Appendix C and the sources.

---

## §10 — Operator questions (none block W1)

1. **TIL supersession sign-off** — §2.5's ruling (absorb vs phase-2) is presented for ratification with the census evidence. ⟨PENDING-TIL-CENSUS⟩
2. **THS scrape cadence** — nightly diffs of 237 concept boards vs the current ad-hoc cadence: any ToS/robots posture the operator wants recorded before we automate it?
3. **Citrini institutional feed** — license includes redistribution rights; may GMI use Citrini theme definitions as crosswalk evidence (`source_class=curated`, licensed), or keep it foresight-desk-internal?
4. **CN minute-bar investment** — theme-momentum legs at intraday grain need the private minutes plane; W5 can ship daily-grain only. Appetite for extending the entitled plane to theme use?
5. **Product naming** — "Theme Graph" is the working name; product naming (en/zh) is a W6 design-lane decision unless the operator wants to name it earlier.
6. **GR4 sequencing** — GMI W1 unblocks GR4 (CN twin); does Group Reads want to co-charter that wave or inherit the spine when ready?

---

## §11 — Execution record (append-only)

- **2026-08-10 session 0 (this doc):** Phase-0 adjudication authored. 7-agent intake (3 memo digesters, theme census, NW/lobe census, registry sweep, THS screenshot study) + TIL build-state census. Red-team log: ⟨pending — appended below before merge⟩.

---

## Appendix A — Source-memo disposition map (by part; digests carry the section-level detail)

| Memo part | Disposition |
|---|---|
| I (taxonomy failure) + III (US side) | Adopted as motivation + §4 axes; US organ specifics → §5 contracts, §6 R1/R5 |
| II (同花顺 sensorium) | Adopted as CN legs through owners (§5.7) + product lessons (§3.8); rebuilt nothing |
| IV (dislocation) | §5.5 annotation contract; taxonomy §71 adopted as edge/context types; falsification layer §72 folded into expectation grading |
| V (tops/fragility) | §5.6 through TOPA/docket preregs |
| VI/IX (world model/market state) | Refused (§9.2); consumed instead |
| VII (memory/replay) | §5.3 Konseki population; R1-replay-rail deferral honored |
| VIII (NW plugging) | Corrected (§3.6); re-derived §5 |
| X/XI (US/CN organs) | Waves through owners (§7 W5) |
| XII (proprietary concepts) | Tier-C → Appendix C ore ledger |
| XIII (worked examples) | Adopted as acceptance-test fixtures for W3/W4 (§167 rotation-vs-top; §174 learned transmission) |
| XIV (UX) | §8 (mostly convergent with existing doctrine) |
| XV (validation) | Convergent with house epistemics; deltas adopted in G0.2 (semantic leakage, effective_time) |
| XVI (research cortex) | Konseki W6 territory; refused here (§9.3) |
| XVII (data/evidence architecture) | §4.1 evidence objects + §211 licensing tags adopted |
| XVIII–XXI (universal-vs-specific, moat, what-not-to-build, research-before-software) | Adopted wholesale; §20's own don't-build list honored |
| XXII–XXV (object model, cognition framing, masterbrain, roadmap) | Object model adapted into §4.1; masterbrain refused (§9.3); roadmap superseded by §7 |
| XXVI–XXVII (challenge questions, tiers) | Answered §3; tiers adopted as structure |
| XXVIII–XXXV (surfaces, moat, failure modes, competition, ideation, external research, unified architecture, final rec) | §8 surfaces; §338 stack adjudicated §3.1; failure modes fold into gates |
| XXXVI–XXXIX (handoff, ten integrations, references, masterbrain) | This doc is the answer; ten integrations distributed across §5 |
| XL–XLI (basket construction, discovery pipeline) | §9.11 adaptation + §4.4 lawful discovery |
| XLII (market-structure corrections) | G0.4 + CN rule-metadata requirement (W1 carries the versioned limit-rule table) |
| XLIII–XLIV (final system map, completion) | Honored as orientation; §2.4 is the reality-bound version |

## Appendix B — 同花顺 screenshot reference index (design-wave source material)

Files at `/Users/chriswong/Downloads/同花顺/IMG_2827–2841.PNG` (15). Key references: 2827 market-overview progressive disclosure + cohort tiles; 2829 异动 feed; 2830 热点板块 + 龙虎榜 by participant class; 2831–2832 sentiment band gauge + AI 解读 caption pattern; 2833–2835 A50 linkage / PBOC repo / bond-equity panels; 2836–2837 sector stats + 热度 attention metric + fund-flow bars; 2838 景气度 (pattern adopted, composite refused); 2839 商品联动 causal-chain table (THE edge-display reference); 2840 冲刺涨停 card (refused here, CN-alpha territory); 2841 news theme chips. W6 copies its selections into `mockups/refs/theme_graph/` per spawn-handoff law.

## Appendix C — Concept ledger (creative layer preserved; none of these are features)

Narrative Reproduction Number Rₙ (§283) · Theme Gravity · Theme Entropy · Theme Pressure · Potential Energy · Attention Efficiency · Narrative-Capital Conversion · Capital-Price Conversion · Theme Frontier (§163) · Market Consciousness State (§315, memo's own "internal metaphor only") · Speculation Ecology (§18 — partially realized as CN legs) · Capital Species / Capital Confluence (§29–30 — future CN wave candidate through china_* organs) · Theme Translation Matrix (§68 — realized as TRANSLATES_TO edges) · Hidden Beneficiary Engine (§164 — realized as R5 research row) · Theme Market Share (§ Tier-B) · Event Nervous System (§25 — realized as typed events into existing streams). Each name keeps its memo § pointer; graduation path = §6 under a plain name.
