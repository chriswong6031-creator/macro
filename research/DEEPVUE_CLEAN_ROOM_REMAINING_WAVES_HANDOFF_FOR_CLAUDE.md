# Deepvue Clean-Room Remaining Waves — Claude Execution Handoff

- **Status:** canonical execution docket for the work that remains after the August 1 teardown
- **Snapshot date:** 2026-08-06
- **Macro Dashboard baseline inspected and refreshed before handoff:** `a1174cec091b02ba8d8aefb7b9358c988d51dc0a` on `origin/main`
- **Terminal baseline inspected:** `feceb369` on `origin/master` in `/Users/chriswong/Documents/Cluade/charting-app`
- **Predecessor:** `research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md`
- **Audience:** Claude/Fable planning sessions, Opus builders/reviewers/designers, and the operator
- **Visibility:** private build handoff; do not publish through `reports.html` or a customer surface

This file supersedes the predecessor's §10 build docket wherever the two differ. The predecessor remains the evidence book for the Deepvue teardown, public-source observations, feature census, AI comparison, and clean-room reasoning. This file is the execution contract for the remaining work after reconciling both repositories on August 6.

The central correction is simple: **do not clone a Deepvue-looking application. Complete the shared intelligence substrate and extend the Terminal workspace that already exists.** Macro Dashboard/Mastermind owns facts, schemas, provenance, query execution, rating vintages, AI routing, Neural Web packets, and Prophet governance. `charting-app` owns the composable operator experience, widget rendering, responsive layout, and interaction state.

---

## §0 — Acceptance gates: paste these into every Claude build prompt

A wave is **not done unless** all gates relevant to it are satisfied. A pointer back to this file is context, not enforcement; the commissioning prompt must repeat the applicable gates inline.

### 0.1 Discovery and collision gates

- Start from freshly fetched remote default branches: Macro `origin/main`; Terminal `origin/master`.
- Create a fresh `claude/<task>` branch in a worktree under that repository's own `.claude/worktrees/<task>/`. Never use either occupied primary checkout, `/private/tmp`, `~/.codex/worktrees`, a reused squash-merged branch, or the repo-global stash.
- Read every root guide that exists, then every nearer guide governing touched files. For Macro this includes root `CLAUDE.md` and `AGENTS.md`; for Terminal this includes root `AGENTS.md` plus `charting-app/terminal/AGENTS.md` and `charting-app/terminal/CLAUDE.md` (and root `CLAUDE.md` when present on the refreshed branch).
- In Macro, read current `docs/ACTIVE_BUILD_MAP.md`, `research/DO_NOT_REBUILD.md`, this handoff, and the predecessor evidence book before proposing files. Regenerate the active map if stale; never edit the generated map by hand.
- Inspect the actual producers and consumers before naming an artifact. Do not infer ownership from page location.
- For a cross-repo wave, create separate worktrees, branches, commits, and PRs. Record the dependency order in both PR bodies.
- If an active PR overlaps a proposed file, split around it or wait. Do not silently overwrite another lane.

### 0.2 Contract and truth gates

- Every new field has a stable `field_id`, value type, unit, entity scope, universe, source, license class, `observed_at`, `effective_at`, `as_of`, freshness budget, point-in-time policy, missingness semantics, renderer, allowed operators, and authority ceiling.
- Every generated packet declares schema/version, producer, generation time, source as-of, coverage, missingness, provenance, and authority. A timestamp on the wrapper does not make stale source values fresh.
- Unknown, unavailable, stale, and not-applicable are distinct states. Never coerce them to zero, neutral, or a successful-looking blank widget.
- Point-in-time claims are reconstructable from append-only vintages. Nightly is the sole advancer of forward ledgers; intraday requests do not mutate them.
- A browser is never the authoritative calculator for universe-wide factors, ranks, ratings, or query results.
- Price performance is not institutional flow. Theme strength, breadth, participation, persistence, and flow witnesses remain separately named fields.

### 0.3 Determinism, AI, and authority gates

- The LLM may translate natural language into a proposed, typed object. A deterministic validator/executor returns facts, rows, math, ratings, and alerts.
- A ticker, number, rating, filter result, or alert may not originate only in LLM prose.
- Field-level facts retain field-level source receipts. Answer-level generic citations are insufficient for a multi-field answer.
- Explicit prompt context wins over pinned context, which wins over active selection, which wins over ambient widget context. The resolved effective context and reason are visible to the user.
- `DNR:KILL-LLM-ORIGINATION` applies: the LLM never originates signals, scores, escalations, or trade authority.
- `DNR:KILL-FUSED-COMPOSITE` applies to scored paths, ordering, sizing, Neural Web authority, and alerts. Its current display-tier exception is specifically for the governed Portfolio Health Score; it does **not** authorize a new Equity Composite Rating. Any equity composite requires a separate explicit adjudication even if its inputs are transparent and coverage-abstaining.
- `DNR:KILL-STAGE-WIN-GATE` applies: Stage remains display/context and may not become a timing win-rate gate. The surviving quality/hold research is a separate governed construction.
- `DNR:KILL-PROPHET-POP-MERGE` applies: do not blend top setups into the Prophet graded population or create one conviction-times-timing rank.
- `DNR:KILL-PUBLIC-INTERNALS` applies: public Brain sessions read shipped product artifacts and curated receipts, never repository source or private research retrieval.
- Ratings, theme states, Stage context, and screen membership enter Neural Web as typed observations first. They affect Prophet rank, direction, timing, entry, or size only after a separate preregistered point-in-time and out-of-sample promotion.

### 0.4 Product and visual gates

- Before any user-facing work, read the target design doctrine and use the repository's designated frontend-design lane. Design choices are made by the designer/Fable lane, not improvised by a mechanical builder.
- A flagship surface needs a committed design spec or committed reference captures before component assembly.
- A UI wave is not done unless the fresh end-to-end happy path works with zero reloads, console surgery, or manual storage cleanup.
- Entry points are actually wired. A component that exists but cannot be reached through the real product is not shipped.
- Verify desktop, tablet, and phone. Minimum Terminal proof viewports are `1440×900`, `820×1180`, and `390×844`; assert the actual dock/container height, not mere DOM visibility.
- Verify light and dark themes and English/Chinese where the touched product already supports them. Put per-state visual crops in the PR body.
- Preserve the shared Terminal mobile application; do not fork a separate mobile product.
- Do not copy Deepvue's CSS, assets, icons, microcopy, prompt text, panel geometry, or lavender visual identity. Rebuild jobs-to-be-done in Mastermind's own design language.

### 0.5 Validation and shipping gates

- Add contract, happy-path, stale, missing, malformed, replay, and authority tests proportional to the wave.
- Run focused tests, then the repository's required broad checks. Record exact commands and results.
- For latency work, report cold/warm/cache labels, p50/p95 TTFV and completion, tool count, context bytes, source timestamps, and answer correctness. SSE transport by itself is not a latency or freshness result.
- Commit only the wave's paths; push; open a PR; wait for non-spurious checks to **conclude**; squash-merge the same day; verify the merge on the remote default branch; wait for the covering render/deploy when required; verify the real live surface.
- A builder pauses a first-pass flagship UI at `VALIDATED` and returns the PR plus visual proof to the commissioning session. The commissioning session then completes the same-day merge/deploy/live loop; only an explicit operator hold or a real blocker permits stopping there.
- If blocked, state the exact gate, command/error, owner, and smallest next action. Do not call partial work complete.

---

## 1 — Executive ruling

Deepvue's competitive advantage is not evidence of a mysterious rating formula or magical MCP mesh. Its strongest advantage is **compression**: a fast factual path, a broad reusable field catalog, and many workflows composed inside one stateful workspace. Mastermind already has the harder proprietary layer—Stage, theme/cycle intelligence, Neural Web, Prophet governance, and richer contextual artifacts—but exposes those capabilities through too many independent surfaces and an AI path that still treats most native facts as a general investigation.

