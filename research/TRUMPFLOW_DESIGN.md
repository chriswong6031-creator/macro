# Latent Flow Graph Desk — Architecture & Decision Document

A Trump-family / administration investment-flow tracker that catches the *equity-stake-in-a-future-hyperscaler* thesis early, not the *loves-bitcoin* narrative. Built as a firewalled Tier-C desk on the existing macro-dashboard chassis. New code lives under `engine/trumpflow/` and `data/trumpflow/`.

> Source: multi-agent design workflow (`trump-flow-brain-design`, 11 agents). This is the spec we build from.

---

## 1. Who is the brain? Do we need LLM + reasoning + brain layers?

**Direct answer: you need all three *functions*, but they are not three independent layers. They are two thin LLM touchpoints bracketing a deterministic core. The brain is deterministic — making it an LLM would be the single biggest design error available here.**

| Layer | What it is | LLM? | Maps to existing modules | New module |
|---|---|---|---|---|
| **1. LLM layer = EXTRACTOR** | Turns one raw filing/news excerpt into one typed, citation-verified event JSON. Reasons only over provided text; quotes a verbatim citation for every fact; can never invent a ticker/date/holding/edge. The *only* place an LLM touches raw text. | **Yes** (gated, per-new-filing) | `engine/catalyst_tone.py` → `_verify_citations` + `_extract_json` + `_client` | `engine/trumpflow/extract.py` |
| **2. Reasoning layer = ADVERSARIAL PANEL** | *Adjudicates* over the already-built deterministic graph + ledger: which short-paths/mismatches are investable vs noise, picks the cleanest scorable proxy (HUT not ABTC), writes bilingual thesis/dissent, calibrates conviction DOWN on disagreement + own poor track record. **Does not discover, traverse, or invent edges.** | **Yes** (gated, weekly / on novelty) | `engine/ai_desk.py` `_run_panel` + `_adjudicate`; `engine/policy_intent_desk.py` `gather_state`/`synthesize`/interval-gate; `engine/master_brain.py` `_call_model` | `engine/trumpflow/desk.py` |
| **3. BRAIN = DETERMINISTIC fusion + ledger + scorer** | The four graph signal queries that do the actual *discovery*; the always-on rule-emitter that logs a falsifiable thesis on the filing timestamp; the `_reconcile` risk clamp; conviction-down-on-disagreement weighting; the scorer. **The LLM proposes; the deterministic brain disposes.** | **No** | `engine/stock_desk.py` `_reconcile`; `engine/ai_desk_scorer.py` `_score_one` + `_aggregate`; `engine/signal_archive.py` | `engine/trumpflow/signals.py` + `engine/trumpflow/emit.py` |

**Why this and not "three LLM stages":** The discovery that catches the ABTC trap — a multi-hop BFS short-path from Eric Trump to the `ai_infra` theme, plus a label-mismatch detector — is **deterministic graph code**, not LLM reasoning. The accountability that makes it honest — a filing-timestamp falsifiable ledger scored vs SPY, soft-never-scored — is **deterministic ledger code**. Letting the LLM traverse the graph means it hallucinates edges; letting it only adjudicate over deterministic candidates makes it accountable and cheap.

**Build-team caveat:** every source plan cites `engine/demand_ledger.py` as a "verbatim clone" template for the no-LLM rule-emitter. **That file does not exist on this branch** — it lives only on unmerged PR #298. Reconstruct `emit.py` from the `ai_desk._append_ledger` + `_entry_levels` + `_level_asof` + `_check_by` pattern, not by copy.

---

## 2. Architecture end-to-end

All new code under `engine/trumpflow/` and `data/trumpflow/`. **Firewall:** nothing here imports `conditions.py` / `regime.py` / `axes.py` / `stock_score.py`; only a human writes `data/baskets/membership.json`.

