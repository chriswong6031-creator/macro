# Defense Procurement Intelligence OS V2
## D0 Freeze, Archaeology, Competitive-Parity, and Experience-Design Handoff

**Date:** 2026-08-16  
**Primary repository:** `mastermindx-market-intelligence/macro`  
**Related repositories:** `mastermindx-market-intelligence/Mastermind`, `mastermindx-market-intelligence/mastermind-terminal`  
**Program:** Defense Procurement Intelligence OS V2  
**Wave:** D0  
**Status:** READY TO START  
**Authority:** RESEARCH AND DESIGN ONLY  
**Implementation authority:** NONE  
**Canonical masterplan:** `research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`  
**Existing substrate:** Government Revenue Foresight / `engine/government_revenue/**`  
**Required next output:** one audited D0 evidence bundle and two exact implementation handoffs for D1 and D2

---

# 0. Read this before doing anything

Do not begin coding.

Do not “fix the page while you are here.”

Do not write a collector, schema, model, UI component, builder, DAG entry, migration, feature flag, or Prophet adapter in D0.

D0 exists because the previous program repeatedly allowed implementation activity to outrun current-state truth, product definition, runtime wiring, source rights, and browser acceptance.

The D0 outcome is:

> **A frozen, evidence-backed understanding of what exists, what runs, what the user can actually do, what GovTribe and other relevant products actually provide, which source and owner planes are authoritative, what the V2 experience and contracts must be, and exactly what D1 and D2 may build.**

A good D0 makes the next implementation PR obvious and bounded.

A bad D0 produces another abstract masterplan, another page mockup with no data, or another backend subsystem with no user path.

---

# 1. Binding objective

Complete nine workstreams:

1. repository and production archaeology;
2. current capability and authority ledger;
3. source, artifact, runtime, and browser lineage;
4. authenticated GovTribe functional-parity capture;
5. official/licensed source and rights registry;
6. target ontology, temporal contract, and owner map;
7. golden universe and adversarial proof cases;
8. real-data experience compositions;
9. exact D1 and D2 handoffs.

Then stop.

Do not implement D1 or D2.

---

# 2. Authority order

When sources disagree, use this order:

1. current `origin/main`;
2. current deployed production ancestry and runtime;
3. current artifacts and receipts;
4. current repository law and ownership docs;
5. the V2 masterplan;
6. this D0 handoff;
7. older Government Revenue handoffs/masterplans;
8. remembered session claims.

Never use an old handoff to overrule current code or current production.

Never use current production alone to infer intended architecture.

Document every discrepancy.

---

# 3. Mandatory first reads

Fetch current `origin/main` before reading. Record the SHA and time.

## 3.1 Repository law and active ownership

Read current versions of:

- `AGENTS.md`;
- `CLAUDE.md`;
- `docs/ACTIVE_BUILD_MAP.md`;
- `research/DO_NOT_REBUILD.md`;
- `docs/STRATEGIC_STATE.md`;
- `config/dag.yml`;
- `config/synapse.yml`;
- relevant AgentOS decisions/discoveries/handoffs;
- current open PRs touching Government Revenue, Prophet, Neural Web, options, auth, templates, or deployment.

If a listed file moved or does not exist, record that; do not substitute a guessed path.

## 3.2 Government Revenue substrate

Read current versions of:

- `research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`;
- `research/DEFENSE_PROCUREMENT_ALPHA_ENGINE_PRO_EFFORT_HANDOFF_2026-08-16.md`, if present;
- `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md`;
- `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md`;
- latest `research/GOVERNMENT_REVENUE_FORESIGHT_HANDOFF_*.md`;
- `research/GOVERNMENT_REVENUE_CANDIDATE_CENSUS_ADJUDICATION_2026-08-13.md`;
- `research/GOVERNMENT_REVENUE_PROPHET_INTEGRATION_RULING_2026-08-08.md`;
- `research/GOVERNMENT_REVENUE_CANDIDATE_GRADER_PREREG.md`;
- `research/GOVTRIBE_CLEANROOM_STUDY_2026-08-07.md`;
- `engine/government_revenue/**`;
- USAspending, SAM, IDV, subaward, SBIR, budget, and issuer collectors;
- `scripts/build_government_revenue.py`;
- Government Revenue API routes;
- templates, JavaScript, CSS, site artifacts, and tests;
- current data/status/ledger files under `data/government_revenue/**`.