The build therefore has three priorities, in this order:

1. **Make product truth addressable.** Freeze one typed datapoint registry and adapters over existing artifacts.
2. **Make truth composable.** Give AI, screens, alerts, ratings, Neural Web, and Terminal widgets the same field and context contracts.
3. **Make composition fast and inspectable.** Extend the existing Terminal shell with semantic link groups, effective context, dockable intelligence, and deterministic saved/shareable objects.

The anti-goal is feature-count theater. A bubble chart, rating badge, prompt library, or dashboard marketplace built before the field/context kernel would create another attractive silo and multiply drift.

### 1.1 Recommended critical path

```text
truth debt + benchmark baseline
        |
typed datapoint registry + 12-field vertical slice
        |
deterministic fact resolver + AI context envelope
        |
workspace schema + semantic context bus
        +-------------------+
        |                   |
screener AST/executor   Theme Tracker++ widget
        |                   |
saved/shareable objects     |
        +---------+---------+
                  |
rating vintages + rules + reusable visual widgets
                  |
Neural Web observation packets
                  |
Prophet shadow research, then a separate promotion decision
```

Do not parallelize downstream waves across unfrozen schemas. Parallelize within a wave only after the producer/consumer contract and migration order are explicit.

---

## 2 — Reconciled current state: what Claude must reuse

The August 1 docket is already partly obsolete because substantial work shipped between August 1 and August 6.

| Capability | Current state | Evidence / owner | Ruling |
|---|---|---|---|
| Stage per-name classification | Shipped | Macro Stage engine/page | Reuse; do not rebuild classifier |
| Current Stage industry ranks, flows, per-name industry percentiles | Shipped and freshness-hardened in PRs `#4197` and `#4343`; current healthy live scope is US | `engine/stage_industry.py`, Stage artifacts/tests | Extend historical spine from live coverage; keep display/context-only |
| Stage industry rank-over-time heatmap | Partial; current published heatmap can be empty because it still depends on the old `stageanalysis_industry_ranks_weekly` seed | `engine/stage_industry.py` | Replace seed dependency with native nightly history |
| True Brain token streaming | Shipped in PR `#4220`, final tool-round streaming repaired in `#4253` | `engine/neuralweb/brain_gateway.py` | Do not rebuild streaming transport |
| Brain instant facts | Shipped for a narrow quote-only route | `brain_gateway.py::_instant_route` | Expand through typed resolver; do not fork a second AI client |
| Brain latency harness | Shipped | `scripts/brain_latency_bench.py` | Re-run and extend receipts; do not create a second harness |
| Sector Intelligence Workspace V2 | Shipped in Macro PR `#4372` | `templates/sector_central.html.j2`, `templates/si_workspace.js` | Reuse as a domain workspace; not the generic Terminal canvas |
| Theme Tape | Shipped in PR `#4488` and subsequent refinements | `engine/theme_tape.py`, `_theme_tape.html.j2` | Reuse as intelligence; package a compact Terminal projection |
| Theme engines / pathways / history | Broadly shipped | `engine/theme_*`, `data/neuralweb/theme_*`, site projections | Build an adapter, not a replacement theme engine |
| Terminal saved layouts | Shipped for chart-centric layouts, browser state plus Supabase `chart_layouts` | `TerminalShell.tsx`, `/api/layouts` | Migrate once into versioned widget layouts |
| Terminal multi-chart / MTF / chart synchronization | Shipped | `TerminalShell.tsx`, `ChartPane.tsx` | Extend semantic linking without breaking timeframe/drawing rules |
| Terminal replay | Shipped for ordinary charts and options surfaces, with deliberate MTF constraints | `TerminalShell.tsx`, `surface/replayContext.tsx` | Extend, do not rebuild |
| Terminal mobile shell | Shipped | `MobileNav.tsx` and responsive app shell | Preserve one responsive product |
| Terminal Brain integration | Shipped shared widget plus unbuffered/resumable `/api/brain/*` SSE proxy | `BrainWidget.tsx`, `/api/brain/[...path]/route.ts` | All AI orchestration remains in Macro gateway |
| Terminal Chart Bus | Shipped typed active-symbol/timeframe/indicator/drawing context | `lib/useChartBus.ts`, `lib/chartBus.ts` | Adapt into `ai_context_envelope.v1`; do not create a rival bus |
| Terminal screener | Partial client-side filter state over a manifest; local persistence | `ScreenerView.tsx` | Replace with AST UI only after Macro registry/executor exists |
| Equity RS/EPS/Composite passport | Absent | No `equity_rating.v1` implementation found | Build in Macro with daily vintages and transparent components |
| Terminal technical rating | Shipped but unrelated: TradingView-style oscillator/MA vote in `[-1,1]` | `lib/techRating.ts`, `OracleDash.tsx` | Keep separate namespace and label; never blend implicitly |
| Generic alert grammar | Partial legacy/options/suite allowlist | Terminal `/api/alerts`, Macro alert evaluators | Introduce shared typed grammar; keep server validation |
| Generic cross-product workspace/context bus | Absent | No shared contract found | Build contract in Macro; UI behavior in Terminal |
| Typed datapoint registry | Absent | No `datapoint_registry.v1` found | First foundational vertical slice |
| Visible effective AI context | Absent | Chart Bus has inputs but no user-visible resolution contract | Build before agentic actions |

### 2.1 Already covered — integrate, do not rebuild

- chart rendering, chart indicators, drawings, chart command vocabulary, multi-pane charting, and ordinary replay;
- Stage classifier, Stage Analysis surface, present-frame Stage industry ranks and flows;
- existing theme calculations, theme pathways, theme history, Theme Tape, and sector-cycle intelligence;
- existing watchlists, portfolios, positions, calculators, and domain-specific workspaces;
- Research Vault, company-event research, and deterministic market briefs;
- the shared Brain widget, same-origin Terminal proxy, resumable SSE runs, and true incremental token transport;
- Neural Web world state, synapse governance, lobe contracts, and existing context artifacts;
- Prophet board, ledgers, promotion discipline, and authority framework; and
- Terminal mobile navigation and options-surface replay architecture.

### 2.2 Explicit exclusions

- no Deepvue source, bundle de-obfuscation, CSS, assets, icons, copy, prompts, undisclosed weights, customer objects, or proprietary data;
- no second Deepvue-styled canvas in Macro Dashboard;
- no replacement AI stack inside `charting-app` and no revival of its deprecated `/api/copilot` route;
- no universe-wide factor/rating calculations in the browser;
- no use of Terminal's local `techRating` as an RS/EPS/Composite proxy;
- no claim that theme price return measures institutional capital flow;
- no LLM-generated score presented as deterministic or validated;
- no public repo-internals retrieval; and
- no Prophet authority bundled into a feature-delivery PR.

### 2.3 Rights-gated or later distribution work

Defer until a documented rights and operations path exists:

- exchange-grade real-time data redistribution beyond current licenses;
- consensus estimates and analyst-action breadth that require a licensed feed;
- a sub-three-minute global earnings/fundamental SLA;
- broad institutional-flow claims without an actual flow source;
- a browser extension or app-store distribution program; and
- replication of trader-branded proprietary indicator libraries.

The data model and UI may represent these states as unavailable or rights-gated. Do not fill them with weak proxies merely to complete a screenshot.

### 2.4 Collision snapshot — refresh before every slice

At the August 6 audit, no active PR directly occupied the proposed registry contract family, `brain_gateway.py`, or the Stage industry-history files. The active map did show hot shared blast zones:

- `templates/dashboard.html.j2` was contested by PRs `#4735`, `#4718`, and `#4644`;
- `engine/alerts.py` was contested by PRs `#4712` and `#4700`; and
- daily/CI/legacy workflow definitions had multiple overlapping lanes.

This is a timestamped warning, not a reservation. Rebuild `docs/ACTIVE_BUILD_MAP.md` before editing. The generic workspace belongs in Terminal rather than `dashboard.html.j2`, and no wave should touch shared workflows merely for convenient scheduling.