```
L0  COLLECT  [DETERMINISTIC · daily · committed PIT]
    Quiver REST (Token-bearer)        SEC EDGAR full-text         GDELT entity news
    trump_trades/congress/contracts   8-K/S-4/425/EX-99 + Form4   "Trump family business",
    /lobbying/flights                 keyword+CIK watch           "American Bitcoin","WLFI"
        │ collectors/quiver_base.py       │ collectors/edgar_events.py   │ engine/entity_news.py
        ▼                                 ▼  (dated by FILING ts —       ▼
    data/quiver/{ds}/{date}.parquet       the genuinely-early channel;  filtered headlines
                                          trade feeds lag 30–45d STOCK-Act)
                                           ▼
L1  EXTRACT + GRAPH
    (a) extract.py        [LLM · GATED · display-only]
        one excerpt → one typed event JSON, verbatim-citation gated, watermark-dedup
        → data/trumpflow/events.jsonl  {entity,actor,action,asset_named,asset_real_hint,
                                          form,date,citation,provenance∈FACT|DISCLOSED|INFERRED,conf}
    (b) graph_build.py    [DETERMINISTIC]
        normalize L0 rows + events → typed directed append-only edge log
        resolve aliases (ADC=American Data Centers=American Bitcoin-pre=Gryphon→ABTC)
        → data/trumpflow/edges.jsonl  (Person/Entity/Stake/Theme/Ticker/Policy nodes;
           CONTROLS/HOLDS/SPUN_OUT/OPERATED_BY/MEMBER_OF/BENEFITS edges; each edge carries
           provenance{src_type,url,filed_date,observed_date} + confidence FACT.95/DISC.8/INF.5/RUM.3)
        → materialize networkx DiGraph (in-memory, no DB) + snapshot_{asof}.json
        → signal_archive.archive_snapshot('trumpflow', snap, asof)
                                           ▼
L2  SIGNALS + RULE-EMITTER  [DETERMINISTIC · ALWAYS-ON]
    (a) signals.py        [is_context_only=True · display-only into alerts.jsonl]
        4 queries: new-edge delta · Trump→Theme BFS short-path · label-mismatch
                   (entity brand_theme vs argmax over Stake→Ticker→Theme)
                   · co-investment cluster (min-confidence-mass + min-distinct-source gate)
        + conflict_detector (Policy BENEFITS a Theme a Trump Stake is IN)
    (b) emit.py           [THE SPINE · falsifiable · accrues on FILING DAY · no LLM key needed]
        each high-confidence signal → falsifiable thesis row, entry_levels snapshotted,
        vintage-dedup 'event_type:parent_ticker:lean', conviction='low' until earned.
        Subject driven by L2 label-mismatch → HUT not ABTC.
        → data/trumpflow/theses.jsonl  (source='rule')
                                           ▼
L3  REASONING PANEL  [LLM · GATED weekly OR on novelty trigger · accountable]
    desk.py — clone policy_intent_desk + ai_desk._run_panel/_adjudicate
    4 analysts: path_bull / priced-in-skeptic / base_rate / structural_proxy-picker
    ONLY adjudicates (promote/clamp/demote, pick scorable proxy, bilingual thesis+dissent).
    NEVER traverses/invents edges. stock_desk._reconcile clamps 'overweight' on EXTENDED/AVOID → 'cautious'.
        → appends source='llm' rows to SAME data/trumpflow/theses.jsonl
                                           ▼
L4  SCORE  [DETERMINISTIC · verbatim reuse]
    ai_desk_scorer._score_one + _aggregate + _EVAL['rel_return'] grade matured theses
    name-minus-SPY vs op/threshold → data/trumpflow/track_record.json (+ by_source bucket)
    _SCORABLE = liquid ETFs/large names; _SOFT = ABTC/WLFI/private vehicles → logged, NEVER scored.
                                           ▼
L5  BIND + RENDER  [DETERMINISTIC render · human-curated promotion]
    confirmed finding → HUMAN appends membership.json basket → gets theme_scoring /
    theme_alerts / narrative_rotation / theme_crowding for FREE (zero code change)
    scripts/build_trumpflow.py (clone build_policy_watch.py) → templates/trumpflow.html.j2
    → site/trumpflow.html ; one additive daily.yml engine step + QUIVER_API_KEY secret
```

**Deterministic vs LLM:** L0, L1(b), L2, L4, L5 are deterministic. L1(a) and L3 are the only two LLM touchpoints, both gated. **Display-only vs actionable:** L2 `signals.py` is `is_context_only` (raises/lowers conviction, never a numeric score in any axis); L2 `emit.py` + L3 + L4 produce the *actionable* falsifiable ledger. Nothing feeds allocation or any scored axis.

---

## 3. The ABTC worked example, traced through every stage

The held-out validation case. Replaying the Feb–Mar 2025 filings must surface a **HUT-over-ABTC overweight-vs-SPY thesis at the Mar-31 8-K**, before the Dec-2025 lease re-rating — or the graph/label logic is falsified.

