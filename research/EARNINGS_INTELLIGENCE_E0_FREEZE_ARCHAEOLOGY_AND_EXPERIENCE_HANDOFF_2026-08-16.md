# Earnings Intelligence OS V2 — E0 Freeze, Archaeology and Experience Handoff

**Wave:** E0  
**Class:** research + architecture conformance + design specification  
**Repositories:** Macro + Mastermind Terminal; read-only inspection of Mastermind where necessary  
**Production mutation authority:** none  
**Feature implementation authority:** none  
**One-PR objective:** freeze the verified delta between the original Earnings/Company Event program and the actual production estate, then produce the exact approved E1/E2 contracts and real-data experience blueprint  
**Hard boundary:** do not begin E1 or build any new product feature in this session

---

# 0. Mission

Create one evidence-backed, implementation-ready freeze that lets a subsequent operator build the first exceptional vertical slice of Mastermind Earnings Intelligence OS without rediscovering the program or silently narrowing it.

The E0 PR is successful only when another strong frontier operator can read the resulting artifacts and know:

- exactly what exists;
- exactly what is live;
- exactly what is broken or disconnected;
- exactly which prior documents still have authority;
- exactly which product jobs are missing;
- exactly how the final product is organized;
- exactly which event, sources and states E1/E2 will prove;
- exactly what contracts and files E1/E2 may touch;
- exactly how the user-visible outcome will be accepted.

This is not a generic research memo. It is the construction drawing for the next two vertical waves.

---

# 1. Authority order

Read in this order:

1. repository `AGENTS.md` and `CLAUDE.md` in every inspected repository;
2. current Chairman instructions in this handoff;
3. `research/EARNINGS_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`;
4. `research/EARNINGS_WAVE1_CONTRACT_FREEZE_2026-08-06.md` for frozen identity/citation semantics unless E0 proves a direct conflict;
5. `research/EARNINGS_COMPANY_EVENT_SUITE_REMAINING_BUILD_HANDOFF_FOR_CLAUDE_2026-08-06.md` for shipped baseline and historical ordering;
6. `research/COMPANY_EVENT_INTELLIGENCE_SPINE_AND_PREMIUM_IR_SUITE_BUILD_DOCKET_2026-08-01.md` for original full architecture;
7. competitor teardowns as evidence, not implementation authority;
8. live code and production as the current-state truth.

If live code contradicts a plan, record the contradiction. Do not silently choose the code merely because it exists.

---

# 2. Current known baseline to verify, not trust

## 2.1 Macro product

- `/stocks/earnings/` is a source-first transcript-excerpt archive, not the intended analysis workspace.
- Event pages expose exact transcript excerpts and receipts but explicitly omit release, filing, slides, consensus and market-reaction joins.
- Ticker dossiers expose a Company Intelligence block with a summary, positive/pressure context, a small fixed metric set and history tabs.
- The dossier can show `Wording not yet checked` because the narrative is not yet line-cited.
- Stage Analysis contains earnings surfaces and historical score data.

## 2.2 Terminal product

- Full normalized transcripts and Q&A filters exist.
- Earnings actual/estimate charts and financial statements exist separately.
- Company Intelligence has Brief, Transcript, History, Topics and Sources lenses.
- Existing UI can display metadata-only receipts and pending line-level citation state.
- `terminal/docs/COMPANY_INTELLIGENCE_V2_DELTA_SPEC.md` is a spec and screenshot set, not proof every described capability is live.

## 2.3 Backend

- `engine/earnings_narrative/` contains evidence, story, public-wire and context primitives.
- `engine/company_intelligence/` contains v1 context plus early event/identity/document/resolution work.
- Terminal transcript discovery/reader is separate and live.
- SEC Item 2.02 / release binding work exists but may not yet feed the normal event product.
- Qwen qualitative analysis exists and recent PRs attempted to restore model identity, prompt quality and operating bounds.
- the production freshness chain has been under active repair; use the latest main and latest production runs.
- Group Reads/theme exposure/institutional context exist as separate systems and must not be re-created inside Earnings.

