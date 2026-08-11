# Global Market Intelligence (GMI) — Theme Graph program: adjudication + masterplan

**Status:** PHASE-0 ADJUDICATION — charter for a multi-session program; no wave beyond W0 is authorized until its own session opens with this doc's gates inline
**Date:** 2026-08-10→11 (session 0; census HEAD `565450418c` stamped 2026-08-11T06:12Z)
**Owner program:** `gmi-theme-graph`
**Method:** operator-commissioned external brainstorm (ChatGPT, no codebase access; 445 sections, committed at `research/theme_graph/SOURCE_MEMO_GLOBAL_MARKET_INTELLIGENCE_ORGANISM_FINAL_2026-08-10.md`) → 3-lane Sonnet digestion (`research/theme_graph/MEMO_DIGEST_PART{1,2,3}_*.md`) + 4-lane Sonnet codebase/registry census + 同花顺 screenshot study → this Fable adjudication → Opus red-team (§11).
**Sibling sources committed:** `research/theme_graph/SOURCE_V1_THS_MEMO_2026-08-10.md`, `research/theme_graph/SOURCE_V1_DYNAMIC_THEME_GRAPH_MEMO_2026-08-10.md`. Screenshot reference index in Appendix B (files remain in operator Downloads until the design wave copies its selections to `mockups/refs/theme_graph/`).

---

## §0 — ACCEPTANCE GATES (bind every wave; a wave PR that violates one is not done)