| Date | Real event | Stage | What the system does |
|---|---|---|---|
| **2025-02-11** | Eric Trump + Don Jr join Dominari (DOMH) advisory board; EX-99.2 filed; DOMH +90% in 48h | **L0/L1(b)** | Filing row written; adds `Person:EricTrump -ADVISES-> Entity:DOMH` (FACT/0.95). **L2 emit.py:** wide-band rule thesis (low-float). *Logged, not the winning call.* |
| **2025-02-18** | Dominari forms **American Data Centers Inc. (ADC)** — explicit **AI/HPC** mandate (EX-99.1) | **L1(a)/L1(b)** | Extractor: `{entity:ADC, asset_named:"data center", asset_real_hint:"AI/HPC infrastructure", provenance:FACT}`. Graph: `DOMH -CONTROLS-> ADC`, ADC tagged toward `ai_infra`. The AI angle captured before the Bitcoin rebrand buries it. |
| **~Feb 2025** | Genoot↔Eric Trump pizza meeting (no filing) | — | Invisible. **System beats media, not insiders.** |
| **2025-03-31** | Hut 8 8-K: spins ABTC, HUT retains 80% + power/land/data-center real estate, sons ~20% | **L1(b)** | `ADC -SPUN_OUT-> ABTC`, `ABTC -OPERATED_BY-> HUT`, `HUT -HOLDS-> Stake(245MW River Bend)`. ABTC `brand_theme=crypto`. |
| | | **L2 LABEL-MISMATCH** | ABTC.brand_theme (`crypto`) vs argmax over Stake→Ticker→Theme → **`ai_infra`**. **MISMATCH FIRES → repointed_subject = HUT.** conflict_detector links policy `BENEFITS ai_infra`. |
| | | **L2 SHORT-PATH** | BFS `EricTrump→ADC→ABTC→HUT→ai_infra`, 4 hops, min_conf 0.95 → `alerts.jsonl`. |
| | | **L2 emit.py** | Rule thesis `2025-03-31-HUT-infra`, **subject=HUT**, overweight, 126d, op'<' thr -0.05 vs SPY, entry_levels at 8-K close. **THE WINNING CALL — ~6 months before the re-rating, independent of the LLM key.** |
| **2025-05-09** | ABTC↔Gryphon merger S-4/425 | **L2 emit.py** | Vintage-dedup: no duplicate HUT thesis; emits an ABTC-listing-watch **soft** thesis (no price series → never scored). |
| **Weekly (gate open)** | — | **L3 panel** | `structural_proxy` analyst: value compounds in the infra parent, not the commodity-named child; `base_rate` prior that most policy bets don't beat SPY; adjudicator **promotes HUT low→medium conviction**. |
| **2025-12-17** | HUT $7.0B Fluidstack lease (Google-backstopped), +20% session | — | The re-rating the system anticipated. New `LEASE_WITH`/`FINANCED_BY` edges confirm institutional conviction. |
| **At check_by** | HUT strongly positive vs SPY | **L4 scorer** | op'<'(-0.05) FALSE → **outcome=HIT** → `track_record.json` credits the call; next panel reads it. |

The narrative path ("Trump sons love Bitcoin → buy ABTC") never produces the winning thesis — ABTC is `_SOFT` and the label-mismatch detector flips the subject to HUT.

---

## 4. Reuse map

### Existing modules reused (verbatim or clone)