---

## 3 — Cross-repo authority and ownership

The repos are one product but not one codebase. Use this ownership boundary unless current code proves a narrower exception.

| Concern | Macro Dashboard / Mastermind owns | `charting-app` owns |
|---|---|---|
| Datapoints | registry, adapters, truth packets, freshness, provenance, point-in-time policy | rendering declared field types and requesting permitted fields |
| Workspace | canonical `workspace_layout.v1`, widget type registry, context authority rules | composer, persistence UX, migrations, responsive semantic-lane reflow |
| Context | resolution rules and `ai_context_envelope.v1` | selections, link-group interactions, visible effective-context strip |
| AI | routing, instant resolver, cache, tool loop, evidence, telemetry, Neural Web access | host widget, send typed context, render SSE events, resume runs |
| Screener | field allowlist, AST schema, validator, cost guard, executor, saved-query service | AST builder/preview/diff, results interaction, user-facing errors |
| Theme Tracker++ | memberships, metrics, states, witnesses, timestamps, provenance | compact dock/widget and drill-through interactions |
| Ratings | `equity_rating.v1`, cohort definitions, components, coverage, daily vintages, replay | rating passport renderers on chart/watchlist/screen/AI context |
| Alerts | rule schema/evaluator, schedule, idempotency, dedupe, delivery orchestration | rule composer, preview, alert management UI |
| Replay | point-in-time artifacts and provenance | playback controls, synchronized views, existing constraints |
| Neural Web / Prophet | typed observation packets, shadow joins, validation, authority | display-only diagnostic views and explicit context requests |

### 3.1 Terminal substrate constraints that must survive

- Current saved layouts are chart-specific. Migrate browser key `mm.ws` and Supabase `chart_layouts` exactly once; do not leave three diverging stores.
- Current same-timeframe chart synchronization is not a semantic link group. Preserve existing chart sync while adding entity/context links above it.
- Ordinary grids deliberately block duplicate symbols because drawings persist replace-all by symbol. MTF duplicate panes are a special exception. Do not erase this ownership rule.
- Mixed-timeframe grids deliberately disable some sync/replay behavior. New workspace code must surface that constraint rather than pretend synchronization succeeded.
- The Brain proxy already relays SSE without buffering and supports cursor replay. Latency fixes belong in the gateway and context compiler, not in a new Next.js orchestrator.
- Phone docks can be present in the DOM but have zero usable height. Assert measured geometry at `390×844` and `820×1180`.

---

## 4 — Clean-room evidence and epistemic boundary

The predecessor distinguishes direct observation, public documentation, network/client inspection, and inference. Preserve that labeling.

Allowed inputs:

- Deepvue's public website, pricing, documentation, marketing claims, and operator-supplied screenshots;
- behavior observed through ordinary authenticated product use under the operator's account;
- standard browser network and performance observations of requests made by that session;
- our own repositories, artifacts, tests, schemas, and measured benchmarks; and
- licensed or public data feeds with recorded rights/provenance.

Forbidden inputs or claims:

- copying or reconstructing Deepvue's proprietary source, prompts, assets, or non-public datasets;
- evading access controls or extracting other customers' data;
- claiming an inferred formula is Deepvue's exact formula;
- claiming an AI provider, model, retrieval system, or MCP architecture as fact from response style alone; and
- treating one cached competitor answer versus one cold Mastermind investigation as an architecture benchmark.

Every competitive claim in a new build or PR should be tagged as one of `observed`, `documented`, `measured`, `inferred`, or `unknown`.

---

## 5 — Freeze these cross-product contracts before UI expansion

Schemas live in Macro because Macro owns truth and authority. Place JSON Schemas under a product-neutral `contracts/intelligence_workspace/` family unless repository discovery identifies a better existing governed registry. Pair schemas with fail-closed loaders/validators and consumer fixtures. Do not create schema files with no vertical-slice producer and consumer.

### 5.1 `datapoint_registry.v1`

One registry entry defines one semantic field across charts, screens, ratings, AI, alerts, Neural Web, and Prophet research.

```json
{
  "schema": "datapoint_registry.v1",
  "registry_version": "1.0.0",
  "fields": [
    {
      "field_id": "market.price.last",
      "label": "Last price",
      "value_type": "number",
      "unit": "currency",
      "unit_policy": "entity_quote_currency",
      "entity_types": ["security"],
      "universes": ["us_equity"],
      "source_id": "site_quotes",
      "license_class": "subscriber_display",
      "producer": "existing_quote_adapter",
      "timestamp_policy": {
        "observed_at": "required",
        "effective_at": "required",
        "as_of": "required",
        "generated_at": "required_on_value_envelope"
      },
      "freshness_budget_seconds": 120,
      "point_in_time_policy": "observation_time",
      "missingness": ["unknown", "unavailable", "stale", "not_applicable"],
      "operators": ["eq", "gt", "gte", "lt", "lte", "between"],
      "renderer": "price",
      "authority": ["display", "screen", "alert", "ai_fact", "neuralweb_context"]
    }
  ]
}
```

V1 is a deliberately small vertical slice. A contract-review checkpoint inside the W1-A vertical PR must freeze an exact manifest of immutable field IDs before adapters are implemented; do not merge a schema-only artifact with no producer and consumer. The intended seed set is exactly twelve high-value existing fields:

- last price and source timestamp;
- 1-month, 3-month, and 12-month return/relative-strength fields where currently authoritative;
- Stage and weeks in Stage;
- current regional industry-rank percentile on an `industry` entity;
- within-industry member RS percentile on a `security` entity;
- next earnings date;
- latest reported EPS growth and sales growth; and
- one current theme membership/state field.

The exact identifiers may change only during that contract review. Once the V1 manifest merges, they are immutable semantic addresses. If a seed field is blocked and substituted, the schema-review receipt names both fields and the rights/data reason. A later changed definition requires a new version or a compatibility migration, not silent reinterpretation.

### 5.2 Datapoint value envelope

Registry metadata and field values are separate. Every resolved value uses the same envelope:

```json
{
  "field_id": "stage.current",
  "entity": {"type": "security", "id": "AAPL"},
  "value": 2,
  "status": "available",
  "observed_at": "2026-08-06T20:00:00Z",
  "effective_at": "2026-08-06T20:00:00Z",
  "as_of": "2026-08-06",
  "generated_at": "2026-08-06T20:20:00Z",
  "source": {
    "source_id": "stage_live_classifier",
    "artifact": "site/stagedata/stage_board_daily.json",
    "license_class": "internal_derived"
  },
  "freshness": {"state": "fresh", "budget_seconds": 86400},
  "provenance": {"kind": "derived", "formula_version": "stage_classifier.v2"},
  "authority": ["display", "context"]
}
```

`generated_at` is transport/materialization time. `observed_at`, `effective_at`, and `as_of` describe the underlying fact and must not be replaced by it.

### 5.3 `ai_context_envelope.v1`

```json
{
  "schema": "ai_context_envelope.v1",
  "request_id": "uuid",
  "explicit_entities": [{"type": "security", "id": "INOD"}],
  "pinned_context": [],
  "active_selection": [{"type": "security", "id": "AAOI"}],
  "ambient_widget_context": {"symbol": "AAOI", "timeframe": "1D"},
  "effective_context": {
    "entities": [{"type": "security", "id": "INOD"}],
    "reason": "explicit_request",
    "precedence": "explicit_over_active"
  },
  "field_requests": ["earnings.latest.reported"],
  "datapoints": [],
  "screener_ast": null,
  "latency_lane": "instant_fact",
  "provenance_requirement": "field_level",
  "authority": {"may_execute": false, "may_originate_signal": false}
}
```

Resolution order is deterministic: explicit request → pinned context → active selection → ambient widget. Conflicts, dropped context, stale values, and unsupported entity types are printed in an inspectable context receipt.