## 3.3 Sister-program lessons

Read:

- `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_2026-08-16.md` from the shared file/library or repository location;
- current BioCatalyst handoff and current recovery PRs;
- `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_HANDOFF_2026-08-16.md`;
- current Seasonality event-time contracts, builders, state, model, calibration, program watch, and Prophet bridge;
- `research/EARNINGS_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`;
- `research/EARNINGS_INTELLIGENCE_E0_FREEZE_ARCHAEOLOGY_AND_EXPERIENCE_HANDOFF_2026-08-16.md`;
- Sol executive architecture and account instructions in the Mastermind repository.

Extract reusable rules; do not rename or copy sector-specific implementation blindly.

## 3.4 Prophet, Neural Web, Mastermind, and market owner planes

Read current versions of:

- `engine/us_prophet_fusion.py`;
- current Prophet board build and publication path;
- `research/prophet_fusion/families.yml` or its current replacement;
- `engine/prophet_bridge.py`;
- Prophet forward/outcome ledgers and tests;
- `engine/neuralweb/mastermind_context.py`;
- Neural Web artifact registry and summarizers;
- current Mastermind context/decision architecture;
- options, flow, GEX, and dark-pool owner contracts in Macro and Terminal;
- current price/security-master/PIT universe owner;
- Company Intelligence, Corporate, Capital Structure, SEC, transcripts, and ownership planes.

The deliverable must identify one canonical owner for every required fact.

---

# 4. D0 non-goals

D0 may not:

- change production code;
- change templates or assets;
- change data files;
- change workflows/DAG;
- add a collector;
- add or edit a schema contract;
- add a builder;
- add a model;
- add a score;
- create a new database;
- build a graph store;
- add a Prophet family/member;
- modify Neural Web;
- fix current browser defects;
- make a source-health threshold green;
- create mock/demo data;
- add a feature flag;
- claim a source is live without runtime proof;
- claim parity from public marketing pages alone;
- use a current entity map in historical examples;
- collapse uncertain dates into exact timestamps;
- grant any new rank, gate, size, entry, selection, or execution authority.

The only repository changes permitted in D0 are research/design artifacts explicitly listed in §12.

---

# 5. Workstream A — repository and production archaeology

## 5.1 Establish exact current state

Record:

- `origin/main` SHA;
- current open Government Revenue PRs;
- recent relevant merged PRs;
- production checkout SHA;
- deployment mechanism;
- services and timers;
- current publication generation/pointer;
- current source/artifact timestamps;
- current browser route and API routes;
- current entitlement requirements.

Do not assume the docs-only branch containing this handoff is the implementation base. D1 must begin from then-current `origin/main`.

## 5.2 Build the runtime lineage map

For every visible current page metric and tab, trace:

```text
official source
→ collector/request
→ raw snapshot/receipt
→ normalizer
→ graph/event projection
→ candidate/company projection
→ published artifact
→ API reader
→ edge/proxy/auth
→ browser fetch
→ rendered component
```

Include:

- exact path/module;
- owner;
- schedule;
- input/output contract;
- last successful run;
- current artifact;
- validation;
- failure behavior;
- restart/reload behavior;
- test coverage;
- current consumer.

## 5.3 Reproduce the real signed-in product

Use a production-equivalent entitled session.

Capture:

- page URL;
- deployed SHA;
- session/entitlement result;
- network requests;
- status/content type/response size;
- API schema/version;
- request IDs;
- console errors;
- rendered counts;
- loading/empty/stale/unavailable behavior;
- screenshots at 1440, 820, and 390 px where possible.

Test all current tabs:

- Candidate Radar;
- Changes;
- Award Tape;
- Opportunities;
- Recompete Watch;
- Budget & Programs;
- Companies.

Do not fix failures in D0. Classify them.

## 5.4 Trace one record through three serving layers

For one known award-change event:

1. public browser;
2. edge/origin;
3. localhost/API reader or production service equivalent.

Capture:

- source receipt;
- raw source identity;
- effective time;
- first observed/known time;
- graph mapping;
- candidate state;
- projection/generation;
- API payload;
- browser output.