| Module | How reused |
|---|---|
| `engine/ai_desk_scorer.py` `_score_one`/`_aggregate`/`_EVAL['rel_return']` | **Verbatim** — grades the ledger name-minus-SPY. No changes. |
| `engine/ai_desk.py` `_run_panel`/`_adjudicate` | Adversarial 4-analyst panel chassis for L3 `desk.py`. |
| `engine/ai_desk.py` `_append_ledger`/`_entry_levels`/`_level_asof`/`_check_by`/`_derive_check` | **Template for `emit.py`** (since `demand_ledger.py` is NOT on this branch). |
| `engine/policy_intent_desk.py` `run`/`gather_state`/`synthesize`/`_SCORABLE`/`_SOFT`/interval-gate | Closest analog — cloned as `desk.py`; reads `data/trumpflow/intel.json`; `interval_days=7`. |
| `engine/stock_desk.py` `_reconcile`/`_is_risk_blocked` | Clamp: 'overweight' on an engine-AVOID/EXTENDED name → 'cautious' (the CASY anti-chase). |
| `engine/master_brain.py` `_call_model`/`_brief_age_days`/`_macro_backdrop`/`_translate_brief` | LLM client (never raises), interval gate, regime backdrop, cheap zh via deepseek-v4-flash. |
| `engine/catalyst_tone.py` `_extract_json`/`_client`/`_verify_citations`/`_norm` | **Verbatim** — the L1 extractor's verbatim-citation safety gates. |
| `engine/signal_archive.py` `archive_snapshot`/`load_archive` | PIT node/edge record + 12-month IC falsifiability study. |
| `engine/macro_news.py` `filter_headlines`/`classify_theme` + GDELT fetch | Cloned for `entity_news.py` with a `TRUMP_ENTITY_THEMES` dict. |
| `engine/theme_discovery.py` `discover_candidates` | Extended with `pre_seeded_groups` to test Trump-trade cohort overlap with existing baskets. |
| `engine/theme_scoring.py` `_MACRO_PRIOR`/`_SECTOR_PROXY`/`compute_theme_intel` | New basket entries auto-scored; add priors (e.g. `trump_ai_power_infra`). |
| `engine/theme_alerts.py` `rebuild()` | Auto-monitors any new basket → `alerts.jsonl`, zero code change. |
| `engine/narrative_rotation.py` + `theme_crowding.py` + `theme_extension.py` | Auto-cover any new basket via `_region_cfg('us')`. |
| `collectors/base.py` `Adapter`/`run_adapter` | Circuit-breaker runner for all Quiver/EDGAR collectors. |
| `collectors/edgar_13f.py` + `collectors/finra.py` + `collectors/sec_insider.py` | Patterns for Quiver snapshots + EDGAR events; **reuse free Form-4 instead of paying Quiver for insider data**. |
| `scripts/build_policy_watch.py` + `templates/policy_watch.html.j2` | Cloned as `build_trumpflow.py` + `trumpflow.html.j2`. |
| `.github/workflows/daily.yml` | One additive engine step + `QUIVER_API_KEY` in the collect env block. |
| `data/baskets/membership.json` | The ONLY file a confirmed finding writes to (human-curated). |

### New modules

| New module | What it does |
|---|---|
| `collectors/quiver_base.py` | `QuiverBaseAdapter` — `Authorization: Token {key}` header, backoff+jitter, `config.secret('QUIVER_API_KEY')`, `expected_failure` when key absent. |
| `collectors/quiver_{trump,congress,contracts,lobbying,flights}.py` | Thin Tier-1 dataset subclasses → `data/quiver/{ds}/{date}.parquet`. |
| `collectors/edgar_events.py` | EDGAR full-text-search for 8-K/S-4/425/EX-99 by political-name + infra-keyword set → `data/trumpflow/edgar_events.parquet`. **Catches the Feb-18 + Mar-31 filings at filing time.** |
| `engine/entity_news.py` | GDELT entity-news subclass + `TRUMP_ENTITY_THEMES` dict for news-confidence edges. |
| `engine/trumpflow/extract.py` | **L1 LLM-as-extractor** — excerpt → typed event JSON, verbatim-citation + watermark gated. |
| `engine/trumpflow/graph_build.py` | Normalize → typed provenance+confidence edges; alias resolution; networkx DiGraph; snapshot; archive. |
| `engine/trumpflow/signals.py` | **The 4 deterministic graph queries** + `conflict_detector`. |
| `engine/trumpflow/emit.py` | **The always-on rule-emitter spine** — falsifiable thesis on the filing day. |
| `engine/trumpflow/desk.py` | **L3 gated LLM panel** — clone of `policy_intent_desk`; 4 analysts incl. `structural_proxy`-picker; `_reconcile` clamp. |
| `engine/trumpflow/_SCORABLE / _SOFT` registry | SCORABLE {SMH, SOXX, ITA, XLE, XLF, IBIT, URA, HUT/DJT if clean series}; SOFT {ABTC, WLFI, DOMH, private vehicles}. |
| `data/trumpflow/aliases.json` | Entity alias table. **The keystone — a missed rename silently breaks discovery.** |
| `data/trumpflow/edges.jsonl` | Append-only provenance-stamped edge log (the substrate). |
| `data/trumpflow/intel.json` | Hand-curated FACT/INFERENCE/PRIOR substrate in the `policy_intel.v1` schema. |
| `scripts/build_trumpflow.py` | Orchestrator: graph_build → signals → emit → desk.run → scorer → archive → render. |
| `templates/trumpflow.html.j2` | Bilingual page: scorecard, d3 force-graph, short-path cards, label-mismatch callouts, falsifiable ledger, track record. |

