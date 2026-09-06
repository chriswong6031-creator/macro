# BCI-0B — Current-State Archaeology, Contract Reuse, and Supersession Handoff

**Program:** Mastermind Biopharma Cycle Intelligence OS  
**Workstream:** `WS:BIOPHARMA-CYCLE-INTELLIGENCE`  
**Wave:** BCI-0B  
**Status:** Not authorized until BCI-0A architecture review/merge  
**Primary repository:** `mastermindx-market-intelligence/macro`  
**Bounded cross-repository reads:** `mastermind-terminal`, `Mastermind`  
**Latest audited `main` at handoff writing:** `5d600641bc3513f69a37cfb8cac1f1d86238e896`  
**Authority:** Research and design only  
**Stop condition:** Produce the BCI-0B evidence packet and exact BCI-0C/BCI-1 handoffs; do not implement runtime code, schemas, UI, workflows, APIs, models, or authority changes

---

# 0. Observable mission

Produce a current, production-grounded reconstruction of the complete biopharma
intelligence estate so the next implementation can extend one coherent system
without rebuilding BioCatalyst, Market Memory, Company Intelligence, Neural Web,
Prophet, Financial Intelligence Fabric, Capital Structure, Options, Terminal, or
Portfolio.

BCI-0B is complete only when a competent reviewer can answer:

1. what is genuinely live;
2. what is built but disconnected;
3. what is partial, stale, broken, specification-only, or not built;
4. which existing contract owns each required concept;
5. which product surface owns each user job;
6. which data and authority paths must not be duplicated;
7. which one real vertical slice BCI-1 should commission first;
8. exactly what BCI-0C must design and freeze before code.

The output is a reviewed archaeology and architecture packet, not another broad
masterplan and not an implementation PR.

---

# 1. Why this matters

The current Seasonality/biopharma build contains valuable modules but counted files,
tests, and schema shapes as completion without requiring a producer, builder,
artifact, workflow, consumer, health path, and production proof.

At the same time, adjacent programs have now shipped real reusable substrate:

- BioCatalyst current/history/correction lanes and typed client states;
- Market Memory `market_memory.as_known_at.v1` and W2C prospective activation work;
- Company Intelligence `event_workspace.v1` with one real corrected event;
- Context Snapshot point-in-time dimensions;
- US Context Vector forward-only decision-time accrual;
- Prophet evidence-family fusion with an F4 Catalyst/Event family;
- FIF `financial_intelligence_packet.v1` under review;
- Capital Structure, Options, Earnings, Theme Clinical, and Portfolio learning planes.

Without BCI-0B, a new builder is likely to create another event workspace, episode
store, context packet, analogue engine, identity join, or Prophet feature family.
The archaeology wave exists to prevent that.

---

# 2. Authority and document precedence

Read in this order:

1. `research/BIOPHARMA_CYCLE_INTELLIGENCE_CURRENT_HEAD_DELTA_2026-08-16.md`
2. `research/BIOPHARMA_CYCLE_INTELLIGENCE_OS_MASTERPLAN_2026-08-16.md`
3. `agentos/decisions/DEC-BIOPHARMA-FEDERATED-NOT-MEGA-MERGED.md`
4. `agentos/workstreams/WS-BIOPHARMA-CYCLE-INTELLIGENCE.md`
5. current `config/mastermind_programs.yml`
6. current `research/DO_NOT_REBUILD.md`
7. current `docs/PROJECT_ACTIVE_BUILD_MAP.md` only as advisory history; re-query live PRs
8. the source and implementation files named below
9. prior Seasonality/BioCatalyst/Market Memory plans as historical evidence

For status and sequencing, the BCI current-head delta and this handoff supersede the
older Seasonality continuation handoffs.

Prior documents remain authoritative for their validated formulas, temporal laws,
clean-room boundaries, statistical methods, and historical evidence unless this
packet explicitly supersedes them.

No document in this wave grants runtime or decision authority.

---

# 3. Verified starting state and recent movement

Re-query all of this at session start. The values below are the handoff freeze, not
checkout instructions.

## 3.1 Current main

```text
5d600641bc3513f69a37cfb8cac1f1d86238e896
feat(earnings): publish AAPL FY2026 Q3 through event_workspace.v1 (#5817)
```

## 3.2 Material recent merges

