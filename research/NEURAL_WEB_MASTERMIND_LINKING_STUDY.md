# Neural Web -> Mastermind Linking Study for Fable

Date: 2026-07-05
Author: Codex
Purpose: define exactly how Neural Web can be connected to the Mastermind Brain bot, what information can flow, what must remain context-only, and what implementation sequence Fable should review before any build.

## Executive Verdict

We should link Neural Web to Mastermind, but not by making Neural Web a trading brain or by letting the cortex advise the bot in real time. The clean design is a two-layer bridge:

1. Macro Dashboard publishes a compact, deterministic `neural_web_mastermind_context` artifact assembled from committed Neural Web outputs.
2. Mastermind reads that artifact through one new reader, injects it into `market_view` and seat prompts as context, and only later promotes narrow, pre-registered, shrink-only uses after Fable review.

This respects the current house border:

- Neural Web owns rails, memory, governance, synthesis, and reliability context.
- Mastermind owns portfolio construction, position sizing, books, risk limits, and execution.
- Cortex/ask-brain can explain and flag, but cannot originate trades, raise size, rank money-path surfaces, or become a live dependency.

Immediate build target should be an additive read path, not behavior change.

## Current State: What Is Already Linked

### Macro -> Mastermind paths already active

Mastermind already reads several Macro Dashboard products, but these are not yet a unified Neural Web feed.

| Current path | Producer / source | Mastermind consumer | Current use | Evidence |
|---|---|---|---|---|
| US standout board | `site/factordata/us_standouts.json` | `brain/intake.py`, `bot/phase2.py` | candidate corroboration, stops, buy zone, entry grade | `config/synapse.yml:1703-1736`, `/Users/chriswong/Documents/Cluade/Mastermind/brain/intake.py:107-136`, `/Users/chriswong/Documents/Cluade/Mastermind/bot/phase2.py:73-111` |
| Alt-data mastermind feed | `site/altdata/mastermind.json` | `brain/intake.py` | candidate corroboration | `docs/SIGNAL_BUS.md:217-225`, `/Users/chriswong/Documents/Cluade/Mastermind/brain/intake.py:162-174` |
| Radar per-ticker feed | `site/basketdata/radar_ticker.json` | `brain/intake.py` | candidate corroboration and falsifier text | `/Users/chriswong/Documents/Cluade/Mastermind/brain/intake.py:143-158` |
| Macro regime | `vendor/macro/data/regime/latest.json` | `brain/regime_frame.py` | single regime reader, budget, cycles, freshness | `/Users/chriswong/Documents/Cluade/Mastermind/brain/regime_frame.py:1-48`, `/Users/chriswong/Documents/Cluade/Mastermind/brain/regime_frame.py:59-69` |
| Mastermind market view | Mastermind-local `brain/market_view.py` | all books/seats | deterministic perception layer | `/Users/chriswong/Documents/Cluade/Mastermind/brain/market_view.py:1-52`, `/Users/chriswong/Documents/Cluade/Mastermind/bot/phase2.py:270-290` |
| Macro freshness anchors | `vendor/macro/site/*`, `vendor/macro/data/*`, R2 stockdata | `data_layer/macro_refresh.py` | refuses stale macro reads | `/Users/chriswong/Documents/Cluade/Mastermind/data_layer/macro_refresh.py:1-50`, `/Users/chriswong/Documents/Cluade/Mastermind/data_layer/macro_refresh.py:129-149`, `/Users/chriswong/Documents/Cluade/Mastermind/data_layer/macro_refresh.py:312-330` |

Important finding: I found no current Mastermind-side reader for `data/neuralweb/*`, `site/neuralwebdata/*`, `site/neuralweb/cortex_memo.json`, or `/api/ask`. The current bot uses Macro artifacts that overlap with Neural Web, but it is not consuming the full Neural Web suite.

### Neural Web outputs already available

The current Macro worktree contains usable Neural Web material:

| Artifact | Current role | Current size / count observed | Direct Mastermind use today |
|---|---|---:|---|
| `data/neuralweb/world_state.json` | N1 blackboard: verdict, regime, breadth, rotation, liquidity, data health, alerts | 99 KB | none |
| `data/neuralweb/spine_index.parquet` | cross-engine claim/outcome spine | 287,929 rows, 31 columns | none |
| `data/neuralweb/kernel_estimates.parquet` | reliability cells | 22 rows | none |
| `data/neuralweb/confluence_graph.json` | graph of feeds/confirms/contradicts | 197 nodes, 551 edges | none |
| `data/neuralweb/kernel_families.json` | family horizon/staleness summaries | 3.9 KB | none |
| `data/neuralweb/cortex/memo.json` | cortex memo | context-only | none |
| `site/neuralwebdata/bottom_sensors.json` | bottom/entry context envelope | 1,722 rows | none |
| `data/options_entry/state.parquet` | options entry context | 388 rows | none |
| `live_flow/feed_current.json` | intraday live options flow | R2, 1h SLA | flow terminal, not Brain |

Signal bus status is consistent with this: core Neural Web artifacts list zero direct external Mastermind consumers, while `site-us-standouts` explicitly lists `mastermind:anchor` and `mastermind:vendored` as external consumers (`docs/SIGNAL_BUS.md:138-166`, `config/synapse.yml:1703-1736`).

## What Can Be Fed to Mastermind

The feed should be explicit about authority. At birth, every Neural Web component below is context-only unless a separate Fable-approved promotion says otherwise.

### 1. World-state context

Source: `data/neuralweb/world_state.json`

Useful fields:

- `verdict`: single resolved market posture and caveats.
- `regime`: current quad, liquidity overlay, sector RS, and source freshness.
- `risk_radar_raw`: byte-verbatim risk radar block.
- `breadth`, `rotation`, `liquidity`, `alerts`, `data_health`: supporting context.
- `options_entry` lobe if present via world-state composition.

Mastermind use at birth:

- Add an advisory `neural_web_world` plane inside `market_view`.
- Let it annotate `label_vs_planes`, `brief`, and seat prompts.
- It may increase caution only in text, not in size, until Fable approves a shrink-only posture gate.

Do not:

- Replace `regime_frame.py` immediately.
- Let this plane loosen budget, raise offense, or override existing validated planes.

### 2. Confluence graph and contradictions

Source: `data/neuralweb/confluence_graph.json`, mirrored to `site/neuralwebdata/confluence_graph.json`.

Useful fields:

- Contradictions involving a ticker, sector, basket, or macro state.
- Confirming edges across signal families.
- Feed edges showing dependency relationships.
- `contradiction_summary` and `contradiction_records`.

Mastermind use at birth:

- Candidate dossier annotation: "this name/book/sector has unresolved contradiction X".
- Seat prompt forcing function: Risk Officer and PM must mention top contradictions.
- Watchlist/lifecycle reason text: `neural_web_conflict`.

Potential later use:

- Shrink-only confidence cap when a candidate is backed by one family but contradicted by independent, fresh, non-stale evidence.

Do not:

- Treat graph "confirms" as a buy signal.
- Let graph centrality add candidates or increase rank.
- Pipe raw 551-edge graph into prompts; summarize first.

### 3. Spine history and kernel reliability

Sources:

- `data/neuralweb/spine_index.parquet`
- `data/neuralweb/kernel_estimates.parquet`
- `data/neuralweb/kernel_families.json`
- future `data/neuralweb/kernel_decisions.json`

Current facts:

- Spine includes historical `engine='us_board'` rows under `ledger='spine'`, plus qledger, track record, CN/HK/CA boards, cortex attention, reflexes, and options entry context.
- There is no dedicated `board_us` adapter analogous to CN/HK/CA. US board history comes via the generic spine substrate.
- Kernel estimates are display-first. The first decision batch is gated for 2026-10, and should not be treated as trading authority before that clock.

Mastermind use at birth:

- Reliability text beside a candidate: "this source family has N historical graded rows; kernel armed false/true; shrunken IC when present."
- Candidate risk flags: stale family, thin family, ungraded family.
- Research/debug dashboards.

Potential later use:

- Size cap or source discount if a family has passed a Fable-approved reliability rule.

Do not:

- Use raw `shrunken_ic` as a weight before kernel decisions are armed.
- Let a kernel cell promote a name that no existing Mastermind intake source selected.
- Query parquet in every hot path; compile a compact summary upstream.