---

## 5. Quiver dataset → signal map (and what Quiver cannot see)

| Quiver dataset | Tier | Powers which detector | Lag |
|---|---|---|---|
| **Donald Trump Stock Trades** (`/bulk/trumpstocktrades`) | T1 | Direct `Person:DT -DISCLOSED_TRADE-> Ticker`; co-investment cluster; conflict_detector | 30–45d OGE |
| **Congress / Senate / House Trading** | T1 | `Person:congress -DISCLOSED_TRADE-> Ticker`; committee-aligned cluster | 45d STOCK-Act |
| **Government Contracts** (`/govcontractsall`) | T1 | `Entity -WON_CONTRACT-> Policy`; flow-burst z-score | ~2wk |
| **Corporate Lobbying** (`/lobbying`) | T1 | Rising CRYPTO/AI/ENERGY spend before regulatory action = leading indicator | Quarterly |
| **Corporate Flights** (`/flights`, ADS-B) | T1 | Pre-announcement edge: C-suite jets to DC/Bedminster/Mar-a-Lago/Riyadh | Daily |
| **Off-Exchange / DPI** (`/offexchange`) | T1 | Dark-pool accumulation context on DJT + crypto-adjacent names | Next-day |
| **Insider (Form 4)** | T2 | **Skip — `collectors/sec_insider.py` covers Form 4 free.** | 2 biz days |
| **13F / sec13fchanges** | T2 | **Skip — `collectors/edgar_13f.py` pulls EDGAR free.** | Q +45d |

**The genuinely-early channel is EDGAR 8-K/S-4/425/EX-99 (free), not the Quiver trade feeds** — the trade endpoints carry a 30–45d reporting lag, so "early" there means *earlier than media*, not earlier than filings.

**What Quiver cannot see — the LLM extraction layer must cover these (enter as INFERRED/RUMORED, low-confidence, mostly `_SOFT`):**

- Eric/Don Jr **private PE-for-stake deals** (e.g. ABTC pre-listing stake) — no OGE 278-T obligation. News + S-1/8-A only.
- **WLFI / USD1 token holdings** ($500M+ family exposure incl. undisclosed UAE stake) — not a registered security; Reg-D + voluntary disclosure + EDGAR full-text on the LLC.
- **Family LLCs / revocable trusts** — sub-investments opaque (Affinity Partners $2B Saudi PIF, etc.).
- **Pre-IPO / SPAC stakes** before public filing — invisible until S-1/8-A.
- **Foreign sovereign side-letters** — UAE/Saudi/Qatar into Trump-branded ventures; outside SEC/OGE.
- **On-chain WLFI/USD1 wallet flows** — need Nansen/Arkham/RPC; **out of scope for this design** (future collector).

The killer asymmetry: the highest-value latent stakes have the weakest provenance, so they are documented in the graph but mostly gated out of the *scored* ledger. The system is honest about this — they render as low-confidence edges and `_SOFT` theses.

---

## 6. Build roadmap

Each phase is independently shippable as one whole-branch PR (branch off `origin/main`, never to main, no auto-merge).

**P0 — Ingestion + graph substrate** *(no LLM, no page)*
- `config.yml` `quiver` stanza; `QUIVER_API_KEY` CI secret + local `.env`.
- `collectors/quiver_base.py` + Tier-1 subclasses; `collectors/edgar_events.py`; register in `scripts/collect.py`; `QUIVER_API_KEY` in daily.yml collect env block.
- `engine/trumpflow/graph_build.py` + `aliases.json` + `edges.jsonl`; `signal_archive.archive_snapshot`.
- Ship gate: collect runs, graph builds without a key crashing the pipeline (degrades cleanly). Data committed; no site change.

**P1 — Deterministic detectors + page** *(no LLM)*
- `engine/trumpflow/signals.py` (4 queries + conflict_detector) → `signals/latest.json` + `alerts.jsonl`.
- `engine/trumpflow/emit.py` — always-on rule-emitter → `theses.jsonl`; `_SCORABLE`/`_SOFT` registry.
- `ai_desk_scorer` wired for scoring (verbatim).
- `scripts/build_trumpflow.py` + `templates/trumpflow.html.j2` (d3 force-graph + ledger) → `site/trumpflow.html`; nav link; additive daily.yml step.
- **Ship gate: replay the Feb–Mar 2025 ABTC filings; the page must show the HUT-over-ABTC short-path + label-mismatch + a rule-emitted HUT overweight thesis dated 2025-03-31.** Held-out validation.