## 2.4 Known recent repairs to inspect

At minimum inspect the merged history and production evidence for:

- the dead evidence-ingestion lane and PyYAML repair;
- the sparse-checkout `engine.press` repair;
- story-packet catch-up/runtime recovery;
- public-wire publication versus protected-main recovery;
- Qwen model/context/prompt repairs, including the discovery that the “definitive” prompt file had not been executed by the live worker;
- current newest upstream/evidence/story/public dates.

Do not use the PR description alone as production proof.

---

# 3. Required investigations

## E0-A — Repository and runtime capability census

Create a capability ledger with one row per concrete capability.

Required state vocabulary:

```text
PROVEN_LIVE
BUILT_NOT_PROVEN
PARTIAL
DARK_OR_DISCONNECTED
BROKEN
SPEC_ONLY
NOT_BUILT
REJECTED_BY_DESIGN
```

Required capability families:

### Source and event truth

- company/security/alias identity;
- event identity and lifecycle;
- earnings calendar;
- release and Exhibit 99.1;
- 8-K / 10-Q / 10-K;
- raw/edited transcript revisions;
- slides;
- audio metadata;
- consensus snapshots;
- market reaction;
- source rights;
- correction replay.

### Extraction and intelligence

- deterministic result facts;
- actual/prior/consensus/guide deltas;
- guidance extraction and history;
- segment/KPI extraction;
- narrative summary;
- narrative change;
- management commitments;
- Q&A exchange structure;
- question topics;
- non-answer/deflection classification;
- tone/uncertainty;
- entity extraction;
- relationship extraction;
- theme/topic evidence;
- contradictions;
- exact per-claim citations.

### Search and research workflow

- transcript search;
- filing/release search;
- slide search;
- global cross-source search;
- exact context open;
- company history comparison;
- peer comparison;
- Topics;
- Mentioned By;
- cited chat;
- exports;
- highlights/notes/workspaces;
- keyword alerts;
- watchlist/calendar integration.

### Group and market intelligence

- season analytics;
- industry earnings heatmaps;
- reporting waves;
- peer read-through;
- relationship paths;
- residual co-movement groups;
- Group Reads integration;
- theme/TIL integration;
- price incorporation/catch-up context.

### Distribution and consumers

- public event archive;
- public event analysis;
- weekly intelligence;
- ticker dossier;
- Stage;
- Terminal;
- Brain/Neural Web;
- Press/research;
- X/alerts;
- Prophet/context;
- Catalyst forward ledger.

For every row include:

- user job;
- current state;
- source files/modules;
- production surface or artifact;
- last verified date;
- current data source;
- missing dependencies;
- governing prior document;
- E-wave owner;
- explicit evidence reference.

## E0-B — End-to-end source lineage map

For at least three real events, trace:

```text
source discovery
 -> raw storage
 -> normalization
 -> evidence generation
 -> extraction/score
 -> company context
 -> public wire
 -> dossier
 -> Terminal
 -> Neural Web/Brain
 -> Stage/Prophet where applicable
```

At each edge record:

- identifier used;
- source and availability time;
- generation/manifest;
- freshness clock;
- correction behavior;
- exact or metadata-only citation precision;
- authority;
- failure state;
- consumer.

Use one recent healthy event, one event with partial sources and one difficult/corrected/identity case.

## E0-C — Program and ownership adjudication

The current semantic program registry includes `group-reads`, which owns group earnings read-through, but it does not clearly identify the entire Company Event/Earnings Intelligence product as one program.

Determine and freeze:

- canonical program key and name;
- relationship to `group-reads`;
- relationship to `thematic-intelligence`;
- relationship to `neural-web`;
- relationship to `prophet`;
- ownership of company/event/document/claim truth;
- ownership of the deep Terminal workspace;
- ownership of public acquisition surfaces;
- repository boundaries.

