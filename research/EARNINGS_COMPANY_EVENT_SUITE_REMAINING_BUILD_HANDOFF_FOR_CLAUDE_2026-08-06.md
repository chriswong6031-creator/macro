# Earnings and Company Event Suite — Remaining Build Handoff for Claude

**Canonical execution handoff for remaining work:** this file

**Status cutoff:** 2026-08-06, after live and repository reconciliation

**Repositories:** Macro Dashboard plus the connected `charting-app` Terminal

**Program decision:** finish one Mastermind-native Company Event Intelligence system. Do not build separate Jodie, Struct, Quartr, EarningsCall.ai, or EquityDesk clones.

This is deliberately a short execution delta, not a replacement for the 2,700-line architecture docket. It supersedes that docket's stale 2026-08-01 status ledger and immediate ordering only.

## 1. Claude boot sequence and document authority

Before editing either repository:

1. Read that repository's `CLAUDE.md` and `AGENTS.md` completely.
2. In Macro, read `docs/ACTIVE_BUILD_MAP.md` and `research/DO_NOT_REBUILD.md`.
3. Read this handoff.
4. Use [Company Event Intelligence Spine and Premium IR Suite Build Docket](./COMPANY_EVENT_INTELLIGENCE_SPINE_AND_PREMIUM_IR_SUITE_BUILD_DOCKET_2026-08-01.md) for detailed contracts, evaluation gates, UI doctrine, economics, and failure states.
5. Consult the evidence appendices only for the lane being built:
   - [Jodie + Struct teardown](./JODIE_STRUCT_ENGINE_TEARDOWN_AND_MASTERMIND_INTEGRATION_DOCKET_2026-07-31.md)
   - [Quartr Pro teardown](./QUARTR_PRO_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md)
   - [EarningsCall.ai teardown](./EARNINGSCALL_AI_TEARDOWN_AND_MASTERMIND_INTEGRATION_2026-08-01.md)
   - [EquityDesk teardown](./EQUITYDESK_TEARDOWN.md)
   - [NewsImpact event-structure teardown](./NEWSIMPACT_EVENT_STRUCTURE_TEARDOWN_2026-08-04.md)
6. Fetch first, audit open PR ownership, and create a fresh worktree/branch from the repository's default branch (`origin/main` in Macro and currently `origin/master` in Terminal). As of this audit, no open Macro or Terminal PR owns the earnings/Company Intelligence/IR parity lanes below; re-check before every lane.

Authority order:

1. repository guidance and explicit user instructions;
2. this file for **current state and remaining sequence**;
3. the 2026-08-01 master docket for architecture and acceptance detail;
4. competitor teardowns as evidence, never as implementation authority.

## 2. Executive ruling

Continue the build. The foundation is real and already valuable. The next bottleneck is not another visual clone; it is turning the existing event context into a claim-level, source-clickable corporate-intelligence product shared by every surface.

The present estate has two strong but separate truths:

| Plane | What exists | What is still wrong |
|---|---|---|
| Exact earnings evidence | `earnings.fact_pack/v1`, `earnings.claim_graph/v1`, `company_event_digest.v1`, `canonical_story.v1`, `earnings.story_packet/v1`, public Wire and compact context packets | It is transcript-only, uses its own event identity, and is not yet the source of every Company Intelligence field |
| Company Intelligence | Stable `cie_…` event IDs, immutable per-company objects, history, topics, source completeness, dossier/API/Neural Web access | Visible summaries and metrics can have document- or metadata-level lineage and explicitly carry `claim_citations_pending`; this is not yet claim-grade Quartr-style evidence |
| Stage and legacy qualitative scores | Large historical backfill, live forward scoring, season/QoQ views, context-only display | A legacy `prophet_stage_fusion.py` path still reads the old parquet and can alter hold horizon from `earnings_call_sent`; this is a split-brain authority path |

The core remaining move is therefore:

```text
one correction-stable company event id
        +
versioned first-party documents and exact spans/cells/pages
        ↓
one approved claim ledger and cited event digest
        ↓
Stage · dossier · Terminal · Brain · Neural Web · weekly · SEO · X
```

Do not let each surface keep its own earnings interpretation. The same event, source revision, claim ID, and correction state must travel end to end.

## 3. Verified shipped baseline — do not rebuild

These capabilities were present on the relevant repository default branch or verified live at the 2026-08-06 cutoff.

### 3.1 Data, ingestion, and operations