### 5.4 `workspace_layout.v1`

```json
{
  "schema": "workspace_layout.v1",
  "revision": 1,
  "name": "Research cockpit",
  "link_groups": {
    "primary_security": {"entity_type": "security"},
    "theme_focus": {"entity_type": "theme"}
  },
  "widgets": [
    {
      "id": "chart-primary",
      "type": "chart",
      "semantic_lane": "primary",
      "grid": {"x": 0, "y": 0, "w": 16, "h": 18},
      "context_in": ["primary_security"],
      "context_out": ["primary_security"],
      "config": {"timeframe": "1D"}
    }
  ],
  "migration": {"source": "chart_layouts", "source_revision": 3}
}
```

Semantic lanes—not scaled desktop coordinates—determine phone/tablet reflow. The current breakpoint and active link-group values belong in a separate ephemeral `workspace_session.v1` envelope, not the durable layout. A layout may declare an explicitly named pinned/default entity only when the user intentionally saves it. Widget types and context ports are allowlisted. Unknown widget types fail closed with a recoverable migration message.

### 5.5 `screener_query.v1`

```json
{
  "schema": "screener_query.v1",
  "universe": {"id": "us_equity", "as_of": "2026-08-06"},
  "where": {
    "all": [
      {"field_id": "stage.current", "op": "eq", "value": 2},
      {"field_id": "market.return.3m", "op": "gte", "value": 0.15},
      {"field_id": "security.industry_member.rs_percentile", "op": "gte", "value": 80}
    ]
  },
  "sort": [{"field_id": "market.return.3m", "direction": "desc"}],
  "select": ["security.symbol", "stage.current", "market.return.3m"],
  "null_policy": "exclude",
  "limit": 100
}
```

The validator rejects unknown fields, disallowed operators, incompatible entity scopes/universes, excessive depth/width/cost, ambiguous units, future as-ofs, and unbounded output. `industry.rank.percentile` (an industry ranked inside its region) and `security.industry_member.rs_percentile` (a security ranked against members of its industry) are separate fields and may never substitute for one another. A related-entity industry field requires an explicit security→industry relationship in the query plan and receipt. Natural-language compilation produces this object plus a human-readable diff; it never executes prose.

### 5.6 `equity_rating.v1`

```json
{
  "schema": "equity_rating.v1",
  "entity": {"type": "security", "id": "AAPL"},
  "vintage": "2026-08-06",
  "cohort": {"id": "us_equity_liquid_v1", "eligible": 4128},
  "components": [
    {
      "component_id": "price_strength_12m",
      "raw_value": 0.27,
      "percentile": 84,
      "coverage": 0.99,
      "formula_version": "price_strength_12m.v1"
    }
  ],
  "display_composite": null,
  "coverage": 0.81,
  "status": "partial",
  "as_of": "2026-08-06",
  "provenance": [],
  "authority": ["display", "context"]
}
```

Do not ship a mysterious single number. Expose cohort, eligibility, components, coverage, missingness, formula versions, and contribution trace. EPS/sales components stay null when the necessary point-in-time fundamentals or rights are unavailable. `display_composite` remains null in V1. Transparent inputs, versioning, coverage abstention, and forward grading are necessary but not sufficient to add one: a new Equity Composite needs a separate explicit adjudication under `DNR:KILL-FUSED-COMPOSITE`, and it never silently becomes Prophet authority.

### 5.7 `theme_state.v1`

Keep distinct measures distinct:

```json
{
  "schema": "theme_state.v1",
  "theme_id": "artificial_intelligence",
  "as_of": "2026-08-06",
  "price_strength": {"percentile": 78, "change_5d": 6},
  "breadth": {"value": 0.64, "eligible": 42, "covered": 39},
  "persistence": {"days": 8},
  "dispersion": {"value": 0.21},
  "concentration": {"top5_share": 0.47},
  "flow_witnesses": [],
  "state": "improving",
  "provenance": [],
  "authority": ["display", "context"]
}
```

Membership changes are versioned. Rank deltas are computed against comparable universes. An empty witness set means no supported flow claim—not zero flow.

### 5.8 `user_rule.v1`

Alerts reuse the screener expression grammar plus trigger policy:

```json
{
  "schema": "user_rule.v1",
  "rule_id": "uuid",
  "scope": {"entity_type": "security", "ids": ["AAPL"]},
  "condition": {"field_id": "stage.current", "op": "changed_to", "value": 2},
  "schedule": {"mode": "on_artifact", "source": "stage_daily"},
  "dedupe": {"key": "entity+field+value+as_of", "cooldown_seconds": 86400},
  "delivery": ["in_app"],
  "authority": ["notify"]
}
```

The browser never passes arbitrary JSON directly to storage or delivery. Server validation, cost limits, idempotency, replay, and delivery receipts are mandatory.

### 5.9 `ai_benchmark_receipt.v1`

Each probe row records at least:

```text
system / build SHA / environment / prompt_id / prompt_text_hash
explicit context / ambient context / cold-warm-cache label
route / headers_ms / first_status_ms / ttfv_ms / done_ms
tool count and duration / context bytes / output bytes
field correctness / numeric correctness / source-span correctness
source as-of coverage / unsupported-claim count / missingness honesty
degraded state / error / reviewer / recorded_at
```

Keep raw prompts and adjudication rubrics versioned. Do not publish authentication material or raw private account data in benchmark artifacts.

---

## 6 — Remaining build waves

W0 through W4-C and W6-A are defined as shippable vertical slices. W4-D, Wave 5, and W6-B are explicitly gated program/research epics that require a subordinate execution docket or preregistration before commissioning. “Files” are ownership anchors, not permission to skip discovery; Claude must re-check current main, the active build map, and connected consumers before editing.

## Wave 0 — Close truth debt and freeze a current baseline

### W0-A — Native Stage industry history

**Objective:** remove the live rank-over-time surface's dependency on the old `stageanalysis_industry_ranks_weekly` seed.

**Macro anchors:**

- `engine/stage_industry.py`
- the nightly Stage orchestrator that already calls current rank/flow builders
- runtime `data/stage_analysis/` / governed durable-store append-only native industry-rank history and generated current projection
- `site/stagedata/industry_heatmap.json`
- `tests/test_stage_industry.py`
- Stage page/build tests and Synapse declarations for any new artifact

**Build:**

1. From each healthy nightly current industry-rank packet, append one idempotent row per `(as_of, region, industry_id, formula_version)` to a native history ledger.
2. Generate the heatmap from that native ledger, not the EquityDesk seed.
3. Preserve source-as-of, taxonomy version, coverage, eligible count, rank universe, and formula version for every vintage.
4. Backfill only from evidence we are licensed and able to reproduce. If history starts August 2026, print the honest start date.
5. Keep the old seed only as a calibration fixture if rights permit; never use it as a silent production fallback.
6. Keep the forward ledger in the existing nightly-owned durable data plane. Do not commit invented observations or advance it from an intraday request merely to populate the UI.
7. Accrue only regions produced by the healthy live classifier. Do not repopulate Europe/Asia from a stale seed to imitate historical breadth.

**Same-day shipping gate — not done unless:**

- a production-shaped healthy nightly fixture produces non-empty current ranks and one idempotent historical vintage;
- rerunning the same fixture date produces byte-equivalent logical rows, not duplicates;
- missing or degraded inputs publish an explicit warn/error receipt and do not advance history;
- taxonomy/rank-universe changes are visible and do not create false rank deltas;
- the live contract truthfully shows insufficient native history rather than a successful-looking blank before natural vintages accrue;
- a production-shaped two-vintage fixture proves the eventual heatmap transition and comparable-rank behavior;
- Stage authority remains display/context only; and
- tests cover healthy, empty, stale, duplicate-date, taxonomy-change, and partial-coverage cases.