Identify the first seam where truth or state changes.

## 5.5 Current artifact census

At minimum, re-compute:

| Item | Current value | Artifact | Clock | Production proof | Healthy? |
|---|---:|---|---|---|---|
| candidate projection count | | | | | |
| candidate ledger rows | | | | | |
| candidate queue states | | | | | |
| mapping backlog | | | | | |
| exact reviewed issuers | | | | | |
| exact covered recipient identifiers | | | | | |
| award/event recency | | | | | |
| USAspending source state | | | | | |
| SAM state | | | | | |
| IDV state | | | | | |
| subaward state | | | | | |
| SBIR state | | | | | |
| budget/program state | | | | | |
| forecast state | | | | | |
| protest state | | | | | |
| timing/model state | | | | | |
| forward grader state | | | | | |
| Neural Web state | | | | | |
| Prophet annotation/shadow state | | | | | |
| live UI/API state | | | | | |

A missing or unreadable artifact is `unavailable`, not zero.

---

# 6. Workstream B — capability and authority ledger

Create:

`research/DEFENSE_PROCUREMENT_D0_CAPABILITY_AND_AUTHORITY_LEDGER_2026-08-XX.md`

Every feature/capability row has:

| Field | Meaning |
|---|---|
| capability ID | stable identifier |
| user job | what a real user/machine can accomplish |
| current owner | canonical module/plane |
| source/data | required evidence |
| contract | schema/version |
| collector | exists/runs? |
| data populated | nonzero and current? |
| builder | exists/runs? |
| artifact | current publication |
| API | served? |
| UI | surfaced? |
| browser proven | signed-in real-data proof? |
| Neural Web | context consumer? |
| Prophet | context/shadow/live? |
| rights | approved/blocked/unknown |
| status | state below |
| blocker | exact reason |
| acceptance | falsifiable completion proof |

Allowed status values:

- unresearched;
- source identified;
- rights blocked;
- contract proposed;
- contract built;
- collector built;
- collector running;
- data populated;
- builder built;
- builder running;
- artifact published;
- API served;
- UI surfaced;
- browser proven;
- research eligible;
- shadow;
- bounded;
- promoted;
- unavailable;
- retired;
- superseded.

“Backend exists” is not a status.

## 6.1 Separate authority dimensions

For every output, record separately:

- public/private access;
- evidence/display authority;
- research authority;
- model/shadow authority;
- Prophet rank authority;
- selection authority;
- size authority;
- gate authority;
- execution authority.

A private feature can still be display-only. A public feature can still be official fact only. Do not conflate access with authority.

## 6.2 Identify built-but-inert engines

Search for modules that:

- have tests but no production caller;
- produce no artifact;
- are not in the DAG;
- have no consumer;
- are behind always-false availability flags;
- are called only in tests or scripts;
- publish claims from static literals rather than live ledgers.

Create a “wire, retire, or refuse” decision for each.

---

# 7. Workstream C — authenticated GovTribe parity capture

The user has partner authorization. Do not request or store passwords.

## 7.1 Capture method

Use one or more of:

- user-provided screenshots;
- screen recording;
- partner-provided route/export documentation;
- sanitized HAR/network export;
- plan/permission inventory;
- sample CSV/PDF reports;
- MCP tool list and sample responses where licensed;
- operator-led walkthrough.

Do not copy proprietary code, styling, prompts, or private customer data.

## 7.2 Route inventory

Inventory at minimum:

### Explore and global navigation

- Explore;
- Global Search;
- recent searches;
- recommendations;
- popular records;
- Daily Briefing;
- AI conversations/projects/memories/automations.

### Opportunities

- federal forecasts;
- federal opportunities;
- federal vehicle opportunities;
- grants;
- state/local if relevant;
- opportunity details;
- activity;
- files;
- Opportunity Stack;
- similar records;
- likely bidders;
- predicted award type/value.

### Awards

- awards;
- transactions/modifications;
- IDVs;
- vehicles;
- task orders;
- subawards;
- funding timelines;
- Opportunity Stack;
- similar awards/IDVs;
- price lists.

### Participants/categories/programs

