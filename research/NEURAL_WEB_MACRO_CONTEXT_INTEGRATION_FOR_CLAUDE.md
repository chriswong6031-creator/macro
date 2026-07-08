# Neural Web Macro Context Integration Research Paper

Date: 2026-07-06
Prepared for: Claude execution handoff
Repo: Macro Dashboard

## Executive Thesis

Neural Web should become a holistic, regime-aware pattern recognition layer, but it should not become an unconstrained "macro opinion machine." The correct design is a governed context system: every signal, idea, contradiction, and historical outcome should know the market state in which it appeared, while all macro context remains display-only until a falsifiable rule earns authority through the existing gauntlet.

The current Neural Web architecture already reconciles the broad design goal. It has:

1. A `world_state` blackboard for current market state.
2. A federated spine index for signals, ledgers, outcomes, regime stamps, and query.
3. A reliability kernel that can eventually learn which engines work in which regimes.
4. A confluence graph that connects signals, regimes, engines, sectors, contradictions, and episodes.
5. A cortex and ask-brain layer that can read Neural Web artifacts under constitutional limits.
6. A Mastermind bridge intended to export compact Neural Web context.

However, the implementation is not yet a complete macro context intake. The evidence says `transmission.html` and `forex.html` are useful and live on the site, and their backing data files exist locally. But the full `data/transmission/latest.json` and `data/forex/latest.json` payloads are not currently first-class Neural Web world-state lobes or Mastermind context lobes. They are only indirectly represented through pieces of `data/regime/latest.json`, the old `engine/master_brain.py`, and the display-only cross-asset contradiction path.

The right next step is not to make rates or FX a buy/sell switch. The right next step is to ingest them as compact, source-stamped context labels attached to Neural Web's signal memory, graph, and ask layer. That lets Neural Web answer questions like:

- Did this bottom signal fire during restrictive real yields or easing real yields?
- Did this sector rotation idea work better when the USD was rising, flat, or falling?
- Was the equity read confirmed or contradicted by bonds and FX?
- Was a commodity-sensitive ticker being recommended into a macro tailwind or headwind?
- Did Oracle's turn model work differently in US Goldilocks, China stagflation, or Hong Kong growth-scare conditions?

Those questions are the practical definition of the holistic pattern-recognition machine. Neural Web should attach state labels, learn conditional reliability over time, surface contradictions, and explain context. It should not grant macro context behavioral authority until evidence proves it.

## Bottom Line Answer

### Is Neural Web currently consuming `transmission.html` and `forex.html`?

Not as first-class Neural Web inputs.

The pages are live:

- `https://mastermind-x.com/transmission.html` returned HTTP 200 on 2026-07-06.
- `https://mastermind-x.com/forex.html` returned HTTP 200 on 2026-07-06.

The local backing files exist:

- `data/transmission/latest.json`
- `data/forex/latest.json`

But Neural Web's main blackboard, `engine/neuralweb/world_state.py`, currently reads a narrower set of sources:

- `data/market_state/latest.json`
- `data/regime/latest.json`
- `data/breadth/breadth.parquet`
- `site/basketdata/oracle_state.json`
- `data/run_status.json`
- `site/factordata/alerts_triage.json`
- factor weather / options weather
- Neural Web contradictions

It does not directly ingest `data/transmission/latest.json` or `data/forex/latest.json`.

There is partial indirect intake:

- `data/regime/latest.json` already contains `rate_inflation_transmission`, `yield_curve`, and `cross_asset_confirm`.
- `engine/cross_asset_confirm.py` reads `data/bonds/bond_health.json` and `data/forex/latest.json`.
- `engine/neuralweb/contradictions.py` reads `data/regime/latest.json:cross_asset_confirm` and creates a display-only contradiction when bonds/FX diverge from the equity read.
- `engine/master_brain.py`, an older/non-Neural-Web state gatherer, already had explicit readers for both FX and rate/inflation transmission.

So the data is present in the wider repo and partly used by older or adjacent systems, but it has not been promoted into Neural Web's core context memory.

### Are these useful to Neural Web?

Yes. They are among the highest-value missing context lobes because they describe the macro water the signals are swimming in.

`transmission.html` and `data/transmission/latest.json` are useful because they encode:

- Real-rate pressure.
- Sticky-inflation pressure.
- Expectations pressure.
- Yield-curve shape and slope context.
- Sector / asset headwinds and tailwinds.
- Whether any transmission chain is currently scored or display-only.

`forex.html` and `data/forex/latest.json` are useful because they encode:

- Dollar regime.
- Real-rate regime.
- Fed-path backdrop.
- USD valuation and trend.
- FX/liquidity direction.
- Currency and asset transmission links.
- Headwind / tailwind mapping for equities, EM, gold, copper, oil, Treasuries, and Bitcoin.

These are exactly the labels Neural Web needs to know when a signal happened, what surrounded it, whether other asset classes agreed, and when a previously strong signal might be fragile.