**Accrual gates:** verify the first natural nightly run appends exactly one production vintage. After the second natural nightly vintage, verify the live heatmap automatically becomes non-empty with no manual backfill or storage repair. Record both follow-up receipts against the original PR/program. The implementation PR may be `SHIPPED` after the same-day gate, but W0-A remains `ACCRUING` until both operational receipts exist; the ship loop must not invent observations to satisfy them.

### W0-B — Refresh the permanent AI bakeoff baseline

**Objective:** measure the current product after shipped streaming fixes before changing routing again.

**Macro anchor:** extend and run `scripts/brain_latency_bench.py`; do not replace it.

**Build:**

1. Preserve the original four August 1 prompts.
2. Add stable prompt IDs for native multi-field, context collision, screener compilation, calculation, filing/event, and deep synthesis.
3. Add receipt output for context bytes, cache status, source timestamp coverage, field-level correctness, and unsupported claims.
4. Run authenticated production probes with secrets supplied out-of-band.

**Not done unless:**

- baseline records identify exact deployed SHA, route, cold/warm/cache state, and prompt version;
- manual quality scoring uses a frozen rubric and separates speed from correctness;
- the INOD-explicit / AAOI-ambient collision case is included;
- results are stored as a private reproducible receipt, not an anecdotal screenshot; and
- no credential, cookie, bearer token, private prompt content, or account identifier is committed.

**Exit:** publish one baseline memo/receipt and use it as the comparator for W1-B. Do not block the registry build on competitor access.

---

## Wave 1 — Make native product truth addressable and fast

### W1-A — Registry kernel plus twelve-field vertical slice

**Objective:** one typed field address works across a deterministic resolver, one test screen/query, and Brain.

**Macro candidate paths:**

- `contracts/intelligence_workspace/datapoint_registry.v1.schema.json`
- `contracts/intelligence_workspace/datapoint_value.v1.schema.json`
- `engine/intelligence_workspace/registry.py`
- `engine/intelligence_workspace/resolver.py`
- a governed registry catalog under `config/intelligence_workspace/`
- adapter modules over existing quote, Stage, industry, earnings, fundamental, and theme artifacts
- `tests/test_intelligence_workspace_registry.py`
- `tests/test_intelligence_workspace_resolver.py`
- `config/synapse.yml` entries for new produced artifacts

**Build:**

1. Implement fail-closed schema/registry loading with duplicate-ID, incompatible-unit, unsupported-operator, bad-authority, and version checks.
2. Register the exact V1 field manifest from §5.1 using existing producers; do not recalculate them in the registry. Keep regional industry-rank percentile and within-industry member RS percentile separate in ID, entity scope, adapter, and receipt.
3. Resolve batch requests by `(entity, field_ids, requested_as_of)` with bounded size and a typed value envelope.
4. Produce an internal and subscriber-safe projection that strips non-redistributable provenance details while retaining honest source labels/as-ofs.
5. Prove at least one consumer each in a deterministic query fixture and Brain fact fixture.

**Not done unless:**

- every field in the frozen V1 manifest resolves with explicit available/missing/stale states against production-shaped fixtures;
- duplicate or semantically conflicting fields fail the build;
- the same fact has the same value/as-of across resolver, Brain fixture, and query fixture;
- rights classes prevent accidental public projection;
- batch and field cost limits are tested; and
- no page or LLM owns an alternate formula.

### W1-B — Expand the instant factual lane

**Objective:** answer simple native questions from typed packets in seconds, with exact field receipts and no general tool loop when unnecessary.

**Macro anchors:**

- `engine/neuralweb/brain_gateway.py`
- the new registry/resolver
- existing Brain SSE contracts and widget tests
- `scripts/brain_latency_bench.py`

**Build:**

1. Replace quote-specific routing logic with an allowlisted intent-to-field plan for the V1 registry slice.
2. Resolve facts deterministically and render compact answers from typed values. Use an LLM only for optional phrasing after facts are fixed; the direct template path is preferred for one-line asks.
3. Emit field-level citations/receipts, source as-ofs, freshness states, effective context, cache label, and route timing.
4. Stream early status and incremental visible answer events through the existing gateway contract.
5. Fall through to deep investigation only for unsupported or synthesis requests; do not fabricate a fact to preserve the instant route.

**Latency budget to validate, not merely assert:**

- route decision p95 ≤ 100 ms in-process;
- registry/context assembly p95 ≤ 300 ms for the V1 fact packet;
- warm-production single/native-fact p95 TTFV ≤ 1.5 s and completion ≤ 3 s;
- cold-production completion ≤ 5 s when dependencies are healthy; and
- no regression to deep-route factual accuracy or resumable SSE behavior.

If production network/model constraints make a threshold impossible, report the measured decomposition and revise the budget openly; do not game TTFV with content-free status text.

**Not done unless:**

- price, Stage, industry rank, within-industry member percentile, next earnings, and latest EPS-growth questions use their correct typed fields; the two industry measures never substitute for each other;
- explicit INOD beats ambient AAOI and the UI can show why;
- stale/missing values answer honestly without deep-loop hallucination;
- every numeric clause maps to a field receipt;
- the current quote-only path remains compatible; and
- W0-B prompts are rerun with before/after receipts.

### W1-C — Visible context compiler and effective-context receipt

**Objective:** make the exact context sent to Brain deterministic and inspectable before workspace actions expand.

**Macro owns:** `ai_context_envelope.v1`, resolution/validation, subscriber-safe receipt.

**Terminal owns:** adapt the existing Chart Bus to send typed context and render the effective-context strip/drawer.

**Not done unless:**

- resolution precedence is deterministic and contract-tested;
- unsupported/stale/dropped context is visible;
- changing a linked symbol changes the receipt once, without a loop;
- the existing Brain guest/auth/run-resume behavior still works;
- public receipts contain no repo internals or secret source locations; and
- phone/tablet effective context remains reachable without covering the prompt box.

**Wave 1 exit:** the same five native facts resolve identically in a direct resolver test, Brain, and a Terminal context inspection. This is the foundation for every later feature.

---

## Wave 2 — Compose the operator workspace and theme intelligence

### W2-A — Versioned workspace schema and migration

**Objective:** evolve Terminal's existing chart layouts into a generic widget graph without losing current users' layouts.

**Macro owns:** `workspace_layout.v1`, widget/data registry, semantic context-port rules, subscriber-safe contract projection.

**Terminal anchors:** `TerminalShell.tsx`, `/api/layouts/route.ts`, current `mm.ws` browser state, Supabase `chart_layouts`, responsive shell tests.

**Build order:**

1. Inventory all current layout payload versions and persistence keys.
2. Freeze the migration from chart-only layout → widget layout.
3. Add allowlisted widget descriptors and semantic lanes while retaining 1/2/4-pane and MTF behavior.
4. Read old records, migrate in memory, persist the new version once, and retain a bounded rollback/export path.
5. Add create, rename, duplicate, reset, import/export, and failure recovery only after migration tests pass.

**Not done unless:**

- every representative old layout opens correctly after migration;
- one account does not accumulate divergent `mm.ws`, `chart_layouts`, and new workspace truth;
- unknown widget/config revisions fail recoverably;
- desktop, tablet, and phone reflow by semantic lane rather than coordinate shrink;
- a clean account can create/save/reopen a mixed-widget workspace end-to-end; and
- cross-account/user isolation is tested.

### W2-B — Semantic link groups

**Objective:** allow chart, Stage, theme, screener, rating, watchlist, and Brain widgets to share explicit entity context without hidden coupling.

**Terminal owns interaction behavior; Macro owns context semantics.**

**Build:**

- type link groups by entity (`security`, `industry`, `theme`, `portfolio`, `event`);
- declare each widget's `context_in` and `context_out` ports;
- show group color/name and current value without adding low-contrast chrome;
- log one bounded context-transition receipt for debugging;
- preserve lower-level chart synchronization and drawing ownership rules; and
- prevent circular updates with origin/revision IDs.

**Not done unless:**