**P2 — LLM extraction + reasoning** *(gated)*
- `engine/trumpflow/extract.py` (L1, `catalyst_tone` gates, watermark-dedup) → `events.jsonl`.
- `engine/entity_news.py` GDELT entity layer.
- `engine/trumpflow/desk.py` (L3 panel, clone `policy_intent_desk`, `interval_days=7`, novelty trigger) → `source='llm'` rows; `_reconcile` clamp; zh via `_translate_brief`.
- `data/trumpflow/intel.json` hand-curated substrate.
- Ship gate: weekly desk run produces a HUT thesis with `structural_proxy` dissent; cold-key run still emits rule theses (LLM is amplifier, not dependency).

**P3 — Falsifiable ledger maturity + basket binding**
- `theme_scoring` priors + proxies for `trump_ai_power_infra` / `trump_crypto_treasury` / `trump_defense_primes`.
- Human-curated `membership.json` baskets (members dated from catalyst events) → free scoring/alerts/rotation/crowding.
- `theme_discovery.discover_candidates(pre_seeded_groups=…)`; `data/policy/intel.json rotation.targeted[]` `basket_id` cross-refs.
- Ship gate: `track_record.json` with a `by_source` bucket renders; first matured theses scored.

---

## 7. Honesty / risks

- **Accountability-first, not alpha-first.** Executive-branch policy bets beating SPY may have ~0 IC — the same NEUTRAL verdict this repo already reached for SUE/insider and demand_ledger Phase-0. **Whole-design falsifier:** after ~12 months, `signal_archive.load_archive('trumpflow')` → IC of short-path/label-mismatch flags vs forward proxy returns. If ~0 IC, the actionable tier collapses to display-only and the desk survives as an auditable narrative + track-record layer. Conviction starts `'low'` and must be *earned*.
- **The alias keystone is the single point of failure.** `aliases.json` is manual/news-driven; a missed rename silently fragments the short-path. Mitigation: LLM-assisted alias *suggestion* (extractor-only, human-confirmed — never auto-merge an alias).
- **LLM hallucination guards (non-negotiable):** LLM touches raw text in *exactly one place* (L1 extractor), every fact passes `catalyst_tone._verify_citations` or is rejected; the LLM **never traverses or invents graph edges** (all discovery is deterministic networkx); the L3 panel only adjudicates over deterministic candidates; `stock_desk._reconcile` clamps overweight on extended/avoid names; every fact carries `FACT|DISCLOSED|INFERRED|RUMORED` provenance, ≥0.8 required before a *scored* thesis.
- **Data licensing.** Quiver Tier-1 ≈ $30/mo + a GitHub secret; rate limits undocumented (defend with the `collectors/base.py` circuit-breaker + ≥1s spacing). Some advertised endpoints (Google Trends, Inflation, ETF Holdings) are unconfirmed in the public python-api — treat as unavailable until tested with a live key. Keep non-commercial.
- **Legal / PEP framing — public information only, non-partisan by construction.** Every input is a public filing (SEC EDGAR, OGE 278-T), a public disclosure (STOCK Act), or public news (GDELT). Never read the user's own holdings; never send raw SEC text to the model (extract scalar fields only). Reason from *revealed financial interest as fact*, never partisan editorializing. Same realpolitik discipline already shipped in `policy_intent_desk` / Fed & Policy Watch.
- **Display-only vs actionable firewall.** L2 `signals.py` is `is_context_only=True`. The desk writes only to `data/trumpflow/`; nothing imports `conditions`/`regime`/`axes`; only a human promotes a finding into `membership.json`. Thin-float entity tickers (DJT, ABTC, DOMH) are `_SOFT` — logged and displayed, never scored.
- **Cost.** L1 extraction scales with new-filing count (near-zero on quiet days, watermark-gated). The L3 panel (~5 DeepSeek V4 Pro calls × ~8k tokens) fires at most weekly *and* only on the deterministic novelty trigger. With no key / disabled, the rule-emitter spine still emits and scores — the LLM is an accountability amplifier, not a dependency.