### 4. Bottom sensors and entry-quality context

Source: `site/neuralwebdata/bottom_sensors.json` and `data/neuralweb/bottom_sensors.parquet`.

Useful fields:

- `trigger_tier`, `trigger_age_ticks`
- `coiled`, `star`, `coiled_fire`
- `donor_state`, `hold_state`, `entry_quality_band`
- `squeeze_state`, `knife`
- distance to 21d low and 126d high
- sponsorship state when available
- balance-sheet survival ratios when available

Mastermind use at birth:

- Candidate card: bottom quality, entry location, hold/basing state, knife risk.
- Entry-risk text beside existing `buy_zone`, stop, and entry grade.
- Seat prompt: force "why now / why not now" on names Mastermind already considers.

Potential later use:

- Withhold or park a new add if a Fable-approved, pre-registered negative condition fires.
- Never add names.

Do not:

- Re-rank the standout board from inside Mastermind.
- Treat `entry_quality_band` as independent alpha. It is context until validated.

### 5. Options entry state and live flow

Sources:

- `data/options_entry/state.parquet`
- `data/options_entry/gate.json`
- `live_flow/feed_current.json`

Current status:

- Options entry state is a display-tier raw-fields fusion table.
- Options gate is shadow and building history; n << 30 per bucket.
- Live flow current has a 1h freshness SLA and is currently external to `mastermind:flow-desk-terminal`.

Mastermind use at birth:

- Add `options_context` block to candidate dossiers: IV, skew, DOI, gamma regime, wall distances, pin risk, evidence quality.
- Entry caution in text only: "options surface thin / pin risk / put-rich contradiction".

Potential later use:

- Only after the options gate validates: shrink-only entry timing veto or entry delay.

Do not:

- Use options fields as signed alpha before gate validation.
- Let live intraday flow alter nightly books without a separate intraday design and stale guard.

### 6. Cortex memo and ask-brain

Sources:

- `data/neuralweb/cortex/memo.json`
- `site/neuralweb/cortex_memo.json`
- `/api/ask` backed by `engine/neuralweb/ask_brain.py`

Current status:

- Cortex is on shadow probation.
- Ask-brain exposes read-only tools, quotas, prompt-injection defenses, and an advice post-filter.
- It returns context-only answers or memo-quote fallback.

Mastermind use at birth:

- Read committed `cortex_memo.json` as a memo/context block for operator review.
- Optionally show it in the Mastermind dashboard UI.

Do not:

- Call `/api/ask` during book builds.
- Feed live ask-brain prose into scoring, ranking, sizing, or candidate generation.
- Let a language answer become an input to order decisions.

If ask-brain is ever used by Mastermind, it should be offline/operator-facing only: "explain why this book was cautious", never "what should the book buy".

### 7. Governance, machine registry, and experiments

Sources:

- `data/neuralweb/governance.jsonl`
- `data/neuralweb/machine_registry.jsonl`
- `data/neuralweb/cortex/probation.json`
- `site/marketdata/experiments.json`

Mastermind use at birth:

- Operational/audit dashboard.
- "This context is shadow/probation/accruing" labels in UI.
- Acceptance-clock awareness for future gates.

Do not:

- Treat a staged hypothesis as a tradable claim.
- Let active experiments change production books without a pre-registered promotion.

## Recommended Bridge Architecture

### Chosen design: Macro-side compact export plus Mastermind-side one reader

Build a new deterministic Macro artifact:

`site/feeds/neural_web_mastermind_context.json`

Potential sibling data copy:

`data/neuralweb/mastermind_context.json`

Why this is better than having Mastermind read raw Neural Web files directly:

- It preserves Mastermind's "one reader" architecture.
- It avoids parquet reads and giant graph payloads in hot book builds.
- It makes freshness and authority explicit.
- It lets Macro own Neural Web schema churn.
- It gives Fable one contract to review.

### Proposed artifact shape