### Is this integrated yet into Neural Web's system?

Partially architected, not fully integrated.

The system can support this integration. The important primitives already exist:

- Spine rows have regime stamp columns such as `rate_pressure`, `quad_hard_label`, `fused_risk_label`, `vol_regime`, and `risk_radar_state`.
- Spine rows also have role flags such as `is_context`, `is_sizing`, `is_veto`, `is_alpha`, `is_timing`, `falsifier`, and `half_life`.
- Neural Web query can filter by regime labels.
- The confluence graph has regime nodes and display-only edges.
- The Mastermind bridge can auto-include registered lobes when artifacts declare `external_consumers: ["mastermind:context"]`.
- The ask brain can read `world_state` for macro/regime questions.

The missing part is that FX and rate-transmission data have not been made into first-class Neural Web lobes, and most spine rows do not yet carry robust macro labels. The local `spine_index.parquet` had 287,929 rows, but only 3,841 rows had non-null regime stamps in the current snapshot. The qledger adapter explicitly notes that qledger regime fields are currently null. There are no current `scope_type = macro` spine rows, and a direct search of the spine found zero rows matching `forex`, `transmission`, `rate_inflation`, `yield_curve`, `dollar`, or `usd`.

## How Neural Web Actually Functions

Neural Web is not a single model. It is a governed evidence and context system built over many market engines.

The current operating chain is:

1. Domain engines produce artifacts.
   Examples: regime, risk radar, Oracle, altdata, factor alerts, options entry, bottom sensors, sector boards, track records, China/HK/Canada regimes, FX, transmission, bonds, commodities.

2. The Synapse registry declares artifact contracts.
   `config/synapse.yml` tells the system which artifacts exist, where they live, and how downstream systems should treat them. Some artifacts are exported to Mastermind context through `external_consumers`.

3. `world_state` builds a compact blackboard.
   `engine/neuralweb/world_state.py` reads selected current-state files and creates `data/neuralweb/world_state.json`. This is the quick answer to "what does Neural Web think the current market state is?"

4. The spine federates memory.
   `data/neuralweb/spine_index.parquet` is the query layer over ledgers and signal records. It does not migrate every ledger into one monolith. It indexes records, labels, outcomes, and source paths so Neural Web can query across systems.

5. The reliability kernel studies conditional performance.
   The kernel is designed to answer which engines or signal families work under which contexts. It is display-first until enough evidence exists. The first formal kernel FDR batch is scheduled for 2026-10 according to prior program notes.

6. The confluence graph connects signals and context.
   `engine/neuralweb/confluence.py` creates display-only nodes and edges for engines, sectors, regimes, theses, episodes, contradictions, and co-firing families. It explicitly cannot gate, rank, or raise signals.

7. Contradiction detection finds disagreements.
   `engine/neuralweb/contradictions.py` looks for disagreement between selected sources. One existing pair already checks `cross_asset_confirm`, which carries bonds/FX divergence from `data/regime/latest.json`.

8. Cortex and ask-brain read but do not originate.
   `engine/neuralweb/ask_brain.py` and the cortex tooling are read-only / shadow-first layers. They can cite artifacts and explain context, but they do not create official alpha or override calibrated engines.

9. The Mastermind bridge exports compact context.
   `engine/neuralweb/mastermind_context.py` creates `site/neuralwebdata/mastermind_context.json` from registered and summarized Neural Web artifacts. This context is intended to help Mastermind explain candidate setups without changing candidate generation.

The key governing rule is: Neural Web can add context before it can add authority. This matters for macro data. FX, rates, bonds, commodities, and global regimes should first become labels and context. Only later, if a specific rule is falsifiable and passes the gauntlet, should it influence ranking, sizing, veto, or priority.

## Live And Local Evidence Snapshot

Evidence gathered on 2026-07-06 from the current worktree and active live site.

### Live Site

| URL | Status | Finding |
| --- | ---: | --- |
| `https://mastermind-x.com/forex.html` | 200 | FX mapper page is live. |
| `https://mastermind-x.com/transmission.html` | 200 | Rate/inflation transmission page is live. |
| `https://mastermind-x.com/committee.html` | 200 | Neural Web committee page is live. |
| `https://mastermind-x.com/neuralwebdata/bottom_sensors.json` | 200 | Public Neural Web constituent artifact is live. |
| `https://mastermind-x.com/neuralwebdata/kernel_families.json` | 200 | Public Neural Web constituent artifact is live. |
| `https://mastermind-x.com/neuralwebdata/confluence_graph.json` | 200 | Public Neural Web constituent artifact is live. |
| `https://mastermind-x.com/neuralweb/cortex_memo.json` | 200 | Cortex memo is live. |
| `https://mastermind-x.com/factordata/us_standouts.json` | 200 | Public candidate/context source is live. |
| `https://mastermind-x.com/altdata/mastermind.json` | 200 | Public altdata context source is live. |
| `https://mastermind-x.com/basketdata/radar_ticker.json` | 200 | Public radar ticker source is live. |
| `https://mastermind-x.com/factordata/alerts_triage.json` | 200 | Public alerts source is live. |
| `https://mastermind-x.com/neuralwebdata/mastermind_context.json` | 404 | Critical bridge artifact is not currently live, despite local file existing. |

