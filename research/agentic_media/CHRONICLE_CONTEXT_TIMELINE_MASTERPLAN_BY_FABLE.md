# Chronicle — market context timeline engine (masterplan)

**Program:** Agentic Media / Chronicle · **Author:** Fable · **Date:** 2026-07-25 · **Status:** CHARTERED (W0 spawn-ready)
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` (AM-R5 is this program's constitution)

The operator's core thesis, adopted verbatim as the program goal: *any predictive agent — AI, engine, or human — needs a historical timeline of events plus streaming context to anticipate the future.* Today that timeline exists only implicitly, scattered across ~20 append-only ledgers, nightly snapshots, and the vault catalog. Chronicle makes it explicit, queryable, and budgeted — one event spine, narrative threads over it, and horizon rollups ("streaming consciousness") that every consumer (Mastermind chat, personas, press desks, Research Reports, eventually users) reads through one context-pack API.

## §0 ACCEPTANCE GATES (W0 is not done unless…)

1. **Deterministic + rebuildable:** `python -m scripts.build_chronicle --rebuild` regenerates `data/chronicle/` from canonical sources byte-stable (modulo `generated_at`); deleting the directory and rebuilding loses nothing. No hand-maintained content anywhere in the store (CXI-R12).
2. **Full back-catalog compile:** every research-vault catalog item, prophet ledger close, breaking-desk item retained on disk, and regime/risk state flip derivable from committed history appears as exactly one event; idempotent re-runs add zero duplicates (stable event ids).
3. **Packs answer real questions under budget:** `context_pack()` returns coherent briefs for the three canonical queries — (a) "what changed in the last 5 sessions for semis," (b) "what is the 3-month narrative backdrop for rates," (c) "what happened around <date-3-months-ago> ±1w" — each within its token budget, each line carrying a source ref.
4. **Zero render-path cost:** spine compile adds ≤2 min inside the nightly engine job (measured, printed in the job log) or runs in its own off-render lane; the 67-min render budget is untouched. LLM compaction (W1) never runs on the render path.
5. **Ledger law:** `data/chronicle/*.jsonl` advances only in nightly (intraday lanes discard writes, same as every forward ledger); artifacts carry the standard envelope stamp; `config/synapse.yml` registers them (display tier, `horizon_role: context`).
6. **Brain lobe live:** a `chronicle` entry in `LOBE_SUMMARIZERS` (`engine/neuralweb/mastermind_context.py`, currently 22 lobes) serves the short-horizon digest + open narratives to Mastermind, fail-soft like every sibling; visible in one real chat answer before the wave closes.
7. **Epistemics:** no event, narrative, or rollup carries an originated score/signal/escalation; LLM fields (W1+) are prose + references only; the word "validated" appears nowhere (CI guard already enforces).

## 1. Placement + non-collision

- **Not a second knowledge base** (CXI-R12): Chronicle stores *derived events*, keyed to canonical sources; truth stays in the sources. The Macro Context Index remains the repo-internals retrieval organ (operator/agent audience); Chronicle is a *market-facts* organ (public-safe by construction) — different content class, different audience, no overlap.
- **Not a parallel news store:** breaking/news desks keep their own artifacts; Chronicle ingests references (adapter), not copies beyond display strings.
- **Not the metabolism:** metabolism curates surfaces/keys; Chronicle curates *history*. The nightly compactor borrows the metabolism's budget-capped off-render *pattern* only.
- Audience fence (CXI-R23): every event body is public-safe (facts already shipped by the site, vault summaries already public in `catalog.json`, market prints). Engine-internal diagnostics never enter events.

## 2. Data model (`engine/chronicle/`)

### 2.1 Event spine — `chronicle.event.v1` (`data/chronicle/events.jsonl`, append-only, nightly)

```jsonc
{"id":"cev-<source>-<stable-hash>",      // idempotency key: source + source_ref (+date)
 "ts":"2026-07-25T13:30:00Z",            // event time (source-native), not ingest time
 "date":"2026-07-25",
 "source":"research_vault|prophet_ledger|breaking|macro_release|regime_flip|risk_band|earnings|altdata_event|marketing_receipt",
 "source_ref":"<catalog id / ledger row id / artifact path#key>",
 "kind":"report|signal_close|news|print|state_flip|earnings|flow_event|receipt",
 "title":"Goldman: hedge funds least long Mag7 in 10 years",
 "facts":["…verbatim/near-verbatim strings lifted from the source artifact…"],
 "tickers":["NVDA"], "themes":["positioning","mag7"],
 "horizon_hint":"short|medium|long",      // deterministic mapping by kind (report=medium, print=short, …)
 "weight_hint":0-3,                       // deterministic salience (e.g. regime flip=3, routine print=1); DISPLAY ONLY
 "links":{"site":"/research/<slug>.html","receipt":null}}
```

W0 adapters (all read committed artifacts; each ~50-line pure function, fail-soft per adapter):
`research_vault` (catalog items → one event each, `summary_points` → `facts`); `prophet_ledger` (`data/prophet/ledger.jsonl` closes); `breaking` (breaking-desk retained items); `macro_release` (release ledgers, e.g. `data/release_forecast/forward_ledger.jsonl` + calendar prints); `regime_flip` + `risk_band` (state deltas between consecutive committed snapshots — the flip event is *derived*, so history rebuilds from git-committed artifacts without a new writer); `earnings` (earnings feed events already used by marketing). W1+ candidates: theme_thesis ledger, china/hk ledgers, darkpool context deltas, ignition audit grades, marketing publication receipts (our own public calls become events — the receipts culture joins the timeline).

### 2.2 Narratives — `chronicle.narrative.v1` (`data/chronicle/narratives.jsonl`, W1)

Storylines that thread events: `{id, title, state: emerging|escalating|cooling|resolved, event_ids[], first_ts, updated_at, plain_summary (≤80w), watch_next (≤30w), themes, tickers}`. Produced by the **nightly compactor** (off-render, budget-capped): the LLM proposes clustering + prose; a deterministic validator enforces — every `event_id` exists; no numbers in prose absent from the referenced facts; no stance vocabulary beyond the house plain-word set; state transitions monotone-legal (resolved is terminal; reopen = new narrative linking the old). LLM may merge/close (de-escalate) narratives freely; *promoting* salience beyond deterministic `weight_hint` requires ≥2 distinct sources among the referenced events (mechanical check, not judgment).

### 2.3 Rollups — the "streaming consciousness" tiers (`data/chronicle/rollups/`)

- **short** (`daily/<date>.json`): last 5–10 sessions, event-level, ≤1.5k tokens.
- **medium** (`weekly/<iso-week>.json`): rolling 13 weeks, narrative-level, ≤2.5k tokens.
- **long** (`epoch/<yyyy-mm>.json`): 6–24 months, epoch cards ("the AI-capex bind era", dated regime segments), ≤2k tokens, LLM-drafted W1+, validator-checked, frozen once written (append corrections as errata, never rewrite history).

W0 ships short+medium deterministically (template renderings of events/threads); W1 adds LLM polish + long tier. Rollups are the compression ladder the operator described: day-by-day, week-by-week, epoch — each tier is what a human analyst "remembers" at that distance.

### 2.4 Context packs — `engine/chronicle/context_pack.py`

`pack(topics=None, tickers=None, horizons=("short","medium"), token_budget=3000, as_of=None) -> {"lines":[{text, source_ref, site_url}], "narratives":[…], "budget_used":n}` — deterministic assembly: epoch backdrop (if `long` requested) → open narratives filtered by topic/ticker → recent events by recency×weight_hint until budget. `as_of` time-travel (for backtests, W6-style studies, and "what did we know on date X" honesty). Consumers: brain-gateway lobe (§0.6), marketing copywriter context (Persona masterplan §5), press desks (Media masterplan §4), Research Reports, admin inspector.

## 3. Waves

| Wave | Ships | Notes |
|---|---|---|
| **W0** | `engine/chronicle/` spine + adapters ×6, short/medium rollups (deterministic), `context_pack`, `scripts/build_chronicle.py`, dag.yml + daily.yml wiring, synapse registration, brain lobe entry, admin Chronicle inspector panel (read-only), tests | No LLM anywhere. Opus `builder`. ≈1 PR. |
| **W1** | Nightly narrative compactor + long-tier epochs (off-render workflow, explicit token budget + circuit breaker), validator suite, errata mechanism | Model: cheapest that passes validator (start sonnet, effort low); budget cap in config; skip-silently on breaker. |
| **W2** | Consumer wiring: copywriter persona context, press desk context, Mastermind prompt-budget tuning; `as_of` packs for vault-W6 | Lands with Persona W2 / Media W1. |
| **W3** | **User-facing timeline page** (`/timeline` or macro.html module): the market's story, three-horizon lens, plain-word, EN/ZH | `designer` lane; DESIGN_DOCTRINE + frontend-design skill mandatory; glance tier = "what's the story now", technicals demoted to hover; public-safe filter asserted in CI. |
| **W4** | Back-history densification: backfill epochs from committed artifact history (git-archaeology adapters), coverage report printed | Optional depth; display-tier. |

## 4. Honest limits (printed)

- **Vault history is ~days old** (79 items, 2026-07-23→25 in the committed snapshot). The 6–12-month context backdrop the operator wants will *accrue* — epochs backfill from our own committed engine history (W4) and from vault accrual forward. Do not fake depth; rollups state their coverage window.
- Narrative quality is an LLM product with a validator, not a guarantee; the compactor's failure mode is *bland*, never *wrong-numbers* (validator) — accepted trade.
- `weight_hint` is deterministic and crude by design; anything smarter is a promotion question with a prereg, not a tweak.
- Mastermind gains history awareness only as deep as the spine; answers about pre-Chronicle history remain grounding-digest quality.

## 5. Spawn prompt seeds (W0)

Builder spawn must inline: §0 gates verbatim; the event schema (§2.1); adapter source list with exact paths (`data/research_vault/catalog.json`, `data/prophet/ledger.jsonl`, `data/release_forecast/forward_ledger.jsonl`, breaking-desk store path per `engine/marketing/breaking_feed.py`, regime/risk snapshot paths per `engine/neuralweb/mastermind_context.py` `_summarize_market`); `LOBE_SUMMARIZERS` registration point (`engine/neuralweb/mastermind_context.py:1567`); synapse/dag/daily wiring per the marketing-governor precedent (`docs/MARKETING_LOBE_BUILD_SPEC.md` §Registration); envelope stamping via `engine.neuralweb.envelope.stamp`; house test conventions (`tests/test_marketing_engine.py` as the shape reference).