```json
{
  "schema": "neural_web_mastermind_context.v1",
  "as_of": "YYYY-MM-DD",
  "generated_utc": "...",
  "is_context_only": true,
  "authority": {
    "can_add_candidates": false,
    "can_raise_size": false,
    "can_lower_size": false,
    "can_block_entry": false,
    "can_force_exit": false,
    "notes": "All fields advisory until explicit Fable-approved promotion."
  },
  "freshness": {
    "world_state": {"as_of": "...", "stale": false},
    "confluence_graph": {"as_of": "...", "stale": false},
    "bottom_sensors": {"as_of": "...", "stale": false},
    "kernel": {"as_of": "...", "stale": false},
    "cortex_memo": {"as_of": "...", "stale": false}
  },
  "macro_context": {
    "verdict": {},
    "regime": {},
    "risk": {},
    "breadth": {},
    "rotation": {},
    "liquidity": {},
    "data_health": {}
  },
  "source_reliability": {
    "families": [],
    "kernel_decisions": [],
    "kernel_clock": {"first_batch_due": "2026-10-01", "behavior_allowed": false}
  },
  "candidate_context": {
    "TICKER": {
      "bottom": {},
      "options": {},
      "graph_conflicts": [],
      "graph_confirms": [],
      "kernel": {},
      "cortex_notes": [],
      "allowed_behavior": "annotate_only"
    }
  },
  "book_context": {
    "top_macro_contradictions": [],
    "decaying_families": [],
    "attention_items": []
  },
  "gap_notes": [],
  "source_artifacts": []
}
```

### Mastermind-side reader

Add one new module:

`brain/neural_web_context.py`

Responsibilities:

- Read only `vendor/macro/site/feeds/neural_web_mastermind_context.json`.
- Validate schema, `as_of`, freshness, and `is_context_only`.
- Return a stable empty object on any miss or staleness.
- Never import Macro Python modules in the bot hot path.
- Expose:
  - `context()`
  - `candidate(ticker)`
  - `market_plane()`
  - `seat_prompt_block(tickers)`
  - `audit_row()`

This follows the existing Mastermind pattern:

- `regime_frame.py` is the single macro regime reader.
- `market_view.py` is the single perception artifact.
- Neural Web should have one reader, not scattered JSON reads.

### Mastermind integration points

At birth, integrate in three places only:

1. `brain/market_view.py`
   - Add a new advisory plane, `neural_web`.
   - It can mark conflict or degraded coverage.
   - It cannot sign validated `net_posture_tilt`.

2. `brain/pm_conviction.py` / `brain/strategist.py`
   - Add prompt sections:
     - "Neural Web context"
     - "Top contradictions"
     - "Source reliability caveats"
     - "Candidate-specific context"
   - The text must explicitly say context only.

3. `brain/intake.py` or candidate dossier assembly
   - Attach `neural_web_context` to already selected names.
   - It cannot add new names to the funnel.

Do not wire it into:

- order sizing
- budget equation
- cluster caps
- firm exposure caps
- sell path
- new candidate universe
- live intraday order flow

until a separate Fable-approved promotion exists.

## Proposed Build Sequence

### Phase 0: Fable review and contract lock

Deliver this study to Fable.

Fable should rule on:

- artifact path: `site/feeds/neural_web_mastermind_context.json` vs `site/neuralwebdata/mastermind_context.json`
- whether Mastermind may sync the whole `site/feeds/` directory or just one file
- whether any field can be born as shrink-only, or whether all behavior must remain dark
- stale threshold and failure mode
- public/R2 exposure acceptability

No code before these rulings unless the user explicitly asks to prototype.

### Phase 1: Macro export, zero Mastermind behavior

Files likely touched:

- `scripts/build_neuralweb_mastermind_context.py`
- `scripts/build_feeds.py`
- `config/synapse.yml`
- `docs/SIGNAL_BUS.md`
- tests for shape, stale fields, no NaN, additive behavior

Acceptance criteria:

- Artifact exists even when optional inputs are missing.
- Missing inputs create `gap_notes`, not fake neutral values.
- `is_context_only: true` and authority booleans are all false.
- `candidate_context` includes only tickers already present in source candidate surfaces or bottom/options context.
- No raw ask-brain prose is generated.
- No LLM call occurs.

### Phase 2: Mastermind reader and UI/prompt attachment, zero behavior

Files likely touched in Mastermind:

- `brain/neural_web_context.py`
- `data_layer/macro_refresh.py`
- `brain/market_view.py`
- `brain/pm_conviction.py`
- `brain/strategist.py`
- tests for stale guard, prompt inclusion, no scoring changes