The 404 on `mastermind_context.json` is important. The local bridge artifact exists, and the bridge research program says the public home should be `site/neuralwebdata/mastermind_context.json`. Claude should treat this as a deployment or publication defect before deeper integration work.

### Local Neural Web Artifacts

| Artifact | Status | Key Evidence |
| --- | --- | --- |
| `data/neuralweb/world_state.json` | Exists | Produced 2026-07-05. Reads market, regime, breadth, Oracle, run status, alerts, factor/options weather, contradictions. |
| `data/neuralweb/mastermind_context.json` | Exists | Schema `neural_web_mastermind_context.v1`, as_of 2026-07-02, produced 2026-07-06. |
| `site/neuralwebdata/mastermind_context.json` | Exists locally | Same aggregate bridge target that was 404 live. |
| `data/neuralweb/confluence_graph.json` | Exists | Display-tier graph, as_of 2026-07-01. |
| `data/neuralweb/kernel_families.json` | Exists | Reliability family artifact. |
| `data/neuralweb/spine_index.parquet` | Exists | 287,929 rows, 31 columns. |
| `data/neuralweb/bottom_sensors.parquet` | Exists | Bottom-sensor spine/context input. |
| `data/options_entry/state.parquet` | Exists | Options entry state input. |

### Local Macro Context Artifacts Not Fully Promoted

| Artifact | Current Snapshot | Why It Matters |
| --- | --- | --- |
| `data/forex/latest.json` | Date `Jul 05, 2026`, regime `US growth premium`, risk `risk-on`, favored `USD`. USD valuation fair, trend up, liquidity soft. | Needed as `fx_dollar` Neural Web lobe. It maps dollar pressure and cross-asset headwinds/tailwinds. |
| `data/transmission/latest.json` | As of 2026-07-02, calibrated true, display-only scored status. Headwinds include XLB, XLK, XLF, QQQ, SPY, XLV. Tailwinds include GC=F, TLT, FXI. Active chains include real_rate, sticky_inflation, expectations. | Needed as `rates_transmission` lobe. It maps rate/inflation pressure to sectors and assets. |
| `data/bonds/bond_health.json` | As of 2026-07-02, includes health score, cycle phase, recession risk, drawdown risk, pillars, stress legs, alarms, drivers, Fed path, and cross-asset bond compass. | Needed as `rates_credit` lobe. Bonds are a high-signal contradiction and macro fragility source. |
| `data/commodity/latest.json` | Date Jul 03, 2026, regime Goldilocks, favored Gold/Copper. | Needed as `commodity_context` lobe. Helps interpret resource sectors, inflation, global growth, and safe-haven flow. |
| `data/china_regime/latest.json` | Date 2026-07-03, quad Q3 Stagflation. | Needed in `global_regimes` lobe. China context is especially relevant for commodities, EM, HK, and global risk. |
| `data/hk_regime/latest.json` | Date 2026-07-03, quad Q4 Growth-scare. | Needed in `global_regimes` lobe. Helps separate local market stress from US macro context. |
| `data/canada_regime/latest.json` | Date 2026-07-03, quad Q1 Goldilocks. | Needed in `global_regimes` lobe. Helps compare North American resource / rate sensitivity. |
| `site/intelligence/briefing.json` | As of 2026-07-06, includes divergence counts and priority/actionable items. | Needed as richer intelligence lobe. Currently only narrow contradiction usage is visible. |
| `site/intelligence/by_ticker.json` | As of 2026-07-06. | Needed to connect intelligence divergences to ticker-level signal context. |
| `site/factordata/factor_series.json` | As of 2026-07-02. | Needed for deeper factor weather and crowding / rotation context. |

## Reconciliation: What We Built Versus What Is Missing

The previous claim was directionally right: Neural Web should use macro regimes and different states to assess when signals work and when they do not. The current codebase shows that this principle has already been accepted and partially built.

What is already built:

- `engine/neuralweb/query.py` includes regime stamp columns.
- The spine adapter maps `rate_pressure`, `quad_hard_label`, `fused_risk_label`, `vol_regime`, and `risk_radar_state`.
- Query can filter across those regime fields.
- The confluence graph creates regime nodes.
- The reliability kernel is intended to learn conditional performance.
- The cortex and ask brain can read world state and cite artifacts.
- The Mastermind bridge is designed to ship context-only Neural Web summaries.

What is still missing:

- Direct world-state lobes for FX/dollar, rate/inflation transmission, bonds/credit, global regimes, commodities, and intelligence briefing.
- Direct Mastermind bridge summaries for these lobes.
- Macro-scope rows in the spine.
- Broad, consistent regime stamps across qledger and other adapters.
- A live public `mastermind_context.json` endpoint.
- Ask-brain routing that knows when to read richer macro lobes rather than only generic world state.
- Tests proving these lobes cannot change ranking, sizing, veto, or candidate generation.

The reconciliation is therefore:

Neural Web is already architected to attach state labels and learn conditional reliability, but it has not fully populated the macro state layer. It has the skeleton, not the full nervous system. The next work should attach macro labels to the spine and publish compact macro lobes into world state and Mastermind context, while preserving display-only authority.

## Recommended Integration Model

### Principle 1: Labels Before Claims

A label describes the world at the time a signal appeared.

Examples:

- `quad_hard_label = Q1`
- `fused_risk_label = neutral`
- `vol_regime = normalizing`
- `risk_radar_state = caution`
- `usd_trend = up`
- `real_rate_regime = Restrictive real yields`
- `transmission_active_chains = ["real_rate", "sticky_inflation", "expectations"]`
- `yield_curve_shape = inverted`
- `china_quad = Q3`
- `hk_quad = Q4`

A claim predicts an outcome.

Examples:

- "When USD is rising and FX transmission is unstable, EM equity bottom signals have lower 21-day follow-through."
- "When real rates are restrictive and XLK is a transmission headwind, QQQ breakout signals have worse forward drawdown."
- "When bond health is deteriorating while equity risk is neutral, equity risk-on signals have lower win rate."

Neural Web should ingest the first group immediately as labels. It should only create the second group when each claim has:

- A pre-registered hypothesis.
- A target universe.
- A horizon.
- A direction.
- A falsifier.
- A non-leaky as-of timestamp.
- A planned grading path.

### Principle 2: Context Before Authority

FX, rates, bonds, and global regimes should help Neural Web explain and condition signals. They should not directly change signal priority until they have passed evidence gates.

Initial authority should be:

```json
{
  "display": true,
  "ranking": false,
  "sizing": false,
  "veto": false,
  "origination": false
}
```

### Principle 3: Compact State, Not Raw Payload Dumping

World state and Mastermind context should carry distilled fields, not full dashboards.

For each new lobe, include:

- `asof`
- `source`
- `stale`
- `display_only`
- `scored` or `validated` status where relevant
- top labels
- top headwinds/tailwinds
- top contradictions
- max 5 to 10 notable items
- source artifact path

Do not copy entire page payloads into `world_state.json` or `mastermind_context.json`.

### Principle 4: Every Signal Should Know Its Weather

Future spine rows should carry a compact macro snapshot hash or snapshot id. That allows later historical research to ask:

- What was the macro context when this signal was born?
- What context changed before it succeeded or failed?
- Which signal families degrade under which conditions?
- Which contexts create false positives?
- Which contexts reveal missed opportunities?

Recommended fields:

- `macro_context_id`
- `macro_context_asof`
- `macro_context_hash`
- `quad_hard_label`
- `fused_risk_label`
- `vol_regime`
- `risk_radar_state`
- `rate_pressure`
- `usd_trend`
- `usd_regime`
- `real_rate_regime`
- `yield_curve_regime`
- `bond_cycle_phase`
- `commodity_regime`
- `global_regime_set`

## Proposed New Neural Web Lobes

### 1. `rates_transmission`

Source:

- `data/transmission/latest.json`

Current status:

- Exists locally.
- Backing page is live.
- Not directly in `world_state`.
- Not directly in `mastermind_context`.

Fields to include:

- `asof`
- `scored_status`
- `calibrated`
- `active_chains`
- `headwinds`
- `tailwinds`
- `yield_curve.shape`
- `yield_curve.regime`
- `yield_curve.recession`
- `yield_curve.slopes`
- `yield_curve.momentum`
- `display_only = true`

Use cases:

- Explain when rate pressure is a headwind to a sector idea.
- Attach rate/inflation context to technical and Oracle signals.
- Identify when equity risk reads are fragile because the rate channel disagrees.
- Later study whether specific transmission chains affect follow-through.

Important guardrail:

The current transmission artifact says no rate/inflation leg passed the forward-drawdown bar with purged-CV robustness. Therefore, this lobe must be context-only at first.

### 2. `fx_dollar`

Source:

- `data/forex/latest.json`

Current status:

- Exists locally.
- Backing page is live.
- Used indirectly by `engine/cross_asset_confirm.py`.
- Not directly in `world_state`.
- Not directly in `mastermind_context`.

Fields to include:

- `date`
- `regime`
- `risk`
- `favored`
- `dollar_desk.lean`
- `real_rate_regime`
- `fed_path_bps`
- `usd_valuation`
- `usd_trend`
- `liquidity_dir`
- `smile_confidence`
- `transmission.usd_dir`
- `transmission.asset_correlations`
- `headwind_for`
- `tailwind_for`
- `unstable`
- `display_only = true`

Use cases:

- Explain whether USD direction is a headwind or tailwind to EM, commodities, US equities, bonds, and Bitcoin.
- Attach dollar context to ticker/sector signals.
- Detect contradictions when equity risk is benign but FX transmission says caution.
- Later study whether dollar trend changes false-positive rates for global/commodity signals.

Important guardrail:

FX context can be coincident or confirming. It should not become a predictor by assumption.

### 3. `rates_credit`

Source:

- `data/bonds/bond_health.json`

Current status:

- Exists locally.
- Used by `engine/cross_asset_confirm.py`.
- Not exposed as a rich Neural Web lobe.

Fields to include:

- `asof`
- `health_score`
- `cycle_phase`
- `recession_risk`
- `drawdown_risk`
- `pillars`
- `stress_legs`
- `alarms`
- `drivers_for`
- `fed_path`
- `bond_cross_asset`
- `display_only = true`

Use cases:

- Explain equity/risk contradictions.
- Connect yield-curve and credit stress to sector follow-through.
- Condition bottom signals on whether bond stress is improving or deteriorating.

### 4. `global_regimes`

Sources:

- `data/china_regime/latest.json`
- `data/hk_regime/latest.json`
- `data/canada_regime/latest.json`
- existing US `data/regime/latest.json`

Current status:

- Local files exist.
- Not represented as one compact global Neural Web context lobe.

Fields to include:

- country/market code
- `date`
- `quad`
- `transition_state`
- `risk_state`
- `liquidity_overlay`
- `stale`
- `display_only = true`

Use cases:

- Separate US regime from China/HK/Canada regimes.
- Explain why commodity, EM, Hong Kong, China, and Canada signals may diverge.
- Attach global context to cross-market Oracle and basket ideas.

### 5. `commodity_context`

Source:

- `data/commodity/latest.json`

Current status:

- Exists locally.
- Not a Neural Web lobe.

Fields to include:

- `date`
- `regime`
- `favored`
- top commodity drivers
- gold/copper/oil states if available
- `display_only = true`

Use cases:

- Context for resource sectors.
- Inflation/growth interpretation.
- Cross-check for China and USD regimes.

### 6. `intelligence_context`

Sources:

- `site/intelligence/briefing.json`
- `site/intelligence/by_ticker.json`

Current status:

- Exists locally.
- Public briefing data is current.
- Not a rich Neural Web lobe.

Fields to include:

- `as_of`
- `n_divergences`
- priority counts
- top actionable divergences
- top ticker-level divergences
- source links
- `display_only = true`

Use cases:

- Attach live divergence context to ticker-level questions.
- Help ask-brain answer "what else disagrees with this idea?"
- Provide graph edges from intelligence divergences to tickers/sectors.

### 7. `factor_weather_v2`

Sources:

- `site/factordata/factor_series.json`
- existing factor weather inputs
- `site/factordata/alerts_triage.json`

Current status:

- Some factor/weather summary exists in world state.
- Alerts triage is present but richer alert pressure is not fully summarized.

Fields to include:

- factor trend / breadth
- crowding or rotation states if available
- critical / major alert counts
- top alert families
- source as_of
- `display_only = true`

Use cases:

- Better explain why a signal is swimming with or against factor flow.
- Connect factor pressure to sector/standout candidates.

## Implementation Plan For Claude

### Phase 0: Fix Live Bridge Publication

Priority: critical.

Problem:

`site/neuralwebdata/mastermind_context.json` exists locally, but `https://mastermind-x.com/neuralwebdata/mastermind_context.json` returned 404 on 2026-07-06.

Tasks:

1. Verify the local file exists and is generated by the expected build path.
2. Check whether deployment excludes this file or directory.
3. Ensure `site/neuralwebdata/mastermind_context.json` is committed and published.
4. Add a deploy smoke check for the live route.

Acceptance:

- `curl -I https://mastermind-x.com/neuralwebdata/mastermind_context.json` returns 200.
- Response body has schema `neural_web_mastermind_context.v1`.
- The artifact includes `authority.display = true` and all behavior authority flags false.

### Phase 1: Register Missing Artifacts In Synapse

Priority: high.

Likely file:

- `config/synapse.yml`

Add or verify artifact entries for:

- `forex-latest` -> `data/forex/latest.json`
- `transmission-latest` -> `data/transmission/latest.json`
- `bond-health` -> `data/bonds/bond_health.json`
- `commodity-latest` -> `data/commodity/latest.json`
- `china-regime-latest` -> `data/china_regime/latest.json`
- `hk-regime-latest` -> `data/hk_regime/latest.json`
- `canada-regime-latest` -> `data/canada_regime/latest.json`
- `site-intelligence-briefing` -> `site/intelligence/briefing.json`
- `site-intelligence-by-ticker` -> `site/intelligence/by_ticker.json`
- `site-factor-series` -> `site/factordata/factor_series.json`