- vendors;
- agencies/offices;
- contacts/Beacon;
- NAICS/PSC;
- major defense programs;
- funding and related-record reports.

### Reports

- funding;
- new entrants;
- any vehicle/market reports;
- filters and comparison periods;
- drill-down behavior;
- export.

### Capture/workspace

- dashboard;
- pipelines;
- pursuits;
- tasks;
- saved searches;
- watches/alerts;
- files;
- teaming;
- integrations.

### AI/MCP

- record-grounded AI;
- skills;
- generated files;
- automations;
- MCP tools, reads, and mutations;
- source citations;
- credit/plan behavior;
- limits and failure states.

## 7.3 For every route capture

- user job;
- plan/permission;
- normal/loading/empty/error/gated states;
- fields;
- filters;
- sorts;
- tabs;
- relationships;
- actions;
- alerts;
- exports;
- data sources/refresh disclosure;
- AI behavior;
- files;
- route/API identity;
- screenshot;
- investor relevance;
- current Mastermind equivalent;
- V2 beyond-parity expression.

## 7.4 Deliverable

Create:

`research/DEFENSE_PROCUREMENT_D0_GOVTRIBE_PARITY_MATRIX_2026-08-XX.md`

Classification:

- parity-critical;
- useful later;
- partner/licensed extension;
- excluded;
- already owned elsewhere;
- replace with investor-native capability.

No “complete parity” claim without authenticated evidence.

---

# 8. Workstream D — source and rights registry

Create:

`research/DEFENSE_PROCUREMENT_D0_SOURCE_AND_RIGHTS_REGISTRY_2026-08-XX.md`

For every current or proposed source:

- source;
- owner;
- authority;
- native IDs;
- authentication;
- rate/credit limit;
- update cadence;
- historical depth;
- original-release/PIT quality;
- correction behavior;
- raw retention;
- files;
- licensing/terms;
- internal derivative use;
- public redistribution;
- model/training use;
- expected coverage;
- known gaps;
- failure state;
- replay;
- launch SLO;
- implementation wave.

## 8.1 Source families to adjudicate

At minimum:

- USAspending;
- SAM opportunities;
- SAM entity/reference;
- DoD contract announcements;
- DoD budget exhibits;
- agency acquisition forecasts;
- DLA/DIBBS;
- IDV/vehicle opportunity sources;
- subawards;
- SBIR/STTR;
- OTA/prototype;
- GAO protests;
- DSCA/FMS;
- service/program-office documents;
- congressional authorization/appropriation;
- SEC/earnings/transcripts;
- Massive/Polygon;
- EOD options;
- Terminal flow;
- dark pool;
- GEX;
- GovTribe partner data/MCP/exports;
- other licensed data.

## 8.2 One owner per fact

For each fact family decide:

- current canonical owner;
- new Government Procurement owner;
- consumed adapter;
- prohibited duplicate.

Do not implement a second:

- security master;
- corporate-action history;
- SEC store;
- transcript store;
- price store;
- options store;
- dark-pool store;
- user/tenant state;
- Prophet ranker;
- Neural Web core graph.

---

# 9. Workstream E — target ontology and contract freeze

D0 proposes contracts; D2 implements them.

Create:

`research/DEFENSE_PROCUREMENT_D0_CONTRACT_AND_ONTOLOGY_FREEZE_2026-08-XX.md`

## 9.1 Freeze core objects

At minimum:

- source snapshot;
- temporal fact;
- document/file;
- entity;
- entity edge;
- program/mission;
- forecast;
- opportunity;
- vehicle;
- IDV;
- award/order;
- transaction;
- subaward;
- budget line/action;
- protest;
- procurement event;
- company exposure;
- transmission hypothesis;
- timing forecast;
- market context;
- scenario;
- candidate observation;
- forward grade;
- Neural Web packet;
- Prophet contribution;
- health.

## 9.2 Freeze temporal contract

Require:

- precision;
- lower/upper bounds;
- bound rule;
- source publication;
- source update;
- first observed;
- system known;
- first tradable;
- effective interval;
- correction/supersession;
- generation.

No generic `date` field may substitute for these.

## 9.3 Freeze amount semantics

Enumerate:

- incremental obligation;
- cumulative obligation;
- deobligation;
- current value;
- potential value;
- ceiling;
- budget request;
- appropriation;
- estimated opportunity range;
- outlay;
- backlog;
- revenue.

Specify allowed arithmetic and forbidden comparisons.

## 9.4 Freeze identity and lineage

- stable source-native IDs;
- stable causal event ID;
- entity and edge IDs;
- graph digest;
- source/evidence refs;
- ownership path;
- lineage/overlap ID;
- authority.

## 9.5 Freeze failure semantics

- valid empty;
- source stale;
- transport stale;
- source unavailable;
- not covered;
- projection missing;
- projection invalid;
- contract mismatch;
- identity unresolved;
- amount unsupported;
- rights blocked;
- late discovered;
- quarantined;
- model abstained.

---

# 10. Workstream F — golden universe and adversarial proof cases

Create:

`research/DEFENSE_PROCUREMENT_D0_GOLDEN_UNIVERSE_AND_CASES_2026-08-XX.md`

The golden universe is not a marketing list. It is a compact test set that spans the hard semantics.

## 10.1 Required case classes

Select real, source-backed examples for:

1. major prime with multiple subsidiaries;
2. acquired/renamed/novated entity;
3. JV or consortium;
4. private recipient with no public issuer;
5. vehicle/IDV and child-order hierarchy;
6. ceiling versus funded obligation;
7. positive obligation;
8. deobligation;
9. late-discovered/backfill event;
10. source correction;
11. opportunity/forecast before award;
12. option/recompete;
13. budget request versus appropriation;
14. protest/corrective action;
15. small/mid-cap materiality;
16. supplier/competitor read-through;
17. negative loss/cancellation;
18. pre-event options activity;
19. post-event options chase;
20. valid zero versus not covered;
21. fixed-price margin or loss-contract risk;
22. capacity bottleneck that limits funded-demand realization;
23. company disclosure versus official-record divergence;
24. FMS/export or supplemental-demand pathway;
25. portfolio-level shared supplier or program concentration.

## 10.2 Suggested issuers to evaluate, not automatically adopt

- LMT;
- RTX;
- NOC;
- GD;
- LHX;
- HII;
- IRDM;
- BWXT;
- KTOS;
- AVAV;
- LDOS;
- BAH;
- PLTR;
- TDG;
- HEI.

D0 may replace any symbol if current exact evidence is better elsewhere.

## 10.3 Required proof packet per case

- source receipts;
- source-native IDs;
- temporal braid;
- identity path;
- amount semantics;
- event classification;
- company denominator availability;
- market-data availability;
- options availability;
- expected product surfaces;
- expected refusal/abstention behavior;
- current system result;
- target system result.

Use frozen bytes for closed incidents.

---

# 11. Workstream G — experience architecture and real-data compositions

Create:

`research/DEFENSE_PROCUREMENT_D0_EXPERIENCE_AND_INFORMATION_ARCHITECTURE_2026-08-XX.md`

## 11.1 Required navigation architecture

Design, using real golden-case data:

- Defense Command Center;
- Catalyst Radar;
- Change Tape;
- Opportunity/Recompete Radar;
- Budget & Program Intelligence;
- Explorer;
- Company Dossier;
- Program/Vehicle/Award/Opportunity Dossiers;
- Supply Chain Graph;
- Market Incorporation & Alpha Lab;
- Watches/Alerts/Briefings;
- Ask Procurement;
- Data/API/MCP;
- Operator Console.

## 11.2 Required screen states

For each primary surface:

- normal nonempty;
- valid empty;
- loading;
- stale/degraded;
- unavailable/integrity blocked;
- access locked where relevant;
- correction/quarantine;
- mobile overflow;
- long names/files/tables.

## 11.3 Required compositions

Produce real-data compositions at:

- 1440 px;
- 820 px;
- 390 px.

Priority pages:

1. Command Center;
2. Catalyst Radar;
3. Company Dossier;
4. Program/Vehicle Dossier;
5. Change Tape;
6. Alpha Lab;
7. Operator Console.

## 11.4 Required page questions

Every design must answer:

- what happened;
- when known;
- who is exposed;
- how exact is the join;
- how large and funded;
- when it matters;
- what is already priced;
- what contradicts it;
- what happens next;
- where the receipts are.