Acceptance criteria:

- With artifact absent: book outputs are byte-identical except an explicit "absent" audit log if Fable wants it.
- With artifact present: only prompt/context/audit fields change.
- Candidate set, sizes, caps, budget, orders, and sell decisions remain identical.
- `market_view.net_posture_tilt` does not change.
- Any stale context is excluded, never treated as safe.

### Phase 3: Shadow scoring and attribution

Build a shadow-only ledger:

`data/neural_web_shadow/decisions.jsonl` in Mastermind, or equivalent.

For each book build:

- snapshot the Neural Web context that would have mattered
- record candidate-level conflicts, kernel caveats, bottom/option warnings
- compute "would have blocked / would have shrunk" flags
- grade later against realized MAE, stop-outs, and benchmark ledger

Acceptance criteria:

- No production book reads the shadow flags.
- Shadow definitions are pre-registered.
- Negative and positive controls exist.
- Fable reviews before any arming.

### Phase 4: Narrow shrink-only promotions

Only after Phase 3 evidence:

Potential first promotions:

1. Candidate de-risk annotation -> mandatory Risk Officer acknowledgement.
2. Fresh, independent contradiction -> cap candidate confidence, not add/sell.
3. Options/bottom entry risk -> delay or park a new add, never exit an existing position.
4. Kernel family reliability -> cap source weight when family is thin/stale/failing.

Rules:

- Never add a candidate.
- Never raise size.
- Never loosen a cap.
- Never override hard risk constraints.
- Never take action from cortex prose.
- Every promotion gets a rollback flag and a registry come-back date.

## Information Mapping to Mastermind Surfaces

| Neural Web information | Mastermind surface | Birth authority | Possible later authority |
|---|---|---|---|
| World-state verdict/regime/risk | `market_view` advisory plane, seat prompts | annotate only | shrink-only posture floor if pre-registered and validated |
| Graph contradictions | candidate dossier, Risk Officer prompt | annotate only | confidence cap / mandatory review |
| Graph confirms | dossier text | annotate only | none unless independent outcome evidence proves value |
| Kernel estimates | reliability caveat | annotate only | cap source family after kernel decision batch |
| Kernel decisions | not yet active | none | only after 2026-10 batch and Fable approval |
| Spine rows | offline summaries | annotate only | source reliability after summaries are validated |
| Bottom sensors | entry timing context | annotate only | entry delay/park only after gate |
| Options entry state | options context | annotate only | entry delay/park after options gate validates |
| Live options flow | flow desk only | display only | separate intraday design required |
| Cortex memo | PM/Strategist context | annotate only | none as direct behavior input |
| Ask-brain | operator UI | none | never in build loop |
| Governance/probation | audit and labels | annotate only | none directly |

## Red-Team Notes

### Failure mode 1: Neural Web becomes a second trader

Do not allow. The bridge must carry authority metadata that defaults to false. Mastermind remains the only trading organism.

### Failure mode 2: LLM prose leaks into money path

Do not call `/api/ask` in builds. Do not pass cortex prose into scoring. Read committed memo only, and only as context.

### Failure mode 3: Graph confirmation becomes hidden momentum chasing

The graph can explain corroboration, but cannot rank or add. Confirms are observational until independently graded.

### Failure mode 4: Kernel premature use

Kernel estimates are not kernel decisions. First behavior gate is after the scheduled FDR batch. Until then, all kernel text is caveat/context.

### Failure mode 5: Hot-path parquet and giant graph reads

Avoid this. Compile a compact Macro-side export. Mastermind should read one JSON artifact.

### Failure mode 6: Staleness silently loosens behavior

Stale Neural Web context must disappear or only shrink confidence. It must never make a book more aggressive.

### Failure mode 7: Duplicate world models

Do not replace `regime_frame` or `market_view` immediately. Add a Neural Web plane. If Fable later wants convergence, do it as a separate architecture wave.

## Open Questions for Fable