- propagation is deterministic in unit and browser tests;
- unlinking a widget truly freezes/localizes it;
- a context collision is visible before an AI request;
- duplicate-symbol and MTF exceptions remain correct;
- no propagation loop, stale closure, or double network fetch appears; and
- mobile interaction requires no hover-only control.

### W2-C — Theme Tracker++ dock

**Objective:** expose existing theme intelligence in a compact, time-aware Terminal widget that exceeds a simple performance leaderboard.

**Macro owns:** `theme_state.v1` projection, membership vintages, ranks, deltas, breadth, persistence, dispersion, concentration, supported witnesses, freshness, provenance.

**Terminal owns:** compact dock, timeframe controls, sorting, selection/link output, detail drill-through.

**Default glance tier:** theme name, state, strength percentile, rank delta, breadth, as-of.

**Inspect tier:** persistence, dispersion, concentration, member participation, supporting/contradicting witnesses, membership revision.

**Study tier:** open existing Sector Intelligence / theme detail surfaces.

**Not done unless:**

- rank deltas compare like-for-like universes and membership versions;
- every field has source/as-of and missingness;
- performance and flow witnesses are separately labeled;
- selected theme propagates through the semantic link group;
- no empty or stale tracker looks healthy;
- visual proof covers light/dark, EN/ZH, desktop/tablet/phone; and
- the dock has measured non-zero usable height at mobile breakpoints.

**Wave 2 exit:** a user can save a workspace with Chart + Theme Tracker++ + Brain, change a theme/security, inspect the effective context, reload, and get the same layout/context without manual recovery.

---

## Wave 3 — Deterministic screening and reusable investigations

### W3-A — Screener AST, validator, and executor

**Objective:** replace ad hoc/local filtering with one authoritative, point-in-time query contract.

**Macro owns:** `screener_query.v1`, field/operator validation, universe resolution, query planning/cost limits, deterministic execution, result receipts, saved-query service.

**Terminal owns:** AST builder, filter chips, preview, human-readable diff, results table, errors, save/share UX.

**Build order:**

1. Execute hand-authored ASTs over the W1 registry slice.
2. Prove null/as-of/universe/operator semantics and deterministic ordering.
3. Add saved server-side queries with immutable revision IDs.
4. Replace Terminal's local `FilterState` persistence via an explicit migration.
5. Only then add natural-language compilation.

**Not done unless:**

- the same AST + universe vintage yields the same ordered result and receipt;
- unknown fields/operators, mismatched units, costly trees, and future as-ofs fail closed;
- result rows retain field values and source-as-ofs used for inclusion;
- null policy is explicit and tested;
- broad-universe calculations do not execute in the browser; and
- old local presets are migrated or clearly exported, not silently lost.

### W3-B — Natural language → proposed AST

**Objective:** let Brain translate intent without giving it result authority.

**Build:**

1. Send the LLM only the bounded compatible field/operator catalog.
2. Validate its proposed AST server-side.
3. Show a plain-language interpretation and structural diff before execution when ambiguity or material cost exists.
4. Execute through W3-A and generate the answer from deterministic rows.
5. Record compiler errors and unsupported concepts as product feedback, not silent fallbacks.

**Not done unless:**

- no ticker result comes directly from generated prose;
- ambiguous units/time windows prompt a bounded clarification or visible assumption;
- compiler injection/adversarial prompts cannot escape the field/operator allowlist;
- natural language and hand-built equivalent ASTs produce identical rows; and
- field receipts survive into Brain's cited response.

### W3-C — Versioned saved and shareable objects

Create a product-neutral envelope for saved screen, investigation, prompt, list section, and workspace template:

```text
object_id / object_type / owner / revision / schema
payload hash / created_at / updated_at / source vintages
visibility / rights class / redaction policy / compatibility floor
```

**Macro owns:** versioned object service, immutable revision lookup, owner/recipient authorization, rights redaction, revocation, and audit receipt.

**Terminal owns:** create/save/open/share UX over that service; no browser-only canonical copy.

Start with saved screens and cited investigations. Share links reference immutable revisions or explicitly named live heads. Recipients without data rights see a structured unavailable state, not leaked values or a broken page.

**Not done unless:**

- immutable revision lookup and explicitly named live-head lookup cannot be confused;
- owner, intended recipient, visibility, and data-right checks are enforced server-side;
- unauthorized users cannot enumerate object IDs, metadata, revisions, or redacted field values;
- revoke/unshare behavior is immediate and receipt-backed;
- an authorized object reopens on another device with the same payload hash and source vintages;
- rights-limited recipients receive a structured redacted/unavailable state; and
- revision, concurrency, deletion/retention, and migration behavior are tested.

**Wave 3 exit:** an operator can express a screen in UI or natural language, inspect the exact AST, execute it deterministically, save a revision, reopen it on another device, and share an authorized receipt.

---

## Wave 4 — Rating passports, generic visual widgets, and rules

### W4-A — Equity rating fabric and daily vintages

**Objective:** ship transparent IBD-style jobs-to-be-done without pretending to know Deepvue's undisclosed weights.

**Macro build:**

1. Freeze eligible cohorts and point-in-time universe policy.
2. Implement independently named price-strength and fundamentals components over registry fields.
3. Store daily vintage, coverage, missingness, formula version, and contribution trace.
4. Add replay by requested as-of and cohort vintage.
5. Expose subscriber-safe rating passports to stock, screen, watchlist, Terminal, and Brain consumers.

**Terminal build:** render the passport beside—not blended with—the existing oscillator/MA technical rating.

**Not done unless:**

- percentile direction, ties, minimum history, corporate actions, delistings, IPOs, and universe entry/exit are specified and tested;
- every component can be recomputed from its vintage inputs;
- unavailable EPS/sales history produces explicit partial/abstain status;
- no look-ahead or survivor-only cohort enters historical replay;
- the local `techRating` keeps a separate label, schema, and visual grouping;
- `display_composite` remains null unless a separate explicit Equity Composite adjudication is merged under `DNR:KILL-FUSED-COMPOSITE`; and
- no Prophet board/rank code changes in this wave.

### W4-B — Registry-driven bubble and mini-chart widgets

**Objective:** make visualization a generic renderer over governed fields, not a new calculation silo.

- Bubble chart declares entity universe, x/y/size/color field IDs, null policy, scales, and max points.
- Mini chart declares entity, field ID, vintage range, missingness, and revision markers.
- Tooltip values come from typed envelopes and include as-of/provenance access.
- Server prepares bounded datasets; the browser renders them.

**Not done unless:** malformed/incompatible fields fail visibly, scales cannot hide nulls, large requests are bounded, keyboard/touch navigation works, and all visual states pass design proof.

### W4-C — Shared user-rule grammar and alert evaluator

**Objective:** generalize alerts without converting a browser API into arbitrary JSON storage.

**Macro owns:** schema, validator, evaluator, schedules, replay, dedupe, idempotency, delivery receipts.

**Terminal owns:** composer, preview, enabled/paused state, history, and delivery settings.

**Not done unless:**

- every condition references registry fields and compatible operators;
- reprocessing the same artifact does not double-send;
- a changed rule revision is distinct from a repeated event;
- stale source data cannot trigger as though fresh;
- replay tests cover crossing, changed-to, persistence, compound all/any, cooldown, and missing data; and
- existing allowlisted alerts migrate without weakening validation.

### W4-D — Analyst action tape, rights-gated discovery epic

Do not commission implementation until a subordinate execution docket records the feed, redistribution right, coverage/SLA, correction policy, storage boundary, and cost. Then model event time, announcement time, firm, analyst, action type, prior/new rating, prior/new target, currency, source, corrections, and affected securities. If only issuer releases or sparse public sources are available, label coverage as partial and do not market broad completeness.

**Wave 4 exit:** rating passports replay point-in-time, render consistently across at least three consumers, and can participate in screens/alerts as display/context fields without changing Prophet authority.

---

## Wave 5 — Compounding workflows and distribution epics