For context-exported lobes, add:

```yaml
external_consumers:
  - mastermind:context
```

Guardrail:

Do not add any behavior-changing consumer. These artifacts should be context/display only.

Acceptance:

- Synapse registry validation passes.
- `docs/SIGNAL_BUS.md` is regenerated or verified fresh.
- New artifacts appear in the Mastermind context lobe manifest only if explicitly selected.

### Phase 2: Add New World-State Lobes

Priority: high.

Likely file:

- `engine/neuralweb/world_state.py`

Add compact composers:

- `_compose_rates_transmission(...)`
- `_compose_fx_dollar(...)`
- `_compose_rates_credit(...)`
- `_compose_global_regimes(...)`
- `_compose_commodity_context(...)`
- `_compose_intelligence_context(...)`

Design requirements:

- Fail open when a source is missing.
- Preserve source paths and as_of timestamps.
- Mark all lobes display-only.
- Include stale flags.
- Include scored/calibrated status when available.
- Limit arrays to compact top-N slices.
- Do not copy raw page-size payloads.
- Do not affect any engine score, rank, size, veto, or candidate universe.

Suggested top-level shape:

```json
{
  "rates_transmission": {
    "asof": "2026-07-02",
    "source": "data/transmission/latest.json",
    "display_only": true,
    "scored_status": "...",
    "active_chains": [],
    "headwinds": [],
    "tailwinds": [],
    "yield_curve": {}
  },
  "fx_dollar": {
    "asof": "Jul 05, 2026",
    "source": "data/forex/latest.json",
    "display_only": true,
    "regime": "...",
    "risk": "...",
    "usd_trend": "...",
    "headwind_for": [],
    "tailwind_for": []
  }
}
```

Acceptance:

- `data/neuralweb/world_state.json` contains the new lobes.
- Existing world-state keys are preserved.
- Missing source files do not fail the build.
- No new lobe contains behavior-authority fields set to true.

### Phase 3: Extend Mastermind Context Bridge

Priority: high.

Likely file:

- `engine/neuralweb/mastermind_context.py`

Tasks:

1. Add source artifact IDs for the new macro/context artifacts.
2. Add lobe summarizers for:
   - `rates_transmission`
   - `fx_dollar`
   - `rates_credit`
   - `global_regimes`
   - `commodity_context`
   - `intelligence_context`
   - `factor_weather_v2`
3. Include these lobes in `lobe_manifest`.
4. Keep payload compact.
5. Keep all bridge authority context-only.

Acceptance:

- `site/neuralwebdata/mastermind_context.json` includes the new lobes.
- Total payload remains comfortably small enough for the live site.
- Candidate feeds remain direct. Neural Web only adds context.
- Mastermind `regime_frame` is not replaced.
- No names outside the candidate/context universe are introduced unless already present in source artifacts.

### Phase 4: Add Display-Only Graph Edges

Priority: medium.

Likely file:

- `engine/neuralweb/confluence.py`

Add graph support for:

- rate-transmission headwind/tailwind edges to sectors/assets
- FX headwind/tailwind edges to assets and broad groups
- bond/credit stress edges to equity risk state
- global regime nodes for US, China, HK, and Canada
- intelligence divergence edges to tickers/sectors

Required edge metadata:

```json
{
  "tier": "display",
  "authority": "context_only",
  "can_gate": false,
  "can_rank": false,
  "can_raise": false
}
```

Acceptance:

- Graph builds successfully.
- New nodes and edges appear in `data/neuralweb/confluence_graph.json`.
- Existing hard law remains: confluence never gates, ranks, or raises.

### Phase 5: Backfill Macro Labels Into The Spine

Priority: high, but after compact lobes exist.

Likely files:

- `engine/neuralweb/query.py`
- spine build scripts or adapters
- qledger adapter
- track record adapter

Tasks:

1. Fix the qledger regime-stamp gap.
2. Add `macro_context_id`, `macro_context_asof`, and `macro_context_hash` to new spine rows where feasible.
3. Consider `scope_type = macro` context rows for daily macro states.
4. Ensure macro rows are `is_context = true`.
5. Keep `direction = 0` unless the row is a pre-registered, falsifiable claim.
6. Backfill carefully using only as-of-safe state. Do not leak future regime labels into historical rows.

Acceptance:

- New spine builds include macro labels on materially more than the current 3,841 stamped rows.
- qledger rows no longer have all-null regime fields when the underlying record has an as-of date.
- Macro context rows do not masquerade as alpha claims.
- Query can filter: "show signals born during restrictive real yields and rising USD."

### Phase 6: Teach Ask-Brain To Use Rich Macro Context

Priority: medium.