- Terminal transcript discovery is live with a large fail-closed corpus, revision hashes, dates, per-ticker transcript access, and a continuous producer. The original shipped evidence is Terminal PRs [#295](https://github.com/chriswong6031-creator/mastermind-terminal/pull/295), [#299](https://github.com/chriswong6031-creator/mastermind-terminal/pull/299), and [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303).
- Stage is no longer in a data-contract `Warming up` state. The committed health artifact is `ready`, with 50,982 accepted historical rows, 3,581 issuers, 17 fiscal anomalies quarantined, latest call date 2026-08-04, and a 500-row compact dashboard projection.
- The installed forward worker is scheduled, idempotent, and advancing. It increased known intake from 25,798 to 26,134 and score rows from 3,980 to 4,270 during the current audit; 47 rows remained under normal batch throttling rather than a dead queue.
- The real-time SEC 8-K Item 2.02 discovery/extraction lane exists through Macro [#4527](https://github.com/mastermindx-market-intelligence/macro/pull/4527). Item 2.02 acceptance timestamps also re-enabled the governed M4 earnings event prior through [#4624](https://github.com/mastermindx-market-intelligence/macro/pull/4624).
- Earnings collector breadth, staleness alarms, and catalyst fields are present through [#4341](https://github.com/mastermindx-market-intelligence/macro/pull/4341) and [#4485](https://github.com/mastermindx-market-intelligence/macro/pull/4485).

### 3.2 Evidence, stories, and product projections

- An append-only, content-addressed, receipt-verified transcript evidence catalog is shipped through [#4262](https://github.com/mastermindx-market-intelligence/macro/pull/4262) and secured through [#4409](https://github.com/mastermindx-market-intelligence/macro/pull/4409).
- Exact UTF-8 quote and numeric spans, source-body hashes, immutable generations, source correction lineage, deterministic digests, promotion decisions, canonical story shells, and story packets exist. See `engine/earnings_narrative/` and PRs [#4280](https://github.com/mastermindx-market-intelligence/macro/pull/4280), [#4284](https://github.com/mastermindx-market-intelligence/macro/pull/4284), and [#4287](https://github.com/mastermindx-market-intelligence/macro/pull/4287).
- Public Earnings Wire, dated weekly intelligence, RSS/sitemap routes, exact public previews, and the member continuation gate are live. The latest successful hosted build produced 436 public call records. The last complete weekly period is 2026-07-27; the current in-progress week correctly has no dated page yet.
- Private full records remain entitlement-first and fail closed: anonymous access returns `401`, `Cache-Control: private, no-store`, `Vary: Authorization`, `X-Content-Type-Options: nosniff`, and `X-Robots-Tag: noindex, noarchive`.
- Company Intelligence immutable objects, public teaser, ticker-dossier integration, API, and verified Neural Web reader exist through [#4215](https://github.com/mastermindx-market-intelligence/macro/pull/4215), [#4221](https://github.com/mastermindx-market-intelligence/macro/pull/4221), [#4298](https://github.com/mastermindx-market-intelligence/macro/pull/4298), [#4318](https://github.com/mastermindx-market-intelligence/macro/pull/4318), and [#4327](https://github.com/mastermindx-market-intelligence/macro/pull/4327).
- Hosted publication, exact private-generation reuse, public navigation, and launch hardening are shipped through [#4412](https://github.com/mastermindx-market-intelligence/macro/pull/4412), [#4415](https://github.com/mastermindx-market-intelligence/macro/pull/4415), and [#4417](https://github.com/mastermindx-market-intelligence/macro/pull/4417).
- Compact earnings context is available to Mastermind AI and Neural Web and can be attached to Prophet **after candidate selection** with explicit `may_rank=false`, `may_size=false`, `may_gate=false`, and `prophet_authority=false` permissions.
- Press and deterministic X derivatives have governed ingress/correction seams. No X scheduler was armed by the original consumer work.

### 3.3 Existing surfaces to extend, not replace

- Research megamenu entry: `templates/_navlinks.html.j2` → Earnings Wire.
- Public product: `templates/earnings_wire/`, `site/stocks/earnings/`.
- Stage: `stage_analysis.html` and `data/stage_analysis/*.json`.
- Company Intelligence: `engine/company_intelligence/`, `app/company_intelligence.py`, dossier templates, and the verified Neural Web reader.
- Exact evidence: `engine/earnings_narrative/`, its builders, publishers, workflows, and tests.
- Terminal transcript estate: extend the current transcript index, drawer, and ticker panes. Do not create a second transcript archive or standalone app.

### 3.4 Terminal is already beyond a transcript tab

Terminal production and `origin/master` were both at `feceb369` during the audit. The live transcript root held 26,134 bodies across 3,350 symbols, and no relevant Terminal PR was open.

Do not rebuild these shipped Terminal capabilities:

- the per-ticker archive and reader from [#295](https://github.com/chriswong6031-creator/mastermind-terminal/pull/295) and revisioned bodies from [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303);
- the responsive Company Intelligence workspace from [#313](https://github.com/chriswong6031-creator/mastermind-terminal/pull/313), including Brief, Transcript, History, Topics, Sources, evidence rail, and source manifest;
- exact ticker-scoped transcript search and two-event comparison from [#319](https://github.com/chriswong6031-creator/mastermind-terminal/pull/319);
- current theme membership context from [#323](https://github.com/chriswong6031-creator/mastermind-terminal/pull/323);
- point-in-time 13-F context from [#332](https://github.com/chriswong6031-creator/mastermind-terminal/pull/332);
- `MegaPane` Intelligence/Transcripts tabs, embedded responsive workspace, EN/ZH behavior, and existing 1440/820/390 E2E coverage.

Canonical Terminal extension points on `origin/master`:

- `terminal/components/fin/CompanyIntelligencePage.tsx`
- `terminal/components/fin/EvidenceRail.tsx`
- `terminal/components/fin/CompanySourceManifest.tsx`
- `terminal/components/fin/TranscriptSearchWorkspace.tsx`
- `terminal/components/fin/TranscriptDrawer.tsx`
- `terminal/components/fin/MegaPane.tsx`
- `terminal/components/fin/CompanyThemeContextCard.tsx`
- `terminal/components/fin/CompanyInstitutionalContextCard.tsx`
- `terminal/app/api/company-source-search/[ticker]/route.ts`
- `terminal/lib/companySourceSearch.ts`
- `terminal/lib/companySourceSearchServer.ts`
- `terminal/e2e/company-intelligence.spec.ts`

Important limitation: exact spans exist in transcript search, but generated Company Intelligence briefs still expose `claim_citations_pending=true`. Search is ticker-scoped, literal, transcript-only, and requires explicit event selection. The remaining Terminal work is multi-document evidence, global search, calendar/live events, richer narrative/relationship history, slides, saved research/alerts/export, ticker teaser/news synthesis, and visibly grounded Mastermind answers.

## 4. Explicit no-rebuild and authority fence

Do not:

- rebuild auth, billing, public navigation, transcript storage, R2 publication, Signal Bus, Brain gateway, Research Vault, Press, X outbox, or the Terminal shell;
- treat EquityDesk, Jodie, Struct, Quartr, or EarningsCall.ai as a live scrape target or implementation dependency;
- create a standalone Jodie or Quartr clone;
- let an LLM originate a trade signal, rank, position size, gate, veto, confidence score, Prophet escalation, or expected-return claim;
- turn 13-F changes, relationship edges, management tone, mention volume, or residual co-movement into directional authority without a separately pre-registered point-in-time promotion process;
- publish one long article per filing, duplicate SEO URLs, or model prose that is not backed by the canonical claim ledger;
- preserve the legacy `earnings_call_sent` production influence merely because it predates the exact evidence spine;
- build global live audio, universal transcription, or Quartr-scale market coverage before the U.S. evidence/correction loop is excellent;
- copy competitor visual identity. Preserve the jobs-to-be-done and build a cleaner Mastermind interaction grammar.

Existing Stage scores can remain descriptive UI fields while migration proceeds. They are not the new evidence contract and must not become hidden authority.

## 5. Current regressions that must be fixed first

### R0-A — restore actual Qwen-first inference

The worker is configured as local-first, but recent work is not local-first in practice.

Observed on 2026-08-06:

- installed plist requests `qwen3:14b` at `http://127.0.0.1:11435/v1`;
- `/v1/models` exposes only `qwen3.5:9b`;
- all 741 scored rows after the switch were marked `model=deepseek`;
- all 749 metered ledger calls were DeepSeek V4 Flash;
- cumulative metered cost was still small—about `$0.5736` for 3,549,639 input and 257,380 output tokens—but the local-primary claim is currently false.

Tracked repair files:

- `ops/launchd/com.mastermind.earnings-worker.plist`
- `ops/bootstrap_earnings_worker.sh`
- `ops/launchd/run_earnings_worker.sh`
- `tests/test_earnings_worker_launchd.py`
- `config/earnings_qual.yml`

Installed verification targets:

- `/Users/chriswong/Library/LaunchAgents/com.mastermind.earnings-worker.plist`
- `/Users/chriswong/earnings-ops-wt/`
- `/tmp/mm_earnings_worker.log`
- `/Users/chriswong/earnings-runtime/data/ai_costs/usage.jsonl`
- `/Users/chriswong/earnings-ops-wt/data/earnings_calls/scores.parquet`

Required repair:

1. Align the tracked and installed model ID to the actual served ID, or restore a stable server alias.
2. Add a startup/preflight check that records the local model's exact unavailability reason instead of silently making the fallback look like a successful local run.
3. Keep DeepSeek Flash as the fallback; do not remove resilience to prove a cost point.
4. Use a tiny direct `/v1/chat/completions` smoke against the local endpoint. Do not invoke a worker “dry run” that can mutate score state.
5. Let the next natural scheduled job process a real record, then prove the newest score row says `model=openai_compat` and the corresponding run did not call DeepSeek while Qwen was healthy.

Exit gate: local model identity is verified, one natural scored record is served locally, fallback still works in a controlled failure test, and the installed plist matches the tracked template.

### R0-B — repair the SEC marketing lane's zero-emission checkout

The real-time EDGAR workflow runs, but its sparse checkout omits the universe it requires. `engine/marketing/fastlane.py` correctly fails closed when `site/marketdata/sp500_heatmap.json` is absent, so the 2026-08-06 workflow emitted zero cards.

Repair:

- add `site/marketdata` to `.github/workflows/marketing-earnings-wire.yml` beside `site/live`;
- add a pin in `tests/test_marketing_fastlane.py::TestTheEarningsLaneIsActuallyArmed` proving the universe is in the sparse cone;
- preserve the fail-closed universe behavior;
- update stale workflow commentary that still says the lane has never run;
- run a workflow-dispatch dry run, then observe one natural scheduled pass. Zero emission is acceptable only when the run reports real eligibility/extraction reasons, not `universe unavailable`.

Exit gate: the workflow loads the intended universe and its emitted/skipped/quarantined counts are attributable. No publisher kill switch is changed.

### R0-C — retire or quarantine the legacy earnings split-brain

`engine/prophet_bridge.py` has a correct exact-evidence annotation path that runs after selection and cannot rank, size, gate, or change geometry. The same file also imports `engine/prophet_stage_fusion.py`, reads the legacy local earnings parquet, applies `EC_SENT_GATE = 24`, and can extend hold horizon through a Stage-2/earnings-score leash.

Required decision and migration:

- keep the historical PSF/PSQ harness as research evidence if needed;
- remove the legacy parquet/score arm from production plan behavior, or rewire any retained descriptive view to the exact cited context contract;
- do not let missing legacy parquet change eligible candidates or plan fields;
- add a regression test proving that, after migration, running with versus without the legacy file yields identical candidate IDs/order, rank, size, gate, geometry, horizon, options, and tranches;
- preserve the point-in-time research ledger separately. Do not rewrite old experiment results.

Exit gate: one governed earnings context path exists in production; legacy sentiment cannot alter a live plan.

### R0-D — freeze the benchmark and remaining experience architecture

The old CEI-00B golden corpus remains unfinished. Terminal already has a polished responsive Company Intelligence v1, so do not redo its shell. Freeze only the experience architecture for the genuinely missing multi-document, global-search, calendar, timeline, slides, research-operations, ticker-teaser, news-synthesis, and grounded-chat work.

Macro deliverables:

- `research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json`
- permitted/synthetic fixtures under `tests/fixtures/company_intelligence/`
- contract and replay tests for at least 100 issuers and 200 difficult events

The corpus must cover fiscal-year ambiguity, amendments, duplicate releases, share classes, dual listings, GAAP/non-GAAP basis, units/currency, banks/insurers/REITs, missing transcripts, missing releases, PDF tables, changed slide families, speaker-role errors, and future-dated/quarantined records. Store hashes and minimal permitted excerpts where full raw fixtures are inappropriate.

Terminal delta deliverables:

- a Mastermind-native Company Intelligence **v2 delta** specification that preserves the existing workspace;
- committed real-payload reference compositions at 1440, 820, and 390 pixels;
- populated, partial, stale, corrected, blocked, empty, and provider-down states;
- EN/ZH copy, keyboard/focus behavior, and performance budgets.

Exit gate: the corpus and missing-feature reference compositions are approved before deep feature assembly. A screenshot collage, generic component inventory, or redesign of already-good v1 surfaces is not sufficient.

## 6. Remaining build waves

R0-A through R0-D are Wave 0. After they are underway, execute the following dependency order.

## Wave 1 — converge the event, document, and claim spine

**Goal:** one correction-stable event identity and claim receipt contract across transcripts, releases, filings, and later slides.

Do not replace the working transcript evidence contracts. Add a versioned convergence layer and adapters.

Macro work:

1. Choose one canonical `event_id` independent of source date/revision. Map the current transcript `ticker/transcript_id` event key and current `cie_…` ID to it.
2. Add closed versioned contracts for:
   - company/issuer/listing identity;
   - company event and lifecycle;
   - event document and document revision;
   - exact evidence block: text span, table cell, or page region;
   - fact/claim with basis, units, period, currency, source availability, and receipt;
   - correction/supersession dependency graph;
   - compact consumer manifest.
3. Adapt the existing `earnings.fact_pack/v1` and `earnings.claim_graph/v1` transcript path into that model without rewriting old immutable objects.
4. Bind the existing SEC Item 2.02 watcher and backfill to the event resolver. Ingest the filing, Exhibit 99.1/release, acceptance timestamp, and amendment lineage as event documents rather than only marketing events.
5. Add deterministic extraction for reported revenue/EPS, guidance ranges, margins, segments, cash flow/capex, and reconciliation labels. A number without basis/units/period/source is absent, not guessed.
6. Extend to 10-Q/10-K facts and table cells only after the 8-K/release binding is reliable.
7. Build correction replay: one changed document revision invalidates affected claims, digest, dossier view, Terminal cache, public derivative, alert, and X draft while retaining the logical event ID.
8. Replace `claim_citations_pending` in the v2 Company Intelligence projection with exact receipts or an explicit missing-citation state. Do not silently convert document-level lineage into span-level lineage.

Suggested Macro areas:

- extend `engine/earnings_narrative/` and `engine/company_intelligence/` through adapters;
- add identity/document/resolver modules under `engine/company_intelligence/` rather than a third top-level engine;
- reuse `engine/marketing/edgar_earnings_wire.py` and `collectors/edgar_earnings_8k.py` as discovery/parsing inputs;
- retain R2 content-addressed publication and current health semantics.

Acceptance:

- every visible golden-corpus fact resolves to `event_id → document_revision → exact span/cell/page` or renders a typed absence;
- amendments preserve event identity and correct every derivative;
- duplicate releases do not create duplicate events;
- issuer/listing/share-class mapping cannot inflate coverage or theme breadth;
- availability timestamps prove no consumer outran the source;
- zero new provider/model calls occur for unchanged document hashes;
- all outputs remain `context_only`.

## Wave 2 — ship one product contract and the two flagship surfaces

**Goal:** make the stock dossier the exceptional glance product and Terminal the deep-work version of the same object.

### 2A. Compact product contract

Publish an authenticated/detail-safe `mastermind.corp/v1`-style payload from the Wave 1 spine. It should carry:

- event header, fiscal identity, source/correction state, and known-at time;
- reported versus consensus only when basis and period match;
- deterministic key facts, guidance deltas, segment changes, cash/capex, and reaction context;
- exact citation tokens and source rail;
- source completeness across filing/release/transcript/slides/consensus;
- links to public record, dossier, Terminal, and source documents;
- explicit authority permissions.

The compact payload is not the raw document store. Heavy source bodies remain behind authenticated, bounded retrieval.

### 2B. Dossier-first Earnings Impact block

Extend the canonical stock/ticker dossier rather than adding another page family.

Glance tier:

- what changed;
- beat/miss only on comparable basis;
- guidance raised/held/cut with old/new range;
- market reaction with denominator and measurement window;
- three evidence-backed watch conditions;
- source completeness and correction badge.

Deep tier:

- exact evidence drawer;
- quarter history and management commitments;
- transcript/release/filing tabs;
- deep link into Terminal.

Acceptance:

- no model confidence or directional score;
- every fact click reaches the exact source location;
- nulls explain basis mismatch or source absence;
- EN/ZH, dark/light, 390/820/1440, keyboard, focus, zoom, and reduced-motion QA pass;
- the block uses Inter/San Francisco through the existing design tokens—no new font family.

### 2C. Upgrade the existing premium Terminal corporate workspace

Adapt the shipped workspace from PR #313 to the Wave 1 multi-document contract. Preserve its existing Brief, Transcript, History, Topics, Sources, evidence rail, source manifest, exact search, comparison, theme, and 13-F components. Extend the current lens system with the missing capabilities rather than starting over.

Expected v2 lenses:

- upgraded claim-cited Brief;
- multi-document Sources;
- existing Transcript and exact search;
- narrative/commitment History;
- Peers/Mentioned By;
- Slides, when Wave 5 is available.

The existing Transcript drawer/index remains the source body. The new workspace consumes the same product contract and citation tokens as the dossier; it does not create another ingestion path.

Acceptance:

- ticker pane, workspace, transcript drawer, and dossier deep links share one event ID;
- citation chips open the exact source and preserve context;
- long transcripts virtualize and do not block the Terminal shell;
- no generic spinner survives into a terminal state;
- premium QA score is at least 85/100 with no load-bearing category below 7/10.

## Wave 3 — primary-source search, comparison, calendar, and cited Brain

**Goal:** turn stored evidence into a research workflow rather than a collection of cards.

Macro:

- preserve the shipped exact literal ticker/transcript search as an explicit mode;
- add corpus-wide lexical/BM25 primary-source search, then add embeddings beside exact search only where measured relevance improves;
- extend the index from transcript spans to release paragraphs, filing sections/table cells, and later slide pages with company/event/period/source/speaker filters;
- add point-in-time search manifests and correction invalidation;
- expose bounded tools:
  - `search_company_sources`
  - `get_company_event`
  - `compare_company_narrative`
  - `get_peer_topic_pulse`
- build event calendar, watchlist/saved-query hooks, alerts, and correction notifications through existing auth/watchlist/notification systems.

Terminal:

- universal company-source search;
- cross-quarter and peer comparison table;
- saved searches and filters;
- watchlist-aware earnings calendar;
- citation-preserving handoff into Brain.

Acceptance:

- every numeric Brain answer is cited or declined;
- retrieval evaluation reports precision@k, recall on the golden corpus, stale-index rate, and citation-open success;
- issuer/period/source filters cannot leak another company's material;
- search p95 stays below one second for indexed text; heavy source opens progressively;
- alerts are idempotent and corrections supersede prior alerts.

## Wave 4 — narrative history, commitments, relationships, and themes

**Goal:** reach the valuable part of Jodie and Quartr without granting descriptive graphs trading authority.

Build:

- narrative timeline: what was added, dropped, repeated, strengthened, or weakened;
- management commitment ledger with `{repeated, modified, achieved, missed, dropped, unverifiable}`;
- peer Q&A topic pulse;
- `Mentioned By` with resolved entity direction, speaker, context, and exact evidence;
- high-precision company/product/customer/supplier/competitor relationship candidates, with uncertain edges kept internal;
- `theme_evidence_edge` objects with event, source span, sign, novelty, management-versus-analyst origin, peer path, known-at time, and expiry;
- residual co-movement communities, lifecycle/lineage, acceleration, dispersion, breadth, and event joins by adapting the existing theme stack;
- 13-F as a separately dated ownership/crowding context join, never as fresh flow or directional proof.

Reuse:

- `engine/theme_discovery.py`
- `engine/theme_scoring.py`
- `engine/theme_context.py`
- `engine/theme_catalyst_binder.py`
- current Signal Bus, Neural Web, and sector/theme artifacts.

Acceptance:

- every public relationship and narrative delta has an exact receipt;
- share classes cannot inflate breadth;
- similar language cannot become a customer/supplier assertion;
- residual groups pass null, factor-collinearity, parameter-stability, and lineage tests;
- outputs say context, confluence, breadth, acceleration, divergence, or research priority—never probability, conviction, expected return, or capital-deployment instruction;
- Prophet sees these only after candidate selection unless a later pre-registered promotion earns more authority.

## Wave 5 — premium IR workflow and slide intelligence

**Goal:** close the most important remaining Quartr workflow gaps after claim-grade evidence is reliable.

Build in this order:

1. personalized calendar and calendar sync;
2. saved filters, alerts, workspaces/bookmarks, and source exports;
3. filing/release/transcript source tabs and one-click citation export;
4. slide text extraction, selective OCR, page-region receipts, and search;
5. controlled Key Slide tags;
6. slide-family candidates and History Mode with manual override audit;
7. side-by-side quarter comparison and numeric-change extraction.

UI requirements:

- calendar, search, Brief, Timeline, Peers, and Slides use the same Terminal interaction grammar;
- exports retain event/source/claim identifiers and correction state;
- slide ambiguity is visible; false family merges never masquerade as history;
- PDF images lazy-load, zoom cleanly, and remain keyboard accessible.

Acceptance:

- at least 1,000 labeled slide pages clear page citation, search relevance, Key Slide precision, and family merge/split thresholds;
- source exports are rights-aware and do not expose private R2 objects through public URLs;
- saved state and alerts survive correction replay;
- desktop, tablet, and mobile reference tasks pass.

Defer five-second live audio and universal call coverage. Add audio only when its incremental value and source rights clear a separate gate.

## Wave 6 — cited AI analysis and the Struct-style distribution compiler

**Goal:** make the exact evidence spine produce genuinely excellent research and acquisition content without turning prose into truth.

Maintain two explicit layers:

1. `exact_record`: deterministic, receipt-complete, publicly inspectable source facts;
2. `cited_analysis`: model-written synthesis whose every atomic claim maps to the approved claim ledger.

Pipeline:

```text
approved event claims
  → deterministic outline and allowed-claim packet
  → writer
  → independent claim/arithmetic/period/attribution verifier
  → correction-aware story revision
  → dossier · weekly · article · newsletter · alert · X derivatives
```

Model routing:

- deterministic parsing and projections: no model;
- bulk extraction/classification/reranking: local Qwen first;
- cheap fallback: DeepSeek V4 Flash;
- Tier A long-form or difficult verification: selectively use a stronger model only after the promotion gate;
- unchanged source hashes reuse prior extraction and prose; no repeat token burn;
- all calls write provider/model/input/output/cost and source-version telemetry.

Distribution rules:

- Tier C updates product context only;
- Tier B receives a compact brief/weekly/dossier derivative;
- Tier A may receive long-form research and broader distribution;
- all channels share one story ID and revision;
- X accounts receive distinct jobs and formats, not paraphrase spray;
- public pages have canonical URL, structured data, OG image, sitemap/RSS state, correction state, and measurable route into dossier/Terminal membership.

Acceptance:

- 500-story shadow run has zero unsupported claims, arithmetic errors, unresolved period/basis mismatches, or unlabeled corrections;
- the verifier blocks publication rather than “fixing” unsupported prose invisibly;
- article/dossier/X/alert claim sets are subsets of the same approved ledger;
- thin and duplicate pages are `noindex` or not generated;
- quality review compares the analysis against Struct, EarningsCall.ai, and the approved house style without copying their text or prompts.

## Wave 7 — scale, reliability, and governed intelligence use

**Goal:** expand coverage and usefulness without degrading truth or smuggling descriptive context into signal authority.

Scale ladder:

```text
100 → 300 → 1,000 → roughly 2,000 U.S./Canada companies
```

At every step publish a scorecard for:

- event/source coverage and latency;
- identity/fiscal-period defects;
- deterministic numeric accuracy;
- citation coverage and citation-open success;
- correction replay;
- search and comparison quality;
- story quality and block rate;
- UI task completion and performance;
- Qwen hit rate, fallback rate, tokens, metered cost, and machine occupancy;
- queue age, poison events, and operator interventions.

Neural Web/Prophet:

- accrue narrative, relationship, theme, and event-context features point in time;
- pre-register any directional hypothesis before inspecting outcomes;
- preserve context-only status while the forward clock matures;
- promote only through the existing authority ledger and promotion gauntlet;
- a failure to earn signal authority does not reduce product value: cited context still improves research, explanations, dossiers, and content.

Operational acceptance:

- last-good artifacts survive missing/malformed/collapsed inputs;
- health distinguishes `ready`, `degraded`, `stale`, `partial`, `blocked_rights`, and `empty`;
- peak earnings-day backpressure and retry behavior are observable;
- the scheduled worker is not dependent on Codex/Claude subscriptions;
- annual metered cost remains a measured output, not a speculative blocker.

## 7. Competitor parity matrix after the current foundation

| Benchmark | Already achieved | Remaining parity/differentiation |
|---|---|---|
| EquityDesk | Large Stage history, season/QoQ views, live forward scoring | Retire the trial-era score split-brain; use exact claims and current events everywhere |
| EarningsCall.ai | Transcript corpus, per-ticker access, exact ticker search/comparison, exact public records, weekly pulse | Global multi-document search, richer peer/narrative views, saved workflows, cited synthesis |
| Struct | Public Earnings Wire, SEO routes, exact previews, membership funnel | Tiered high-quality cited prose, one canonical story fan-out, correction and conversion analytics |
| Jodie | Company history/topics and existing theme infrastructure | Residual groups, lineage, filing relationships, event/theme joins, divergence/breadth UI—all context-only |
| Quartr | Premium Company Intelligence v1, transcript/source lenses, exact ticker search/comparison, themes and 13-F sidecars | Multi-document/global search, calendar/live events, claim-cited Brief, narrative Timeline/Peers/Mentioned By, slides/History, alerts, exports, workspaces |
| Mastermind advantage | Stage, dossiers, Prophet, Neural Web, themes, public research, X, and one evidence spine already coexist | Converge them so one exact event object compounds across every product and distribution surface |

Full parity does **not** mean global live-audio coverage or a visual copy. It means the research jobs above are as fast, trustworthy, source-addressable, and polished as the premium benchmark—then become more useful because they feed Mastermind's existing intelligence graph.

## 8. UI and UX release law

Every front-facing lane must meet all of the following before merge:

- existing Inter/San Francisco design stack only;
- one coherent Mastermind design language, not a vendor collage;
- intentional 1440, 820, and 390 compositions;
- English and Chinese where the host surface supports both;
- dark/light where the host surface supports both;
- populated, partial, stale, corrected, blocked, empty, entitlement-locked, and provider-down states;
- semantic landmarks, keyboard navigation, visible focus, screen-reader labels, contrast, 200% zoom, reduced motion, and touch targets;
- immediate shell; lazy/virtualized long documents and slides;
- skeletons only during bounded loading, never as a terminal state;
- every glance answer has an evidence path and a next research action;
- screenshot/reference-composition comparison with real payloads before merge;
- no clipped tables, horizontal page overflow, broken drawers, or buried citations.

Recommended performance gates:

- public page LCP below 2.5 seconds on a representative mobile profile;
- primary Terminal shell interaction below 150 ms after load;
- indexed search p95 below one second;
- transcript/slide content never blocks the initial shell;
- no unbounded browser payloads.

## 9. Build slicing and parallelization

Use narrow producer-before-consumer PRs. Do not combine the whole program in one branch.

| Batch | Macro lane | Terminal lane | Dependency |
|---|---|---|---|
| 0A | Qwen model alignment/preflight/install proof | — | none |
| 0B | EDGAR workflow universe repair/observability | — | none |
| 0C | retire legacy Prophet earnings influence | — | none |
| 0D | golden corpus and contract fixtures | experience spec/reference compositions | none; commissioner review gates UI |
| 1A | canonical event/document/evidence contracts and identity adapter | typed fixture reader only | golden corpus |
| 1B | 8-K/release/filing adapters and correction replay | — | 1A |
| 1C | cited v2 product projection and compact manifest | typed client/proxy | 1A–1B |
| 2A | dossier Earnings Impact block | — | 1C + approved design |
| 2B | — | v2 contract adapter, claim-cited Brief, and multi-document source rail | 1C + approved design |
| 3A | search/index/tools/calendar/alerts contracts | — | 1C |
| 3B | — | search/compare/calendar/saved UX | 3A |
| 4A | timelines/commitments/mentions/relationships/themes | — | 1C + search |
| 4B | dossier compact history/context | Timeline/Peers UI | 4A |
| 5A | slide parsing/search/families | — | 1A + search |
| 5B | — | Slides/History Mode UI | 5A |
| 6A | cited-analysis writer/verifier/story revision | — | 1C + golden evaluation |
| 6B | SEO/weekly/X/alert derivatives and analytics | deep links only | 6A |
| 7 | scale ladder and point-in-time research accrual | performance hardening | prior quality gates |

Builders can work in parallel within a row only after the producer contract is frozen. Give separate agents separate worktrees and file ownership. Reviewers should check contract/authority, data quality, UI, and operations independently.

## 10. Per-PR completion contract

Every implementation PR must include:

1. explicit input/output schema and authority classification;
2. point-in-time and correction behavior;
3. golden/adversarial fixtures;
4. unit, contract, integration, and failure-state tests;
5. shrink/staleness/health handling where data is published;
6. UI reference proof at required breakpoints for front-facing changes;
7. no unrelated files;
8. updated status row in this handoff or a successor status ledger;
9. merge, deployment, and live verification under the repository's agent contract.

For data and UI claims, “implemented locally” is not complete. Record PR, squash merge, production commit, artifact generation, and live route evidence.

## 11. Definition of complete

The remaining program is complete when:

- a new event arrives without manual backfill and is assigned one logical identity;
- filing, release, transcript, presentation, and corrections bind to that event;
- every visible fact is deterministic or has an exact claim receipt;
- the dossier and Terminal present premium glance and deep-work versions of the same object;
- search, comparison, calendar, alerts, narrative history, Mentioned By, themes, and slides work on that same spine;
- Brain answers are cited or decline;
- Neural Web and Prophet receive point-in-time context under explicit authority limits;
- one correction regenerates or invalidates every downstream derivative;
- exact records and cited AI analysis remain separate layers;
- one canonical story version fans into weekly research, SEO, alerts, and X;
- coverage scales without rising manual rescue or falling quality;
- the product remains useful even if no qualitative feature ever earns directional signal authority.

## 12. First Claude execution prompt

Use this as the first instruction in the new Claude session:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/ACTIVE_BUILD_MAP.md`, `research/DO_NOT_REBUILD.md`, and `research/EARNINGS_COMPANY_EVENT_SUITE_REMAINING_BUILD_HANDOFF_FOR_CLAUDE_2026-08-06.md` completely. Treat the handoff as the current execution sequence and the 2026-08-01 Company Event docket as detailed architecture authority. Re-audit open PR ownership. Start three isolated repair lanes: R0-A Qwen model alignment and proof, R0-B EDGAR sparse-checkout/observability repair, and R0-C legacy Prophet earnings-influence retirement. Keep the coordinating/main lane on R0-D golden-corpus and missing-feature experience design. Do not start new UI implementation until the relevant Terminal reference compositions are approved. Preserve the exact evidence spine, keep all qualitative outputs context-only, use fresh worktrees from each repository's default remote branch, and finish each tracked change through PR, squash merge, deployment, and live verification.

If scope must be cut, cut global coverage, live audio, consensus breadth, slide volume, and article volume. Do not cut event identity, point-in-time timestamps, exact evidence receipts, correction replay, health, evaluation, entitlement safety, or front-facing product quality.