## 11.5 Design constraints

- reuse current design system;
- no mega-dashboard;
- no nested-scroll maze;
- no clipped chips;
- no browser scoring;
- no unsupported top-line counters;
- evidence and model class visible;
- operator controls separated;
- source receipts reachable in one action;
- URL/state deep links;
- keyboard and responsive behavior.

---

# 12. Permitted D0 repository outputs

D0 may add or update only research/design files such as:

1. `research/DEFENSE_PROCUREMENT_D0_CURRENT_STATE_TRUTH_LEDGER_2026-08-XX.md`
2. `research/DEFENSE_PROCUREMENT_D0_CAPABILITY_AND_AUTHORITY_LEDGER_2026-08-XX.md`
3. `research/DEFENSE_PROCUREMENT_D0_RUNTIME_LINEAGE_2026-08-XX.md`
4. `research/DEFENSE_PROCUREMENT_D0_GOVTRIBE_PARITY_MATRIX_2026-08-XX.md`
5. `research/DEFENSE_PROCUREMENT_D0_SOURCE_AND_RIGHTS_REGISTRY_2026-08-XX.md`
6. `research/DEFENSE_PROCUREMENT_D0_CONTRACT_AND_ONTOLOGY_FREEZE_2026-08-XX.md`
7. `research/DEFENSE_PROCUREMENT_D0_GOLDEN_UNIVERSE_AND_CASES_2026-08-XX.md`
8. `research/DEFENSE_PROCUREMENT_D0_EXPERIENCE_AND_INFORMATION_ARCHITECTURE_2026-08-XX.md`
9. `research/DEFENSE_PROCUREMENT_D1_PRODUCTION_TRUTH_AND_USER_JOURNEY_HANDOFF_2026-08-XX.md`
10. `research/DEFENSE_PROCUREMENT_D2_TEMPORAL_EVIDENCE_AND_PUBLICATION_CONTRACT_HANDOFF_2026-08-XX.md`
11. one D0 closeout handoff;
12. AgentOS decision/discovery records following current schemas.

Avoid duplicating content across ten essays. A compact canonical set with linked tables is preferable.

No code or runtime file belongs in the D0 PR.

---

# 13. Exact D1 handoff requirements

D0 must write a paste-ready D1 implementation handoff.

D1 objective:

> **Make the existing Government Revenue product truthful, diagnosable, nonempty for a golden entitled user, and browser-proven without adding new feature scope.**

D1 must specify:

- exact root cause(s);
- exact owned paths;
- exact prohibited paths;
- health/error contract;
- current generation/artifact;
- golden event and user;
- source/transport/projection/API/browser test matrix;
- production deployment/restart;
- browser verifier;
- acceptance screenshots;
- rollback.

D1 may not:

- add sources;
- change scoring;
- add Prophet/Neural Web authority;
- redesign the whole suite;
- create new graph contracts;
- paper over zeros;
- widen freshness to make green.

D1 completion:

- entitled browser;
- real nonzero rows;
- typed failure states;
- no unexpected console/network errors;
- one event source-to-screen;
- exact deployed ancestry.

---

# 14. Exact D2 handoff requirements

D0 must write a separate paste-ready D2 implementation handoff.

D2 objective:

> **Implement the bounded temporal evidence, source snapshot, correction, health, and atomic publication contracts required by all later V2 waves.**

D2 must specify:

- exact schemas;
- migration/backward compatibility;
- raw snapshot envelope;
- temporal bound rules;
- amount semantics;
- identity/lineage keys;
- generation/pointer publication;
- replay;
- producer validation;
- mutation tests;
- owner paths;
- allowed first source;
- no product redesign.

D2 completion:

- one selected source replays from frozen raw bytes;
- exact and bounded time cases validate;
- invalid precision fails;
- correction lineage works;
- atomic generation publishes and rolls back;
- reader/writer handshake;
- no historical byte mutation.

---

# 15. D0 research questions that must be answered

## Current product

1. What is actually live and nonempty?
2. Why do screenshots and current artifacts disagree?
3. Which counters share an evidence cut?
4. Which tabs are unimplemented versus broken versus valid empty?
5. Does membership gating reflect intended entitlement?
6. Which services/timers publish the current generation?
7. Which tests execute in the same lane as producers?