| PR / SHA | Current meaning for BCI |
|---|---|
| `#5805` / `e1ec8865ac92` | Market Memory M0A first-cause nested R2 path repair merged; no broad V2 authorization |
| `#5804` / `021553985cbe` | API restart no longer incorrectly depends on W2C owner-replay success |
| `#5806` / `6ac162329a84` | BioCatalyst P0-B2 production acceptance recorded; entitled browser proof remained open |
| `#5810` / `9d91bf877da4` | BioCatalyst P0-C1 typed client hydration states merged |
| `#5791` / `53a7fd082141` | Earnings bounded catch-up/publication recovery merged |
| `#5814` / `810d6ae0b443` | Defense D0R entitled census and architecture packets merged; D1 not started in that PR |
| `#5817` / `5d600641bc35` | Real AAPL `event_workspace.v1`, immutable sibling publication, verified reader, correction replay |
| `#5813` / `8b5cd60f706e` | Prophet Fusion PR-3A merged; F4 and broader fusion program continue independently |

## 3.3 Important open work at freeze

- PR `#5809`: FIF-1R, held for operator re-review; no FIF-2.
- Re-query every open PR touching Seasonality, BioCatalyst, Company Intelligence,
  Market Memory, Neural Web, Prophet, Context Snapshot, Terminal event UX, Portfolio
  Neural Web, daily workflows, DAG, Synapse, Signal Bus, and CI registrations.

## 3.4 Existing semantic ownership

`config/mastermind_programs.yml` currently has:

- `biocatalyst` as the biopharma event/clinical/seasonality intelligence owner;
- `market-memory` as a separate horizontal cognitive/data plane;
- Neural Web as context/memory routing, not signal origination;
- Prophet as decision engine;
- Terminal as interactive workspace and user-state owner;
- Portfolio as paper-book decision/learning owner.

Do not create a separate BCI semantic program card in BCI-0B. Recommend one only if
the archaeology demonstrates that a subprogram cannot express the owner boundary.

---

# 4. Exact scope

## 4.1 Macro repository

Inventory and trace at minimum:

### Current Seasonality / BCI candidate implementation

- `engine/seasonality/__init__.py`
- `engine/seasonality/contracts.py`
- `engine/seasonality/foundation.py`
- `engine/seasonality/panel.py`
- `engine/seasonality/calendar.py`
- `engine/seasonality/scanner.py`
- `engine/seasonality/multiplicity.py`
- `engine/seasonality/universe.py`
- `engine/seasonality/event_clock.py`
- `engine/seasonality/event_study.py`
- `engine/seasonality/regime.py`
- `engine/seasonality/model.py`
- `engine/seasonality/calibration.py`
- `engine/seasonality/state.py`
- `engine/seasonality/prophet_bridge.py`
- `engine/seasonality/screener.py`
- `engine/seasonality/program_watch.py`
- `app/seasonality.py`
- all `scripts/*seasonality*`
- all `tests/test_seasonality*`
- `templates/stock_seasonality.*`
- `site/stock_seasonality.*`
- `site/seasonalitydata/**`
- `data/seasonality/**`

### BioCatalyst truth and product plane

- `engine/biocatalyst/**`
- `collectors/biocatalyst/**`
- `contracts/biocatalyst/**`
- `config/biocatalyst_sources.yml`
- `config/biocatalyst_closed_beta_source_manifest.yml`
- `config/biocatalyst_outcome_family_policy.yml`
- `app/biocatalyst.py`
- `templates/biocatalyst.*`
- `site/biocatalyst.*`
- BioCatalyst deploy/timer/service files
- current P0 evidence and handoffs under `research/biocatalyst_recovery_v2/`

### Company Intelligence event workspace

- `engine/company_intelligence/event_workspace.py`
- `engine/company_intelligence/event_workspace_build.py`
- `engine/company_intelligence/event_id_adapter.py`
- `engine/company_intelligence/events.py`
- `engine/company_intelligence/identity.py`
- `engine/company_intelligence/documents.py`
- `engine/neuralweb/company_intelligence_reader.py`
- `tests/test_company_intelligence_event_workspace.py`

### Market Memory and context fabric

- `engine/neuralweb/market_memory.py`
- `engine/neuralweb/market_memory_*`
- `engine/neuralweb/context_api.py`
- `engine/neuralweb/mastermind_context.py`
- `engine/us_context_vector.py`
- Market Memory services/timers/deploy units
- Market Memory Agent OS workstream and latest handoffs
- `research/MARKET_MEMORY_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`
- `research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md`