1. Should the bridge artifact live in `site/feeds/` as a machine contract, or in `site/neuralwebdata/` as a Neural Web public data product?
2. Should Mastermind sync the entire `site/feeds/` directory through the existing R2 manifest path, or add a narrow git/R2 anchor for one file?
3. Should Phase 2 include prompt text only, or also dashboard UI panels?
4. Should `world_state` become a source plane in Mastermind `market_view`, or should the bridge emit its own already-summarized `market_plane`?
5. Should candidate context include all tickers in `bottom_sensors`, or only names already present in Mastermind's current candidate universe?
6. Should options live flow remain terminal-only until a separate intraday bot design exists?
7. What exact shadow ledger metrics should decide the first shrink-only promotion: stop-out reduction, MAE reduction, defensive benchmark improvement, or book-level drawdown?
8. Is public exposure of the bridge artifact acceptable if it only contains already-public site data and context-only labels?
9. Should Fable require `docs/SIGNAL_BUS.md` and `config/synapse.yml` to list Mastermind as an external consumer before the Mastermind-side reader lands?
10. Should any `neural_web_context` prompt section be excluded from the LLM seat until we have prompt-regression tests?

## Recommended Fable Ruling

Recommended ruling:

APPROVE Phase 1 and Phase 2 as context-only. REJECT any immediate behavior-changing link.

Specific approval language:

- Build a Macro-side compact `neural_web_mastermind_context.v1`.
- Build one Mastermind reader.
- Wire it into `market_view` and seats as advisory context only.
- Add freshness guards and a dark shadow ledger.
- No candidate additions, no size increases, no sell/exit triggers, no live ask-brain calls.
- Revisit shrink-only promotions only after shadow evidence and Fable review.

This is the highest-information, lowest-regret bridge: Mastermind starts seeing the full Neural Web picture without letting unearned synthesis become portfolio authority.

## Appendix: Current Evidence Snapshot

Observed in the Macro worktree on 2026-07-05:

- `data/neuralweb/spine_index.parquet`: 287,929 rows.
- Main ledgers: `track_record` 277,070; `qledger` 8,737; `spine` 964; `board_cn` 960; `board_ca` 160; `board_hk` 36; `cortex_attention` 1; `reflexes` 1.
- `engine='us_board'` appears in 950 spine rows, but there is no dedicated `board_us` adapter in `engine/neuralweb/query.py`.
- `data/neuralweb/kernel_estimates.parquet`: 22 rows; engines include `track_record`, `us_board`, `altdata`, `desk:ai_desk`, `policy`, `radar`.
- `data/neuralweb/confluence_graph.json`: 197 nodes, 551 edges.
- `site/neuralwebdata/bottom_sensors.json`: 1,722 rows, `is_display_only` true.
- `data/options_entry/state.parquet`: 388 rows.
- Mastermind code search found no reader for `data/neuralweb`, `site/neuralwebdata`, `world_state`, `ask_brain`, or `/api/ask`.

Key code/document references:

- Neural Web signal bus: `docs/SIGNAL_BUS.md:138-166`.
- Mastermind-facing standouts: `config/synapse.yml:1703-1736`.
- Options NW entry state: `config/synapse.yml:3324-3380`.
- Live options flow external consumer: `config/synapse.yml:3433-3455`.
- Bottom sensors display-only contract: `config/synapse.yml:3608-3655`.
- Neural Web spine query layer: `engine/neuralweb/query.py:1-85`, `engine/neuralweb/query.py:961-1012`.
- Cortex authority limits: `engine/neuralweb/cortex.py:1-35`.
- Ask-brain read-only/advice filter: `engine/neuralweb/ask_brain.py:1-28`, `engine/neuralweb/ask_brain.py:710-745`.
- Feeds plane for world-state copy: `scripts/build_feeds.py:1-18`, `scripts/build_feeds.py:212-224`.
- Committee public Neural Web data copies: `scripts/build_site.py:3637-3660`.
- Mastermind single regime reader: `/Users/chriswong/Documents/Cluade/Mastermind/brain/regime_frame.py:1-48`.
- Mastermind market view invariants: `/Users/chriswong/Documents/Cluade/Mastermind/brain/market_view.py:1-52`.
- Mastermind intake standouts/alt/radar: `/Users/chriswong/Documents/Cluade/Mastermind/brain/intake.py:95-176`.
- Mastermind macro freshness anchors: `/Users/chriswong/Documents/Cluade/Mastermind/data_layer/macro_refresh.py:1-50`.