## Identity

8. How many exact reviewed issuers exist now?
9. How many recipient IDs and dollars/events map exactly?
10. Which major primes are missing and why?
11. How are acquisitions, novations, JVs, consortia, and multiple identifiers handled?
12. What mapping work is safely automatable versus mandatory review?

## Sources

13. Which sources are live?
14. Which are built but inert?
15. Which are stale?
16. Which have replayable history?
17. Which have rights restrictions?
18. Which high-value GovTribe capabilities depend on data we do not yet own?

## Lifecycle

19. Can we connect forecast→opportunity→vehicle/IDV→award→transaction today?
20. What stable IDs support each join?
21. What can only be similarity-linked and must remain derived?
22. How are corrections and cancellations represented?

## Economic layer

23. Which point-in-time corporate denominators exist?
24. Can reported backlog/segment data be joined safely?
25. Which calculations are deterministic?
26. Which require calibrated models?
27. Which events lack sufficient semantics and must abstain?
28. Which contract-type, pricing, incentive, option, working-capital, and loss-contract fields are available?
29. Which capacity, facility, production-rate, supplier, and lead-time facts have canonical owners?
30. Can official funding be reconciled point-in-time against company backlog, guidance, and commentary?

## Timing/seasonality

31. Which lifecycle timestamps exist historically?
32. Which are exact versus bounded?
33. What is the earliest PIT-safe cohort?
34. What timing engines already exist elsewhere and can be reused?
35. Which builders/runners are missing?
36. Which agency/program/vehicle/CR regime variables are required for conditional hazard?

## Market/options

37. Which canonical PIT prices are available?
38. Which options features are replay-safe?
39. Which are intraday-only?
40. What does Prophet F5 already consume?
41. How will pre-event anticipation and post-event chase remain separate?
42. Which attention, estimate, valuation, and company-disclosure vintages are lawful?

## Policy/capacity/read-through

43. Which official policy, supplemental, FMS, and program sources are usable?
44. Which industrial-base capacity facts can be sourced and timestamped?
45. Which supplier/read-through relationships can be exact or reviewed?
46. Which portfolio stress scenarios are descriptively useful before model authority?

## Neural Web/Prophet

47. What procurement context is already emitted?
48. What is the exact current Prophet family registry?
49. Is an F9 family necessary or would curated F4/F7 members be cleaner?
50. How will causal duplicates be detected?
51. What evidence would justify a bounded rank effect?

## Product

52. Which GovTribe jobs are parity-critical?
53. Which are bidder-only and excluded?
54. Which investor-native surfaces create the moat?
55. What is the minimum complete V2 beta?
56. What screen and evidence bundle would convince the user that D1 is truly fixed?

---

# 16. D0 acceptance checklist

D0 is complete only when all are true:

- [ ] current `origin/main` and production SHA recorded;
- [ ] no implementation changes made;
- [ ] every visible current feature appears in the capability ledger;
- [ ] every required source appears in the source/rights registry;
- [ ] current runtime lineage is mapped source-to-browser;
- [ ] signed-in browser behavior is captured;
- [ ] all current tabs are classified;
- [ ] current candidates, ledger, mapping backlog, and source states are re-counted;
- [ ] built-but-inert modules are identified;
- [ ] GovTribe authenticated parity capture is complete or exact unavailable items are listed;
- [ ] competitor jobs are translated into investor-native jobs;
- [ ] canonical owner map is complete;
- [ ] temporal and amount semantics are frozen at design level;
- [ ] golden universe covers all adversarial classes;
- [ ] real-data 1440/820/390 compositions exist;
- [ ] D1 handoff is exact and implementable;
- [ ] D2 handoff is exact and implementable;
- [ ] unresolved blockers have owners and stop conditions;
- [ ] D0 evidence bundle is attached;
- [ ] no statement calls infrastructure a completed feature without user proof.

---

# 17. Required D0 PR evidence

The D0 PR body must include:

## Repository

- base SHA;
- branch;
- changed files;
- docs-only confirmation;
- no runtime/data/workflow changes.

## Current-state proof

