# Chronicle — market context timeline engine (masterplan)

**Program:** Agentic Media / Chronicle · **Author:** Fable · **Date:** 2026-07-25 (rev 2 after adversarial review) · **Status:** CHARTERED (W0 spawn-ready)
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` (AM-R5 is this program's constitution)

The operator's core thesis, adopted verbatim as the program goal: *any predictive agent — AI, engine, or human — needs a historical timeline of events plus streaming context to anticipate the future.* Today that timeline exists only implicitly, scattered across ~20 append-only ledgers, nightly snapshots, and the vault catalog. Chronicle makes it explicit, queryable, and budgeted — one event spine, narrative threads over it, and horizon rollups ("streaming consciousness") that every consumer (Mastermind chat, personas, press desks, Research Reports, eventually users) reads through one context-pack API.

## §0 ACCEPTANCE GATES (W0 is not done unless…)

1. **Deterministic + rebuildable (derived layer):** `python -m scripts.build_chronicle --rebuild` regenerates the derived store `data/chronicle/` (events + rollups) from canonical committed sources byte-stable (modulo `generated_at`); deleting it and rebuilding loses nothing. The W1 LLM prose layer lives separately under `data/chronicle/llm/` and is exempt by declaration (see §2.2) — no hand-maintained content anywhere in either store (CXI-R12).
2. **Back-catalog compile, coverage-honest:** every research-vault catalog item, prophet ledger close, and release-ledger row in committed history appears as exactly one event; regime/risk flip events accrue **forward-only from the W0 run date** (derived from consecutive committed snapshots; historical flips are W4 git-archaeology). Idempotent re-runs add zero duplicates (stable event ids).
3. **Packs answer real questions honestly under budget:** `context_pack.pack()` (a) answers "what changed in the last 5 sessions for semis" from real events; (b)/(c) — the 3-month narrative backdrop and the `as_of=<date-3-months-ago>, window=±1w` query — return an explicit **coverage-window statement and an empty-with-reason result** until history accrues (full answers are W4's gate). Every returned line carries a source ref; budget respected via per-tier reserve fractions (§2.4).
4. **Budget (the real one):** spine compile's added wall-clock is measured and printed in the job log; the binding constraint is the **200-minute nightly job cap with ~10 minutes of observed headroom** (worst observed ≈190m, memory: daily-engine-timeout-200m), not the 67-min render figure. If measured cost exceeds ~2 min, the spine moves to its own off-render lane — that is the default posture to propose in the W0 PR, with the in-job step as the fallback.
5. **Ledger law + envelope:** `data/chronicle/*.jsonl` advances only in nightly (intraday lanes discard writes). Envelope stamping uses a **sidecar `data/chronicle/manifest.json`** (a dict — `envelope.stamp()` operates on single dict payloads and cannot stamp a JSONL stream) carrying the standard keys + per-ledger row counts/hashes; `config/synapse.yml` registers the artifacts (`format: jsonl` for ledgers, display tier, `horizon_role: context`).
6. **Public-safe projection BEFORE the brain lobe:** each adapter declares a per-adapter public-safe field allowlist (modelled on `engine/research_vault/catalog.py` `_ITEM_FIELDS` and the marketing governor's public-safe subset — there is no pre-existing shared filter), with a CI test that fails if any event body carries a field outside its adapter's allowlist. Only then is the `chronicle` lobe registered — at **all three** registration points: `LOBE_SUMMARIZERS` (`engine/neuralweb/mastermind_context.py:1567`, currently 20 lobes), `_LOBE_TO_ARTIFACT_IDS` (`:1591`), and the `source_artifacts` map (~`:2262`) — fail-soft like every sibling, serving the short-horizon digest (plus `narratives: []` with a stated accruing-reason until W1). Visible in one real chat answer before the wave closes.
7. **Epistemics:** no event, narrative, or rollup carries an originated score/signal/escalation; LLM-writable fields (W1+) are prose + references only, and no LLM-authored change may move a state upward or raise any numeric field (validator-asserted — note the repo's "validated"-word CI guard scans templates/site only, so this is a chronicle-local validator assertion, a W0/W1 deliverable, not an inherited guard).
8. **Adapter DNR pre-flight:** every adapter (W0 and later) is checked against `research/DO_NOT_REBUILD.md` before wiring, recorded in a one-line table in the PR body (the ignition-radar suspension row already governs one W1 candidate — see §3).

## 1. Placement + non-collision

- **Not a second knowledge base** (CXI-R12): Chronicle's derived layer stores *derived events*, keyed to canonical sources; truth stays in the sources. The Macro Context Index remains the repo-internals retrieval organ (operator/agent audience); Chronicle is a *market-facts* organ (public-safe by construction) — different content class, different audience, no overlap.
- **Not a parallel news store:** breaking/news desks keep their own artifacts; Chronicle ingests references + capped display strings (§2.1), never article bodies.
- **Not the metabolism:** metabolism curates surfaces/keys; Chronicle curates *history*. The nightly compactor borrows the metabolism's budget-capped off-render *pattern* only.
- **`daily_brief_history.jsonl`:** the regime/risk flip adapters **consume** the committed `data/neuralweb/daily_brief_history.jsonl` state-delta ledger where it already records the transition (it is the existing committed derivation of this event class), and re-derive from snapshots only for state classes it does not carry — never a parallel re-derivation of the same rows.
- **`engine/neuralweb/context_api.py`:** boundary — context_api is the shipped **per-ticker PIT dimension snapshot** substrate; Chronicle is the **market-facts narrative spine**. Vault-W6 uses Chronicle for `as_of` narrative/stance joins and context_api for per-ticker dimensions; neither replaces the other.
- Audience fence (CXI-R23): every event body passes its adapter's public-safe projection (§0.6). Engine-internal diagnostics never enter events.

## 2. Data model (`engine/chronicle/`)

### 2.1 Event spine — `chronicle.event.v1` (`data/chronicle/events.jsonl`, append-only, nightly)

```jsonc
{"id":"cev-<source>-<stable-hash>",      // idempotency key: source + source_ref (+date)
 "ts":"2026-07-25T13:30:00Z",            // event time (source-native), not ingest time
 "date":"2026-07-25",
 "source":"research_vault|prophet_ledger|macro_release|earnings|regime_flip|risk_band",   // W0 set (6)
 "source_ref":"<catalog id / ledger row id / artifact path#key>",
 "kind":"report|signal_close|print|earnings|state_flip",
 "title":"Goldman: hedge funds least long Mag7 in 10 years",
 "facts":["…strings derived from the source artifact…"],
 "tickers":["NVDA"], "themes":["positioning","mag7"],
 "horizon_hint":"short|medium|long",      // deterministic mapping by kind (report=medium, print=short, …)
 "weight_hint":0-3,                       // DETERMINISTIC salience (regime flip=3, routine print=1). Not display-only:
                                          // it orders pack inclusion (§2.4) — which is exactly why no LLM may set or raise it.
 "links":{"site":"/research/<slug>.html","source":null,"receipt":null}}
```

**Third-party-derived events** (vault reports about street research; any future news-class adapter) obey the AM-R4 rev-3 line, validator-enforced: a per-fact string length cap (~200 chars) so the spine stores *facts*, not passages, and `links.source` populated where a source URL exists. Attribution rendering is a per-surface editorial choice (the timeline page and press desks decide), not a spine mandate — the spine's job is to keep stored strings short and factual.

**W0 adapters (6, all reading committed artifacts; each ~50-line pure function, fail-soft per adapter):**
`research_vault` (`data/research_vault/catalog.json` items → one event each; `summary_points` → `facts`, subject to the third-party constraints); `prophet_ledger` (`data/prophet/ledger.jsonl` closes); `macro_release` (`data/release_forecast/forward_ledger.jsonl` + calendar prints); `earnings` (the **committed nightly earnings artifact** — `data/earnings/` parquet written by the nightly, NOT `engine/marketing/earnings_feed.py`, which is fetch-only and writes nothing); `regime_flip` + `risk_band` (deltas between consecutive committed snapshots — `data/neuralweb/world_state.json` regime label + risk band artifacts (`data/risk_radar/` scorecard/forward log), consuming `daily_brief_history.jsonl` rows where they already record the transition; **forward-only from W0**, history = W4).

**Deferred adapters:** `breaking` is **not in W0** — the breaking-desk store is gitignored/local-only, so events from it would be irreproducible; it joins in W1 *only* with a committed source (either a new committed, nightly-advanced `data/marketing/breaking/items.jsonl` or the committed outbox receipts), with its rebuild-exemption named in gate 1 if partial. Other W1+ candidates: theme_thesis ledger, china/hk ledgers, darkpool context deltas, marketing publication receipts (our own public calls join the timeline). `ignition audit grades` is a candidate **blocked on DNR:137's re-surface conditions + an operator ruling** (registry-suspended surface) — listed to make the block visible, not to invite wiring.

### 2.2 Narratives — `chronicle.narrative.v1` (W1; staging + promote, split store)

Storylines that thread events: `{id, title, state: emerging|escalating|cooling|resolved, event_ids[], first_ts, updated_at, plain_summary (≤80w), watch_next (≤30w), themes, tickers}`.

- **Store split (CXI-R12):** LLM-authored prose lives under **`data/chronicle/llm/narratives.jsonl`** — declared irreproducible, never a truth source, references only into the derived layer; deleting it degrades (packs lose narrative prose) but breaks nothing (validator-tested). The derived layer (`data/chronicle/`) keeps gate-1 byte-stable rebuild.
- **Ledger law:** the compactor runs **off-render** and writes a **staging artifact**; the **nightly promotes** staging into `data/chronicle/llm/narratives.jsonl`. No lane outside nightly commits any `data/chronicle/**` ledger. (W1 acceptance gate.)
- **De-escalate-only, mechanically:** the LLM may merge, close, and move states *downward* (`escalating→cooling→resolved`); `emerging` and `escalating` are assigned **deterministically** by the spine (event count / distinct-source count / weight rule computed before the LLM sees the cluster). The LLM never sets or raises `weight_hint`, never assigns an upward state, never introduces a number absent from referenced facts. Validator enforces: every `event_id` exists; no originated numbers; plain-word stance vocabulary only; monotone-legal transitions (resolved terminal; reopen = new narrative linking the old); any upward state change or numeric raise in an LLM-authored diff = hard fail.

### 2.3 Rollups — the "streaming consciousness" tiers (`data/chronicle/rollups/`, derived layer)

- **short** (`daily/<date>.json`): last 5–10 sessions, event-level, ≤1.5k tokens.
- **medium** (`weekly/<iso-week>.json`): rolling 13 weeks, narrative-level, ≤2.5k tokens.
- **long** (`epoch/<yyyy-mm>.json`): 6–24 months, epoch cards ("the AI-capex bind era", dated regime segments), ≤2k tokens — W1+, LLM-drafted into the `llm/` store, validator-checked, frozen once written (append corrections as errata, never rewrite history).

W0 ships short+medium deterministically (template renderings of events); W1 adds LLM polish + the long tier. Rollups are the compression ladder the operator described: day-by-day, week-by-week, epoch — each tier is what a human analyst "remembers" at that distance. Every rollup states its coverage window (honest-depth law, §4).

### 2.4 Context packs — `engine/chronicle/context_pack.py`

**The one pack symbol every consumer binds:** `context_pack.pack(topics=None, tickers=None, horizons=("short","medium"), token_budget=3000, as_of=None, window=None) -> {"lines":[{text, source_ref, site_url}], "narratives":[…], "coverage":{start,end,note}, "budget_used":n}` — deterministic assembly with **per-tier reserve fractions** (long 20% / medium 30% / short 50% of budget when all three horizons are requested; unused reserve spills down) so tier budgets compose under any `token_budget`. `as_of` + `window` give time-travel queries their testable form (empty-with-reason until W4 depth exists). Consumers: brain-gateway lobe (§0.6), marketing copywriter context (Persona §5), press desks (Media §4), Research Reports, admin inspector. The **pack-injection helper** (prompt-assembly wrapper) ships in **Chronicle W2 and nowhere else** — Persona/Media call it, never re-implement it.

## 3. Waves

| Wave | Ships | Not done unless (per-wave gates) | Model lane |
|---|---|---|---|
| **W0** | `engine/chronicle/` spine + 6 adapters, short/medium rollups (deterministic), `context_pack.pack`, `scripts/build_chronicle.py`, manifest envelope, dag/daily (or off-render lane) wiring, synapse registration, per-adapter public-safe projections + CI test, brain lobe (3 registration points), admin Chronicle inspector (read-only), tests | §0 gates 1–8 | Opus `builder`; admin panel markup pinned by commissioning session or `designer` |
| **W1** | Narrative compactor (off-render staging → nightly promote), `llm/` store split, long-tier epochs, full validator suite (§2.2), errata mechanism, `breaking` adapter iff committed source lands | staging/promote flow proven (no off-nightly ledger commit); delete-`llm/`-store degradation test green; validator kills a seeded upward-state + originated-number diff; compactor budget cap + circuit breaker configured; brain lobe now serves real narratives | cheapest model passing validator (start sonnet, effort low) via `builder` |
| **W2** | **Pack-injection helper** (single owner) + consumer wiring: copywriter persona context, press desk context, Mastermind prompt-budget tuning; `as_of` packs exposed for vault-W6 | helper is the only prompt-assembly site (grep-proven); one logged sample per consumer shows pack lines with source refs | Opus `builder` |
| **W3** | **User-facing timeline page** (`/timeline` or macro.html module): the market's story, three-horizon lens, plain-word, EN/ZH | committed reference crops under `mockups/refs/chronicle/`; light+dark+zh screenshots in PR body; public-safe CI assertion green; nav-gap + render-cost checks green; DESIGN_DOCTRINE glance-tier budgets held | `designer` (frontend-design skill + DESIGN_DOCTRINE mandatory) |
| **W4** | Back-history densification: git-archaeology adapters over committed artifact history (incl. historical regime/risk flips), coverage report, full gate-3(b)/(c) answers | coverage report printed (windows per source); §0 gate-3 queries (b)/(c) answer with real content; archaeology cost measured off-render | Opus `builder` |

## 4. Honest limits (printed)

- **Vault history is days old** (~80 items at charter, growing hourly). The 6–12-month backdrop the operator wants will *accrue* — epochs backfill from our own committed engine history (W4) and vault accrual forward. Do not fake depth; every rollup and pack states its coverage window.
- Narrative quality is an LLM product with a validator, not a guarantee; the compactor's failure mode is *bland*, never *wrong-numbers or escalation* (validator) — accepted trade.
- `weight_hint` is deterministic and crude by design; anything smarter is a promotion question with a prereg, not a tweak.
- Mastermind gains history awareness only as deep as the spine; answers about pre-Chronicle history remain grounding-digest quality.

## 5. Spawn prompt seeds (W0)

Builder spawn must inline: §0 gates verbatim; the event schema + third-party constraints (§2.1); the 6-adapter source list with exact paths (`data/research_vault/catalog.json`, `data/prophet/ledger.jsonl`, `data/release_forecast/forward_ledger.jsonl`, the committed nightly earnings artifact under `data/earnings/`, `data/neuralweb/world_state.json` + `data/neuralweb/daily_brief_history.jsonl`, `data/risk_radar/` scorecard/forward log); the **three** brain registration points (`LOBE_SUMMARIZERS` `engine/neuralweb/mastermind_context.py:1567`, `_LOBE_TO_ARTIFACT_IDS` `:1591`, `source_artifacts` ~`:2262`); synapse/dag/daily wiring per the marketing-governor precedent (`docs/MARKETING_LOBE_BUILD_SPEC.md` §Registration); manifest-sidecar envelope stamping via `engine.neuralweb.envelope.stamp` (dict payloads only); per-adapter public-safe projection requirement + CI test; house test conventions (`tests/test_marketing_engine.py` as the shape reference).