Likely file:

- `engine/neuralweb/ask_brain.py`

Tasks:

1. Update classifier seeds for macro/rates/FX/bonds/commodities/global-regime questions.
2. Ensure responses cite artifact paths.
3. Prefer `world_state` macro lobes for current conditions.
4. Prefer spine/kernel only for historical or reliability questions.
5. Add refusal/limitation language when a lobe is display-only.

Acceptance:

- Ask-brain can answer: "What is the current dollar and rate backdrop for QQQ?"
- It cites `data/forex/latest.json`, `data/transmission/latest.json`, and/or `data/neuralweb/world_state.json`.
- It does not turn the context into financial advice or a buy/sell command.

### Phase 7: Tests And Docs

Priority: high.

Tests to add or update:

- World-state lobe composer tests with missing source files.
- World-state real-data smoke test.
- Mastermind context payload schema and authority tests.
- Confluence graph display-law test for new edges.
- Spine query tests for macro/regime filters.
- Ask-brain classification tests for FX/rates questions.
- Synapse registry validation.
- `docs/SIGNAL_BUS.md` freshness test.
- Live deploy smoke test for `mastermind_context.json`.

Commands to run where applicable:

```bash
python -m pytest tests/test_neuralweb_world_state.py
python -m pytest tests/test_neuralweb_mastermind_context.py
python -m pytest tests/test_neuralweb_confluence.py
python -m pytest tests/test_neuralweb_query.py
python -m pytest tests/test_signal_bus_doc.py
python scripts/check_synapse_registry.py
```

Use the repo's existing test names if these exact files differ.

## Specific Code Targets

### `engine/neuralweb/world_state.py`

Current role:

- Builds `data/neuralweb/world_state.json`.
- Reads selected state artifacts.

Needed change:

- Read and summarize the missing macro context files.
- Add compact lobes while preserving current output.

Do not:

- Add behavioral authority.
- Copy entire raw files.
- Fail the build when optional context is missing.

### `engine/neuralweb/mastermind_context.py`

Current role:

- Builds compact Mastermind context.
- Has rich lobes for market, reliability, contradictions, bottom sensors, options entry, and cortex.

Needed change:

- Add rich summarizers for new macro context lobes.
- Ensure `source_artifacts` includes the new artifact paths.
- Ensure `lobe_manifest` reflects availability, staleness, and rich-summary status.

Do not:

- Replace Mastermind's own candidate universe.
- Replace Mastermind `regime_frame`.
- Set authority beyond context.

### `engine/neuralweb/confluence.py`

Current role:

- Builds a display-only graph connecting engines, sectors, regimes, theses, episodes, and contradiction/confluence edges.

Needed change:

- Add macro context nodes and display-only edges.

Do not:

- Let graph edges gate/rank/raise.

### `engine/neuralweb/query.py`

Current role:

- Reads the spine index and exposes query/filter behavior.
- Already supports regime columns.

Needed change:

- Backfill or adapt additional regime/macro labels, especially qledger.
- Add macro context fields if needed.

Do not:

- Treat macro labels as claims unless falsifiers exist.

### `engine/neuralweb/ask_brain.py`

Current role:

- Read-only Neural Web question-answering over selected tools/artifacts.

Needed change:

- Route FX/rates/bonds/commodities/global-regime questions to the new lobes.

Do not:

- Answer as if display-only context has proven predictive authority.

### `config/synapse.yml`

Current role:

- Central artifact registry.

Needed change:

- Add missing macro/context artifact registrations.
- Mark Mastermind context consumers where appropriate.

Do not:

- Add behavior consumers until authority is earned.

## How Neural Web Will Use This Information

### Current-Signal Explanation

When a ticker or sector signal appears, Neural Web should attach current context.

Example:

```text
Signal: QQQ breakout / options-entry setup
Regime: US Q1 Goldilocks, risk neutral, vol normalizing
Rates: restrictive real yields, real-rate and sticky-inflation chains active
Transmission: QQQ listed as rate/inflation headwind
FX: USD trend up, liquidity soft, US equities listed as headwind
Bonds/FX cross-asset: diverge from equity read
Authority: context-only, no veto
```

Interpretation:

Neural Web does not kill the QQQ signal. It says the signal is firing into a macro headwind and cross-asset divergence, so future research should study whether this setup has lower follow-through or higher drawdown.

### Historical Conditional Reliability

Later, once labels are backfilled, the kernel can ask:

- Did QQQ breakout signals have worse 21-day forward drawdown when rate transmission flagged QQQ as a headwind?
- Did Oracle sector turns work better when USD liquidity was soft or improving?
- Did bottom sensors fail more often when bond health deteriorated?
- Did China-related signals behave differently when US was Q1 but China was Q3?

This is the real pattern-recognition benefit.

### Contradiction Surfacing

Neural Web should surface when systems disagree:

- Equity regime says neutral/risk-on.
- Bonds/FX says caution/diverge.
- Transmission says major equity sectors are headwinds.
- Intelligence briefing says divergence count is rising.

The result should be a displayed contradiction, not a veto.

### Graph Connections

Confluence graph can add edges like:

- `rates_transmission -> XLK headwind`
- `rates_transmission -> QQQ headwind`
- `fx_dollar -> EM equities headwind`
- `fx_dollar -> oil tailwind`
- `china_regime:Q3 -> copper context`
- `bond_health:deteriorating -> equity risk contradiction`

These edges help a human and ask-brain understand why a setup is clean, conflicted, or context-dependent.

### Ask-Brain Answers

After integration, ask-brain should answer:

```text
The current QQQ setup is occurring in US Q1 Goldilocks with neutral risk and normalizing vol, but the rate/inflation transmission lobe lists QQQ as a headwind and active chains include real-rate, sticky-inflation, and expectations pressure. FX context shows USD trend up and liquidity soft. These are context-only labels, not validated vetoes. Source: data/neuralweb/world_state.json, data/transmission/latest.json, data/forex/latest.json.
```

That is the correct behavior.

## What Not To Build

Do not build a macro master score that hand-weights FX, rates, bonds, commodities, and regimes into one number.

Do not let FX or rates directly change:

- rank
- sizing
- veto
- alpha origination
- candidate inclusion
- Oracle output
- Mastermind candidate universe

Do not backfill historical rows with future-known labels.

Do not copy full dashboard payloads into Neural Web context.

Do not make the confluence graph a decision engine.

Do not treat current macro headwinds as proven predictive signals unless the specific hypothesis has passed out-of-sample evidence.

## Research Hypotheses To Register Later

These are examples of falsifiable future claims. They should not be activated until registered and tested.

1. Rising USD plus soft liquidity reduces 21-day follow-through for EM and commodity-linked equity signals.
2. Restrictive real-yield regimes increase forward drawdown for long-duration growth breakouts.
3. Bond/FX divergence from equity risk state increases false-positive rates for risk-on equity signals.
4. China Q3 stagflation reduces reliability of copper-sensitive bullish signals unless commodity context confirms.
5. Rate/inflation headwind flags improve drawdown filtering for sector ETFs only when paired with deteriorating bond health.
6. Cross-market regime dispersion increases the value of contradiction-aware display but not standalone vetoing.

Each hypothesis needs:

- Universe.
- Horizon.
- Direction.
- Falsifier.
- Pre-registration timestamp.
- Out-of-sample grading.
- Multiple-testing control.

## Acceptance Criteria For The Integration

The integration is complete when:

1. `https://mastermind-x.com/neuralwebdata/mastermind_context.json` returns 200.
2. `data/neuralweb/world_state.json` includes compact lobes for rates transmission, FX/dollar, rates/credit, global regimes, commodity context, and intelligence context.
3. `site/neuralwebdata/mastermind_context.json` includes those lobes in its manifest and compact context payload.
4. New lobes are display-only and cannot affect ranking, sizing, veto, or candidate generation.
5. Synapse registry and `docs/SIGNAL_BUS.md` reflect the new artifacts.
6. Confluence graph includes macro context nodes/edges but preserves display-only law.
7. Spine rows begin carrying materially broader macro labels, with qledger regime nulls fixed where possible.
8. Ask-brain can answer rates/FX/macro questions with citations and limitations.
9. Tests pass.
10. Live route smoke checks pass after deployment.

## Suggested Claude Execution Order

1. Start from a clean branch from `origin/main`.
2. Fix publication of `site/neuralwebdata/mastermind_context.json` first.
3. Add Synapse entries for missing macro/context artifacts.
4. Add compact world-state composers.
5. Add Mastermind context summarizers.
6. Add tests around authority and fail-open behavior.
7. Regenerate docs / signal bus.
8. Build Neural Web artifacts locally.
9. Add graph edges only after the lobe payloads are stable.
10. Backfill spine labels only after current-state semantics are settled.
11. Update ask-brain routing.
12. Deploy and live-check the public endpoint.

## Final Recommendation

`transmission.html` and `forex.html` should be integrated into Neural Web, but in the Neural Web way: context first, labels first, display first, evidence before authority.

The current architecture already knows how to become a holistic pattern-recognition system. It has the blackboard, spine, kernel, graph, cortex, and bridge. The missing layer is a richer macro intake that promotes rates, FX, bonds, commodities, global regimes, and intelligence divergences into compact, source-stamped Neural Web lobes.

Once that is done, Neural Web can stop treating signals as isolated events. Every idea can carry its surrounding weather: regime, dollar, real rates, curve, bond stress, commodity tone, global dispersion, factor pressure, and live divergences. Then the kernel can learn which signals are genuinely robust and which ones only looked good in one narrow environment.

That is the right path from dashboard pages to a real market memory system.