### Adjacent canonical owners

- `engine/theme_clinical.py`
- `engine/biocatalyst/theme_rollup_pit.py`
- FIF packet/kernel/contracts and PR `#5809`
- Capital Structure governed adapters and projections
- Options expectation, surface, flow, and event-state packets
- Earnings/company event workspace and packets
- canonical market/regime planes
- Prophet Fusion family registry and F4 paths
- Context Index/Synapse/Signal Bus/lobe charters/intelligence registry

## 4.2 Mastermind Portfolio repository

Read only the exact current contracts and consumers related to:

- `brain/neural_web_context.py`
- candidate context and `graph_conflicts` use
- decision-mode defaults and authority map
- decision-time learning/provenance fields
- portfolio event/exposure and thesis-memory precedents
- Macro snapshot/import provenance

Do not modify this repository in BCI-0B.

## 4.3 Mastermind Terminal repository

Read only:

- canonical chart/event marker interfaces;
- user-state/watchlist/alert ownership;
- saved research/workspace contracts;
- existing company/earnings/biocatalyst thin-client surfaces;
- Macro context consumption boundaries.

Do not modify this repository in BCI-0B.

---

# 5. Explicit non-goals

BCI-0B must not:

- write or modify engine code;
- create schemas or fixtures;
- add a builder;
- wire an API/router;
- change the daily workflow, DAG, Synapse, Signal Bus, or CI packs;
- redesign or implement UI;
- collect new data;
- activate a source;
- alter BioCatalyst P0;
- repair Market Memory M0B;
- merge/rewrite FIF or Defense plans;
- create a new analogue engine;
- add Context Snapshot fields;
- change Portfolio authority;
- add Prophet inputs;
- flip a live availability flag;
- call a spec or handler a shipped capability;
- broaden the masterplan into another cross-company mega-program.

If a production defect is discovered, record it with evidence, owner, impact, and a
separate proposed PR. Do not fix it in the archaeology PR.

---

# 6. Required capability ledger

Use exactly these states:

- `PROVEN_LIVE`
- `BUILT_NOT_PROVEN`
- `PARTIAL`
- `DARK_OR_DISCONNECTED`
- `BROKEN`
- `SPEC_ONLY`
- `NOT_BUILT`
- `REJECTED_BY_DESIGN`

Every row must include:

- user or machine job;
- current state;
- canonical owner;
- producer;
- entrypoint/builder;
- artifact/store;
- workflow/service;
- real consumer;
- product surface;
- freshness/health;
- authority;
- production proof;
- missing link;
- preserve/repair/retire decision;
- exact next wave.

Required rows include at least:

1. Calendar Clock
2. selection accounting
3. calendar forward ledger
4. `biopharma.event.v2`
5. BioCatalyst current record
6. BioCatalyst record history/change tape
7. BioCatalyst outcome-family clocks
8. BioCatalyst BCI machine projection
9. event clock adapter
10. event-study engine
11. regime adapter
12. forecast model
13. calibration
14. current seasonality Neural Web state
15. Context Snapshot biopharma dimension
16. Seasonality program watch
17. research browser handlers/API route
18. current product Catalyst mode
19. Company Intelligence `event_workspace.v1`
20. Market Memory as-known-at contract
21. Market Memory operational episode/index/retrieval
22. US Context Vector BCI fields
23. Theme Clinical PIT union
24. financial packet
25. capital-structure context
26. options expectation state
27. catalyst collision
28. peer read-through
29. Portfolio event map
30. Terminal alert/workspace
31. Prophet F4 BCI contribution
32. live BCI authority.

A module with tests and no real caller is `DARK_OR_DISCONNECTED`, not built/live.
A handler with no router is `SPEC_ONLY` or `DARK_OR_DISCONNECTED`, not an API.
A UI shell with no real data journey is `PARTIAL`, not a finished product.

---

# 7. Producer-to-consumer lineage map

For every capability claiming more than `SPEC_ONLY`, draw the exact path:

```text
source truth
→ producer
→ immutable or governed store
→ builder/adapter
→ canonical artifact
→ workflow/service
→ consumer
→ UI or machine projection
→ freshness/health
→ production evidence
```

Specifically prove or disprove:

- whether `event_study.py` is ever called outside tests/re-export;
- whether `model.py` and `calibration.py` ever create forecast bytes;
- whether `prophet_bridge.py` has any caller;
- whether `app/seasonality.py` is registered in the production FastAPI app;
- whether `live_screener`, `live_event_graph`, and `live_forecasts` flags match reality;
- whether `program_watch.py` reads canonical DAG state after workflow extraction;
- whether current Neural Web state contains real event/regime/expectation clocks;
- whether the current Mastermind context actually includes seasonality/BCI;
- whether Market Memory operational retrieval can ingest a domain episode today;
- whether BioCatalyst exposes a suitable machine projection already under another name;
- whether Company Intelligence event workspace can compose a biopharma domain block;
- whether Theme Clinical's PIT union is configured/running or merely available code.

---

# 8. Contract reuse matrix

For each proposed BCI object, decide one of:

- reuse unchanged;
- extend by composition;
- create a versioned sibling;
- reject as the wrong owner;
- defer until a producer exists.

At minimum adjudicate:

| Need | Existing candidate | Required question |
|---|---|---|
| bounded domain event | `biopharma.event.v2` | Does it cover current BioCatalyst source/revision semantics without creating a new event dialect? |
| user-facing event investigation | `event_workspace.v1` | Can a BCI block compose into the existing workspace while BioCatalyst remains fact owner? |
| point-in-time market context | `market_memory.as_known_at.v1` | Which domains are currently operational versus contract-only? |
| domain market episode | no accepted BCI object yet | What is the smallest prospective packet not already owned by Market Memory or Company Intelligence? |
| outcome path | Market Memory labels / event-study outputs / BioCatalyst outcomes | Which owner writes domain outcome versus market path? |
| current machine context | current seasonality NW state / Context Snapshot | Can the existing state evolve without an unnecessary v3? |
| financial context | `financial_intelligence_packet.v1` | What exact accepted packet/service can BCI consume, and when? |
| event identity | Company Intelligence IDs plus BioCatalyst trial/program IDs | Can aliases/refs compose without a second identity graph? |
| Prophet contribution | existing F4 family registry | Which fields belong in F4, which are strata/interactions, and which are forbidden? |

For every new-schema recommendation, include:

- why composition/reuse is insufficient;
- owner;
- producer;
- consumer;
- time semantics;
- correction semantics;
- null behavior;
- rights;
- authority;
- migration/no-rebuild boundary.

The default outcome is reuse or composition, not a new schema.

---

# 9. Complete user-journey archaeology

Reconstruct what a user can do now, not what documents say.

## 9.1 Existing BioCatalyst journey

With an entitled production user, verify:

- page/client assets;
- session/bootstrap;
- Trial Screen;
- Milestones;
- Peer Matrix;
- Change Tape;
- First-Seen Tape;
- dossier;
- typed empty/locked/source-outage/integrity-block states;
- one real source receipt;
- production generation/checkout identity.

Record every place the primary task breaks or becomes unclear.

## 9.2 Existing Calendar Clock/Catalyst journey

Verify in production at desktop, tablet, and mobile:

- symbol selection;
- Calendar Clock;
- selected windows;
- evidence/statistics;
- Catalyst mode;
- whether Catalyst contains real events or only shell/empty state;
- methodology/coverage;
- stale/outage behavior;
- route/access boundaries.

## 9.3 Existing event workspace journey

Using the real AAPL event workspace reader/product path, determine:

- what is user-visible today;
- what is only a machine object;
- which fields are earnings-specific;
- which fields are generic event investigation primitives;
- whether correction replay is surfaced;
- whether BCI can compose or must remain a sibling packet.

## 9.4 Cross-product journey

Trace one healthcare ticker through:

- stock dossier;
- BioCatalyst;
- Calendar Clock;
- Neural Web context;
- Prophet board/plan context;
- Terminal chart/workspace;
- Portfolio context.

Record duplicate facts, missing links, conflicting labels, stale clocks, and dead
navigation.

---

# 10. Data, contract, time, null, and correction behavior

For every candidate seam, document:

## 10.1 Time

- effective time;
- source lower/upper bounds;
- submitted time;
- posted/published time;
- known-at;
- observed-at;
- available-at;
- recorded-at;
- superseded-at;
- evaluation cutoff;
- outcome known-at.

Identify any place where:

- current snapshots leak backward;
- a date range becomes a midpoint;
- event date is confused with publication date;
- source refresh is confused with source-content time;
- render time launders stale input;
- a weekend-valid market state is rejected by wall-clock age incorrectly;
- current-vintage prices are presented as PIT.

## 10.2 Identity