- **G0.1 Tier law.** Every GMI artifact ships display-tier: synapse-registered (`config/synapse.yml`) with `tier: display`, `weights: none`, `scored_path_surfaces: []`, `horizon_role: context` (CI-required field), `owner_program: gmi-theme-graph`, a freshness SLA, and all **six** authority booleans (`can_rank/can_size/can_gate/can_originate_signal/can_add_candidates/can_escalate`) literal `false` — `can_add_candidates: false` is the machine-checkable form of §5.2's "GMI can neither source nor veto a pick". No fused composite anywhere in GMI: theme readings are printed as named legs; state/lifecycle labels come only from deterministic thresholds baked once from history (the TOPA threshold-baking pattern), never from a weighted blend, never from an LLM. (`DNR:KILL-FUSED-COMPOSITE` forbids composites on any scored path; its Amendment 2 permits one display-tier composite family under the PSI §3.1.2 construction law — GMI deliberately does not use that allowance.)
- **G0.2 Point-in-time law.** Every graph edge is bitemporal (`evidence_time`, `belief_time`, `valid_from/valid_to`; `effective_time` where the underlying reality lags publication — memo §206, adopted). Reconstructed history is era-labeled (`era="reconstruction"`) and is never promotion evidence, matching the Konseki authenticated-vs-reconstruction distinction and DRL's gap-era rule. **Semantic-leakage law (new, named):** an LLM-assisted edge may cite only dated evidence documents; membership backfilled from a model's general knowledge (undatable) is forbidden — that is look-ahead smuggled through language (memo §190, §103). No historical theme claim ships while the membership snapshot cadence is stalled (§2.6 defect).
- **G0.3 No-parallel-organ law.** Named owners keep their territory: Group Reads (basket participation/earnings reads), Contagion Sensing (attention/propagation keys), TOPA + Short-Side docket (top/fragility species), DRL `engine/price_pressure/` (residual shocks), CN limit-alpha (limit ecology, auction, Tushare spine), `china_*` collectors/engines (CN participants/flows/intel), Konseki Market Memory (memory/salience/cortex machinery), Prophet (pick authority), TIL/Thematic Foresight Desk assets (§2.5). GMI extends owners through their own pipelines via the §5 contracts; it never re-detects, re-scores, or re-surfaces what an owner already emits (`DNR:KILL-ROTATION-SCHEDULE`, `DNR:KILL-PROPHET-POP-MERGE` precedent class). Two inherited TIL laws bind as standing gates, not just §2.5 context: **every GMI hit-rate or lead/lag claim prints as EXCESS over the placebo tape (R-TIL-6)**, and **every GMI artifact is an assembler over organs that already exist, never a new scorer (R-TIL-9)** — the fence `engine/group_pulse.py` already cites for itself. Specific live fence: `narrative_rotation` carries "Never reorders theme_scoring recos" (synapse.yml:3227); GMI ThemeState legs must never feed `narrative_rotation.allocate()` or any ordering path.
- **G0.4 CN data law.** CN price/limit truth comes only from authorized planes (unadjusted TuShare spine, `china_stocks_raw`, receipted collectors). The adjusted-price limit tape is permanently closed (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`). THS concept scrapes keep their complete-or-fail receipts. No architecture may assume real-time Northbound flow (dead since 2024 — memo §33/§432; historical aggregates only, availability re-verified at build time).
- **G0.5 Forward-claim law.** Theme expectations accrue in an internal graded ledger first. No user-facing forward/ignition surface until ALL of the `DNR:HOLD-IGNITION-SURFACES` re-surface conditions are met, transcribed in full: **≥30 graded calls (a "call" = one distinct episode, never one fire) with an acceptable broad true-positive rate; event-sector exclusion for narrow themes (a geopolitical single-sector bid ≠ ignition); an honest-null "nothing igniting" state with no forced top-N in a dead tape; and an operator ruling.** `DNR:KILL-FORCED-CALLS` binds throughout. Falsifier/refutation language never front-facing (operator 2026-07-27): user surfaces show windows and "what we're watching", full verdicts live on the Calibration Lab.
- **G0.6 LLM law.** Constitution Article 1 / A7 is absolute: no LLM-originated signal, score, weight, confidence, escalation, or narrative tag into any organ (`DNR:KILL-LLM-ORIGINATION` + Article 1 are the general law; `DNR:KILL-LLM-FRAME-TAGS`, `DNR:KILL-LLM-CONTAGION-TAGS` the narrative-tag precedents; `DNR:KILL-LLM-CONFIDENCE` — scoped to CHF surfaces in the registry — the numeric-confidence precedent GMI adopts program-wide). LLM roles in GMI are exactly three, all display-tier, provenance-stamped, curation-gated: (1) propose candidate taxonomy (names/merges/splits) into a probation queue a human ratifies; (2) disambiguate collisions between existing vocabulary entries; (3) de-escalate per the authority ladder's A3 DE-ESCALATE rung (`AuthorityLevel`, `engine/neuralweb/constitution.py` — the ladder rung, not Article 3). Where an LLM touches evidence text, the TIL R-TIL-5 standard binds: extraction-with-receipts only — exact-substring, char-span validated against the source document. Deterministic math computes every number.
- **G0.7 Ship law.** Session-chain program (context economy): one wave per session, durable state in this doc's §11 execution record + a continuation handoff; each wave lands commit → push → PR → merge-on-green → live verification. Graph compute runs in the nightly collect lane, never the render path; heavy artifacts go to R2. Nightly remains the sole advancer of forward ledgers.
- **G0.8 Design law.** Any user-facing surface goes through the design lane (DESIGN_DOCTRINE.md + frontend-design skill; opus `designer` chooses, `builder` implements a pinned spec): glance tier = state + plain-word stance, technicals demoted to Tier-2 receipts, zh copy laws (红涨绿跌; zh authored, not translated), no third nav family, `docs/site_semantics/` rows for every new stat.
- **G0.9 Vocabulary honesty.** GMI's crosswalk unifies the existing theme vocabularies; it must never become vocabulary N+1 with its own drift. Every GMI theme node must resolve (via `expresses`/`same_as` edges) to the vocabularies users already see, and `DNR:KILL-PARALLEL-KNOWLEDGE-BASE` binds: the graph is a product data artifact (like `data/group_pulse/`), not a second hand-curated knowledge store parallel to the Macro Context Index.
- **G0.10 Instrument-verdict law.** A theme state label, window expiry, or chain-failed expectation is an instrument verdict, never a market verdict (operator 2026-08-09): syntheses lead with the dual-read against the tape; scope-limited phrasing ("no broadening within the declared window", never "theme dead").
- **G0.11 Ordering law.** GMI surfaces order by recency or canonical id only — never by a leg value, exposure attribute, or any magnitude (DRL F11 "recency-only ordering everywhere" precedent). A user-exposed query that returns members sorted by an exposure attribute is a ranker and is forbidden; graph queries surface membership + evidence, with sort fixed to recency/id.

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
| Wider theme organ roster | `engine/` carries ~25 `theme_*`/theme-adjacent modules — beyond the analytics row above: `company_theme_exposure/` (deterministic **context-only exposure sidecar**, `AUTHORITY="context_only"`, own contracts), `narrative_rotation.py` (**live cross-sectional ranker with `allocate()`** — fenced "Never reorders theme_scoring recos", synapse.yml:3227), `theme_catalyst_binder.py`, `theme_context.py`, `theme_validation.py`, `theme_warn/alerts/activity/adoption/downside_rs/extension/revisions.py`, TIL waves `theme_hiring/trade_flows/clinical/options_witness.py`, graders `theme_placebo.py`/`foresight_leadlag.py`/`qledger_falsifier.py` | W1 opens with a per-module disposition sweep of all 25 (consume / extend / fence-off), so G0.3 is enforceable against the full roster |

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
| Market state / world model (Parts VI, IX) | `engine/market_state.py` hero, `data/regime/latest.json`, NW `world_state.py`, breadth/vol suites; `research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` verdict #1 REJECTED the deep/multimodal world model (N-insufficiency, 7.5% fundamentals coverage, fusion law); `research/NW_MASTERMIND_BRIDGE_PROGRAM.md` names "duplicate world models" as a standing failure mode | consume; a third plane is refused (§9) |
| Historical memory / replay (Part VII) | Konseki W2–W4A; future-lobes docket R1 replay rail (rule-experiment registry, trial budgets) + `LAW-ERA-SPLIT`, `LAW-TIME-CLUSTERED-CI` | populate; replay questions register through R1's governor when chartered (§5.3) |
| Attention / narrative propagation | Contagion Sensing program (engine-originated contagion key + glance chip live; Ignition Radar suspended = cautionary tale) | consume as attention legs (§5.4) |
| CN limit ecology / auction / participants | CN limit-alpha (W1–W3 priced several families dead; fillability tax measured), `china_lhb/connect/flows/participation/crowding/intel_hub` | consume; its kills bind any CN entry-flavored claim (§5.7) |
| Policy → funding ladder (memo §110) | GovRev Foresight rails (announcement→award→spend separation already load-bearing) | catalyst edges consume GovRev artifacts (§5.8) |
| Prophet as output organ (§340) | Prophet US+CN with two ratified lobe-integration templates: GovRev ruling (lobe owns the WHY; byte-identical on/off proof; preregistered grader = only promotion path) and CN-alpha §10 (re-rank already-selected picks) | §5.2 adopts both templates verbatim |

### 2.5 TIL reconciliation — RULING: inheritance, not supersession (census 2026-08-10)

The Thematic Intelligence Layer (`research/THEMATIC_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`, ratified 2026-07-09) diagnosed the same disease this program targets — uncoordinated vocabularies, no thesis objects, no phase history, no NW citizenship — and then **shipped its core charter within nine days** (W0–W6 merged 2026-07-09→07-18) plus extension waves W7/W8/W10/W11. Live today via standing `daily.yml` steps: `config/theme_crosswalk.yml` v2 (18 foresight themes → 49-basket ids → Finviz 40/268 subsector keys; updated 2026-08-02), `engine/neuralweb/thematic_state.py` + `data/neuralweb/theme_phase_history.jsonl` (160 hash-chained PIT rows through 2026-08-10), `theme_thesis.py` + 162-row hash-chained thesis ledger (mechanism/winners/losers/falsifiers EN/ZH, falsifiers genuinely evaluated), `theme_pathways.py` curated beneficiary/loser graph, `theme_asymmetry.py` per-leg panel, `state_of_themes.html` terminal, full NW citizenship (`world_state.py` §6g block, `ask_brain`/`cortex` read tools, `mastermind_context` summarizer), and the W6 grading pack (`data/foresight/earliness_log.jsonl` 450 rows, lead/lag grades computing). Group Reads is formally a TIL sub-program bound by R-TIL-1..9. Loose ends on record: `data/qledger/falsifier_evaluations.jsonl` has no rows yet; Citrini ingestion never opened (OPEN-OPERATOR gate §7.4 unanswered — `citrini_basket_ids` empty on every crosswalk row). Nobody is actively building core TIL (zero open lanes); it is complete-and-parked, not stale.

**Ruling:** GMI is the **next TIL chapter**, not its replacement. (1) R-TIL-1..9 are inherited wholesale as binding GMI fences — most sharply R-TIL-1 + `DNR:KILL-THESIS-LOBE` (theme work is an organ cluster + waves, never a new lobe), R-TIL-2 (relationship graphs = curated, PR-reviewed config, display-only, losers AVOID-shaped), R-TIL-5 (LLM = extraction-with-receipts, exact-substring char-span validated — adopted into G0.6 as the implementation standard), R-TIL-6 (promotion = preregistered PIT trial + placebo, alpha over a free factor panel, first eligible read ~2026-10+), R-TIL-9 (new collectors keyless/free/PIT-clean/off-render-path; evidence lands in existing organs). (2) GMI extends TIL's living substrate in place — `theme_crosswalk.yml`, the phase-history tape, the W6 grading machinery — rather than parallel stores where TIL already has one. (3) TIL's product target ("investigation packet, never a stock pick") is retained verbatim. (4) What TIL never covered is exactly GMI's charter: CN (all 237 THS baskets sit outside the crosswalk), edge-grain company↔theme membership with evidence and bitemporal intervals (TIL's crosswalk is theme→basket-id grain, config-level), exposure axes, typed company-grain supply-chain/catalyst edges, cross-market translation, and consequence-window grading richer than earliness lead/lag. **RATIFIED by operator 2026-08-11 (§10.1).**

### 2.6 The true gap list (what GMI actually builds — post-TIL-census)

1. **CN in the graph** — the single largest hole: all 237 THS concept baskets (and any CN theme reality) sit entirely outside `theme_crosswalk.yml`, the phase tape, the thesis ledger, and NW citizenship. The operator's US+CN amalgamation ask is, concretely, "give the TIL substrate a China half + a bridge."
2. **Edge-grain bitemporal membership** — TIL's crosswalk maps theme→basket ids at config grain; nobody stores company↔theme edges with evidence refs and `valid_from/valid_to`. The memo's §405 "hindsight chart" warning describes a live defect (CN THS PIT snapshots stalled at 2; US baskets have curation dates, not interval history).
3. **Exposure decomposition** — economic/narrative/trading axes per edge (memo §8, Tier-A3). Not greenfield: `engine/company_theme_exposure/` already ships a deterministic context-only exposure sidecar with its own contracts — GMI extends that organ to the three-axis, cross-market, edge-attached form rather than building a parallel one (G0.3/R-TIL-9); membership elsewhere stays binary curated today.
4. **Typed company-grain edges beyond membership** — SUPPLIES/ENABLES/BOTTLENECK_OF from `linked_outsiders` 8-K counterparties + XBRL fingerprints; CATALYST_OF from GovRev rails. TIL's `theme_pathways.yml` is theme-level curated; company-grain evidence edges are new (built to the R-TIL-2 curated-config pattern).
5. **Cross-market translation** — global theme nodes with per-market local expressions and empirical (never hardcoded) lead-lag (memo §66–69).
6. **Consequence-window grading** — theme-level grading machinery EXISTS and accrues (foresight 45-row graded ledger; TIL W6: earliness lead/lag grades, `theme_placebo.py` placebo tape, `foresight_leadlag.py`, `qledger_falsifier.py`); what does not exist is the §355 "expected consequences" form — typed windows per state transition, proper-scored, spanning both markets. GMI extends the shipped graders (R-TIL-9) and reports excess-over-placebo (R-TIL-6); Konseki population is a separate, Konseki-gated step (§5.3).
7. **CN analytics parity where lawful** — Group-Reads-class reads over THS baskets (GR4, coordinated within the shared TIL fence family, not parallel).

---

## §3 — Adjudication of the memo (the challenge layer)

Answering the memo's own §352 challenge questions with codebase truth. Format: **ruling** — reasoning.

### 3.1 The central reframe

**Ruling: adopt the memo's §338 stack as an orientation map, reject it as a build plan.** Ten of its eleven boxes map onto live programs (§2.4). The genuinely missing box is the third: DYNAMIC THEME GRAPH — semantic topology. The memo is right that without it "the Neural Web has many sensors but fewer structured relationships" (§339), and right that Prophet should read as an output organ over shared understanding (§340) — a reframe our GovRev/CN-alpha Prophet contracts already implement in miniature. GMI = build the missing box, wire it into the ten that exist.

### 3.2 Tier-A rulings (memo §281)

- **A1 Dynamic multi-label Theme Graph — ADOPT, as a deterministic substrate.** Learned graph structure is closed on two distinct grounds: `DNR:KILL-CAUSAL-DAG-ALPHA` is a permanent Article-1/2 forbid (no clock — the DAG→alpha→trade construction), and `DNR:HOLD-STRUCTURE-LEARNERS` holds structure learning until at least 2027-01-15 with auto-deny at intake. The lawful construction is exactly what the memo's Tier A actually needs: explicit typed edges with evidence, deterministic edge math, append-only history. `research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md`'s salvage constructions — the deterministic edge-outcome ledger (its wave-2b) and transparent k-NN analog display (wave-2c) — are realized here by the §4.1 expectation ledger and the §5.3 analog contract respectively.
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

**Nodes** (`data/theme_graph/nodes.parquet`): `node_id` (stable slug; for `kind=company` a **permanent identity key with an explicit identity-break rule, never a bare ticker** — reused-ticker zombie law), `kind` ∈ {theme, company, etf, catalyst, policy_program, commodity, participant_class, market}, `names` {en, zh} — **a node with no `SAME_AS`/`EXPRESSES` edge to an existing vocabulary carries NO user-visible name** (internal join key only, per G0.9), `market_scope` ∈ {US, CN, GLOBAL, …}, `tier` ∈ {macro_category, theme, micro_theme}, `status` ∈ {candidate, canonical, retired, merged→target}, birth/retire dates + provenance. Themes die and merge; dead themes are retained (theme-level survivorship — memo §189) **and dead members stay in every denominator**: a delisted constituent remains in breadth/leadership legs with a terminal state, never silently exits (gap-refusal survivorship law).

**Edges** (`data/theme_graph/edges.parquet`, append-only): `edge_id`, `src`, `dst`, `type` ∈ {MEMBER_OF, EXPRESSES, SAME_AS, TRANSLATES_TO, PARENT_OF, RELATED, SUPPLIES, ENABLES, BOTTLENECK_OF, BENEFITS_FROM, CATALYST_OF, TRACKS, HEDGES}, exposure axes where applicable — each axis stores an **independently-computed continuous quantity with its formula id** (`economic_share` from XBRL/filing revenue exposure, `trading_beta` from co-movement, `attention_share` from receipted attention feeds) **plus** a display rounding (enum {none, weak, core}); the continuous quantities are the measurable objects (§6 R1 runs on them — three curated 3-level ordinals cannot support a disagreement estimand), the enum is glance-tier presentation only, `evidence` (list of receipt refs), `source_class` ∈ {curated, filing, co_movement, scrape, llm_proposed_ratified}, bitemporal fields per G0.2, `confidence_basis` (deterministic formula id, never a bare number without basis).

**Evidence** (`data/theme_graph/evidence.parquet`): receipt rows — `evidence_id`, `kind` (filing/xbrl/8k_counterparty/scrape_receipt/comovement_stat/news_item/operator_curation), `published_at`, `effective_at`, `source_ref` (path/accession/url-hash), `licensing` tags (`internal_ok/display_ok/redistribution_ok/retention` — memo §211). Contradictory evidence coexists as separate rows; nothing nets (memo §205).

**ThemeState** (`data/theme_graph/state/YYYY-MM-DD.parquet` + `latest.json` for surfaces): per canonical theme per session: price legs (theme factor return, residual vs market/sector — `peer_basis` disclosed per DRL's law), breadth legs (from group_pulse where a basket expresses the theme), leadership legs, flow legs (`theme_flow_rollup`), attention legs (contagion keys; THS 热度 where receipted), catalyst-recency legs (event refs), crowding legs (`theme_crowding`), regime context (read-only), `lifecycle_state` (deterministic label, **abstaining below a declared per-leg coverage floor** — the label reads "insufficient coverage", it never computes on a thinned cross-section), `data_coverage` chip (which legs are null and why — nulls printed, never hidden). Every row carries **`computed_at` + engine version alongside its `as_of` date** (a per-date ledger can still be run-date stamped — re-runs must be distinguishable), and assembly is read-only over owner artifacts (R-TIL-9): no leg value feeds any ordering or `allocate()` path (G0.11, narrative_rotation fence).

**Expectation ledger** (`data/theme_graph/expectations.parquet`, nightly-advanced only): on qualifying state transitions, emit typed windows (`expected_consequence`, `horizon_sessions`, `declared_at`, closure-tolerant chain rules, grade fields). Sealed into Konseki Forecast/OutcomeRecords via §5.3. Honest-N = distinct episodes, never fires.

### 4.2 Namespace & registration

`engine/theme_graph/` (new; "theme_graph" collides with nothing — `engine/theme_*.py` singles stay untouched), `scripts/build_theme_graph.py`, `data/theme_graph/`, `contracts/theme_graph/`, synapse entries `theme-graph-{nodes,edges,state,expectations}` (display, booleans false), lobe charter row, `tests/test_theme_graph*.py`. Nightly step in `daily.yml` collect lane, non-fatal, `COLLECT_LANE=nightly`-gated ledger writes.

### 4.3 The crosswalk — extend TIL's live v2, never fork it

`config/theme_crosswalk.yml` (TIL W0, v2) already resolves foresight-18 → basket-49 ids → Finviz 40/268 subsector keys and is nightly-consumed. GMI extends it in place: (1) a CN column family (THS concept ids from `data/baskets_china_ths/concept_map.json`, with the same explicit `unmapped` honesty the v2 file keeps for the 31 unmapped US baskets); (2) canonical `theme_node_id` per row, joining the yml to the graph stores; (3) the reserved `citrini_basket_ids` column may now be filled from the in-hand Citrini theme **definitions** as operator-reviewed curated evidence — feeds stay closed forever (operator ruling 2026-08-11, §10.3; TIL §7.4 resolved). Every other vocabulary keeps living exactly where it lives; GMI adds `EXPRESSES`/`SAME_AS`/`TRANSLATES_TO` edges resolving them to canonical nodes. Judged by G0.9: if a surface can't resolve its vocabulary through the graph, the crosswalk failed; if GMI mints names users never see elsewhere, it failed the other way.

### 4.4 LLM roles + the semantic-leakage law

Per G0.6. Implementation detail that makes it enforceable: LLM-proposed taxonomy writes only to a probation queue (`data/theme_graph/probation/`) with `source_class=llm_proposed`; ratification (operator or explicitly delegated curation session) flips nodes to canonical with the ratifier recorded. Every LLM-assisted edge lists ≥1 dated evidence ref; a CI check refuses `llm_proposed_ratified` edges whose evidence list is empty or undated. Historical backfill jobs run with the LLM disabled entirely — reconstruction edges come only from dated documents and deterministic co-movement, era-labeled.

### 4.5 Classification (future-lobes docket §1 taxonomy): rail + organ-cluster waves — NOT a lobe

R-TIL-1 settles this ("Not a lobe; theme ≠ stock. Thematic intelligence decomposes into an organ cluster + waves"), reinforced by `DNR:KILL-THESIS-LOBE` (the registry kill of the nearest lobe-shaped construction, a thesis lobe duplicating long-hold) and the docket's warning that "misfiling waves as lobes is how sprawl happens." Honest sort: the **substrate (nodes/edges/evidence/crosswalk extension) is a PRODUCT DATA PLANE** — exactly the `data/group_pulse/` class G0.9 already assigns it: rail-*like* in function (serves every organ, no objective function of its own) but NOT an NW-core rail, so it is not chartered through `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` and consumes no slot under the two-lobe concurrency cap (GMI charters **zero** lobes; if the substrate ever migrates into `engine/neuralweb/` core, that migration goes through the rails program's authority). Everything else is **waves on the existing TIL organ cluster and its neighbors**: consequence grading extends TIL W6's grading pack (one flat FDR family string, TrialLedger-compatible); CN reads extend the crosswalk + GR4; attention legs consume Contagion; fragility constructions file through TOPA/the Short-Side docket. The memo's "one organism" framing survives intact across this sort — it just doesn't need a new organ to be true. (The commissioning language said "a brand new lobe"; the census shows the lawful and honest shape is a plane + waves — ratified by operator 2026-08-11, §10.1.)

---

## §5 — Integration contracts (the "deeply integrate into the entire system" deliverable)

Each contract names: what flows, in which direction, with what authority, and its proof obligation.

1. **Group Reads (basket reads; regional twins).** GMI consumes `data/group_pulse/` + `site/basketdata/*.json` as breadth/participation/earnings legs wherever a basket `EXPRESSES` a theme. GMI's CN membership spine (W1b) is a necessary input for GR's CN/HK regional twins — but GR4's own declared gate is "after US proves" and is unchanged by GMI; coordination happens in GR's masterplan before any CN read ships, and GMI never computes participation itself. Proof: zero duplicated stat names; `docs/site_semantics/` rows disambiguate.
2. **Prophet (both markets).** GovRev-template annotation: theme context (which canonical themes a pick expresses; those themes' state legs) attaches post-selection; byte-identical board on/off proof required; GMI can neither source nor veto a pick. Any future re-ranking use rides CN-alpha's §10 pattern behind its own preregistered gauntlet. Prophet hierarchical context (memo §341–342: was the miss theme-level or expression-level?) lands as autopsy annotation in the existing postmortem stores, display-only.
3. **Konseki Market Memory — BLOCKED-ON-KONSEKI, not a GMI wave.** Konseki's own fences currently admit only `synthetic_fixture_only` records (W2B1) and forbid feature projection into W4A coordinates; its W3 playback store has an open DRAFT repair PR (#5296). GMI would be Konseki's **first production callsite** — that admission is a Konseki wave, chartered by Konseki, with named preconditions: W2B1 opens a production-record class; the playback store repair lands; a theme-record contract is ratified on their side. Until then GMI accrues its expectation ledger standalone (§4.1) in a Konseki-compatible shape, and NO GMI wave's done-criteria depend on Konseki. When admitted: GMI→Konseki writes via the capture spine; GMI reads analogs back only for display with era/effective-N disclosures.
4. **Contagion Sensing.** Contagion/attention keys are consumed as ThemeState attention legs via the crosswalk. GMI adds no attention detector; any "attention leads price" claim grades contagion's existing keys at theme level in §6. Ignition-surface law (G0.5) inherited.
5. **DRL (price pressure).** DRL events gain a display-only `theme_cohort` context axis (which themes the shocked name expresses; whether the residual is theme-wide or idiosyncratic — memo §71's price-vs-theme type). DRL's masterplan already fenced "basket residual = context axis only"; GMI rides that fence. The LSR fence stays LSR-pure; GMI never classifies shock causes.
6. **TOPA + Short-Side docket.** Theme-level maturation/fragility constructions (leadership renewal, breadth divergence, §77's state machine states) are offered as candidate species THROUGH the docket's prereg ladder with TOPA's inversion finding as prior. GMI ships only display legs meanwhile. AVOID-not-SHORT absolute.
7. **CN limit-alpha.** GMI consumes zt-pool/limit-tape (authorized planes) for CN speculation-ecology legs (昨日涨停 cohort by theme, board-aware normalized). Auction/fillability kills bind: no CN theme surface may imply an entry edge at daily resolution. The 冲刺涨停-class prediction stays in CN-alpha's Prophet-propensity charter.
8. **GovRev Foresight.** Policy catalyst edges (`CATALYST_OF` policy_program→theme) consume GovRev's rails/artifacts with their funding-stage semantics intact (announcement ≠ cash — §110). No timing predictions (`DNR:KILL-POLICY-TIMING-PREDICTOR`).
9. **Mastermind chat.** One `LOBE_SUMMARIZERS["theme_graph"]` entry + a THEMES block in `market_packet.py` reading `latest.json`/`site` artifacts only (CXI-R23): answers "why is X moving" with graph neighborhood + state legs + provenance, in plain words. This is memo §178's product surface at near-zero marginal cost once artifacts exist. Leak-screen sentinels inherited; nothing chat outputs persists into GMI state (NAR-R4).
10. **Site surfaces.** Extend existing families first: Sector Central flyout, basket detail pages (theme chips + graph context band), `state_of_themes.html`, `narrative_radar.html`, cn theme pages. New pages only via the design lane after W3, and none may become a rotation-schedule surface (`DNR:KILL-ROTATION-SCHEDULE`).

---

## §6 — Research program (hypotheses before software; each row = future prereg, none authorized here)

Pilot rule (memo §352.9): every probe runs first on ONE global pilot set of six named slots — US-mature-broad, US-young-narrow, US-institutional (GovRev-adjacent), CN-mature, CN-young-speculative, and one cross-market pair (a single canonical theme with live US and CN expressions). Slots are filled by name in the W2 prereg; the set is fixed for the program's first year. Every prereg carries: episode-level honest-N, era-split, time-clustered CIs, survivorship statement (dead themes included), and the coverage-floor law for nullable inputs.

| # | Hypothesis (memo §) | Data readiness | Honest clock |
|---|---|---|---|
| R1 | The three exposure axes' **continuous quantities** (economic_share, trading_beta, attention_share — §4.1) disagree measurably & stably (§8, §42). Runs on independently-computed quantities, never on curated enums (a probe on minted labels measures annotation variance and is in-sample of the labeling — refused). §319's disagreement-alpha framing stays parked until R1 establishes the quantities are stable measurements at all | filings/XBRL + co-movement + attention keys: ready on pilot | short — cross-sectional |
| R2 | Breadth acceleration leads continuation vs exhaustion (§23, §77) | group_pulse + baskets history: partial | needs PIT accrual for theme-level; basket-level proxy sooner |
| R3 | Leadership renewal distinguishes rotation from distribution (§49, §167) | prices ready; TOPA prior binds | medium |
| R4 | Attention → price lead (contagion keys graded at theme level) (§23, §436) | contagion history: check depth | medium |
| R5 | Exposure-disagreement episodes resolve directionally (hidden-beneficiary/optionality-excess/dislocation triage) (§319, §363) | needs R1 first | long |
| R6 | Lifecycle transition hazards conditioned on regime (§58–59) | needs accrued PIT ThemeState history — accrual STARTS AT W3, not W1 (W1 accrues membership only) | LONG — earliest honest answer ≈ W3 + 12–18 months of accrued state; TIL's phase tape (US-18, since 2026-07) is the only head start |
| R7 | Cross-market transmission via TRANSLATES_TO edges (empirical lead-lag) (§66–69, §174) | THS + US planes ready at basket grain | medium |
| R8 | Catalyst response elasticity (good-news response as state read) (§10, §437) | GovRev + earnings events partial | medium |
| R9 | Theme-cohort context improves DRL/TOPA readings (annotation value, not new signal) (§71, §77) | after W4 edges | medium |

Ore ledger discipline: a null closes the specific construction tested, never the search space; every null prints; Tier-C names may only enter through this table under plain names.

---

## §7 — Wave plan

Session-chain: one wave per session; each session opens with §0 inline in its prompt, closes with §11 append + continuation handoff. Model routing per house law: Fable = this adjudication + wave charters + merges; opus `builder` = all code; opus `reviewer` = every make-or-break prereg/ruling; opus `designer` = W6 surfaces; sonnet = census/mechanical fan-out only.

- **W0 (this session):** charter + provenance + red-team + ship. Done when this doc is merged and the program memory file exists.
- **W1a — PIT hazard fix FIRST (small, ships alone).** Revive the THS snapshot cadence (nightly diff, append-only, receipted) + US membership snapshotting + the snapshot-freshness tripwire (a stalled cadence goes loud, never silent — the Marketing-publisher lesson). The program's motivating defect (2 THS snapshots ever) is not queued behind anything. Opens with the 25-module theme-organ disposition sweep (§2.1) so G0.3 is enforceable.
- **W1b — CN-half + edge-grain spine.** (a) Extend `theme_crosswalk.yml` per §4.3 (CN column family + canonical node ids; existing mappings untouched); (b) the bitemporal company↔theme edge store (`data/theme_graph/edges.parquet`) materialized from the live membership families (US 49, THS 237, regional) with evidence refs and intervals; (c) era-labeled seed backfill from the 2 existing THS snapshots + curation dates; (d) the versioned CN limit-rule metadata table (board-aware, time-versioned — memo §429–431) as a small config. CI: edge-schema validation (incl. permanent company ids + survivorship fields) + semantic-leakage check.
- **W2 — Exposure-decomposition probe (R1) on the pilot universe.** Research session through an opus reviewer; verdict appends here; a null narrows W4's edge types, it does not kill the rail (ore law).
- **W3 — ThemeState nightly + consequence grading.** Legs assembled from owner artifacts (contracts §5.1/5.4/5.7) for the crosswalked universe (both markets); deterministic lifecycle labels baked from history (coverage-floor abstention per §4.1); consequence windows extend TIL W6's grading machinery (`grade_thematic` lineage — extend, don't parallel; excess-over-placebo reporting per R-TIL-6) and begin accruing internally (G0.5). Konseki population is NOT a W3 criterion — it waits on Konseki's own admission wave (§5.3).
- **W4 — Edges beyond membership.** SUPPLIES/ENABLES from linked-outsiders + XBRL; CATALYST_OF from GovRev; TRANSLATES_TO pilot pairs; PARENT_OF hierarchy from existing taxonomies. Every edge evidenced; the 商品联动-style chain display becomes renderable data.
- **W5 — Sensorium legs.** CN speculation-ecology legs (cohorts by theme, board-aware) + US organ legs (ETF flow extension, options state where entitled) — each as waves through owner contracts. Intraday grain: operator approved extending the entitled private CN minutes plane to theme use (§10.4, 2026-08-11) — intraday theme-momentum legs may charter here behind that plane's own attestation gates; daily grain remains the floor if attestation blocks.
- **W6 — Surfaces + chat.** Design-lane session(s): basket-page graph bands, theme detail Tier-2, packet THEMES block, "what changed" diff view (KILL-ROTATION-SCHEDULE-aware; G0.11 ordering — diff entries by recency only). Screenshot refs copied to `mockups/refs/theme_graph/` in this wave's PR.
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
11. **A seventh basket-construction suite as separate product surfaces** (memo §394–408's seven per-theme baskets) — ADAPTED instead: the roles live as §4.1 exposure-axis quantities and edge types (`BOTTLENECK_OF`, laggard/leader as state legs); surfaced membership views order by recency/id only (G0.11 — a purity-sorted member list is a ranker and is refused); standing basket products stay the 49+237 the users know (G0.9). New tradeable-basket products are a design-lane/business decision deferred to operator.
12. **The "even larger unified vision document" the source session proposed** — refused as a deliverable: it would duplicate five live charters. This masterplan + the committed source memo + digests ARE the unified vision, bound to reality; the creative layer survives in Appendix C and the sources.

---

## §10 — Operator questions — ALL ANSWERED (operator, 2026-08-11; verbatim rulings recorded)

1. **TIL inheritance ratification — RATIFIED** ("yes i agree, ratify"). §2.5's inheritance ruling and §4.5's plane-plus-waves classification are now program law.
2. **THS scrape cadence — DELEGATED** ("no do whatever u want"). Proceeding with the W1a nightly-diff cadence + freshness tripwire as specified; receipted complete-or-fail scraping unchanged.
3. **Citrini — DEFINITIONS YES, FEEDS NO** ("existing themes from citrini can be used, but we no longer use their feeds"). TIL's §7.4 gate is resolved (addendum recorded in that doc): no feed ingestion ever ships (CITR-0/1/3/4 closed); the in-hand basket/theme definitions are usable as operator-reviewed curated crosswalk evidence (`source: citrini`), so `citrini_basket_ids` may be filled in W1b/W4 from definitions only.
4. **CN minute-bar plane — APPROVED for theme use** ("yes extend to theme use"). W5 may charter intraday-grain CN theme-momentum legs on the entitled private minutes plane, still behind that plane's own attestation gates (TP-0-style manifest; store stays outside the repo per its contract) — daily-grain remains W5's floor if attestation blocks.
5. **Product naming — ACCEPTED** ("yes sure that works"). "Theme Graph" stands as the working name; final en/zh product naming stays a W6 design-lane deliverable.
6. **Regional-twin sequencing — DELEGATED, DECIDED: inherit-the-spine.** Ruling: GR's regional twins inherit the CN membership spine as-is when GR4's own gate ("after US proves") opens; no cross-program co-charter is created. Reasoning: coupling two programs' wave clocks is the cross-program deadlock class (the pack-heal lesson generalized); the spine is a standalone-consumable product data plane by design; and an early GR opening can consume the W1b crosswalk seed without waiting for full edge-grain coverage. GMI W1b ships a short spine-consumer contract note alongside the schemas.

---

## §11 — Execution record (append-only)

- **2026-08-10→11 session 0 (this doc):** Phase-0 adjudication authored. 8-agent intake (3 memo digesters, theme census, NW/lobe census, registry sweep, THS screenshot study, TIL build-state census). Central census surprise: TIL shipped its whole core charter in nine days (July 2026) and runs live — §2.5's inheritance ruling replaced this doc's drafted absorb-vs-phase-2 fork.
- **Red-team log (opus reviewer, 21 findings; all folded before merge):** Sustained and fixed — census had missed 16 of ~25 live theme organs incl. the `company_theme_exposure` sidecar and the fenced `narrative_rotation` ranker (§2.1/§2.6 re-derived); R1 was circular on curated enums (axes re-specified as continuous quantities + display roundings, §4.1/§6); synapse authority booleans are six not five (`can_add_candidates` added, + `horizon_role`); G0.5 had transcribed only 2 of the 4 HOLD-IGNITION-SURFACES conditions (all four now verbatim); KILL-CAUSAL-DAG-ALPHA is permanent while only HOLD-STRUCTURE-LEARNERS carries the 2027 clock (§3.2 A1 split); substrate reclassified product data plane, zero lobes chartered (rails-program authority + two-lobe cap respected, §4.5); G0.11 ordering law added (DRL F11 precedent); R6's clock re-attributed to W3 with an honest earliest-answer date; §5.3 Konseki contract marked BLOCKED-ON-KONSEKI (synthetic_fixture_only fences, draft #5296); W1 split W1a/W1b so the PIT-cadence fix ships first; four schema hazards pinned (permanent non-ticker company ids, member-level survivorship in denominators, `computed_at` run stamps, coverage-floor abstention on lifecycle labels); R-TIL-6/R-TIL-9 promoted from §2.5 context into standing G0.3 gates; pilot universe made executable (six named global slots); plus 6 citation-scope/wording corrections (LLM-CONFIDENCE scope, A3 ladder-rung disambiguation, FUSED-COMPOSITE Amendment 2, GR4 gate wording, §9.11 attributes, date stamp). Refuted: the reviewer's F1 "AQM adjudication does not exist" — it grepped the abbreviation; `research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` exists with the cited verdict (fixed anyway: full filenames now cited at every use). Verdict after fixes: sound phase-0 charter; §0 gate structure, §5 contract shape, §9 refusals register strongest parts.
- **2026-08-11 operator ratification (same session, pre-merge):** all six §10 questions answered — TIL inheritance RATIFIED; THS cadence delegated; Citrini = definitions-yes/feeds-never (TIL §7.4 resolved by addendum in that doc); CN minutes plane approved for theme use (W5, attestation-gated); "Theme Graph" naming accepted; regional-twin sequencing delegated and decided inherit-the-spine. Ship-chain note: W0 PR's first pack-9 red was a stale-base red (fix landed on main 15 min after the merge-ref was cut, inside #5315) — healed by base refresh + a clear-field main baseline dispatch; an isolated-worktree builder verified current main green (33/33) and correctly declined to open a duplicate heal; residual fixture clock-margin hazard spun off to its own session.

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