This wave converts substrate into retention. It is deliberately after contracts, screening, and ratings. These are program epics, not build prompts: each requires a subordinate execution docket with owner, storage/API boundary, authorization, migrations, inline acceptance gates, exact tests, design proof, and PR slicing before commissioning.

### W5-A — Combo Lists and persistent sections

- server-synced lists with user-defined sections, ordering, notes, tags, and optional saved-screen membership;
- immutable membership-change receipts for cited investigations;
- bulk actions constrained by permissions and cost; and
- import/export with explicit symbol-resolution errors.

Reuse existing watchlist/portfolio semantics where possible. Do not create a fourth security-list model.

### W5-B — Dashboard templates, prompt library, and cited investigations

- templates are versioned `workspace_layout` objects, not copied component trees;
- prompts declare required context/fields and expected output shape;
- cited investigations freeze their source vintages and disclose later revisions;
- education teaches existing proprietary intelligence rather than advertising generic prompt tricks; and
- shared objects obey rights/redaction rules.

### W5-C — Synchronized diagnostic replay

Extend existing replay only where it materially improves research:

- requested historical `as_of` propagates to compatible widgets;
- incompatible/live-only widgets show an explicit state;
- mixed-timeframe and drawing constraints remain visible;
- point-in-time rating/theme/screen artifacts are used, never today's recalculation; and
- Prophet research replay remains separate from the production graded board.

### W5-D — Mobile capture and extension research

First make current Terminal research views excellent on mobile. A cashtag capture extension is a separate distribution/security project with threat model, store policy, auth, data rights, and telemetry gates. It is not required for core Deepvue competitive parity.

**Program exit:** a user can capture an idea, place it in a structured list, open a saved workspace, run a cited screen/investigation, replay the relevant state, and share an authorized revision across devices. No individual W5 epic may claim this integrated exit without fresh end-to-end proof.

---

## Wave 6 — Neural Web accrual and conditional Prophet promotion

This is two different activities. Do not combine them.

### W6-A — Neural Web observation packets

Neural Web may consume, as typed context:

- rating components, cohort, coverage, freshness, stability, and disagreement;
- Stage, weeks-in-stage, industry rank and distribution;
- theme strength, breadth, persistence, dispersion, concentration, membership revision, and supported witnesses;
- screener membership with exact AST hash and universe/as-of;
- user attention/list membership as user context, not market truth; and
- AI evidence packets only when claims retain source spans.

Each packet labels legs as `observed`, `derived`, `inferred`, or `model_generated`, prints missingness, and declares allowed authority. LLM output may summarize or de-escalate; it may not become a new scored leg.

**Not done unless:** schema and Synapse producer/consumer wiring are explicit, time alignment is tested, stale packets fail closed or abstain, contradictions survive aggregation, and customer-visible text does not expose internal lobe/repo language.

### W6-B — Prophet shadow research

Only after enough native vintages accrue:

1. preregister feature definitions, eligible universe, join timing, regimes, liquidity cohorts, metrics, null handling, and promotion thresholds;
2. reconstruct point-in-time values and join strictly after selection for the first shadow study;
3. measure incremental information beyond existing Prophet features;
4. report multiple-testing controls, calibration, stability, and failures;
5. keep the shadow artifact outside the production graded population; and
6. request a separate adjudication for any authority change.

The default first authority is **abstention/de-escalation** under stale, contradictory, concentrated, or low-coverage states. No positive score, rank, entry, direction, timing, or size authority is implied by building the feature.

**Wave 6 exit:** W6-A may ship as context once contracts pass. W6-B has no automatic exit into production; it ends in a measured promote/hold/kill decision tied to the exact construction tested.

---

## 7 — Permanent AI bakeoff program

Use identical timestamped prompts, explicit context, and scoring rubrics across systems. Preserve raw receipts privately and publish only rights-safe summaries.

| Prompt class | Required test | Score |
|---|---|---|
| Simple fact | current price, next earnings, one rating | TTFV, completion, freshness, numeric accuracy, field citation |
| Native packet | RS horizons + Stage + industry + earnings | native-context use, per-field provenance, missingness |
| Current market | regime + breadth + themes + liquidity | timestamp coverage, source quality, unsupported claims |
| Filing/event | explain one reported quarter from primary evidence | claim-to-source-span correctness, recency |
| Screener | compile and execute a multi-condition query | AST fidelity, deterministic rows, explanation fidelity |
| Calculation | position size from explicit inputs | exact math, units, reproducibility |
| Context collision | explicit INOD while ambient AAOI | precedence correctness and visible receipt |
| Deep synthesis | Neural Web + Prophet question | tool choice, contradiction handling, authority discipline |

### 7.1 Required telemetry

- exact system/build/deploy version;
- prompt version and context envelope hash;
- cold/warm/cache state;
- p50/p95 headers, first status, TTFV, and completion;
- route, tools, tool durations, context bytes, and output bytes;
- source-as-of coverage and citation/source-span precision;
- factual and numerical correctness;
- explicit-context utilization;
- unsupported-claim rate and missingness honesty;
- degraded/error states; and
- useful verified information per second.

### 7.2 A/B interpretation rules

- Separate transport speed, route choice, retrieval latency, generation latency, and answer length.
- Compare equivalent tasks. Do not compare a cached quote to a cold multi-source investigation.
- “Instant” means useful verified content, not a spinner, status phrase, or uncited token.
- A fast wrong or stale answer loses. A correct answer whose only source is hidden also fails the product gate.
- Response quality does not prove a specific model, prompt, MCP topology, or data provider.

---

## 8 — Verification matrix Claude must tailor per PR

| Area | Minimum proof |
|---|---|
| Contracts | JSON Schema/loader tests; duplicate/version/unknown-field failures; bounded input tests |
| Stage history | `tests/test_stage_industry.py`; nightly idempotency; stale/empty/taxonomy fixtures; page build |
| Brain | instant route, streaming/SSE, gateway, tool economics, context collision, citations, guest/auth, resumable runs |
| Latency | `scripts/brain_latency_bench.py` cold/warm production receipts; before/after comparison |
| Screener | AST validation, cost limits, units, nulls, PIT universe, deterministic order, NL equivalence |
| Ratings | cohort/PIT, ties, IPO/delist, corporate actions, missing fundamentals, replay, contribution trace |
| Theme | membership revision, comparable ranks, freshness, missing witnesses, provenance |
| Alerts | validator, crossings/changed-to, dedupe/idempotency, cooldown, stale data, replay, delivery receipt |
| Neural Web | schema, Synapse producer/consumer, time alignment, authority denial, contradiction/missingness |
| Terminal workspace | old-layout migration, save/reopen, link loops, drawing ownership, MTF constraints, auth/isolation |
| UI | real entry path, console/network clean, screenshots light/dark/EN/ZH, `1440×900`, `820×1180`, `390×844`, measured dock height |
| Repo integrity | focused tests, contract drift, Synapse checks, dead refs, template/site sync where applicable, validated-claims guard |
| Delivery | concluded CI, squash merge, remote-default inclusion, covering deploy/render, real live surface |

Do not cargo-cult every test into every PR. The PR body must state which rows apply, exact commands run, what was not tested, and why.

---

## 9 — Adversarial failure modes to test deliberately

1. Explicit `INOD` prompt while AAOI is active and AAPL is pinned.
2. A field wrapper generated now around a value last observed three days ago.
3. One registry ID defined twice with different units or authority.
4. An issuer with missing EPS history but valid price strength.
5. A rank universe that changes sharply between vintages.
6. A theme whose members are renamed/added/removed between rank observations.
7. A theme with strong price return and no supported flow witness.
8. A saved old layout containing a widget/config revision no longer installed.
9. A duplicate-symbol chart grid with drawing persistence plus an MTF exception.
10. A mobile dock that is mounted but has zero height.
11. A natural-language screen asking for an unregistered or licensed-only field.
12. An AST with excessive nesting, output size, or adversarial strings.
13. A stale artifact replayed twice through the alert evaluator.
14. A share link opened by a user without the underlying data right.
15. Brain stream disconnect/reconnect after tool execution but before final deltas.
16. A cached fact whose field definition or formula version changed.
17. A rating cohort containing a future survivor or today-only universe.
18. A Neural Web packet with contradictory fresh and stale theme legs.
19. A proposed Prophet feature joined before selection or with today's recalculation.
20. A public Brain request attempting to retrieve repository internals.