Trace issuer, listing/security, ticker history, sponsor, asset/program, trial, target,
indication, partner, application/product, and peer identity.

Classify joins as:

- deterministic source-native;
- reviewed;
- unresolved;
- prohibited inference.

## 10.3 Null and unavailable

Inventory every output state and detect any default to:

- zero;
- false;
- neutral;
- no event;
- current ticker;
- latest source;
- midpoint;
- fresh.

## 10.4 Corrections

Prove whether:

- source versions are immutable;
- corrections append;
- prior transaction intervals close;
- prospective packets preserve their original inputs;
- latest-known/current-corrected views are explicit;
- user workspaces and Market Memory can resolve the same event after correction;
- old outcome/forecast rows are never rewritten.

---

# 11. Deterministic, statistical, and model-generated method ledger

Every calculation or field must be classified as one of:

## Deterministic

Examples:

- source diffs;
- timing bounds;
- identity joins;
- calendar window arithmetic;
- event collisions;
- return paths;
- options implied move calculation;
- coverage and freshness;
- exact cohort filters.

## Statistical

Examples:

- event-study AR/CAR;
- clustered confidence intervals;
- selection correction;
- matched controls;
- realized-versus-implied distributions;
- analogue distance and reliability;
- calibration.

## Model-generated

Examples:

- clinical/regulatory forecast from an approved owner;
- market-response forecast;
- learned retrieval;
- language synthesis.

For model-generated fields, identify:

- training data;
- PIT eligibility;
- baseline;
- version;
- prospective ledger;
- calibration;
- abstention;
- authority.

A historical up-share is statistical/descriptive, not a forecast.
A language summary is presentation, not an evidence value.

---

# 12. Failure-state audit

At minimum test or inspect:

- source unavailable;
- source stale;
- rights blocked;
- identity unresolved;
- event timing imprecise;
- correction conflict;
- partial coverage;
- no events;
- valid empty;
- malformed payload;
- pointer/manifest mismatch;
- stale current context;
- event collision;
- unestimable event study;
- insufficient independent N;
- missing options expectation;
- Market Memory unavailable;
- Context Snapshot absent;
- expired Neural Web packet;
- Prophet contribution absent;
- Terminal user-state unavailable;
- Portfolio consumer on stale vendor checkout.

For each, record current user copy, machine state, recovery behavior, last-good policy,
and whether anything silently appears healthy.

---

# 13. Ordered execution sequence

## Step 1 — Fresh repository/PR/worktree census

- fetch current main in all three repositories;
- list open PRs and changed paths;
- list active worktrees/branches if available;
- identify protected/high-collision files;
- record production checkout/service versions for relevant products.

## Step 2 — Capability call graph

Use static search/import/call analysis and artifact/workflow inspection. Do not infer a
caller from a re-export or test.

## Step 3 — Production and browser proof

Capture current real products and APIs. Screenshots without network/source evidence do
not prove hydration; API responses without browser proof do not prove product utility.

## Step 4 — Contract and owner census

Map every required object to existing contracts/owners. Inspect exact current files,
not only masterplans.

## Step 5 — Temporal/identity/correction audit

Trace at least three golden cases:

- one current trial revision;
- one historical correction/version;
- one real company event workspace.

## Step 6 — Cross-repository authority audit

Prove how current Neural Web context can or cannot influence Portfolio and Prophet. Pay
special attention to generic conflict counts, default decision modes, stale handling,
and context prompts.

## Step 7 — Product topology and journey audit

Build current-state diagrams and identify one canonical destination for each user job.

## Step 8 — Supersession ledger

For every prior Seasonality, BioCatalyst alpha, Market Memory, and BCI document:

- still authoritative;
- authoritative only for history/formulas;
- superseded for status;
- superseded for ownership;
- rejected by design.

## Step 9 — Exact next-wave freezes

Write:

1. BCI-0C Experience Architecture and Contract Freeze handoff;
2. BCI-1 Prospective Market Episode vertical handoff;
3. any separate production-defect or cross-repo-authority handoff;
4. updated workstream state;
5. Agent OS handoff.

Stop.

---

# 14. Required deliverables

## A. `BCI_0B_CURRENT_STATE_CAPABILITY_LEDGER.md`

Complete maturity ledger with evidence and owners.

## B. `BCI_0B_PRODUCER_CONSUMER_RUNTIME_MAP.md`

Diagrams and tables for all real paths.