Preferred answer unless evidence disproves it:

```text
earnings-intelligence-os / company-event-intelligence
  owns event/document/claim/earnings product truth
  contains no duplicate theme or co-movement engine
  consumes Group Reads and TIL
  feeds Neural Web and research
  feeds Prophet only through governed context/shadow contracts
```

If adding the program to `config/mastermind_programs.yml` would require generated-map or registry work beyond a docs-only E0, record the exact follow-up and create a valid Agent OS workstream under the closest existing owner only if semantically honest. Do not mislabel the program merely to satisfy schema validation.

## E0-D — Competitor workflow matrix

Reinspect Quartr, EarningsCall.ai, Jodie and Struct directly. Use the existing teardowns as starting evidence, not a substitute for current inspection.

For every important workflow capture:

- entry point;
- exact user task;
- interaction sequence;
- data required;
- output shape;
- source/evidence behavior;
- persistence/alerts;
- likely engine;
- Mastermind current state;
- Mastermind upgrade;
- verdict: `COPY_JOB`, `ADAPT`, `DEFER`, `REJECT`.

Required Quartr jobs:

- event summary;
- global search;
- transcript search;
- slide search/history;
- Topics;
- Mentioned By;
- AI chat with sources;
- calendar/watchlists/alerts;
- split-view research workflow;
- exports.

Required EarningsCall.ai jobs:

- analysis views;
- historical and peer analysis;
- chat;
- weekly intelligence;
- topic tracker;
- alerts;
- programmatic event pages.

Required Jodie/Struct jobs:

- market-neutral groups;
- lifecycle/lineage;
- group participation;
- relationship map;
- “what changes next” monitor;
- Moving Together;
- Filing Read;
- Supply Chain;
- Daily Radar;
- story → live product route.

## E0-E — Golden universe and difficult states

Select at least five companies and eight events covering:

- profitable mega-cap with release/transcript/slides;
- unprofitable growth company with meaningful operating KPIs;
- industrial or supply-chain company;
- bank/insurer/REIT basis differences;
- dual-class or dual-listing identity;
- corrected source;
- missing transcript or slides;
- malformed/speaker-role issue;
- high analyst Q&A pressure;
- strong peer-wave/read-through opportunity.

At least one golden wave must contain:

- one early announcer;
- several not-yet-reporting peers;
- explicit operating mechanism;
- positive and negative/competitive interpretations;
- measurable market incorporation;
- later events that can grade the hypothesis.

The golden universe becomes the acceptance set for E1–E8.

## E0-F — Experience architecture

Produce real-data reference compositions—not empty wireframes—for:

1. Earnings Command Center.
2. Company Event Brief.
3. Results/Guidance.
4. Q&A Intelligence.
5. Narrative Timeline/Commitments.
6. Peer/Read-Through Wave.
7. Global Search.
8. Evidence/source rail.
9. Dossier glance module.
10. Mobile event research flow.

Required sizes:

- 1440;
- 820;
- 390.

Required states:

- complete/current;
- partial;
- stale;
- corrected;
- conflicting sources;
- blocked rights;
- empty;
- provider down.

Every composition must answer:

- glance answer;
- evidence path;
- next research action;
- what persists during navigation;
- what is source text vs Mastermind analysis;
- what is deterministic vs inferred;
- where Ask Mastermind fits.

Do not redesign the Terminal shell. Extend its existing grammar.

## E0-G — Contract freeze for E1 and E2

Freeze the minimum versions needed for the golden vertical slice.

Required decisions:

- canonical event identifier;
- document and revision identifier;
- source span/cell/page address;
- event fact;
- metric delta;
- guidance item;
- event claim;
- Q&A exchange;
- management commitment;
- narrative change;
- market reaction;
- compact event workspace payload;
- correction dependency/invalidation;
- citation token shared by Macro and Terminal;
- explicit authority and point-in-time clocks.