- artifact census summary;
- production/browser matrix;
- one source-to-screen lineage;
- current candidate and mapping counts;
- active timers/services;
- known incidents.

## Competitive proof

- public GovTribe sources;
- authenticated capture inventory;
- missing/gated items;
- parity summary;
- clean-room/rights statement.

## Design proof

- owner map;
- target ontology;
- contract decisions;
- golden cases;
- experience comps;
- exact D1/D2 boundaries.

## Uncertainty

- facts not verified;
- sources not accessible;
- rights unresolved;
- production access gaps;
- decisions deferred.

---

# 18. Stop conditions

Stop D0 and report the blocker when:

- production or entitled-browser access cannot be obtained;
- GovTribe authenticated capture is not available;
- source terms cannot be reviewed;
- a current owner plane is in active conflicting migration;
- current main changes materially during the audit;
- a required file is missing and no canonical replacement can be identified;
- D1 root cause cannot be narrowed from evidence;
- physical architecture depends on unresolved source/rights decisions.

A stopped D0 is acceptable when it produces a precise blocker packet.

An invented answer is not.

---

# 19. Paste-ready opening prompt for the D0 Codex/agent session

> You are starting D0 of Defense Procurement Intelligence OS V2 in `mastermindx-market-intelligence/macro`.
>
> Do not implement anything. Do not fix the current page, add a source, change a schema, add a model, wire Prophet, modify Neural Web, or create a new data plane.
>
> Fetch current `origin/main` and record the SHA. Read `AGENTS.md`, `CLAUDE.md`, the active build map and do-not-rebuild records, then read:
>
> - `research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`
> - `research/DEFENSE_PROCUREMENT_D0_FREEZE_ARCHAEOLOGY_AND_EXPERIENCE_HANDOFF_2026-08-16.md`
> - current Government Revenue masterplans/handoffs, candidate census, Prophet ruling, grader preregistration, and GovTribe study
> - current `engine/government_revenue/**`, collectors, builders, APIs, templates, artifacts, workflows, and tests
> - current Prophet family fusion, Neural Web bridge, Mastermind architecture, options/flow/dark-pool owner contracts
> - BioCatalyst V2 recovery, Seasonality current handoff, and Earnings Intelligence OS E0 architecture
>
> Your only objective is to produce a current-state truth ledger, capability/authority ledger, source-to-browser runtime lineage, authenticated GovTribe parity matrix, source/rights registry, target temporal/ontology freeze, golden universe/adversarial cases, real-data experience architecture, and exact D1/D2 implementation handoffs.
>
> Use a signed-in entitled browser to capture the current Government Revenue product. Trace one event through official source, raw receipt, normalized event, issuer mapping, candidate projection, publication generation, API, and browser. Distinguish valid zero, not covered, stale, unavailable, projection failure, contract mismatch, access failure, and frontend failure.
>
> For GovTribe, use the user's authorized account only through secure operator access or sanitized screenshots/recordings/HAR/exports. Never request or record credentials. Inventory every relevant paid route, filter, field, relationship, alert, export, AI/MCP, report, and workspace behavior. Preserve clean-room boundaries and record rights.
>
> Make no runtime changes. The D0 PR is documentation/design only. Completion is not an architecture essay: it is a falsifiable evidence package and two exact handoffs that make D1 and D2 bounded and executable.

---

# 20. D0 closeout format

At completion, write:

`research/DEFENSE_PROCUREMENT_D0_CLOSEOUT_HANDOFF_2026-08-XX.md`

Use this structure:

1. Executive verdict
2. Base and production ancestry
3. What is live
4. What is broken
5. What is built but inert
6. Current capability census
7. Current source/coverage census
8. Current identity census
9. Current authority census
10. Browser truth
11. GovTribe parity findings
12. Source and rights decisions
13. Frozen ontology/contract decisions
14. Golden universe
15. Experience architecture
16. D1 handoff link
17. D2 handoff link
18. Blockers
19. Risks
20. Exact next action
21. Explicit stop: D1 not started

---

# 21. Final D0 maxim

> **D0 does not build the intelligence system. It prevents the next build from becoming another technically impressive wrong system.**

> **Find the truth. Freeze the joins. Prove the user journey. Then build one vertical capability at a time.**