## C. `BCI_0B_CONTRACT_REUSE_AND_IDENTITY_MATRIX.md`

Exact reuse/composition/version decisions, including `event_workspace.v1`.

## D. `BCI_0B_PRODUCT_AND_EXPERIENCE_ARCHAEOLOGY.md`

Current journeys, browser evidence, product topology, and failure states.

## E. `BCI_0B_TEMPORAL_CORRECTION_RIGHTS_AUDIT.md`

Clock, correction, source, and distribution findings.

## F. `BCI_0B_NEURAL_WEB_PROPHET_PORTFOLIO_AUTHORITY_AUDIT.md`

Exact authority and leak paths.

## G. `BCI_0B_SUPERSESSION_LEDGER.md`

Document and project boundary decisions.

## H. BCI-0C handoff

Real-data experience architecture and contract freeze only.

## I. BCI-1 handoff

One independently useful prospective episode vertical only.

## J. Durable memory update

Workstream, decisions/discoveries, and exact next action.

A single large narrative without these artifacts does not satisfy BCI-0B.

---

# 15. Acceptance tests

## 15.1 Repository truth

- current SHA and open PRs recorded;
- no claim uses a stale Active Build Map as current truth;
- every capability row links to exact implementation and artifact evidence;
- no test-only or fixture-only path is called production.

## 15.2 Completion truth

- every `PROVEN_LIVE` row has real input through real production path to a visible
  user or machine consumer;
- every `BUILT_NOT_PROVEN` row states the missing proof;
- every disconnected module is labeled accordingly;
- every spec has no shipped claim.

## 15.3 Contract truth

- no duplicate event, identity, financial, memory, user-state, or decision owner is
  proposed without an explicit rejection of existing owners;
- `event_workspace.v1` reuse is adjudicated;
- `biopharma.event.v2` reuse is adjudicated;
- Market Memory and BCI episode boundaries are explicit.

## 15.4 Temporal truth

- no hidden current/latest/nearest fallback;
- no source temporal midpoint fabrication;
- correction replay is demonstrated;
- current-vintage price limitations are visible;
- freshness clocks are separated.

## 15.5 Product truth

- entitled BioCatalyst and current Calendar/Catalyst journeys are demonstrated;
- current event workspace behavior is demonstrated;
- all relevant failure states are captured;
- current primary-task gaps are named.

## 15.6 Authority truth

- Macro/Neural Web/Prophet/Portfolio paths are traced;
- context-only BCI contradictions cannot be assumed safe merely because their own
  packet has all-false authority;
- any decision-visible leak becomes a separate blocker/handoff.

## 15.7 Scope truth

The PR changes only research/Agent OS/artifact evidence files. Any runtime change is a
failure of BCI-0B scope.

---

# 16. Production proof required in BCI-0B

This is an archaeology wave, so production proof is observational rather than a new
deployment.

Required observations:

1. current main and relevant production checkout/service versions;
2. entitled BioCatalyst real-data hydration and typed states;
3. current Calendar Clock/Catalyst surface at 1440, 820, and 390 widths;
4. one real Company Intelligence event workspace and correction-capable reader;
5. current Seasonality/BCI Neural Web artifact and expiry/freshness behavior;
6. current Mastermind context/Portfolio consumer behavior from exact current code;
7. current Market Memory W2C prospective state;
8. current FIF/Defense integration status from live PR/merge state.

Do not claim that an authenticated route exists if no entitled browser/API proof was
captured. Do not expose tokens, cookies, private source bytes, or credentials in the PR.

---

# 17. Stop condition

Stop immediately after:

- all BCI-0B deliverables are committed in one architecture/research PR;
- Agent OS validates;
- the PR description names all verified/unverified production claims;
- BCI-0C and BCI-1 handoffs are complete;
- no runtime file has changed.

Do not start BCI-0C design work or BCI-1 code in the same session.
Do not fix discovered defects.
Do not open multiple speculative implementation PRs.

---

# 18. Required continuation handoff

The final handoff must state:

- exact main and production SHAs;
- PR number and head SHA;
- capability-state totals;
- newly proven live capabilities;
- disconnected/broken capabilities;
- exact ownership decisions;
- accepted/rejected contract reuse;
- product findings;
- authority findings;
- unresolved blockers;
- BCI-0C mission;
- BCI-1 mission;
- first exact next action;
- do-not-redo list;
- stop confirmation.

A continuation prompt that says only “continue the masterplan” is invalid.