---

## 10 — PR slicing and dependency order

Prefer small vertical PRs over one “Deepvue clone” branch.

| Order | PR slice | Repo | Depends on | May run in parallel with |
|---:|---|---|---|---|
| 0 | Native Stage industry history | Macro | current Stage packet | benchmark refresh |
| 0 | AI benchmark receipt extension/current baseline | Macro | shipped harness | Stage history |
| 1 | Registry schemas + loader + 12-field adapters + resolver fixtures | Macro | none | no downstream schema consumer yet |
| 2 | Instant fact expansion + field receipts | Macro | registry | workspace schema design review |
| 2 | AI context envelope + compiler | Macro | registry | Terminal context-strip design |
| 3 | Terminal context adapter/strip | Terminal | envelope projection | workspace migration after schema freeze |
| 3 | Workspace schema/projection | Macro | registry/context | screener schema review |
| 4 | Terminal saved-layout migration + semantic link groups | Terminal | workspace contract | Theme projection backend |
| 4 | Theme state projection | Macro | registry | Terminal workspace implementation |
| 5 | Theme Tracker++ dock | Terminal | workspace/link groups/theme projection | screener executor |
| 5 | Screener AST/validator/executor | Macro | registry | rating research |
| 6 | Terminal screener AST UI/migration | Terminal | executor API | NL compiler |
| 6 | NL → proposed AST | Macro | AST executor | saved-object envelope |
| 6 | Saved-object envelope/service | Macro | saved-query service, auth, rights/redaction policy | NL compiler |
| 7 | Saved/share UX for screens and investigations | Terminal | saved-object service | rating backend |
| 7 | Equity rating vintages/passport API | Macro | registry/PIT inputs | generic visual widgets |
| 8 | Rating renderers + generic widgets | Terminal | rating API/workspace | alert backend |
| 8 | User-rule evaluator | Macro | registry/query grammar | Terminal composer design |
| 9 | Alert composer/history | Terminal | rule service | saved/shareable workflows |
| 10 | Neural Web observation packets | Macro | stable registry/rating/theme vintages | W5 workflows |
| later | Prophet shadow study | Macro | sufficient PIT accrual + prereg | never bundled with product PR |

Every cross-repo pair must state compatibility order. Prefer backward-compatible producers first, consumers second, and producer cleanup only after consumer deployment is verified.

---

## 11 — Claude execution protocol

### 11.1 First Claude session: adjudicate one slice, not the whole roadmap

Recommended first commissioned build: **W1-A registry kernel and twelve-field vertical slice**, while a separate small lane handles W0-A Stage native history. The registry unlocks the competitive flywheel; Stage history closes a concrete truth defect but should not monopolize the architecture lane.

The first session must:

1. refresh both repos and report current SHAs;
2. read current build maps/kill registry and check for collisions;
3. inventory exact existing producers for the proposed V1 fields;
4. freeze the exact V1 field manifest; if a seed field is rights/data blocked, record the substitution and reason in the schema-review receipt;
5. freeze schema plus one real resolver/Brain/query vertical slice;
6. list exact files before editing;
7. build, test, ship, and live-verify the slice; and
8. update this docket only if implementation evidence changes dependency order or acceptance.

Do not begin by redesigning the whole Terminal. Do not begin with the rating formula. Do not begin with a prompt rewrite.

### 11.2 Required response contract from every Claude build lane

Begin the return with exactly one status:

```text
STATUS: DISCOVERED | BLOCKED | IMPLEMENTED | VALIDATED | SHIPPED
```

Then report:

```text
Wave / slice:
Repo + baseline SHA:
Branch / worktree:

REUSED
- existing producers, contracts, UI substrate

BUILT
- schema, producer, projection, consumer, migration

DEFERRED / EXCLUDED
- exact reason, rights/authority/dependency gate

TRUTH RECEIPT
- observed_at / effective_at / as_of / generated_at
- freshness / coverage / missingness / provenance
- authority ceiling

VALIDATION
- exact commands and results
- browser paths/viewports/states
- benchmark before/after where applicable
- not tested and why

DELIVERY
- commit / PR / concluded CI / squash merge
- remote-default verification
- deploy/render and live verification

RISKS / NEXT DEPENDENCY
- smallest next shippable slice
```

`IMPLEMENTED` means local/code complete but not fully proved. `VALIDATED` means required proof passed but delivery is incomplete. `SHIPPED` requires merge and live evidence. Do not use `SHIPPED` for a local commit or open PR.

### 11.3 Model and review routing

- Use the main/Fable lane for architectural adjudication and final cross-repo sequencing.
- Use the repository's Opus-pinned builder for code, tests, refactors, and migrations.
- Use the Opus reviewer for contract/security/stats red-team review.
- Use the Opus designer for user-facing UI choices after reading the design doctrine.
- Use Sonnet only for bounded census/exploration and Haiku for trivial extraction, with explicit routing required by repo law.
- A flagship UI builder pauses at `VALIDATED` and returns PR + visual proof to the commissioning session; that session owns the remaining same-day merge/deploy/live loop.

---

## 12 — Completion scoreboard

Claude should maintain this table in the PR description or an implementation successor—not by marking aspirational work complete in this research file.

| Slice | Current status on 2026-08-06 | Completion evidence required |
|---|---|---|
| W0-A native Stage history | Remaining | native ledger + non-empty honest heatmap + nightly/idempotency proof |
| W0-B current AI baseline | Remaining | versioned production receipts and frozen rubric |
| W1-A registry vertical slice | Remaining | 12 fields, resolver, query/Brain consumers, rights/freshness tests |
| W1-B instant native facts | Partial: quote only | multi-field deterministic route + receipts + latency/quality proof |
| W1-C effective context | Remaining | envelope, precedence tests, visible Terminal receipt |
| W2-A workspace migration | Partial: chart layouts only | generic schema + lossless migration + save/reopen proof |
| W2-B semantic link groups | Remaining | typed propagation + loop/drawing/MTF proof |
| W2-C Theme Tracker++ | Partial intelligence, no dock | governed projection + Terminal widget + visual proof |
| W3-A deterministic screener | Partial local UI only | server AST validator/executor + PIT receipts |
| W3-B NL compiler | Remaining | proposed AST + diff + deterministic equivalence |
| W3-C saved/shareable objects | Remaining | versioned service + rights-safe cross-device proof |
| W4-A rating fabric | Remaining | PIT cohorts/vintages/components/replay/passport |
| W4-B generic visuals | Remaining | registry-driven bounded widgets |
| W4-C alert grammar | Partial legacy paths | shared validator/evaluator/migration/replay |
| W4-D analyst tape | Rights-gated | source/right decision + event contract |
| W5 compounding workflows | Partial substrate | integrated end-to-end capture→study→share path |
| W6-A Neural Web packets | Remaining for new fields | typed observed/context packets + Synapse/authority proof |
| W6-B Prophet promotion | Conditional future research | PIT accrual + prereg + OOS adjudication |

---

## Final instruction to Claude

Build the operating system, not the screenshot.

The first durable competitive win is not a lavender dashboard or a guessed Composite score. It is one fact—defined once, timestamped honestly, resolved quickly, screened deterministically, rendered anywhere, cited by Brain, observed by Neural Web, replayed point-in-time, and denied trading authority until evidence earns it. Repeat that pattern field by field and workflow by workflow. That is how Mastermind absorbs Deepvue's best product lesson without becoming its clone.