Do not attempt to freeze the entire future graph in code. Freeze E1/E2 contracts and document the later graph extension seams.

## E0-H — First vertical slice boundary

E1/E2 should prove one end-to-end event, not build a corpus-scale shell.

Recommended boundary:

### E1

One real event binds:

- issuer identity;
- earnings release / Exhibit 99.1;
- transcript;
- deterministic result facts;
- guidance;
- exact per-claim receipts;
- correction-aware publication;
- one compact payload.

### E2

The existing Terminal workspace and dossier render:

- what happened;
- reported/prior/consensus where basis matches;
- guidance change;
- narrative/Q&A materiality;
- history comparison;
- market reaction;
- source completeness;
- exact evidence opens.

Freeze exact acceptance screenshots and interactions.

---

# 4. Required E0 artifacts

Create or update only the minimum authoritative files.

Required:

1. `research/earnings_intelligence/E0_CAPABILITY_LEDGER.md`
2. `research/earnings_intelligence/E0_LINEAGE_AND_RUNTIME_MAP.md`
3. `research/earnings_intelligence/E0_COMPETITOR_WORKFLOW_MATRIX.md`
4. `research/earnings_intelligence/E0_GOLDEN_UNIVERSE_AND_ACCEPTANCE_CASES.md`
5. `research/earnings_intelligence/E0_EXPERIENCE_ARCHITECTURE.md`
6. `research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md`
7. real-data reference images under a clearly named docs/research verification directory where repository law permits;
8. one Agent OS decision or discovery for any cross-session architectural ruling that is valid under the schema;
9. one exact E1 implementation handoff and one exact E2 handoff, with E2 dependent on E1.

Update the masterplan only when E0 evidence changes a ruling. Do not duplicate its unchanged prose across every artifact.

---

# 5. Explicit non-goals

Do not:

- fix the current freshness outage unless explicitly reassigned after the recovery session ends;
- build the new UI;
- create production schemas or migrations;
- reimplement Terminal transcripts;
- reimplement Stage;
- build slide OCR;
- build global search;
- build the relationship graph;
- build the read-through model;
- call Qwen or another model for production output;
- add Prophet authority;
- publish public articles;
- create an independent app;
- create a second program registry or lifecycle store;
- spend the session polishing prose while leaving the capability ledger incomplete.

---

# 6. Acceptance gates

## Gate 1 — Completeness

Every capability family in §3 has a row. No `UNKNOWN` state remains without an owner, evidence plan and next action.

## Gate 2 — Current-state honesty

Each `PROVEN_LIVE` row has production evidence. Each spec-only capability is labeled `SPEC_ONLY`, even if the spec is excellent.

## Gate 3 — Cross-repository identity

The same golden event can be traced across Macro and Terminal identifiers, or the mismatch is explicitly named and assigned to E1.

## Gate 4 — Product specificity

The experience blueprint contains concrete real-data information hierarchy and interactions. A component inventory or generic card collage fails.

## Gate 5 — Competitor fidelity

Every benchmark workflow retains its concrete user job. “We already have search/AI/themes” without matching the job is not accepted.

## Gate 6 — Architecture boundary

No duplicate transcript, event, theme, graph, auth, queue or publication system is proposed.

## Gate 7 — E1/E2 executability

A frontier operator can implement E1 and E2 from the freezes without making a new product decision.

## Gate 8 — Reviewability

The PR is docs/research/reference-composition only, has a clear evidence index, passes repository validation and leaves no generated-state drift.

---

# 7. Stop condition

Stop when:

- E0 artifacts are complete;
- architecture conflicts are adjudicated or escalated;
- golden cases and reference compositions are approved;
- E1 and E2 are bounded and implementation-ready;
- Agent OS records the exact next action.

Do not begin E1 in the same session.

The next session should be able to receive one sentence:

> Implement E1 exactly as frozen; prove the selected real event from source documents through the canonical compact payload and one real consumer.

If that sentence is not yet safe, E0 is not complete.