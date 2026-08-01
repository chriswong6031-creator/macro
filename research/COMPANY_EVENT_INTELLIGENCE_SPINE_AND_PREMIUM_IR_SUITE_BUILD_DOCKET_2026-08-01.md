# Company Event Intelligence Spine and Premium IR Suite Build Docket

**Canonical active build docket:** this file

**Decision date:** 2026-08-01

**Repositories:** Macro Dashboard plus the connected `charting-app` Terminal

**Decision:** build one Mastermind-native Company Event Intelligence Spine and expose it through the existing Stage Analysis, Terminal, Neural Web/Brain, Research, SEO, and X Growth products. Do not create separate Jodie, Struct, Quartr, EarningsCall.ai, or EquityDesk clones.

**Delivery status at this memo refresh:** the Stage recovery and Terminal transcript-discovery lanes are **merged, deployed, and live**. Stage shipped through Macro [#4181](https://github.com/chriswong6031-creator/macro/pull/4181), with its mobile containment follow-up in [#4187](https://github.com/chriswong6031-creator/macro/pull/4187). Terminal transcript intelligence shipped through Terminal [#295](https://github.com/chriswong6031-creator/mastermind-terminal/pull/295), with evidence-bound role repair in [#299](https://github.com/chriswong6031-creator/mastermind-terminal/pull/299). The continuous forward adapter is now merged through Terminal [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303) and Macro [#4192](https://github.com/chriswong6031-creator/macro/pull/4192); the live Terminal index generated at `2026-08-01T14:41:55Z` carries 25,438 bodies, 25,438 revision hashes, 25,438 dates, and 3,288 symbols. Runtime-telemetry isolation for the installed Mac appliance merged through Macro [#4201](https://github.com/chriswong6031-creator/macro/pull/4201) as `fdd75709f79dbd19a6456ff1b954e3e9dec89d1a`. The first-batch checkpoint was 63 of 64 attempted eligible records healthy, with future-dated `HCM/2026Q2` quarantined and 29 pending plus 1 retry before drain. Commissioning then completed at **2026-08-01 09:07 America/Vancouver**: generation `90595cb8924f2ef3992f4e16` was atomically promoted; the final run attempted 29, succeeded on 28, and left only the intentionally pending future `HCM/2026Q2` record (`call_date=2026-08-06`, `source_future_call_date`). All currently causal real calls are drained. Chronicle, Brain, Press, and X consumer projections are implemented and validated on a local integration branch but are not yet shipped.

**Evidence appendices:**

- [Jodie + Struct teardown](./JODIE_STRUCT_ENGINE_TEARDOWN_AND_MASTERMIND_INTEGRATION_DOCKET_2026-07-31.md)
- [Quartr Pro teardown](./QUARTR_PRO_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md)
- [EarningsCall.ai teardown](./EARNINGSCALL_AI_TEARDOWN_AND_MASTERMIND_INTEGRATION_2026-08-01.md)
- EquityDesk delta audit: `/Users/chriswong/Documents/Cluade/equitydesk_backfill/delta_2026-07-31/README.md`

The three teardown memos are the evidence record. This docket is the implementation authority. Where an older memo describes a separate engine, page, or roadmap, this unified plan wins.

---

## 0. Acceptance gates

This program is not done because a transcript is stored, a summary reads well, or a page looks like Quartr. It is done only when the following gates hold.

### 0.1 Product gates

1. A new company event is discovered once, assigned one stable event identity, and progresses through a durable lifecycle without manual backfill.
2. Its filings, release, transcript, presentation, audio metadata, and corrections attach to that same event instead of creating parallel quarter records.
3. Every derived numerical claim is deterministic or reconciled against a deterministic source fact.
4. Every narrative claim carries one or more stable source-span receipts.
5. Stage, Terminal, Neural Web/Brain, public articles, and X derivatives consume the same versioned digest.
6. A corrected or superseded source invalidates and regenerates every affected derivative without changing the event identity.
7. A missing source produces an explicit coverage state. It never presents as “warming up,” silently deletes last-good links, or publishes an uncited guess.
8. The first release works for a controlled company universe end to end. Coverage expands only after quality and operating gates pass.

### 0.2 Epistemic gates

1. Company-event, narrative, theme, mention, relationship, 13-F, and co-movement outputs ship as **display/context tier**.
2. LLMs may extract, reconcile, summarize, retrieve, and de-escalate. They may not originate a trade signal, confidence score, rank, portfolio weight, or Prophet escalation.
3. A “story priority” or “research urgency” score is never labeled as expected return, conviction, or alpha.
4. Jodie-style residual themes and filing relationships may become Prophet or Neural Web inputs only after point-in-time accrual and a separate pre-registered promotion gauntlet.
5. The known Jodie evidence is represented honestly: descriptive structure survived; public directional edge did not.

### 0.3 Data and rights gates

1. Every source has a machine-readable rights profile covering storage, transformation, internal retrieval, user display, public derivatives, AI processing, retention, and deletion.
2. EquityDesk is a frozen migration/calibration seed, not a future dependency.
3. Jodie, Struct, Quartr Pro, and EarningsCall.ai are product and evaluation benchmarks, not scrape targets or corpus suppliers.
4. A Quartr Pro seat is never used to populate Mastermind. Any Quartr API use requires a written Order that explicitly permits Mastermind's intended storage, AI, display, evaluation, and public-derivative uses.
5. Raw transcript, presentation, audio, and consensus rights are checked separately. “Available on the web” is not a redistribution license.

### 0.4 Operational gates

1. Writes are idempotent, atomic, content-hashed, replayable, and point-in-time stamped.
2. Last-good production artifacts survive absent, malformed, stale, or implausibly collapsed inputs.
3. Health reports distinguish `ready`, `degraded`, `stale`, `partial`, `blocked_rights`, and `empty`.
4. Nightly/render jobs consume compact published artifacts; heavy document parsing, embeddings, OCR, and model work run off the render path and publish to R2.
5. Peak earnings-day concurrency, retry budgets, poison events, and provider outages are observable.
6. No public page or Neural Web packet can outrun its source availability time.

### 0.5 Distribution gates

1. One canonical story object fans out to the blog, ticker dossier, X, alerts, and short form; none rereads raw documents independently.
2. Public content passes source, fiscal-period, arithmetic, quote, attribution, freshness, completeness, duplicate, correction, and promotion checks.
3. There is no requirement to publish one article per earnings call. Tier C events update the product silently; Tier B receives a compact brief; Tier A earns long-form treatment.
4. X accounts express distinct jobs and voices from one fact packet. They do not spray paraphrases of the same post.
5. Every public article has a measurable route into the live ticker/event experience and a canonical URL, structured data, Open Graph image, sitemap state, and correction state.

### 0.6 Premium experience gates

This is a core product surface, not an internal data viewer. The acceptance bar is a **purpose-built, billion-dollar-SaaS-quality research experience**: coherent, fast, precise, trustworthy, visually unmistakable, and polished in every real state. A release fails even when its data is correct if it feels like several vendor features bolted into Mastermind, a generic dashboard kit, or a technically impressive prototype.

1. The suite presents one coherent **Mastermind Research OS** interaction model across Stage, Terminal, and Brain. It may borrow proven product primitives, but must not visually or structurally clone Quartr, Jodie, Struct, EarningsCall.ai, or EquityDesk.
2. A dedicated experience-architecture and design-spec lane precedes feature assembly. Builders do not choose the information architecture, visual hierarchy, density, or responsive behavior ad hoc.
3. Every primary screen has a clear glance answer, an evidence path, and a next research action. Dense does not mean cryptic; premium does not mean decorative.
4. Desktop, tablet, and mobile are intentional compositions, not a shrinking desktop canvas. The critical event, transcript, citation, comparison, and search tasks remain possible at 390, 820, and 1440 pixels.
5. Light, dark, English, and Chinese states are specified where the host product supports them. No untranslated internal slug or research-state vocabulary reaches the glance tier.
6. Initial shell interaction is immediate; long documents, search results, slide renders, and AI views progressively stream or virtualize without locking the Terminal.
7. Keyboard navigation, focus visibility, semantic landmarks, screen-reader labels, reduced motion, contrast, zoom, and touch targets meet the accessibility rubric in section 5.
8. Empty, partial, stale, corrected, blocked-rights, and provider-down states are designed as first-class research states. No generic spinner survives a terminal state.
9. Visual QA must compare committed reference compositions with real-data renders at the required breakpoints before the UI PR can merge.
10. The experience must score at least 85/100 on the premium QA rubric, with no load-bearing category below 7/10.
11. Premium hierarchy, restrained explanatory motion, perceived performance, and end-to-end evidence traceability are release criteria, not post-launch polish.

---

## 1. Executive ruling

The suite should become a core Mastermind feature. The right product is not a literal competitor clone. It is a shared evidence system that makes every existing Mastermind surface smarter.

The competitors contribute different pieces:

| System | What it really contributes | What Mastermind should take | What Mastermind should reject |
|---|---|---|---|
| Quartr | Company identity → event → content lifecycle; source addressing; search; Timeline; Topics; Mentioned By; slides; correction operations | The evidence spine and premium IR workflow | Global/live parity, a desktop clone, and Pro-seat ingestion |
| EarningsCall.ai | Low-cost transcript pipeline, full-text search, many narrative views, historical/peer chat, programmatic SEO | Transcript/search ergonomics and one-pass structured extraction | One prompt per tab, uncited synthesis, weak entitlement patterns, copied corpus |
| Jodie | Residual co-movement groups, lifecycle/lineage, filing relationships, market anomaly × structural relationship join | Theme discovery, relationship receipts, dislocation/context joins | Opaque score cloning or directional authority |
| Struct | Structured fact packet → well-packaged article → ticker CTA → subscription funnel | Digest-first public content compiler and acquisition loop | Launch-volume article spam and unsupported prose |
| EquityDesk | A large historical structured earnings-analysis seed | Migration, schema calibration, regression corpus | Expiring trial/RLS as an operating source |

The core architecture is:

```text
first-party and licensed sources
        ↓
company identity + event lifecycle
        ↓
immutable documents + stable source spans
        ↓
deterministic facts + one structured extraction
        ↓
cited company-event digest + correction lineage
        ↓
┌───────────────┬──────────────┬──────────────┬──────────────┐
│ Stage cohorts │ Terminal IR  │ Neural Web   │ Canonical    │
│ and QoQ       │ and dossier  │ / Brain      │ story        │
└───────────────┴──────────────┴──────────────┴──────┬───────┘
                                                     ↓
                                         SEO + X + alerts + short form
```

This system is strategically attractive because Mastermind already owns the downstream context that the competitors lack: market state, sector and theme structure, per-ticker dossiers, technicals, alternative data, Signal Bus governance, Prophet research infrastructure, Research Vault, Brain, and a multi-account publishing operation. The moat is not “we summarize calls.” The moat is that a source-cited change in management language can be joined, at the moment it matters, to price dislocation, theme formation, peer propagation, positioning, and the user's current research context.

Jodie's own published evidence is the reason for the context-only firewall: confirmed-group persistence was 52%, forming-group persistence about 40%, annual-report text peers 42.9% versus a 30% base rate, and filing-linked read-through +0.046 with a reported confidence interval of [.017, .075]. Its methodology also says direction was effectively a coin flip and the predictive trading edge did not survive. The system may improve what Mastermind notices and investigates; those figures do not license automatic capital deployment.

### 1.1 Difficulty verdict

| Target | Difficulty | Practical Mastermind estimate | Decision |
|---|---:|---:|---|
| EarningsCall.ai feature parity on the existing corpus | 4/10 | Bounded adapter, retrieval, and presentation lanes | Absorb into the spine |
| Struct-like article and SEO compiler | 4/10 | A derivative once the canonical digest exists | Build from the same event object |
| Jodie residual themes and lineage | 6/10 | Calibration-heavy quant lane with point-in-time evaluation | Build independently |
| High-precision filing relationship graph | 8/10 | Controlled identity, evidence, expiry, and review lanes | Build in controlled scope |
| Quartr-like cited search, event digests, Timeline, Topics | 7/10 | Several dependent product lanes on one shared evidence plane | Build incrementally |
| Quartr slide search, Key Slides, History Mode | 8/10 | Multimodal extension after the text spine is reliable | Build after text spine |
| Complete 2,000-name U.S./Canada operating service | 8/10 | Scale the already-shipped corpus, Stage, R2, Terminal, and agentic build system | Core production target |
| Quartr-scale global/live parity | 10/10 | A different coverage and SLA objective, not the planning ruler for this build | Explicitly out of scope |

### 1.2 Commercial ruling

Do not launch another $29 standalone subscription. Put the capability inside Mastermind's existing conversion and retention ladder:

- public Event Briefs and ticker pages acquire search and social traffic;
- registered users receive raw transcript access, a bounded digest, and watchlist entry points;
- paid users receive history, search, comparisons, Timeline, Topics, Mentioned By, source-grounded chat, and theme/peer joins;
- the highest entitlement receives broad exports, alerts, advanced narrative history, and later slide-history tooling if rights permit.

Jodie's inspected pricing was $29 monthly or $290 annually, not $29 per month billed annually. That price demonstrates a viable self-serve category; it does not require Mastermind to fragment its own product. The suite should raise Mastermind conversion, usage frequency, retention, and content supply while sharing one data plane.

### 1.3 What frontend/code inspection established

The public code confirms product shape, not private engine weights.

- **Jodie:** public bundles showed Next.js 16.2.6, a React 19.3 canary, Turbopack/App Router, nginx, same-origin APIs, bearer auth, and route families for themes, read-throughs, ticker dossiers, filing assessments, exposures, feeds, watchlists, alerts, billing, and TradingView relay. Cache horizons and request patterns were visible. Backend factor construction, graph thresholds, database, prompts, and orchestration were not.
- **Struct:** a Vercel-hosted Next.js/React Server Components publication with mostly server-rendered/prerendered pages. One sampled article shipped about 47 KB HTML and roughly 718 KB framework/font/CSS/JS assets, with only about 21 KB of custom client logic. Its bundle points to Jodie product/API and ticker-logo hosts. The publication frontend is easy; the digest/correction system behind it is the meaningful work.
- **EarningsCall.ai:** a conventional Vercel Next.js App Router application using server rendering and client streaming, Clerk, Stripe, utility CSS/Ant Design, Hotjar, and Google Analytics. Public engineering disclosure identified Lambda polling, a Next.js cron/webhook, Neon Postgres/Prisma, Vercel Blob, and ParadeDB full-text search. No proprietary quantitative engine was exposed because the product is chiefly source normalization plus prompt-defined analyses.
- **Quartr:** the public marketing/company estate is Next.js/Vercel with Storyblok. Public source maps for the Pro client exposed React, TanStack React Start/Router/Query, Vite/Rolldown, typed Elysia clients, OIDC-style auth, Sentry, Amplitude, feature flags, asset/user/watchlist/chat/AI-workflow routes, polling and caching behavior, and desktop-wrapper code. They did not expose ingestion, rights, search weights, embeddings, Topics/slide thresholds, prompts, human QC, or correction operations.

This is why literal frontend parity is the straightforward part, while trustworthy evidence, corrections, and operating automation are the real work. No public repository or private backend source was obtained, and none is required for the independent Mastermind implementation.

### 1.4 Where Mastermind should surpass the originals

| Original limitation | Mastermind upgrade |
|---|---|
| Jodie detects structure but does not establish direction | Preserve nondirectional context, add explicit null/stability diagnostics, and test only incremental Prophet value in a separate point-in-time gauntlet |
| Jodie relationships and scores are product-specific | Stable source-span receipts, edge expiry/supersession, typed relation confidence, and direct use across ticker, theme, Brain, Stage, and research |
| Struct can publish polished but numerically/attribution-fragile prose | Deterministic facts, approved claim set, sentence-level citations, correction replay, and A/B/C promotion instead of volume |
| EarningsCall.ai generates many prompt-shaped views | One structured extraction and digest creates every view consistently and cheaply |
| Lightweight transcript products conflate ticker and issuer | Legal issuer, security, listing, event, and source-version identities remain distinct |
| Quartr is broad but separated from the user's live market system | Join primary-source narrative to Mastermind price, sector, theme, flow, technical, dossier, and user research context |
| Competitor AI often appears as a page-level answer | Evidence rail, exact span, source version, “as known at” timestamp, and reusable cited Brain tools |
| Competitor products optimize their own funnel | One event object improves product value, Neural Web context, public SEO, X accounts, alerts, and short form while preserving one truth |
| Vendor correction and rights operations are mostly invisible | First-class completeness, raw/edited/corrected, blocked-rights, last-good, and derivative invalidation states |
| Research terminals often feel like dense document inventories | Purpose-built Mastermind Research OS with a premium event-first workflow and source beside claim |

---

## 2. Active repair baseline: finish before extending

The program begins from two real repair lanes. Neither should be rebuilt inside later phases.

### 2.1 Stage Analysis earnings recovery

**Status at memo cut:** shipped and live through Macro [#4181](https://github.com/chriswong6031-creator/macro/pull/4181), with mobile filter containment shipped through [#4187](https://github.com/chriswong6031-creator/macro/pull/4187). The corrected generation preserves reviewed semantic counts, issuer-safe period comparison, explicit provenance, and `ready`/manifest-valid health. Stage now serves the repaired history instead of the old terminal “Warming up” state.

The old state was not “still processing.” It was a fail-open contract failure:

- the dedicated Stage builder expected `data/stage_analysis/backfill/earnings_calls.parquet`, which did not exist;
- the nightly accepted and rendered empty earnings artifacts;
- the expected live R2 score object was absent;
- useful committed and local history existed elsewhere, but the reader had no ordered fallback;
- the UI translated that data-plane failure into “Warming up.”

The reviewed corrected generation is:

| Artifact | Shipped reviewed state |
|---|---:|
| Source EquityDesk snapshot | 51,156 rows |
| Accepted canonical archive | 50,982 rows |
| Import-superseded source revisions | 174 rows in one source conflict/retry group |
| Document tickers/listings | 3,529 |
| Exact exchange-qualified issuer keys | 3,496 |
| Latest listing score view | 3,529 rows |
| Valid-fiscal source rows | 50,965 |
| Canonical issuer-period rows | 50,689 |
| Same-issuer-period superseded rows | 276 |
| Invalid/quarantined fiscal rows | 17 |
| Latest-adjacent-QoQ-eligible issuers | 2,759 |
| Latest-adjacent pairs with both calls scored | 2,611 |
| Latest call date | 2026-07-31 |
| Health | `ready`; transport manifest valid |
| Transport generation | `59c682fe506d9e3cc78ff0e6` — published through the repaired R2/manifest path |
| Source schema-version lineage | 50,981 rows populated |
| Analysis model lineage | 50,883 rows populated |
| Prompt-version lineage | 50,883 rows populated |
| Industry region grid | USA, China, HK, Canada, Other |
| Authority | display/context only |

The final four-cohort Season artifact reconciles to the same generation. “Scored adjacent QoQ” means the current call has a valid immediately prior fiscal-period comparison; raisers and decliners are the direction subsets emitted by the Stage scoring contract.

| Fiscal cohort | Calls | Scored adjacent QoQ | Raisers | Decliners |
|---|---:|---:|---:|---:|
| 2026Q3 | 924 | 660 | 193 | 110 |
| 2026Q2 | 2,449 | 2,160 | 402 | 685 |
| 2026Q1 | 2,945 | 2,556 | 415 | 682 |
| 2025Q4 | 2,957 | 2,623 | 609 | 465 |

The 174-row difference between 51,156 source rows and the accepted 50,982-row archive is now reconciled, not hand-waved. All 174 are older source revisions inside one dirty `AKSO.OL` FY2925-Q4/call-date conflict/retry group. They are not 174 distinct calls and are separate from the fiscal-period quarantine. Deterministic ordering now retains the maximum-`updated_at` April 30 record with `combined_score=19`; the broken unsorted keep-last path had retained the April 16 record with `combined_score=17`.

The review also found two broader construction defects:

- same ticker text can represent different issuers or exchanges and cannot be collapsed into one company;
- repeated calls inside the same nominal fiscal quarter were treated as distinct comparable quarters, which produced a false CLS quarter-over-quarter comparison.

The corrected identity interpretation is not “3,529 tickers collapsed to fewer companies, therefore rows were lost.” The source legitimately has 3,529 `document_ticker` listing/display keys and 3,496 exact exchange-qualified `company_ticker` issuer keys. Health reports both denominators. The UI may continue to display `document_ticker`; reconciliation and comparison group on the exact `company_ticker`/issuer key so, for example, `CLS CN` is never paired with `CLS SJ`.

The corrected repair implements the review requirements:

1. stable source-record ID as the first identity key where present;
2. deterministic duplicate reconciliation ordered by parsed `updated_at`, then `created_at`, then stable source ID/hash—not input order;
3. issuer-safe company/security identity including exchange/source issuer identifiers;
4. explicit handling of dirty symbol reuse and conflicting natural keys;
5. one selected comparable record per **latest validated distinct fiscal period**, with same-quarter duplicates/corrections reconciled before QoQ pairing;
6. a regression fixture for `AKSO.OL` proving the April 30 score-19 record wins;
7. a regression fixture for the false CLS same-quarter QoQ case;
8. count reconciliation that explains every source row as retained, superseded duplicate, invalid/quarantined, or identity conflict;
9. regenerated history, score, Stage, v3 manifest, and health artifacts with reconciled counts;
10. health status and manifest checks that refuse mixed/collapsed generations or unreconciled issuer-period state.

Invalid fiscal labels such as FY `2925` must be quarantined or explicitly fallback-labeled; they may not participate in ordered quarter comparison as if they were valid dates.

The final audited regeneration retains the provenance correction that replaces literal `nan` model labels with `equitydesk_model_unavailable`, restores source schema/model/prompt lineage, and quarantines all 17 fiscal anomalies before issuer-period reconciliation and QoQ construction. The generation validator returns `(True, None)`; immutable score/history keys are generation-addressed, and the repaired artifacts are published and live.

Final validation recorded for the shipped repair:

- focused earnings/Stage suite: 82 passed, 2 skipped;
- the two skips are only the absent optional EC calibration parquet;
- Python compile and `git diff --check`: passed;
- comparison audit: zero same-period, non-adjacent, or cross-exchange QoQ pairs;
- all five region grids populated truthfully;
- transport validator: `(True, None)`;
- health: `ready`, manifest valid.

Implemented files:

- `engine/earnings_qual.py`
- `engine/stage_analysis.py`
- `scripts/build_earnings_scores_from_history.py`
- `scripts/fetch_earnings_scores.py`
- `scripts/publish_earnings_r2.py`
- `scripts/build_stage_analysis_page.py`
- `templates/stage_analysis.html.j2`
- `tests/test_earnings_seasons.py`
- `tests/test_build_earnings_scores_from_history.py`
- `.github/ci/legacy-jobs.yml`
- `.github/workflows/ci.yml`
- generated Stage and health artifacts under `data/stage_analysis/`, `site/stagedata/`, and `data/quality/`

The implemented source ladder is:

```text
data/earnings_calls/history.parquet        canonical R2 history
        ↓ absent
legacy full history
        ↓ absent
committed overview fallback
        ↓ absent
committed score seed
```

The shipped implementation makes every output carry source tier, source rows, source tickers, and latest date; enforces the identity/reconciliation gates above; and adds ready/degraded/stale/empty health states. The UI change that replaces terminal “Warming up” with an explicit unavailable/degraded state remains valid.

**Do not regress:** the future Company Event Spine may replace the contents behind these views, but it must preserve their health, last-good, source-tier, and history-versus-latest semantics.

### 2.2 Terminal transcript archive recovery

**Status at memo refresh:** shipped and live through Terminal [#295](https://github.com/chriswong6031-creator/mastermind-terminal/pull/295), with evidence-bound speaker-role inference and corpus repair shipped through [#299](https://github.com/chriswong6031-creator/mastermind-terminal/pull/299), and revision/date publication shipped through [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303).

The repaired Terminal archive now exposes **25,438 transcript bodies across 3,288 symbols**. The original defect was a missing browser-facing index plus a Macro-root mismatch, which made existing bodies undiscoverable and allowed later generation to erase valid transcript links. The shipped recovery fixes discovery rather than pretending the corpus must be recollected.

The live `mastermind.tx-index/v1` generation stamped `2026-08-01T14:41:55Z` now reports the same 25,438 records for bodies, revision hashes, and dates, across the same 3,288 symbols. That one-to-one coverage is the correction-safe forward-ingestion proof: Macro can distinguish a new or corrected body without inferring change from ticker/quarter identity alone.

Implemented files in `charting-app`:

- `ingest/build_transcript_index.py`
- `ingest/collect_transcripts.py`
- `ingest/gen_fund_us.py`
- `ops/bootstrap_nightly_fund.sh`
- `ops/launchd/com.mastermind.fund.plist`
- `ops/nightly_fund.sh`
- `terminal/components/TerminalShell.tsx`
- `terminal/components/workspaces/AnalysisWorkspace.tsx`
- `terminal/lib/transcripts.ts`
- `terminal/lib/fund.ts`
- `terminal/components/fin/TranscriptsPage.tsx`
- `terminal/components/fin/MegaPane.tsx`
- `terminal/components/fin/TranscriptDrawer.tsx`
- `terminal/app/fin.css`
- `tests/test_transcript_index.py`
- `terminal/lib/__tests__/transcripts.test.ts`

The repair adds:

- `mastermind.tx-index/v1` at `terminal/public/data/tx/index.json`;
- `mastermind.tx-symbol-index/v1` at `terminal/public/data/tx/<SYM>/index.json`;
- an atomic legacy `{SYM: [YYYYQn]}` map for the fund emitter during migration;
- per-ticker direct transcript discovery independent of statement coverage;
- a first-class bilingual **Transcripts** tab in the Terminal finance pane;
- explicit populated, loading, true-empty, and source-unavailable states;
- strict client and body-contract validation without caching a transient 404 as permanent absence;
- canonical `?tx=` transcript deep links across Terminal and Analysis workspaces;
- a premium reader with metadata, search, text filters, speaker and prepared/Q&A navigation, hit highlighting, source links, copy controls, responsive sizing, focus trap, and EN/ZH provenance;
- weekly transcript delta collection plus an every-run self-healing index rebuild from production bodies;
- no-write corpus validation, exact append-only body/index pair checks, and commit-marker-last index publication;
- retry-safe body-only synchronization with locking and a LaunchAgent bootstrap/check path;
- fail-closed floors and 85% collapse guards before any fund overwrite or deployment.

Engineering verification completed for the shipped Terminal repair:

- production VPS no-write corpus scan: 22,789 bodies, 3,041 symbols, exit 0;
- Python targeted suite: 6 passed;
- transcript Vitest: 8 passed;
- full Vitest: 89 files, 1,696 passed, 4 todo;
- Next production build and TypeScript: passed;
- new transcript ESLint scope: zero findings;
- Python compile, shell syntax, plist lint, bootstrap `--check`, and `git diff --check`: passed.

Final commissioner-owned browser QA also completed locally after finding and fixing a deep-link URL race:

- a fresh `?tx=` deep link opens the expected 52-segment transcript drawer;
- first Escape closes the drawer while retaining the Company/finance pane;
- second Escape closes the pane and cleans the URL;
- 1440, 820, and 390 pixel compositions have no overflow;
- EN/ZH, populated, true-empty, archive, and reader states were captured;
- Terminal is intentionally dark-only under its current product contract, so this repair makes no false light-mode claim.

The commit/PR/merge/deploy/live chain is complete. Temporary transcript fixtures and QA captures are not part of the repair's canonical production corpus; approved verification images remain under `docs/verification/company-event-transcripts-20260801/` in the Terminal repository.

**Do not regress:** the Company Event Spine should enrich these raw bodies and indexes. It should not bootstrap a second transcript archive, route transcript availability through financial-statement rows again, or weaken the collapse gate.

### 2.3 EquityDesk delta: snapshot captured, dependency ended

The authorized 24-hour EquityDesk guest session was used for a frozen delta audit with cutoff **2026-08-01 08:08:38 UTC**:

- old local archive: 50,053 rows through 2026-07-17;
- live snapshot: 51,156 rows through 2026-07-31;
- 1,103 genuine additions;
- zero updates to prior rows;
- 802 newly dated calls after July 17;
- 301 historical vendor backfills;
- unchanged 48-field schema;
- every new row identified Gemini 2.5 Pro, unified analysis schema `v1.3`, prompt `system_prompt_for_schema_2025-09-10`;
- no new row had a non-null transcript `file_path`.

The vendor table remains mechanically cursorable, but its temporary entitlement, RLS, schema control, missing transcript bodies, and uncertain downstream rights make it unsuitable for production. Preserve the frozen raw pages, manifest, and importer-compatible snapshot for calibration and regression. Do not schedule another EquityDesk scrape or make future freshness depend on guest access.

---

## 3. Product boundary and ownership

The suite has one backend owner and several consumers.

| Layer | Source of truth | Responsibility |
|---|---|---|
| Identity, events, documents, spans, transcripts, facts, digests, relationships, themes, health | Macro Dashboard / R2 | Ingest, normalize, correct, evaluate, publish contracts |
| Stage Analysis | Macro Dashboard static product | Cross-sectional earnings cohorts, season, QoQ, industries, health |
| Terminal | `charting-app` | Per-ticker research UX; never owns canonical extraction |
| Neural Web / Brain | Macro Dashboard runtime | Retrieve bounded context and exact evidence on demand |
| Prophet and signal research | Macro Dashboard research plane | Point-in-time feature accrual and promotion bakeoffs only |
| Research Vault | Existing separate system | User/curated research corpus; link to event spine, do not replace it |
| Public Event Briefs / ticker modules | Macro Dashboard public site | SEO acquisition from approved canonical stories |
| X Growth and short form | Existing marketing system | Persona-specific derivatives from approved fact packets |

### 3.1 Product surfaces

The user-facing product should be called **Company Intelligence** or **IR Intelligence**, not Jodie, Struct, Quartr, EarningsCall, or EquityDesk.

The premium suite consists of:

1. **Event Archive:** calls, releases, filings, decks, investor days, and corrections by company.
2. **Source Search:** lexical first, semantic rerank second, with paragraph/page/timestamp receipts.
3. **Event Digest:** what changed, guidance, segments, risks, capital allocation, Q&A pressure, and market reaction.
4. **Narrative Timeline:** phrase prevalence, commitments, discontinued language, and topic progression.
5. **Peer Topics:** source-grounded clusters of comparable Q&A exchanges.
6. **Mentioned By:** high-precision issuer and entity references across company sources.
7. **Relationships and Read-through:** customer, supplier, competitor, product, and business-similarity edges with exact receipts.
8. **Theme and Dislocation:** residual group state joined to event evidence and price/flow context.
9. **Slides:** page search, Key Slides, and historical slide families in a later phase.
10. **Ask Mastermind:** cited event and cross-quarter questions through the existing Brain.
11. **Calendar and Alerts:** confirmed/estimated event schedule, saved source/topic searches, watchlist event changes, and correction alerts through existing account/watchlist infrastructure.

---

## 4. Unified contract spine

The competitors all become simpler when their records are normalized into the same identifiers. The spine should use immutable records plus versioned derived views.

### 4.1 Required contracts

| Contract | Purpose | Required invariants |
|---|---|---|
| `company_identity.v1` | Stable issuer/security identity | CIK/LEI/exchange/ticker/share-class aliases; point-in-time validity; no ticker as primary key |
| `company_event.v1` | One economic/company event | Stable `event_id`; scheduled/started/completed/corrected/cancelled lifecycle; availability timestamps |
| `source_document.v1` | One versioned source object | Hash, source class, authority, rights, fetched/published/available times, supersession |
| `source_span.v1` | Stable evidence address | Document version plus page/paragraph/line/segment/time bounds and exact checksum |
| `transcript.v2` | Raw and edited call structure | Speakers, roles, prepared/Q&A chapters, words/segments/timestamps/confidence, correction lineage |
| `slide_page.v1` | One presentation page | Render URI, extracted text, OCR state, table/chart/image regions, page citation |
| `slide_family.v1` | Cross-event slide lineage | Match evidence, confidence, split/merge state, manual override |
| `event_fact.v1` | Deterministic or reconciled fact | Value, unit, period, basis, source spans, method, conflict state |
| `event_claim.v1` | Source-grounded narrative claim | Subject/predicate/object or typed text, evidence spans, polarity, uncertainty, extractor version |
| `guidance_item.v1` | Management guidance | Metric, range, currency/unit, period, status, prior comparable, evidence |
| `mention_edge.v1` | One issuer/entity mention | Source and target identity, relation context, source span, confidence |
| `relationship_edge.v1` | Structural business relationship | Direction, relation type, effective period, receipt set, expiry/supersession |
| `topic_pulse.v1` | Peer/company topic state | Cluster identity, members, exchange spans, lexical measures, lineage, coherence |
| `theme_state.v1` | Residual market group lifecycle | Membership, residual evidence, breadth, lineage, state, null-calibrated surprise |
| `company_event_digest.v1` | Canonical machine-readable event synthesis | Facts, changes, risks, Q&A, guidance, peers, completeness, citations, no prose authority |
| `company_intelligence_context.v1` | Compact Neural Web/Terminal packet | Bounded digest, freshness, receipts, context-tier authority, fetch handles |
| `canonical_story.v1` | One approved distribution object | Claim set, sections, citations, tier, correction state, derivative IDs, CTA attribution |
| `corporate_intelligence_health.v1` | Coverage and operating truth | Counts, age, completeness, latency, corrections, source rights, last-good, status |

### 4.2 Identity rules

1. `company_id` identifies the legal issuer or reporting entity.
2. `security_id` identifies a listed security or share class.
3. `ticker` is an alias with `valid_from` and `valid_to`, never a durable key.
4. Dual classes such as GOOG/GOOGL share an issuer but remain distinct securities.
5. Mergers, spinoffs, ADRs, domestication, delistings, and ticker changes preserve lineage.
6. Events attach to the reporting entity; market reactions attach to one or more securities.
7. In the EquityDesk migration, `document_ticker` remains the display/listing key while exchange-qualified `company_ticker` or a mapped `issuer_key` governs company history and comparisons.
8. Health exposes listing/display coverage and issuer coverage separately; their expected difference is not labeled missing data.

This rule prevents the duplicate-company and wrong-history failures observed in lightweight transcript products.

### 4.3 Event lifecycle

```text
discovered
   ↓
scheduled ──→ rescheduled
   ↓
started
   ↓
completed_partial
   ↓       ↘
complete   corrected/superseded
   ↓
derived_ready
   ↓
distributed

cancelled can branch from scheduled/rescheduled.
blocked_rights and source_missing are coverage states, not event states.
```

Each transition records:

- `observed_at` — when Mastermind saw the transition;
- `source_available_at` — when the underlying source became available;
- `effective_at` — when the issuer says it occurred;
- `processor_version`;
- `source_receipt_ids`;
- prior state and transition reason.

This is the point-in-time firewall for backtests and Prophet experiments.

### 4.4 Core event envelope

```json
{
  "schema": "company_event.v1",
  "event_id": "evt_cik0000320193_2026q3_results",
  "company_id": "cik:0000320193",
  "security_ids": ["nasdaq:AAPL"],
  "event_type": "earnings_results",
  "fiscal_period": {"year": 2026, "quarter": 3, "calendar_end": "2026-06-27"},
  "state": "complete",
  "scheduled_at": "2026-07-30T21:00:00Z",
  "source_available_at": "2026-07-30T20:32:14Z",
  "observed_at": "2026-07-30T20:33:02Z",
  "document_ids": ["doc_release_hash", "doc_10q_hash", "doc_call_edited_hash"],
  "supersedes": null,
  "point_in_time": true
}
```

### 4.5 Source span

```json
{
  "schema": "source_span.v1",
  "span_id": "span_doc_call_edited_hash_qa_0042",
  "document_id": "doc_call_edited_hash",
  "document_version": 2,
  "locator": {
    "kind": "transcript_segment",
    "chapter": "qa",
    "speaker": "chief_financial_officer",
    "segment_start": 1942,
    "segment_end": 1955,
    "time_start_ms": 2834012,
    "time_end_ms": 2867731
  },
  "text_sha256": "...",
  "display_excerpt": "...",
  "rights_profile": "rp_internal_quote_public_short_v1"
}
```

The span is the fundamental receipt. A citation in an article, Brain answer, Topic cluster, relationship edge, or guidance comparison must resolve through it.

### 4.6 Digest contract

`company_event_digest.v1` should contain structured content, not merely one long summary:

```json
{
  "schema": "company_event_digest.v1",
  "event_id": "evt_...",
  "digest_version": 4,
  "available_at": "2026-07-30T22:12:09Z",
  "source_completeness": {
    "release": "present",
    "filing": "present",
    "transcript": "edited",
    "slides": "present",
    "consensus": "unlicensed_absent"
  },
  "facts": [],
  "guidance": [],
  "segment_changes": [],
  "capital_allocation": [],
  "risks": [],
  "management_commitments": [],
  "qa_exchanges": [],
  "narrative_deltas": [],
  "issuer_mentions": [],
  "relationship_updates": [],
  "market_reaction": {},
  "theme_context": [],
  "claims": [],
  "citation_coverage": 1.0,
  "authority": "context_only",
  "extractor": {"name": "event_digest", "version": "1.0.0"},
  "quality": {"status": "ready", "warnings": []}
}
```

### 4.7 Compact consumer contract

Neural Web and the Terminal should not receive every raw document by default. They receive `company_intelligence_context.v1`:

- latest event identity and availability;
- five to ten most material facts and deltas;
- guidance and risk changes;
- Q&A pressure topics;
- relationship/theme context;
- explicit missing-source state;
- source-span handles;
- tools for deeper retrieval;
- `authority: context_only` and freshness.

Raw source access is on demand through governed retrieval tools.

### 4.8 Canonical story contract

`canonical_story.v1` is a distribution manifest, not a separate truth database. It stores:

- `story_id`, event IDs, company IDs, and public slug;
- promotion tier A/B/C and reasons;
- approved claims by `claim_id` and `span_id`;
- deterministic tables/chart specs;
- headline, dek, sections, conclusion, and uncertainty disclosure;
- SEO metadata and structured-data payload;
- correction status and derivative invalidation list;
- X, short-form, alert, email, and ticker-module derivative IDs;
- acquisition attribution parameters;
- writer, verifier, prompt, model, token, and cost ledger.

The story may change voice. Its claim set may not silently change.

---

## 5. Experience architecture: one Mastermind Research OS

The experience should feel like an instrument that happens to contain enormous evidence, not a document warehouse with AI buttons.

### 5.1 Product principles

1. **Event before file.** Users think “What changed this quarter?” before they think “Open the 10-Q.” The event is the primary object; documents are its evidence.
2. **Answer before inventory.** The first viewport states the change, materiality, source completeness, and next action. The archive remains one click away.
3. **Receipts are spatially close.** Citations open in context beside the claim whenever viewport allows, not in a detached bibliography.
4. **One timeline, many lenses.** Calls, filings, decks, guidance, management commitments, peer mentions, theme state, price reaction, and corrections align on one event chronology.
5. **Progressive disclosure.** Glance → inspect → compare → source. No screen dumps the full taxonomy at once.
6. **Research continuity.** A user can move from ticker event to prior quarter, peer topic, linked company, theme, chart, and Brain without losing the current evidence trail.
7. **State is honest.** Missing, stale, partial, raw, edited, corrected, and licensed-unavailable content looks different and says why.
8. **AI is a transparent operator.** Generated analysis identifies its source set, availability cutoff, citation coverage, and version. It never masquerades as source text.
9. **Mastermind-native, not vendor collage.** The product uses the Terminal's existing shell, navigation, typography, language system, chart grammar, entitlements, and dossier identity.
10. **Motion explains system behavior.** Use it for selection, source reveal, timeline change, and pane continuity; never as financial-news decoration.

### 5.2 Primary interaction model

The Terminal Company Intelligence workspace should have one stable top-level model:

```text
Ticker identity + freshness + event selector
        │
        ├── Brief       what changed and why it matters
        ├── Transcript  chapters, search, highlights, source drawer
        ├── Timeline    claims, commitments, language, guidance across events
        ├── Peers       Topics, Mentioned By, relationships, read-through
        ├── Slides      page search, Key Slides, History Mode (later phase)
        └── Sources     complete event document manifest and coverage state
```

This can live inside the current finance/research MegaPane, but it should compose as a coherent workspace rather than adding a long sequence of undifferentiated pills. The already implemented Transcripts tab remains the raw archive entry. Later phases may promote Company Intelligence into a nested research workspace only after the design spec proves the navigation at every breakpoint.

The evidence interaction is consistent everywhere:

```text
select claim
   → source rail opens at exact page/paragraph/timestamp
   → related facts and conflicts remain visible
   → “compare” pins the claim across selected events/peers
   → “ask” sends only the pinned evidence set to Brain
```

### 5.3 Stage interaction model

Stage remains the cross-sectional lens, not a second ticker dossier:

- **Calls table:** rank/filter the latest normalized event scores and source state.
- **By season:** see period distribution and cohort shape.
- **Quarter over quarter:** compare eligible names and the exact changed dimensions.
- **Industries:** see breadth and cohort movement with population denominators.
- selecting a company opens the Terminal Company Intelligence event, not another modal summary;
- selecting a cell explains calculation, denominator, date, source tier, and coverage.

### 5.4 Glance-tier event brief

The first viewport answers five questions:

1. What happened?
2. What changed versus the comparable period and management's prior position?
3. What did the market do after the information became available?
4. Which peers, relationships, or themes make the event broader than one ticker?
5. What source is missing or uncertain?

Recommended composition:

- one plain-language event stance, explicitly context-tier;
- three to five material changes with direction and unit;
- guidance delta;
- Q&A pressure/topic strip;
- market-reaction/dislocation strip;
- source completeness and “as known at” stamp;
- one obvious route to full transcript/source.

Do not put opaque aggregate scores, raw JSON keys, model names, long taxonomies, or unbounded prose in the glance tier.

### 5.5 Responsive acceptance

Required visual fixtures use representative real-data states: a mega-cap with all sources, a small company with only a filing/release, a corrected transcript, a dual-class issuer, an empty ticker, a long Chinese company name, and an event with twelve-plus peer/mention edges.

| Width | Required composition |
|---:|---|
| 1440 px | Event brief and evidence rail can coexist; timeline/compare supports two-pane research; no unused decorative void |
| 820 px | Evidence opens as a resizable or overlaid detail plane; primary context is preserved; tables retain labels and horizontal intent |
| 390 px | One-column task flow; sticky event/source affordances; transcript search and citation jump work; comparison becomes sequential cards; no clipped tabs |

Acceptance includes:

- 200% browser zoom without loss of content or action;
- dynamic type and long EN/ZH copy without overlap;
- minimum 44×44 CSS-pixel touch targets for primary mobile controls;
- safe-area handling and no viewport-height traps;
- no horizontal page scroll except inside an explicitly labeled data table/compare canvas;
- selected event, scroll/citation position, and filters survive pane transitions when reasonable.

### 5.6 Performance acceptance

Planning budgets for production p75 on a normal broadband connection and contemporary mid-range device:

| Interaction | Budget |
|---|---:|
| Existing Terminal shell to interactive Company Intelligence tab | ≤1.5 s when compact ticker payload is cached; ≤2.5 s cold |
| Event selector or tab switch with prefetched metadata | ≤150 ms visible response |
| First lexical search result over indexed corpus | ≤500 ms server response target; results progressively render |
| Open cited transcript span already cached | ≤200 ms |
| Open uncached document/page | visible skeleton immediately; first useful content ≤1.5 s target |
| Long transcript scroll | 60 fps target with windowing; no full-DOM multi-megabyte render |
| Layout shift | CLS ≤0.1 target |

The compact ticker payload must remain bounded. Raw transcript bodies, slide images, large search result sets, and peer corpora load on demand. The Terminal never invokes a long-running generation job synchronously just to open the core page; existing digests render immediately and new generation streams behind an explicit state.

### 5.7 Accessibility acceptance

- WCAG 2.2 AA contrast for text, controls, charts, focus indicators, and status chips;
- complete keyboard path through event selection, tabs, search, result list, source rail, citation jumps, compare pins, and close actions;
- focus moves predictably when drawers/panes open and returns to the invoker on close;
- semantic headings, lists, tables, buttons, dialogs, live regions, and landmarks;
- no meaning encoded by red/green, motion, or position alone;
- chart and heatmap states have textual equivalents and denominators;
- transcript speaker, role, timestamp, and prepared/Q&A boundaries are screen-reader legible;
- reduced-motion mode preserves state transitions without animation dependence;
- language attributes and EN/ZH labels are correct;
- generated text and source text are distinguishable programmatically and visually.

### 5.8 Premium visual QA rubric

Score each category 0–10 using real-data captures. The UI cannot merge below 85/100, and no load-bearing category may score below 7.

| Category | A 9–10 looks like | Automatic failure examples |
|---|---|---|
| Product coherence | Feels native to one Mastermind OS; consistent interaction grammar | Vendor-like mini-apps or conflicting navigation models |
| Research hierarchy | Change, evidence, uncertainty, and next action are obvious in seconds | First viewport is filters, cards, or prose inventory |
| Information density | High signal per pixel with controlled disclosure | Empty luxury spacing or dashboard-card confetti |
| Trust and provenance | Source state and receipts are legible without clutter | AI prose visually indistinguishable from source; hidden missing data |
| Interaction continuity | Event → source → compare → Brain retains context | Modal dead ends, lost selection, back-button surprises |
| Visual identity | Deliberate Mastermind typography, rhythm, color, and signature evidence treatment | Literal Quartr/Jodie clone, generic Tailwind/SaaS template |
| Responsive composition | Each breakpoint is deliberately recomposed | Desktop squeezed into mobile, clipped tabs, overflow |
| Accessibility | Full keyboard/AT flow and resilient content | Keyboard trap, invisible focus, color-only state |
| Performance feel | Immediate shell, stable layout, progressive heavy content | Blank wait, janky transcript, multi-second dead click |
| State craft | Empty/partial/stale/corrected/down states teach and recover | Endless spinner, “warming up,” or silent disappearance |

Visual proof required in each user-facing PR:

- committed reference crops or exact design spec;
- real-data screenshots at 1440, 820, and 390 pixels;
- every supported theme mode and EN/ZH for any affected shared mode; Terminal is currently dark-only by product contract;
- populated, empty, partial/stale, and corrected states as applicable;
- keyboard and focus-path recording or test evidence;
- before/after performance trace for any heavy view;
- a filled rubric with reviewer scores and named defects.

### 5.9 Experience architecture lane

Before the first post-repair feature UI is built, a designer-owned lane must deliver:

- user journeys for earnings review, source search, cross-quarter comparison, peer read-through, and cited Brain inquiry;
- information architecture and navigation decision;
- exact desktop/tablet/mobile compositions;
- evidence-rail interaction and citation grammar;
- component/state inventory;
- EN/ZH copy budgets and empty-state language;
- prototype using representative real payloads;
- premium QA baseline and committed references under the charting repository's approved mockup/reference location;
- a build contract whose acceptance gates are inline for implementation agents.

The lane is not complete with a mood board. It must settle interaction, content hierarchy, responsive composition, and state behavior sufficiently that implementation does not improvise the product.

---

## 6. Source acquisition and never-backfill operations

The permanent fix for backfill is an event state machine with independent discovery, acquisition, parsing, extraction, correction, and publication cursors.

### 6.1 Source priority

| Source class | Preferred source | Use | Rights posture |
|---|---|---|---|
| SEC filings and exhibits | SEC submissions, filing index, Inline XBRL/company facts | Identity, filings, deterministic facts, exhibits | Build; honor SEC access policy and attribution |
| Earnings releases and decks | Issuer IR pages/CDNs, SEC 8-K exhibits | First-party release/deck evidence | Build with source-specific retention/public-display policy |
| Event schedule | Issuer IR, exchange/calendar provider, SEC evidence | Discovery and lifecycle | Reconcile multiple sources |
| Transcript bodies | Licensed transcript vendor and/or rights-cleared issuer source | Search, Q&A, cited analysis | Buy/partner where necessary; rights are load-bearing |
| Audio/live transcript | Licensed provider | Later live experience | Defer unless SLA and display rights justify it |
| Consensus estimates | Licensed estimates vendor | Surprise/guidance comparison | Buy; do not infer consensus from web snippets |
| Market data | Existing licensed/owned price and volume feeds | Reaction and dislocation | Reuse existing point-in-time plane |
| 13-F | SEC filings and existing normalization | Ownership/crowding context | Context only; lag explicit |
| Company relationships | First-party filings and issuer documents | Supplier/customer/competitor edges | Extract with exact receipts and expiry |

### 6.2 Event discovery loop

Run independent schedulers:

1. **Calendar watcher:** discovers scheduled calls/results and reschedules.
2. **SEC watcher:** follows submissions and filing-index changes, including amendments.
3. **Issuer watcher:** monitors known IR feeds/pages for release, deck, webcast, and transcript links.
4. **Transcript watcher:** polls the licensed provider around known events and at a slower orphan-recovery cadence.
5. **Correction watcher:** compares hashes and edited/raw version state for a configurable horizon.
6. **Coverage auditor:** finds events with expected-but-missing source classes and retries by policy.

Every watcher writes observations to the event lifecycle. It does not directly write a public digest.

### 6.3 Cursor model

Each adapter stores:

- inclusive last successful lower bound;
- frozen upper bound for the run;
- stable `(source_updated_at, source_id)` ordering;
- page/token cursor;
- request and response manifest;
- object hash and byte count;
- attempt count, response class, next retry;
- last known source schema;
- rights profile;
- provider availability and lag.

A completed run advances the cursor atomically. A partially failed run leaves the prior cursor and last-good artifacts intact. A periodic overlap window rechecks recent records for corrections; a slower reconciliation sweep catches late historical additions. That is how the system absorbs the 301 late historical additions seen in the EquityDesk delta without a special human backfill.

### 6.4 Ingestion idempotency

Use these natural identities before creating a new event:

- SEC: accession plus exhibit/document identity;
- provider transcript: provider call ID plus provider version;
- issuer artifact: normalized canonical URL plus hash and discovered event;
- earnings event: issuer, fiscal period, event type, and schedule lineage;
- source document: source origin plus content hash;
- derived digest: event ID plus ordered source-version set plus extractor version.

New source versions append. They do not mutate away old point-in-time states.

### 6.5 Event orchestration

```text
OBSERVE
  → RESOLVE IDENTITY
  → ATTACH/CREATE EVENT
  → FETCH IMMUTABLE SOURCE
  → PARSE + ADDRESS SPANS
  → DETERMINISTIC FACTS
  → STRUCTURED EXTRACTION
  → RECONCILE
  → DIGEST
  → QUALITY/PROMOTION
  → PUBLISH COMPACT CONTRACTS
  → FAN OUT
```

Every stage is separately retryable and content-addressed. A poison PDF, provider timeout, or LLM failure does not make the event disappear.

### 6.6 Source completeness rules

Completeness is event-type and latency aware. For a standard U.S. earnings event:

- release or 8-K exhibit: expected at/near results time;
- 10-Q/10-K: may arrive with or after the release;
- raw transcript: expected after call completion when licensed;
- edited transcript: may supersede raw later;
- deck: optional but common for configured issuers;
- audio: optional unless specifically licensed;
- consensus: optional only if the product explicitly shows it unavailable.

The digest may publish in `partial` state if its public tier permits it, but it must list missing sources and automatically rebuild as sources arrive.

### 6.7 Correction replay

When a source hash changes or a higher-authority version appears:

1. write a new `source_document` version;
2. preserve the prior version and point-in-time availability;
3. mark affected spans and claims superseded;
4. rebuild facts, extraction, digest, topic/relationship edges, and canonical story;
5. compare old and new claims;
6. invalidate cached Terminal/Brain payloads;
7. update or append a public correction note if a material published claim changed;
8. never delete historical research state needed for audit/backtest.

---

## 7. Analytical engines

The suite has several engines, but only one evidence layer. Their outputs remain typed so a research-priority ranking cannot accidentally become an investment signal.

### 7.1 Deterministic fact engine

Responsibilities:

- XBRL fact selection and period alignment;
- instant/duration distinction;
- fiscal/calendar mapping;
- unit and scale normalization;
- revenue, margin, EPS, cash flow, balance-sheet, share-count, and segment arithmetic;
- guidance range arithmetic;
- market reaction from point-in-time prices;
- mention counts and token denominators;
- source coverage and latency.

The model never calculates a number that the deterministic layer can calculate. If an extracted statement contains a number, the verifier must map it to an `event_fact` or mark it `quoted_management_number` with a source span and no independent verification.

### 7.2 One-pass structured extraction

The EarningsCall.ai pattern of separate prompts for Highlights, Summary, Guidance, Risks, Q&A, History, Sentiment, Strategic Updates, and topic pages is easy to build but wasteful and internally inconsistent. Mastermind should perform one structured event extraction that produces reusable fields.

Input packet:

- event and company identity;
- deterministic fact table and deltas;
- selected source spans from release, filing, transcript, and deck;
- prior comparable event digest and active management commitments;
- relevant peer/topic aliases;
- explicit source completeness and rights state.

Output:

- claim proposals with source-span IDs;
- guidance items;
- segment and geography deltas;
- demand, pricing, volume, capacity, backlog/RPO, cost, margin, capex, financing, buyback, dividend, workforce, regulation, and risk changes;
- management commitments and fulfillment state;
- analyst questions, management answers, evasion/uncertainty labels with evidence;
- issuer/product/entity mentions;
- candidate relationship updates;
- candidate narrative deltas versus prior comparable events;
- abstentions and unresolved conflicts.

The schema validator rejects unknown fields, missing evidence, impossible periods, unsupported entities, and uncited quotes before reconciliation.

### 7.3 Claim reconciliation and evidence weighting

Source authority is explicit and use-case specific. A reasonable default ordering is:

```text
filed audited/official document
  > filed exhibit / issuer release / issuer deck
  > edited official/licensed transcript
  > raw live transcript
  > licensed third-party normalized record
  > secondary report
```

This is not one universal truth order. For what management said at timestamp T, the audio/raw transcript may be the closest source; for reported GAAP revenue, the filed document wins. Reconciliation therefore uses typed rules, not a single source score.

Each claim receives:

- source authority by claim type;
- citation count and independence;
- deterministic agreement state;
- temporal relevance;
- extraction confidence;
- contradiction and supersession state;
- materiality basis;
- public-display permission.

A low-confidence claim is withheld or shown as disputed. The model may not “average” contradictory facts into a plausible sentence.

### 7.4 Narrative Timeline

Timeline measures should be simple and auditable before using embeddings:

- exact and normalized phrase mentions;
- mentions per 10,000 source tokens;
- number of document types containing the topic;
- prepared-remarks versus Q&A prevalence;
- number of distinct executives/analysts mentioning it;
- quarter-over-quarter and trailing-eight-quarter change;
- commitment first-seen, repeated, modified, fulfilled, missed, or dropped;
- source breadth across issuer and peers.

Semantic topic grouping can sit above this lexical ledger, but the user must be able to inspect the exchanges that created a topic.

### 7.5 Peer Topics

Pipeline:

1. split transcripts into prepared remarks and analyst/management Q&A exchanges;
2. retain speaker roles and stable spans;
3. embed the exchange, not arbitrary chunks;
4. cluster within an industry/theme/time window;
5. label clusters from representative evidence;
6. match clusters across periods for lineage;
7. compute breadth, frequency, acceleration, question pressure, and answer divergence;
8. expose every cluster member and source span.

Quality is measured by cluster coherence, retrieval usefulness, temporal stability, and analyst pairwise judgments. A fluent topic label does not validate a bad cluster.

### 7.6 Mentioned By

High precision matters more than recall. Entity resolution should use:

- issuer and security alias tables;
- product/brand aliases;
- context windows and relation verbs;
- exclusion patterns for ordinary words and ambiguous abbreviations;
- source-type rules;
- exact source span;
- issuer-level deduplication for dual share classes.

The initial public feature should include only high-confidence issuer mentions. Lower-confidence entities remain internal candidates for review or model retrieval.

### 7.7 Filing relationship graph

Relationship edge types:

- customer;
- supplier;
- competitor;
- distributor/channel;
- strategic partner;
- investor/owner where 13-F context applies;
- product/technology dependency;
- comparable business language;
- management-mentioned peer;
- shared narrative/topic exposure.

Each edge carries direction, evidence spans, first/last observed dates, source authority, active/expired/disputed status, confidence, and relation-specific attributes. Customer/supplier edges expire or weaken without recent evidence; competitor and business-similarity edges have different persistence rules. Similar language is never mislabeled as a contractual relationship.

### 7.8 Jodie-style residual theme discovery

This is an independent construction inspired by published methodology, not a reconstruction of private weights.

For stock `i` at time `t`:

```text
r(i,t) = alpha(i) + beta_shrunk(i,t) × r_equal_weight_market(t) + epsilon(i,t)
```

The discovery flow is:

1. compute point-in-time returns and a broad equal-weight proxy;
2. estimate rolling betas and shrink noisy estimates toward a robust cross-sectional target;
3. retain residual returns `epsilon`;
4. estimate a Ledoit-Wolf stabilized covariance/correlation matrix;
5. remove eigenstructure consistent with a Marchenko-Pastur noise band;
6. construct a graph of surviving meaningful relationships;
7. run seeded/reproducible Louvain community detection over a parameter grid;
8. assign group lineage against prior runs with explicit split, merge, expand, weaken, and dissolve rules;
9. store null simulations and stability diagnostics.

The implementation must pre-register or grid-evaluate:

- return frequency and lookback;
- missing-data and IPO rules;
- shrinkage target;
- negative-edge handling;
- eigenvalue/noise treatment;
- edge thresholds;
- Louvain resolution and seed stability;
- minimum group size;
- lineage overlap and split/merge thresholds;
- corporate actions and delistings.

#### Recoverable public heat formula

Jodie's public TradingView companion—not proof of the private backend—uses a 60-bar rolling beta to SPY and defines:

```text
shock   = current residual / rolling residual standard deviation

impulse = five-bar average residual × sqrt(5)
          / rolling residual standard deviation
```

With a peer basket:

```text
raw_heat = 0.45 × abs(shock)
         + 0.35 × abs(impulse)
         + 0.20 × propagation
```

Without a basket, the two surviving weights are renormalized:

```text
raw_heat = 0.5625 × abs(shock)
         + 0.4375 × abs(impulse)
```

The propagation proxy is average peer-member raw heat. Theme heat averages up to the top eight members and multiplies by breadth. A member becomes active at raw heat at least 0.85. Public score anchors map raw heat 0, 0.63, 0.85, 1.11, 1.55, 2.68, 6, and 44 to display scores 0, 20, 40, 60, 80, 95, 99, and 100. Alerts fire crossing display 60 and 95.

The companion labels below 0.85 Calm, 0.85–1.11 Normal, 1.11–2.68 Hot, and at least 2.68 Extreme, with visible lifts 0.8, 1.0, 1.3, and 1.25 respectively. The lower Extreme lift than Hot is what the public source showed, not a Mastermind recommendation. Its own comment cited AUC 0.561 and described outsized movement in either direction. That is a modest volatility/attention classifier, not strong directional alpha.

#### Recoverable public theme-pressure formula

Across 97 inspected U.S. themes, the public pressure field was exactly reproducible after rounding:

```text
pressure = round(100 × (
    0.24 × cluster_impulse
  + 0.22 × breadth_expansion
  + 0.20 × correlation_tightening
  + 0.14 × leader_micro_impulses
  + 0.10 × volume_anomaly
  + 0.10 × propagation_build
))
```

In that snapshot, nonzero `volume_anomaly` was approximately `0.75 × correlation_tightening` with cross-sectional correlation 1.00. The visible score therefore appeared to double-count one underlying construction under two labels. Other fields—theme probability, promotion score, agreement, quorum, and stability—remain opaque and did not behave as one coherent probability scale. Mastermind should reproduce useful primitives with independently calibrated components and an anti-collinearity audit, not copy this display score.

### 7.9 Emerging-group surprise

For a candidate group, transform pairwise residual correlations with Fisher's `z = atanh(r)`, adjust for effective sample size and overlapping windows, and compare the current within-group coordination to historical and simulated null distributions. Persist:

- surprise percentile;
- within-group median/dispersion;
- cross-group separation;
- member breadth;
- turnover;
- stability under window/parameter perturbation;
- liquidity and stress filters;
- established-versus-forming state.

Do not infer direction. A forming group can be a coordinated decline, squeeze, policy shock, or transient noise.

### 7.10 Theme lifecycle and dislocation

Suggested descriptive states:

```text
forming → watching → confirmed → expanding → weakening → dissolved
```

State transitions are deterministic functions of persistence, membership stability, breadth, surprise, and null-calibrated confidence. Market stress/credit/volatility can suppress alert prominence without deleting state.

The useful Mastermind join is:

```text
unusual residual group
  × source-cited company relationship
  × fresh company event or narrative change
  × current price/flow/sector dislocation
  = research investigation candidate
```

It is not:

```text
group score × relationship score = buy conviction
```

### 7.11 Research priority, not investment score

The system may rank which events deserve analyst/user attention. Keep this namespace and UI visually separate from investment authority.

Proposed `research_priority.v1` components, each normalized and inspectable:

- source-backed event materiality;
- magnitude of deterministic fact/guidance change;
- narrative discontinuity versus prior events;
- Q&A pressure and peer-topic breadth;
- relationship/read-through breadth;
- residual-theme novelty/persistence;
- market reaction dislocation;
- user/watchlist relevance;
- source completeness penalty;
- contradiction and staleness penalty.

Start with rule-based tiering rather than a magic weighted score. If a continuous ranking is needed for internal queue order, weights live in versioned config, components display in audits, and the product calls it “research priority.”

### 7.12 13-F handling

13-F data can describe:

- ownership concentration;
- crowded institutional exposure;
- overlap across related companies/themes;
- manager-specific changes with filing lag;
- possible read-through breadth.

It may not be described as fresh fund flow, smart-money endorsement, or directional alpha. Every view carries the report period, filing date, availability date, manager coverage, and lag.

### 7.13 Theme-engine upgrades to test, not assume

The published Jodie market-only residual is a good discovery baseline. Mastermind should evaluate—not silently substitute—stronger variants:

- market-only residuals versus market + sector + style residuals, so sector moves are neither mistaken for novelty nor over-stripped from a real theme;
- daily established communities plus shorter intraday attention/propagation views;
- correlation communities versus lagged/lead-follow candidate edges;
- ensemble stability across lookbacks, thresholds, and Louvain seeds;
- group identity with explicit split/merge ancestry rather than nearest-overlap alone;
- membership probabilities/uncertainty rather than one hard group where the evidence is ambiguous;
- liquidity, corporate-action, volatility, and credit-stress sensitivity;
- event-time joins that distinguish information available before versus after a group move;
- relationship-age/receipt-strength weighting for research priority;
- negative controls using shuffled membership, sector-matched groups, and simulated residual panels.

Ship the simplest stable descriptive construction first. A more complex variant earns adoption only if it improves stability, analyst usefulness, and point-in-time behavior on held-out periods; it does not earn adoption because its graph looks richer.

---

## 8. AI synthesis and editorial system

The observed polished writing is cheap because the hard work occurs before the writer. A writer given a compact, reconciled fact packet does not need to reread a 10-K, deck, release, and transcript for every output.

### 8.1 Efficient generation flow

```text
deterministic facts + addressed source spans
        ↓
one structured extraction
        ↓
claim reconciliation + contradiction ledger
        ↓
canonical event digest
        ↓
promotion classifier (A/B/C)
        ↓
writer from approved claims only
        ↓
deterministic verifier + model critic
        ↓
canonical story
        ↓
cheap channel-specific derivatives
```

The writer never receives permission to introduce a fact merely because it appears in a large raw context. It receives an allowlist of claims and source handles.

### 8.2 Promotion tiers

| Tier | Treatment | Example admission |
|---|---|---|
| A | Full cited research article, ticker module, alert, multi-format X package | Material guidance reversal, major capex/financing shift, important peer read-through, high-confidence theme/event dislocation |
| B | Compact cited Event Brief, ticker update, one or two differentiated posts | Solid earnings change, useful Q&A delta, moderate peer/topic breadth |
| C | Digest/ticker/Neural Web update only; no standalone public article | Routine event, low materiality, incomplete sources, duplicate angle |

Long form is earned by information value and evidence completeness, not by ticker popularity alone. High-demand tickers may receive richer comparisons, but may not bypass evidence gates.

### 8.3 Article blueprint

A Tier A article should normally contain:

1. precise event framing and availability timestamp;
2. the two to four changes that matter;
3. deterministic fact/guidance table;
4. what management emphasized or stopped emphasizing;
5. Q&A pressure and direct source evidence;
6. peer, relationship, or theme read-through;
7. market reaction/dislocation with no causal overclaim;
8. uncertainty, missing sources, and what to watch next;
9. source list and direct event/ticker CTA.

The prose can be AI-drafted. Quality comes from the claim allowlist, retrieval, examples, section jobs, sentence-level citation mapping, and verifier—not from giving a frontier model an enormous transcript and asking it to “write like an analyst.”

### 8.4 Validation gates

Every public story must pass:

- event/accession/fiscal-period identity;
- arithmetic, unit, sign, and comparable-period checks;
- source availability and freshness;
- citation resolution and coverage;
- quote exactness and permitted quote length;
- entity and attribution checks;
- relationship direction and evidence;
- market-timestamp alignment;
- source completeness disclosure;
- contradiction and amendment review;
- duplicate angle and cross-account story lock;
- promotion-tier rules;
- correction propagation;
- deterministic chart/data agreement;
- unsupported superlative and causal-language audit.

A model critic can demote or block. It cannot waive a failed deterministic gate.

### 8.5 Why Struct-like writing can look expensive while being cheap

The inspected Struct launch corpus contained 143 stories and roughly 91,000 final body tokens. A plausible compact-packet generation run costs single-digit dollars in text generation, depending on model. Even a much more rigorous Mastermind pipeline is inexpensive relative to data rights and labor.

Target efficient standard event budget:

- extraction/retrieval: 12,000–24,000 input tokens;
- digest/writing/validation: 12,000–25,000 input tokens;
- total: 24,000–49,000 input and 3,000–6,000 output tokens;
- all SEO/X derivatives: another 2,000–8,000 input and under 1,500 output.

Naively stuffing every raw source into repeated prompts can consume 50,000–150,000 input tokens per event before retries. The contract-first design avoids that waste and, more importantly, avoids inconsistent outputs.

### 8.6 Model routing

- deterministic parser for metadata, arithmetic, counts, period mapping, hashes, citations, and chart data;
- low-cost capable model for structured extraction and routine Tier B digest;
- stronger writer only for Tier A or difficult conflict resolution;
- embeddings once per stable source span/exchange/page;
- prompt caching for company history and repeated system instructions;
- batch processing for non-urgent backfill;
- streaming only for user-initiated chat/on-demand generation;
- hash-based reuse across all derivatives;
- no model call when unchanged source set and processor version already have a valid digest.

### 8.7 Corrections and public trust

The canonical story stores its source-version set. If a material claim changes:

- regenerate the story and derivatives;
- show `updated` or `corrected`, not a silent replacement;
- preserve prior text and change reason internally;
- invalidate social drafts that have not posted;
- never attempt to silently rewrite a post that already left the system;
- prepare a correction item when the original public statement was materially wrong.

---

## 9. Neural Web, Brain, and Prophet integration

### 9.1 Neural Web role

Company Intelligence is a **context organ** and evidence provider. It should register compact artifacts and retrieval capabilities through the existing Signal Bus governance rather than becoming an authority-producing shadow graph.

Initial context keys:

- `company_event.latest_digest`;
- `company_event.guidance_delta`;
- `company_event.narrative_delta`;
- `company_event.qa_pressure`;
- `company_event.relationship_updates`;
- `company_event.peer_topic_pulse`;
- `company_event.source_health`;
- `company_event.theme_dislocation`;
- `company_event.ownership_context`.

Every key includes `event_id`, `available_at`, freshness, source completeness, authority, and receipt handles.

### 9.2 Brain tools

Add four governed tools before exposing a broad agent corpus:

1. `search_company_sources(company, query, filters)`
2. `get_company_event(event_id, sections, include_spans)`
3. `compare_company_narrative(company, event_ids, topics)`
4. `get_peer_topic_pulse(topic, universe, period)`

Later tools can retrieve slide families and relationship neighborhoods. The default Brain prompt receives the compact context object; it calls tools for evidence. This protects latency and tokens and keeps answers source-cited.

Tool responses must:

- enforce user entitlements and source rights;
- return stable span IDs and display-safe excerpts;
- state point-in-time cutoff and missing sources;
- cap result count and token volume;
- preserve raw-versus-edited transcript state;
- avoid leaking internal processor prompts, source credentials, or restricted raw content.

### 9.3 Prophet and signal authority firewall

No new event feature enters Prophet rank, size, gate, or conviction because it sounds useful. First accrue point-in-time feature rows whose availability timestamps precede the outcome window.

The first research bakeoff should test whether event context adds value to existing Prophet predictions, not whether it predicts returns in isolation.

Candidate feature families:

- deterministic surprise/guidance revisions where licensed;
- narrative discontinuity;
- Q&A topic pressure;
- management commitment fulfillment;
- high-confidence relationship read-through;
- residual-theme novelty/persistence;
- reaction-versus-fundamental dislocation;
- peer-topic breadth;
- source completeness and correction risk as uncertainty modifiers.

### 9.4 Promotion bakeoff

Pre-register:

- universe and liquidity filters;
- event and source availability rules;
- fiscal-quarter and issuer identity rules;
- observation time and embargo;
- horizons aligned to Prophet's actual decision use;
- baseline Prophet outputs frozen before adding features;
- missing-value behavior;
- multiple-testing correction;
- sector, size, beta, and event-season controls;
- time-blocked train/validation/forward splits;
- regime and provider sensitivity;
- metrics and minimum practical improvement;
- correction replay and no-lookahead audit.

Evaluate:

- calibration and Brier/log loss for probabilistic outputs;
- rank IC only where the target and cross-section justify it;
- incremental hit/utility versus the frozen baseline;
- tail risk and adverse excursion where appropriate;
- stability across folds, regimes, sectors, and source-completeness levels;
- ablations for every feature family;
- performance after realistic latency and costs if a trade use is ever proposed.

Promotion requires stable incremental value, not one favorable aggregate. Failure leaves the feature in display/context or confluence tier; it does not delete the source data.

### 9.5 Explicit existing ruling

Do not rebuild Stage-2 and Earnings Calls as a win-rate gate on the existing timing entry. That specific construction is already killed in `research/DO_NOT_REBUILD.md`. The Stage/EC context remains useful, and the separate forward-shadow/quality questions remain governed by their existing dockets. Any Company Event feature study must be a clearly new, pre-registered construction.

---

## 10. SEO, blog, X Growth, and conversion system

The Struct insight is correct: primary-source events are an evergreen content supply. The upgrade is to make the product object—not the article—the source of truth.

### 10.1 Acquisition flywheel

```text
new company event/source correction
        ↓
canonical digest updates ticker intelligence
        ↓
promotion gate chooses A / B / C
        ↓
public Event Brief or article when earned
        ↓
search, social, and owned-account distribution
        ↓
deep link to exact ticker event/source/topic
        ↓
registration or paid conversion
        ↓
watchlist, alerts, comparisons, Brain, retention
        ↓
usage improves routing and packaging, never source truth
```

### 10.2 Public route system

Prefer a bounded, durable route estate:

- `/stocks/<ticker>/` — canonical ticker intelligence landing;
- `/stocks/<ticker>/events/<event-id-or-period>/` — event page;
- `/research/<story-slug>/` — Tier A editorial story where distinct from the event page;
- `/topics/<topic-slug>/` — only after a durable topic has enough evidence and update policy;
- `/themes/<theme-id>/` — only for stable theme lineage with freshness.

Do not create separate `/transcript` and `/analyze` pages for every record just to double sitemap size. One canonical event URL can progressively reveal transcript, sources, digest, comparisons, and entitlements while avoiding duplicate intent.

Each indexable page requires:

- self-canonical URL;
- correct index/noindex state by evidence and completeness;
- `Article`/`NewsArticle` where appropriate, `BreadcrumbList`, `Organization`, and defensible `Dataset` markup only when it is genuinely a dataset page;
- published and modified times derived from canonical story state;
- exact ticker/event links;
- source list and correction state;
- Open Graph/X image from deterministic facts or approved chart spec;
- RSS and sitemap membership;
- IndexNow/GSC instrumentation through existing SEO infrastructure;
- `utm` or equivalent first-party attribution from story and channel to ticker/event product entry.

### 10.3 Avoid the programmatic-SEO trap

The inspected EarningsCall.ai sitemap exposed more than 64,000 transcript and analysis URLs. Jodie exposed thousands of ticker routes. That proves the acquisition shape, not traffic or conversion.

Struct itself was a launch-stage property in the inspected snapshot: 143 observed articles, with 140 published across July 30–31 and no credible public evidence yet of rankings, traffic, conversion, retention, or payback. Adopt the funnel architecture, not an unproven belief that publishing volume automatically creates SEO.

Mastermind should index only pages that have:

- unique source-backed information;
- stable event identity;
- meaningful visible content without requiring a model call at crawl time;
- canonical differentiation from the ticker and transcript source;
- acceptable completeness/freshness;
- correction ownership;
- a route into product value.

Thin, duplicate, stale, or rights-blocked pages are `noindex` or absent. “We can generate it” is not an indexation criterion.

### 10.4 One canonical fact packet, distinct X jobs

Map event derivatives into the existing X Growth desks and governance. Do not build a new scheduler or publisher.

| Account job | Event derivative | Difference that must survive |
|---|---|---|
| Flagship | Evidence-led market implication with chart/receipt | Product authority and broadest synthesis |
| Founder | A sharp judgment or strategic implication | First-person thesis; no fake biography or position claim |
| News/wire | Fast factual event line and source | Minimal interpretation; speed and attribution |
| Research property, once armed | Cited event brief/thread | Deeper method and cross-quarter evidence |
| Employee/persona desks | Role-specific angle where the event actually fits | Different question/voice, not synonym rotation |

Examples from one event:

- news: exact revenue/guidance fact and source;
- flagship: why the guidance change matters to the active theme;
- founder: the strategic contradiction or capital-allocation judgment;
- research: three-quarter management commitment ledger;
- short form: one chart plus one source-backed explanation;
- reply desk: on-demand citation when a relevant conversation is discovered.

Use the existing:

- `engine/marketing/story_spine.py` for story identity/dedup concepts;
- `engine/marketing/story_lock.py` for one-owner behavior;
- `engine/marketing/approval_desk.py`, `value_gate.py`, `copy_review.py`, and publisher controls;
- `engine/marketing/earnings_feed.py`, `hot_tape.py`, and existing earnings event kinds;
- `engine/marketing/earnings_card.py`, chart/media infrastructure, and `scripts/marketing_publisher.py`;
- X Growth persona, cadence, near-duplicate, attribution, telemetry, and correction paths.

The integration adapter should turn `canonical_story.v1` into the existing outbox item shape. It must not bypass `make_item`, the approval desk, story locks, attribution, chart requirements, or send-time gates.

### 10.5 Content learning

Measure by event/story/channel:

- impressions and qualified clicks;
- search impressions, query family, indexation, and canonical status;
- ticker/event product opens;
- registration and plan conversion;
- saved company/event, alert creation, transcript search, compare, and Brain use;
- return sessions and retention;
- correction rate and unsupported-claim defects;
- generation and review cost;
- post/story uniqueness across accounts.

Usage may reprioritize which approved angle or format is shown. It may not change source facts, suppress nulls, or train a trading score without a separate governed study.

### 10.6 Monetization packaging

Proposed entitlement boundary, subject to Mastermind's current tier naming and billing source of truth:

| Capability | Public | Registered | Paid core | Highest tier / later |
|---|---:|---:|---:|---:|
| Selected Event Briefs and ticker snippets | Yes | Yes | Yes | Yes |
| Raw source links and bounded transcript archive | Limited | Recent/bounded | Broad | Broad |
| Event digest and guidance delta | Selected | Recent/bounded | Full | Full |
| Search within one event | No | Bounded | Yes | Yes |
| Cross-quarter compare and narrative Timeline | No | Preview | Yes | Yes |
| Peer Topics, Mentioned By, relationships, theme joins | Preview | Preview | Yes | Yes |
| Source-grounded Brain over company history | No | Small quota | Yes | Larger quota |
| Alerts, saved searches, exports | No | Basic watch | Yes | Advanced |
| Slides/History Mode | No | Preview | Limited | Full where licensed |

This suite should increase the value of the existing subscription. A separate $29 micro-plan would complicate positioning, entitlements, and retention while discarding the strongest benefit: integration with the rest of Mastermind.

### 10.7 What the competitors are monetizing and learning

- **Jodie + Struct:** Jodie sells self-serve market/theme/relationship workflow; Struct is the free event-driven acquisition surface. Struct pages route readers into ticker-specific Jodie URLs with article/referral parameters. There were no meaningful signs that ads or affiliates were the core business. Programmatic ticker pages, indexable briefs, social cards, RSS, and the paid watchlist/alert product form the loop.
- **EarningsCall.ai:** large transcript/analysis URL coverage, free discovery, a seven-day trial, and one low-priced Pro plan convert search demand into recurring watchlist/search/chat use. The inspected live price was $25 monthly or $228 annually; older crawl text still showed $29.
- **Quartr:** a multi-surface model—contact-sales Pro, API, MCP, free mobile/public web, and editorial acquisition—monetizes both analyst workflow and licensed infrastructure. Its institutional data operation and rights are more defensible than the visible frontend.

The useful data generated by the products is not only financial content. Account identity, plan, watchlists, alerts, followed companies/themes, searches, clicked evidence, article-to-ticker referral, retained queries, and usage telemetry reveal demand and workflow. Jodie's public privacy language identifies account/watchlist/alert/plan and request/device/log data; Quartr's terms and frontend expose product analytics; EarningsCall.ai uses Clerk, Stripe, Hotjar, and Google Analytics.

Mastermind should collect only the product telemetry it needs and bind it to explicit jobs:

- prioritize source coverage and event processing;
- improve search relevance and route users back to unfinished research;
- measure article/channel conversion;
- identify which comparison, topic, and alert workflows retain users;
- tune content format and entitlement packaging.

It should not silently convert aggregate watchlists or clicks into an investment signal. Usage optimizes product routing; source truth and Prophet authority remain separately governed.

---

## 11. Operating plane, freshness, and health

### 11.1 Schedules

Suggested cadence for the controlled U.S./Canada universe:

| Job | Cadence | Notes |
|---|---|---|
| Event/calendar discovery | 5–15 min in active windows; hourly otherwise | Cheap metadata only |
| SEC submissions watcher | Existing respectful cadence with accession cursor | Reuse SEC identity and User-Agent policy |
| Issuer IR watcher | 10–30 min around scheduled events; daily otherwise | Per-host backoff and change detection |
| Transcript acquisition | 5–15 min after call while expected; exponential backoff | Provider SLA and rights dependent |
| Correction/version watcher | Hourly for 48 h, daily for 14 d, weekly reconciliation | Edited transcript and amended filing path |
| Extraction/digest queue | Event-driven | Priority by source completeness and event tier |
| Search/embedding index | Incremental after addressed spans | Content-hash reuse |
| Stage and compact ticker views | Event-driven plus nightly reconciliation | Publish immutable then pointer/manifest |
| Theme discovery | Nightly | Off render path; fixed point-in-time close |
| Public story/X candidates | Event-driven after promotion gate | Never before required source cutoff |
| Full coverage audit | Nightly | Missing expected sources, lag, collapse, duplicates |
| Historical reconciliation | Weekly/monthly | Late additions and source drift |

The commissioned Mac fallback currently runs through launchd at **17:45, 20:45, and 23:45 America/Vancouver**. At the completed commissioning checkpoint, launchd's last exit was 0, `bootstrap_earnings_worker.sh --check` passed, the ops clone was clean, and both external runtime telemetry ledgers contained 92 rows.

### 11.2 R2 artifact layout

Illustrative private/public split:

```text
company-intelligence/raw/<source>/<company>/<hash>              private immutable blob
company-intelligence/events/<event_id>/event.v1.json            internal/public-safe metadata
company-intelligence/events/<event_id>/documents.v1.json        rights-filtered manifest
company-intelligence/events/<event_id>/digest.v1.json           compact derived object
company-intelligence/events/<event_id>/story.v1.json            approved distribution object
company-intelligence/tickers/<company_id>/index.v1.json         compact ticker event index
company-intelligence/search/<shard>/...                          private index artifacts
company-intelligence/themes/<asof>/...                           compact theme state
company-intelligence/health/latest.json                          production health
```

Terminal/browser payloads contain only public/display-permitted fields. Signed or authenticated APIs mediate licensed raw content.

### 11.3 Health contract

`corporate_intelligence_health.v1` should include:

- generated/observed/source-latest times;
- universe and identity counts;
- events discovered/completed/partial/stale;
- source counts by type, raw/edited/corrected state, and rights profile;
- transcript bodies and index links;
- digests ready/degraded/failed;
- citation coverage and deterministic disagreement rate;
- search indexed spans and lag;
- unresolved duplicates and identity collisions;
- provider latency/error/backoff;
- queue depth and oldest item;
- correction backlog;
- Stage and Terminal compact-artifact hashes/counts;
- previous-last-good comparison and collapse ratios;
- status and human-readable reason.

### 11.4 Fail-closed rules

- Missing source index with published links: abort overwrite and retain last good.
- Count or coverage collapse beyond pre-registered tolerance: abort publish.
- Unknown schema: quarantine adapter output; do not coerce silently.
- Source rights missing/expired: block restricted serving and identify affected coverage.
- Digest citation coverage below threshold: withhold public/Brain narrative while retaining raw metadata.
- Deterministic contradiction unresolved: show disputed state internally; no public claim.
- Provider down: keep last-good source and expose age; do not invent a terminal empty state.
- New event with incomplete sources: publish only the allowed partial view with explicit missing list.
- Correction changed material public claim: block further derivatives until correction state is resolved.

### 11.5 Service objectives for the core universe

Initial targets, to be calibrated against source SLAs:

- event discovery within 15 minutes p95 of the first approved observation source;
- SEC/issuer release retrieval within 10 minutes p95 after discovery;
- transcript visibility within provider SLA plus 15 minutes;
- compact event metadata availability within 5 minutes of source parse;
- cited digest within 60 minutes p90 once required Tier B/A sources are present;
- correction detection within 60 minutes during the first 48 hours;
- Terminal index/digest availability at least 99.5% from last-good artifacts;
- zero silent source-index collapse deployments;
- public numerical claim deterministic agreement at least 99.9%, with the remainder blocked rather than guessed;
- public citation resolution 100%.

SLO misses degrade status and page language. They do not license hallucination.

### 11.6 Operator console

The existing admin/health estate should expose:

- events waiting on source, parsing, extraction, verification, rights, or correction;
- provider/source latency and error cohorts;
- identity collisions and duplicate events;
- coverage by universe/tier;
- latest successful Stage and Terminal manifests;
- public stories awaiting or blocked from promotion;
- model token/cost by stage and tier;
- correction and unsupported-claim defect queue;
- replay/retry controls bounded to exact event/source IDs;
- link to raw manifest and source receipt, respecting rights.

No operator should need to rerun a whole universe to repair one poisoned event.

---

## 12. Rights and source-control matrix

This is a product-enabling rights design, not boilerplate. The wrong rights assumption can make the technically complete suite unusable.

### 12.1 Per-source rights fields

Each `rights_profile` must answer:

- may raw bytes be stored, for how long, and in which region?
- may text be parsed and indexed?
- may embeddings be stored?
- may raw or edited text be shown to authenticated end users?
- may short excerpts be publicly quoted?
- may full transcripts, slides, or audio be redistributed?
- may derived facts and summaries be displayed publicly?
- may the data be used for model inference, evaluation, fine-tuning, or retrieval?
- may it feed internal research/backtests?
- must data be deleted when the contract ends?
- what attribution is required?
- may data appear in API, export, or MCP outputs?

Rights enforcement occurs at retrieval and derivative compilation, not as a comment in collector code.

### 12.2 Competitor fence

- Jodie's data license prohibits bulk extraction, redistribution, resale, and model training. Reimplement published methods on independent data.
- Quartr Pro terms prohibit systematic extraction, database population, competing-product construction, and model training/evaluation. A seat is human benchmark access only.
- Quartr API uses are limited to the approved contract/order. Negotiate every Mastermind use explicitly.
- EarningsCall.ai pages and API behavior can inform product design; its transcript and analysis corpus is not our ingestion source.
- EquityDesk's frozen guest export is a one-time migration/calibration artifact. Do not refresh it after entitlement expiry or depend on vendor RLS.

### 12.3 Buy/build decision

Run a source bakeoff for transcripts and estimates. Score each candidate on:

- universe and historical coverage;
- event latency and corrected-version latency;
- speaker, timestamp, and Q&A quality;
- fiscal/event identity;
- redistribution and derivative rights;
- AI, search, and embedding rights;
- public excerpt rights;
- raw archive access and exit portability;
- correction webhook/poll semantics;
- SLA/support;
- rate/volume limits;
- total cost at 300, 1,000, and 2,000 names.

Build the evidence spine so providers are replaceable. Do not encode one vendor's IDs or enum names as Mastermind's public contract.

### 12.4 Explicit defer list

Until separately contracted, do not promise:

- full transcript redistribution;
- analyst-consensus surprise;
- live five-second transcription;
- downloadable audio;
- unrestricted transcript exports;
- public slide images;
- AI use of any vendor content whose terms are silent or restrictive;
- global coverage simply because issuer URLs are crawlable.

---

## 13. Evaluation system

### 13.1 Golden corpus

Start with 100 companies and at least 200 difficult events. Expand to 300 companies before broad rollout. Include:

- ordinary large caps;
- banks, insurers, REITs, utilities, and biotech;
- ADRs and foreign private issuers;
- dual share classes;
- non-calendar fiscal years and 53-week years;
- ticker/issuer changes, mergers, spinoffs, and delistings;
- amended filings and corrected transcripts;
- custom XBRL and conflicting periods/units;
- missing transcript, deck, filing, or consensus;
- very long calls and presentations;
- scanned or low-text PDFs;
- investor days and non-earnings events;
- named customer, supplier, or competitor relationships;
- events with weak or no material change;
- English and Chinese-facing display fixtures.

Freeze raw source hashes, availability timestamps, expected event identity, expected facts, source spans, correction transitions, and permitted outputs.

### 13.2 Evaluation dimensions

| Dimension | Metric/gate |
|---|---|
| Identity | Issuer/security/event precision and recall; zero cross-company contamination |
| Coverage | Expected event/source recall by universe and source class |
| Freshness | Discovery, source, digest, and correction latency distributions |
| Deterministic facts | Exact value/unit/period agreement and conflict detection |
| Transcript | Speaker/Q&A chapter accuracy; timestamp/citation resolvability |
| Retrieval | Recall@k, MRR/nDCG where labeled, answer-support span recall |
| Citation | 100% resolvability; claim support precision; source-version correctness |
| Digest | Claim precision/recall, numerical consistency, omission severity, analyst usefulness |
| Guidance | Metric/range/period/status accuracy and comparable-prior matching |
| Narrative delta | Pairwise analyst agreement; false-change rate; dropped-language precision |
| Mentioned By | High-precision issuer/entity resolution; dual-class deduplication |
| Relationships | Type/direction/effective-period precision and receipt quality |
| Topics | Cluster coherence, exchange integrity, lineage stability, analyst usefulness |
| Themes | Null-calibrated stability, parameter sensitivity, lineage consistency; no direction claim |
| Slides | Text/OCR accuracy, page retrieval, tag precision, family false-merge/split rate |
| Content | Arithmetic/citation/attribution gates, correction rate, uniqueness, usefulness |
| UX | Premium rubric at least 85, task success, time to evidence, responsive/a11y/performance gates |
| Operations | Replay success, last-good preservation, collapse detection, cost and queue SLO |

### 13.3 Minimum launch gates

For the 100-company pilot:

- event identity precision at least 99.5% and recall at least 98% for the frozen corpus;
- deterministic fact precision at least 99.5%; any unresolved conflict withheld;
- source-span resolution 100%;
- public claim support precision at least 99%;
- no uncited public narrative claim;
- high-confidence Mentioned By precision at least 95%;
- relationship precision at least 90% for admitted public edge types, with lower-confidence edges internal only;
- transcript/source search judged useful for at least 85% of golden queries;
- correction replay regenerates all affected derivatives and preserves history;
- no full-universe overwrite can proceed after an absent or collapsed index;
- premium UX rubric at least 85/100 with no load-bearing category below 7;
- required breakpoint, theme, language, keyboard, and state artifacts attached to the UI PR.

Topic, slide, and theme metrics receive feature-specific thresholds before their phases arm. Do not reuse launch numbers as universal truth.

### 13.4 Comparative bakeoff

For sampled companies/events, compare:

- Mastermind versus Quartr as a human-workflow benchmark;
- Mastermind versus EarningsCall.ai on search and analysis usefulness;
- Mastermind versus EquityDesk's historical structured outputs;
- Mastermind theme/relationship candidates versus Jodie's visible behavior where public and permitted;
- all systems versus primary source and blinded analyst judgment.

Judge task completion, evidence quality, correction behavior, latency, and research usefulness—not screenshot similarity or prose preference alone.

### 13.5 Adversarial cases

Red-team:

- wrong-quarter but numerically plausible facts;
- annual versus quarterly duration collisions;
- currency or unit changes;
- management quote attributed to analyst and vice versa;
- raw transcript error fixed in edited version;
- amended filing that changes a material fact;
- duplicate issuer from dual classes;
- relationship inferred from a hypothetical or negation;
- competitor name that is also an ordinary word;
- slide-family match on a visually similar but semantically different page;
- model-written sentence that fuses two supported claims into an unsupported causal claim;
- page indexed before required source is available;
- article and X derivative disagree after correction;
- source license expiry;
- provider or index collapse;
- backtest using `effective_at` instead of later `observed_at`.

---

## 14. Executable build sequence and file lanes

Every lane starts from a freshly fetched default branch in its own canonical worktree. Macro uses `origin/main`; Terminal uses `origin/master`. Cross-repo contracts merge and deploy in producer-before-consumer order. No builder edits this docket to mark itself complete; the commissioning session records actual PR, merge, deployment, and evaluation evidence.

### 14.0 Shipped repair prerequisites and active forward adapter

These repair lanes are live. Preserve them; do not commission duplicates.

#### REPAIR-S — Stage identity-safe recovery

**Repository:** Macro Dashboard

**State:** shipped and live through Macro [#4181](https://github.com/chriswong6031-creator/macro/pull/4181), with responsive mobile containment in [#4187](https://github.com/chriswong6031-creator/macro/pull/4187)

Files already in lane:

- `engine/earnings_qual.py`
- `engine/stage_analysis.py`
- `scripts/build_earnings_scores_from_history.py`
- `scripts/fetch_earnings_scores.py`
- `scripts/publish_earnings_r2.py`
- `scripts/build_stage_analysis_page.py`
- `templates/stage_analysis.html.j2`
- `tests/test_earnings_seasons.py`
- `tests/test_build_earnings_scores_from_history.py`
- `.github/ci/legacy-jobs.yml`
- `.github/workflows/ci.yml`
- affected generated Stage and health artifacts

Corrected lane now covers:

- deterministic source-ID/`updated_at` reconciliation;
- issuer-safe `company_ticker` grouping while preserving `document_ticker` display coverage;
- `AKSO.OL`, `CLS CN`/`CLS SJ`, same-quarter duplicate, and invalid-FY fixtures;
- latest validated **distinct fiscal period** QoQ;
- complete retained/superseded/quarantined/conflict count ledger;
- health with separate listing and issuer denominators;
- regenerated reviewed counts and guarded `ready` state.

Exit gate recorded complete: the reviewed generation published through R2, merged, rendered, and reached the live [Stage Analysis surface](https://www.mastermind-x.com/stage_analysis.html). Production counts preserve the semantic contract in section 2.

#### REPAIR-T — Terminal transcript discovery

**Repository:** `charting-app`

**State:** shipped and live through Terminal [#295](https://github.com/chriswong6031-creator/mastermind-terminal/pull/295), with role-evidence repair in [#299](https://github.com/chriswong6031-creator/mastermind-terminal/pull/299)

Files:

- `ingest/build_transcript_index.py`
- `ingest/collect_transcripts.py`
- `ingest/gen_fund_us.py`
- `ops/bootstrap_nightly_fund.sh`
- `ops/launchd/com.mastermind.fund.plist`
- `ops/nightly_fund.sh`
- `terminal/components/TerminalShell.tsx`
- `terminal/components/workspaces/AnalysisWorkspace.tsx`
- `terminal/lib/transcripts.ts`
- `terminal/lib/fund.ts`
- `terminal/components/fin/TranscriptsPage.tsx`
- `terminal/components/fin/MegaPane.tsx`
- `terminal/components/fin/TranscriptDrawer.tsx`
- `terminal/app/fin.css`
- `tests/test_transcript_index.py`
- `terminal/lib/__tests__/transcripts.test.ts`

Exit gate recorded complete: production shows the per-ticker Transcripts tab, and the current remote archive exposes 25,438 bodies across 3,288 symbols without breaching the collapse guards.

#### FORWARD-E — Terminal-to-earnings continuous intake

**Repositories:** Terminal producer plus Macro consumer

**State:** producer and consumer merged; Terminal revision/date publication is live through [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303), Macro intake merged/deployed through [#4192](https://github.com/chriswong6031-creator/macro/pull/4192), and the installed Mac appliance's out-of-worktree telemetry hardening merged through [#4201](https://github.com/chriswong6031-creator/macro/pull/4201). The current causal backlog is drained and the recurring launchd schedule is loaded.

This lane adds stable transcript revision hashes/dates at the producer, a durable consumer cursor and retry queue, direct transcript-to-scorer mapping, local-Qwen-first routing, inexpensive provider fallbacks, and automatic publication into the existing Stage/Company Event artifacts. It closes the future-backfill gap without creating a second transcript archive. PR #4201 moves AI-cost and key-metabolism telemetry outside the self-updating ops clone so normal scoring cannot dirty and strand the appliance checkout.

The first bounded checkpoint was 63 of 64 attempted eligible records healthy; future-dated `HCM/2026Q2` was quarantined before provider/model use; and durable state showed 29 pending plus 1 retry. The completed 09:07 America/Vancouver run then attempted those 29, succeeded on 28, and atomically promoted generation `90595cb8924f2ef3992f4e16`. The sole pending/retry is the same causally impossible future record (`call_date=2026-08-06`, reason `source_future_call_date`), so all currently causal real calls are drained without pretending the future call has occurred.

The promoted manifest records 3,620 score rows across 3,558 tickers and 50,982 history rows across 3,529 tickers, with latest call date 2026-07-31. An R2 dry-run reports the generation current. Operational checks also pass: both external runtime telemetry ledgers have 92 rows, the ops clone is clean, launchd last exit is 0, the 17:45/20:45/23:45 schedule is loaded, and bootstrap `--check` passes.

#### CEI-C — Chronicle, Brain, Press, and X consumer bridge

**Repository:** Macro Dashboard

**State:** implemented and validated on local branch `codex/earnings-consumers-integrated-20260801`; not pushed, merged, scheduled, or live at this memo refresh

The integrated consumer stack:

- projects only healthy score rows into committed `earnings.call_event.v1` Chronicle records with stable source identity, transcript URL/hash, causal `call_date <= source_updated_at <= scored_at` lineage, model/prompt/schema provenance, fixed context salience, and no signal/rank/size authority;
- gives Brain the newest cited call packet per ticker while replacing the stale one-time EquityDesk call-quality snapshot;
- gives Press revision-specific staging receipts, supersedes pending stale drafts, and creates an explicit non-emittable `correction_required` record when a published source revision changes;
- gives X a deterministic, bounded derivative lane that admits only structured quarter/year numerics, dedupes an identical revision, and returns `correction_required` rather than queuing an unlabeled second revision; no X scheduler is armed by this implementation.

Post-rebase validation is green: 477 focused Chronicle/Brain/Press/X/Signal-Bus tests and 1,794 broad Brain/Press/Chronicle/marketing/outbox/claim/registry tests passed. Python compile and `git diff --check` also passed.

### 14.1 Wave 0 — rights, benchmark, and design truth

#### CEI-00A — Rights and source decision record

**Repository:** Macro Dashboard

**Type:** research/contract; no production ingestion

Add:

- `research/company_intelligence/SOURCE_RIGHTS_MATRIX.md`
- `research/company_intelligence/TRANSCRIPT_AND_ESTIMATES_BAKEOFF.md`
- `config/company_intelligence_sources.yml`
- `tests/test_company_intelligence_source_rights.py`

Contents:

- explicit rights profile for SEC, issuer IR, current transcript corpus, candidate vendors, consensus, slides, audio, public derivatives, AI, search, export, and deletion;
- provider bakeoff and buy/build recommendation;
- no-scraping competitor fence;
- initial 100-company universe.

Exit gate: every Phase 1 source has an approved rights profile; unknown rights fail closed.

#### CEI-00B — Golden corpus and contract fixtures

**Repository:** Macro Dashboard

Add:

- `research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json`
- `tests/fixtures/company_intelligence/`
- `tests/test_company_intelligence_golden_manifest.py`

Only store permitted source fixtures; otherwise store hashes, metadata, synthetic/minimal excerpts, and expected span addresses. Include the identity/correction/adversarial cases in section 13.

Exit gate: frozen availability timestamps, identities, source versions, expected facts, spans, and correction transitions for the first benchmark set.

#### CEI-00C — Experience architecture and reference compositions

**Repository:** `charting-app`

**Owner:** designer/main-loop design lane; implementation builders do not choose the design

Read and obey the Terminal design doctrine and target repo agent rules. Add exact paths selected by that repo's design process, expected to include:

- a Company Intelligence product/design specification under the Terminal docs/design estate;
- committed reference compositions under the repo-approved `mockups/refs/company-intelligence/` location;
- real-payload prototype fixtures;
- inline implementation acceptance gates;
- premium QA rubric worksheet.

Specify:

- navigation and relationship to the existing Transcripts tab/MegaPane;
- Brief, Transcript, Timeline, Peers, Slides, and Sources interaction;
- citation/source rail;
- comparison and Brain handoff;
- 1440/820/390 layouts;
- every supported theme mode (Terminal currently dark-only), EN/ZH, and populated/partial/stale/corrected/empty states;
- performance and accessibility behavior.

Exit gate: commissioner approves real-data reference compositions. A mood board or vendor screenshot collage does not pass.

### 14.2 Wave 1 — Company Event evidence spine

#### CEI-01 — Contracts, identity, and event lifecycle

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/__init__.py`
- `engine/company_intelligence/contracts.py`
- `engine/company_intelligence/identity.py`
- `engine/company_intelligence/events.py`
- `engine/company_intelligence/rights.py`
- `engine/company_intelligence/schemas/`
- `config/company_intelligence.yml`
- `tests/test_company_intelligence_contracts.py`
- `tests/test_company_intelligence_identity.py`
- `tests/test_company_intelligence_events.py`

Reuse existing ticker/CIK/exchange mapping where authoritative; do not start a parallel symbol dictionary. Implement issuer/security/listing distinction, event transitions, source availability timestamps, schema validation, rights profiles, and point-in-time invariants.

Exit gate: golden identity/event fixtures pass; `document_ticker`/listing and issuer denominators remain distinct; no event can be read before `observed_at`.

#### CEI-02 — Immutable documents and source spans

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/documents.py`
- `engine/company_intelligence/spans.py`
- `engine/company_intelligence/storage.py`
- `engine/company_intelligence/corrections.py`
- `scripts/publish_company_intelligence_r2.py`
- `scripts/fetch_company_intelligence_r2.py`
- `tests/test_company_intelligence_documents.py`
- `tests/test_company_intelligence_spans.py`
- `tests/test_company_intelligence_corrections.py`

Integrate rather than duplicate:

- `collectors/edgar.py`
- `collectors/edgar_8k.py`
- `collectors/edgar_earnings_8k.py`
- existing R2 and atomic-publication patterns.

Deliver content hashes, document versions, stable span addressing, supersession, rights filtering, last-good manifests, and correction replay primitives.

Exit gate: every golden claim can resolve a stable permitted span before and after reprocessing; amendment replay preserves the old point-in-time state.

#### CEI-03 — Event watchers and transcript adapter

**Repository:** Macro Dashboard, with the existing Terminal raw corpus as a migration source after REPAIR-T ships

Add or extend:

- `collectors/company_event_calendar.py`
- `collectors/issuer_ir_events.py`
- `collectors/company_event_transcripts.py`
- `engine/company_intelligence/transcripts.py`
- `scripts/company_event_watch.py`
- `tests/test_company_event_calendar_collector.py`
- `tests/test_issuer_ir_events.py`
- `tests/test_company_event_transcripts.py`

Integrate existing:

- `collectors/finnhub_transcripts.py` where rights and quality allow;
- `collectors/equity_earnings.py` for event/calendar observations;
- Terminal `mastermind.tx-index/v1` and per-symbol indexes for corpus inventory, not canonical issuer identity.

Implement discovery/correction cursors, raw/edited transcript versions, Q&A chapters, speaker roles, stable segment spans, and missing-source states.

Exit gate: a newly observed golden event reaches the correct event and transcript/source state without a manual backfill; late source arrival upgrades the same event.

### 14.3 Wave 2 — facts, digest, search, and compact products

#### CEI-04 — Deterministic event facts

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/facts.py`
- `engine/company_intelligence/guidance.py`
- `engine/company_intelligence/market_reaction.py`
- `tests/test_company_intelligence_facts.py`
- `tests/test_company_intelligence_guidance.py`
- `tests/test_company_intelligence_market_reaction.py`

Reuse existing EDGAR fact collectors and price plane. Normalize periods/units, map comparable periods, reconcile management numbers, and compute reaction only after source availability.

Exit gate: golden numeric precision and period tests pass; invalid fiscal years and conflicts cannot enter comparisons.

#### CEI-05 — Structured extraction, reconciliation, and digest

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/extract.py`
- `engine/company_intelligence/claims.py`
- `engine/company_intelligence/reconcile.py`
- `engine/company_intelligence/digest.py`
- `engine/company_intelligence/model_router.py`
- `engine/company_intelligence/quality.py`
- `tests/test_company_intelligence_extract.py`
- `tests/test_company_intelligence_reconcile.py`
- `tests/test_company_intelligence_digest.py`
- `tests/fixtures/company_intelligence/model_replays/`

Implement one structured extraction, claim allowlist, source-type authority, deterministic agreement, completeness state, citation coverage, abstention, hash reuse, token ledger, and correction invalidation.

Exit gate: golden digest gates pass, every admitted claim has a resolvable span, and repeated unchanged builds make zero model calls.

#### CEI-06 — Search index and retrieval

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/search.py`
- `engine/company_intelligence/retrieval.py`
- `scripts/build_company_intelligence_search.py`
- `tests/test_company_intelligence_search.py`
- `tests/test_company_intelligence_retrieval.py`

Start with lexical search and filters over addressed spans. Add semantic rerank only after lexical baseline and labeled retrieval set exist. Index Q&A exchanges and slide pages as typed units; never return an embedding result without a source span.

Exit gate: golden retrieval thresholds, rights filters, latency budget, and source-version correctness pass.

#### CEI-07 — Compact manifests, health, and Stage adapter

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/views.py`
- `engine/company_intelligence/health.py`
- `scripts/build_company_intelligence.py`
- `scripts/audit_company_intelligence.py`
- `tests/test_company_intelligence_views.py`
- `tests/test_company_intelligence_health.py`

Extend without erasing:

- `engine/earnings_qual.py`
- `scripts/publish_earnings_r2.py`
- `scripts/fetch_earnings_scores.py`
- Stage compact artifacts and `data/quality/earnings_intelligence_health.json` migration.

Publish event, ticker, Stage, and health views from the Company Event Spine while preserving Repair-S source/issuer denominator, distinct-period QoQ, source-tier, last-good, and collapse contracts.

Exit gate: Stage results match the reviewed Repair-S baseline for legacy dimensions; new event-source coverage is additive and health reconciles producer and consumer counts.

### 14.4 Wave 3 — Terminal premium IR core

#### CEI-T01 — Typed client, authenticated proxy, and event shell

**Repository:** `charting-app`

**Dependency:** CEI-00C and CEI-07

Expected files, adjusted to the approved design spec and existing route conventions:

- `terminal/lib/companyIntelligence.ts`
- `terminal/lib/__tests__/companyIntelligence.test.ts`
- `terminal/app/api/company-intelligence/[symbol]/route.ts`
- `terminal/components/fin/CompanyIntelligencePage.tsx`
- `terminal/components/fin/MegaPane.tsx`
- `terminal/app/fin.css`

Implement strict schema normalization, entitlement/rights-aware proxying, event selector, Brief and Sources views, source completeness, correction state, evidence rail, and connection to the Transcripts page/drawer delivered by the prerequisite REPAIR-T lane.

Exit gate: exact 1440/820/390 references, every supported theme mode, EN/ZH, keyboard, screen reader, partial/stale/corrected/empty, performance, and premium rubric gates pass using real payloads. Do not invent a light mode inside this feature while the Terminal remains intentionally dark-only.

#### CEI-T02 — Transcript search and cross-quarter compare

**Repository:** `charting-app`

**Dependency:** CEI-06 and CEI-T01

Expected files:

- `terminal/components/fin/CompanySourceSearch.tsx`
- `terminal/components/fin/NarrativeCompare.tsx`
- `terminal/components/fin/EvidenceRail.tsx`
- additions to the typed client, tests, and finance CSS.

Deliver search/filter, prepared/Q&A boundaries, citation jumps, pinned evidence, selected-event comparison, and Brain handoff. Long documents are virtualized and loaded on demand.

Exit gate: golden research tasks pass within performance and accessibility budgets; no citation opens the wrong source version.

### 14.5 Wave 4 — Neural Web and Brain

#### CEI-08 — Signal Bus context registration

**Repository:** Macro Dashboard

Add:

- `engine/neuralweb/company_intelligence.py`
- registry entries in `config/synapse.yml`
- `tests/test_neuralweb_company_intelligence.py`
- conformance additions to existing synapse/read-gate tests.

Publish bounded `company_intelligence_context.v1` keys with context-only authority, availability, freshness, completeness, and receipts. Register no score/rank/size/gate.

Exit gate: Signal Bus conformance passes; stale/missing/rights-blocked inputs degrade explicitly; no LLM-originated escalation path exists.

#### CEI-09 — Brain retrieval tools

**Repository:** Macro Dashboard

Add or extend:

- `engine/neuralweb/brain_gateway.py`
- `engine/neuralweb/company_intelligence_tools.py`
- `tests/test_brain_company_intelligence_tools.py`
- `tests/test_brain_gateway.py`

Implement the four section-9 tools with entitlement, result-size, token, rights, availability, and citation guards. The Brain receives compact context and retrieves raw evidence only when needed.

Exit gate: adversarial entitlement and prompt-injection fixtures pass; answers cite correct permitted spans and state cutoff/missing sources.

#### CEI-09A — Calendar and alert feed

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/calendar.py`
- `engine/company_intelligence/alerts.py`
- `scripts/build_company_event_calendar.py`
- `tests/test_company_intelligence_calendar.py`
- `tests/test_company_intelligence_alerts.py`

Publish confirmed/estimated/rescheduled/cancelled lifecycle, watchlist-relevant event changes, new-source/correction alerts, and saved topic/mention triggers. Reuse existing account/watchlist and notification infrastructure. Alert facts carry `event_id`, availability, source state, receipts, and dedup/cooldown identity.

Exit gate: no duplicate alert across reschedule/source-arrival transitions; correction alerts supersede rather than masquerade as new events; rights and entitlement gates pass.

#### CEI-T02A — Calendar, saves, and alert workflow

**Repository:** `charting-app`

**Dependency:** CEI-09A and the approved experience architecture

Add the Company Intelligence calendar/filter view, watchlist event markers, saved source/topic searches, and alert settings through existing authenticated preferences. Support calendar timezone, estimated-versus-confirmed state, reschedules/cancellations, and direct event deep links.

Exit gate: desktop/mobile calendar tasks, timezone boundaries, entitlement, EN/ZH, empty/down states, accessibility, and premium rubric pass.

### 14.6 Wave 5 — narrative, relationships, and themes

#### CEI-10 — Timeline, commitments, and Peer Topics

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/narrative.py`
- `engine/company_intelligence/commitments.py`
- `engine/company_intelligence/topics.py`
- `tests/test_company_intelligence_narrative.py`
- `tests/test_company_intelligence_topics.py`

Deliver lexical measures, comparable-event deltas, commitment ledger, Q&A exchange clustering, lineage, and coherence audits.

Exit gate: labeled topic and narrative thresholds pass; every topic/commitment resolves to evidence.

#### CEI-11 — Mentioned By and relationship graph

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/entities.py`
- `engine/company_intelligence/mentions.py`
- `engine/company_intelligence/relationships.py`
- `config/company_intelligence_aliases.yml`
- `tests/test_company_intelligence_mentions.py`
- `tests/test_company_intelligence_relationships.py`

Deliver issuer/product resolution, relation type/direction, receipt sets, first/last seen, expiry, dispute, and review thresholds.

Exit gate: high-confidence public precision gates pass; lower-confidence edges remain internal; similar language never becomes a customer/supplier assertion.

#### CEI-12 — Residual themes, lineage, and event join

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/residual_themes.py`
- `engine/company_intelligence/theme_lineage.py`
- `engine/company_intelligence/dislocation.py`
- `scripts/build_company_intelligence_themes.py`
- `tests/test_company_intelligence_residual_themes.py`
- `tests/test_company_intelligence_theme_lineage.py`
- `tests/test_company_intelligence_dislocation.py`

Reuse/adapt rather than compete with:

- `engine/theme_discovery.py`
- `engine/theme_scoring.py`
- `engine/theme_context.py`
- `engine/theme_catalyst_binder.py`
- current theme state and Neural Web theme artifacts.

Deliver market-neutral residual groups, null simulations, reproducible communities, lifecycle/lineage, relationship/event joins, and research-priority candidates.

Exit gate: parameter/stability, null, and component-collinearity audits pass and every UI/API surface says context/research priority, never directional conviction.

#### CEI-T03 — Timeline and Peers UI

**Repository:** `charting-app`

**Dependency:** CEI-10/11/12 and the approved design architecture

Add the Timeline and Peers lenses, management commitment history, Mentioned By, relationship receipts, peer Q&A topics, and theme/dislocation context. Follow the same evidence rail and premium QA gates; do not add a third interaction grammar.

Exit gate: cross-quarter and cross-company tasks pass at all breakpoints with inspectable receipts and no graph-hairball default view.

### 14.7 Wave 6 — canonical stories, public product, and X

#### CEI-13 — Canonical story compiler

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/story.py`
- `engine/company_intelligence/promotion.py`
- `engine/company_intelligence/story_verify.py`
- `scripts/build_company_intelligence_stories.py`
- `tests/test_company_intelligence_story.py`
- `tests/test_company_intelligence_promotion.py`

Deliver A/B/C tiering, approved-claim-only writer, verifier, story version/correction state, deterministic chart specs, and token/cost ledger.

Exit gate: zero unsupported or unresolved public claims across golden stories; unchanged events produce no new story/model call.

#### CEI-14 — X Growth adapter

**Repository:** Macro Dashboard

Add:

- `engine/marketing/company_event_adapter.py`
- `tests/test_marketing_company_event_adapter.py`
- minimal config additions to `config/marketing.yml` only where the existing kind/account system requires them.

Integrate through the existing outbox, `make_item`, story lock, approval desk, value gate, persona, chart, attribution, cadence, near-duplicate, publisher, telemetry, and correction machinery.

Exit gate: one canonical story produces meaningfully distinct permitted derivatives, no cross-account paraphrase spray, and no bypass around existing publishing gates.

#### CEI-15 — Public event/ticker research surfaces

**Repository:** Macro Dashboard

**Owner:** designer for user-facing decisions; builder implements an exact spec

Expected files:

- `scripts/build_company_event_pages.py`
- approved public templates/components following the existing public navigation family;
- sitemap/RSS/structured-data integration through existing builders;
- `tests/test_company_event_pages.py`
- SEO, canonical, structured-data, indexation, and correction tests.

Deliver Tier A/B pages, ticker intelligence module, event CTA/deep link, metadata, images, RSS/sitemap, noindex logic, and conversion attribution.

Exit gate: public-source/rights gates, premium responsive visual proof, canonical uniqueness, and conversion instrumentation pass; live pages are verified after merge/render.

### 14.8 Wave 7 — slide intelligence

#### CEI-16 — Slide parse, search, tags, and families

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/slides.py`
- `engine/company_intelligence/slide_search.py`
- `engine/company_intelligence/slide_tags.py`
- `engine/company_intelligence/slide_families.py`
- `scripts/build_company_intelligence_slides.py`
- corresponding golden and adversarial tests.

Build page rendering, native text extraction, selective OCR, region detection, controlled Key Slide tags, embeddings/features, family candidates, lineage, and manual override audit. OCR is a fallback, not the universal first step.

Exit gate: page citation, search, tag precision, and false family merge/split thresholds pass on at least 1,000 labeled slide pages.

#### CEI-T04 — Slides and History Mode UI

**Repository:** `charting-app`

Add the Slides lens, page search, Key Slides, side-by-side historical family view, textual numeric changes, ambiguity state, and source download/open behavior allowed by rights.

Exit gate: desktop/tablet/mobile interactions, image loading/performance, keyboard, zoom, rights, and premium visual rubric pass.

### 14.9 Wave 8 — Prophet accrual and controlled scale

#### CEI-17 — Point-in-time research feature accrual

**Repository:** Macro Dashboard

Add:

- `engine/company_intelligence/research_features.py`
- `scripts/accrue_company_intelligence_features.py`
- a new pre-registration under `research/` before outcome inspection;
- forward ledger/artifacts using existing Prophet research conventions;
- tests for availability, correction replay, and no lookahead.

This lane writes context-feature observations only. It does not change Prophet authority.

Exit gate: point-in-time audit passes and a sufficient forward clock exists. Promotion, if any, is a later adjudicated PR.

#### CEI-18 — Scale ladder

Expand only after completed bakeoffs:

```text
100 → 300 → 1,000 → roughly 2,000 U.S./Canada companies
```

At each step publish a scorecard covering rights, event/source coverage, latency, identity defects, deterministic accuracy, citation quality, retrieval, digest quality, correction rate, UX tasks, model/infra cost, and operator burden.

Exit gate: every cohort clears the same quality floor without per-company manual rescue. Coverage volume alone is not a pass.

---

## 15. Operator-scale economics and maintenance

### 15.1 The short answer

**Yes, build it.** Under Mastermind's actual local-first, agentic operating model, neither tokens nor infrastructure is a serious reason to reject the suite. The current Terminal transcript corpus, Stage history, R2 publication path, source rights, research surfaces, and autonomous build capacity already exist. The incremental job is to connect and harden those assets, not finance a greenfield institutional data company.

Local Qwen carries bulk extraction, classification, reranking, and first-pass synthesis with no per-token invoice. Its marginal cost is electricity and machine occupancy, not an API bill. DeepSeek V4 Flash is the default inexpensive API fallback; V4 Pro is a selective quality/escalation route; Kimi K2.6 is reserved for cases where its long-context, multimodal, or Chinese-language strengths justify the higher price. An attached Codex Pro/20x account can now be selected explicitly as a Terra extraction rung; it is never inserted silently, and the inexpensive API/local routes remain the unattended default so subscription capacity is opportunistic rather than an operational dependency.

### 15.2 Event token volume

For 2,000 companies with four standard result events per year:

```text
8,000 events/year
× 24,000–49,000 input tokens/event
= 192–392 million input tokens/year

8,000 events/year
× 3,000–6,000 output tokens/event
= 24–48 million output tokens/year
```

Using the conservative assumption that every input token is a cache miss, then adding 25–75% for retries, evaluations, and unusually long events, the representative annual API alternatives are:

| Route | Price assumption at 2026-08-01 | 8,000-event annual cost including 25–75% overhead |
|---|---:|---:|
| DeepSeek V4 Flash | $0.14/M cache-miss input; $0.28/M output | **$42–$120/year** |
| DeepSeek V4 Pro | $0.435/M cache-miss input; $0.87/M output | **$131–$371/year** |
| Kimi K2.6 | $0.95/M input; $4/M output | **$348–$988/year** |

These are reproducible planning calculations from the volume above and the [official DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) plus [official Kimi K2.6 pricing](https://platform.kimi.ai/docs/pricing/chat-k26.md), not a commitment to route every event through one provider. Caching, deterministic extraction, source-hash reuse, batching, and local Qwen reduce the paid total further.

All SEO and X derivatives together should add less than 10% if they read the canonical story. Letting every account or article reread the source corpus is both more expensive and less consistent.

### 15.3 Backfill strategy

Eight quarters for 2,000 companies is 16,000 events:

- 384–784 million input tokens;
- 48–96 million output tokens;
- approximately twice the 8,000-event forward volume before batching, caching, and local routing.

Do not regenerate prose for the entire EquityDesk history. Migrate structured fields, build deterministic facts and spans, and model only:

- the controlled golden corpus;
- the most recent comparable periods needed for product value;
- Tier A/B events;
- older events on demand or during low-cost batch windows.

The 50,000-plus-row historical Stage dataset is a calibration/analytics history, not a mandate to create 50,000 public articles.

### 15.4 Runtime routing and representative recurring budget

The practical default is a cascade, not a single expensive model:

1. deterministic parsers calculate facts, reconcile periods, and construct compact source packets;
2. local Qwen performs bulk extraction and routine Tier B synthesis;
3. DeepSeek V4 Flash handles overflow, provider fallback, and inexpensive structured extraction;
4. DeepSeek V4 Pro verifies or rewrites the small subset that fails quality gates;
5. Kimi K2.6 handles selected long-context, slide/multimodal, or Chinese-language work;
6. Codex Terra can absorb opportunistic editorial/research batches inside an existing subscription allowance, while the explicit API/local routes remain the unattended SLA path;
7. the strongest interactive model is used only for hard investigations or prompt/evaluation design.

A deliberately generous representative operating allowance is **$15–$40/month of paid API inference plus C$5–$15/month of local electricity**. Actual scheduled text generation can be lower: the annual all-API table above shows that even 8,000 calls are inexpensive before local routing. Interactive Brain demand should still be metered separately with compact retrieval, quotas, caching, and per-query cost logs.

The first two live runs provide a much stronger empirical anchor than the planning table: the external runtime AI ledger records **92 DeepSeek V4 Flash calls**, **447,818 input tokens**, **31,905 output tokens**, and **$0.0721838** total estimated cost. Those invocations produced 91 scored real calls; the extra invocation was a retry. That is about **$0.00079 per recorded model call**, confirming that source quality, causality, correction handling, and product usefulness—not text inference cost—are the binding constraints.

### 15.5 Existing infrastructure advantage

The old greenfield infrastructure estimate does not apply to Mastermind:

- the current Terminal transcript corpus is about **380 MB**, well inside Cloudflare R2's current **10 GB-month included storage tier**, before considering its free Internet egress; see [official R2 pricing](https://developers.cloudflare.com/r2/pricing/);
- Stage, Terminal, R2 manifests, static publication, health checks, SEO, X Growth, dossiers, Brain, and Neural Web already exist;
- transcript and redistribution rights are already handled for this program;
- the current archive contains 25,438 bodies across 3,288 symbols, so this is an incremental forward-ingestion and intelligence layer rather than a from-zero corpus build;
- two or three Codex Pro/20x subscriptions may be useful build capacity, but their subscription price belongs to the development tool budget, not the unattended runtime line; see [official Codex plan pricing](https://learn.chatgpt.com/docs/pricing).

The initial incremental infrastructure cost can therefore be effectively zero beyond the representative model/electricity allowance above. Add paid search replicas, OCR capacity, or new data feeds only after measured usage proves they are necessary.

### 15.6 Agentic build model

Do not translate this roadmap into institutional headcount, loaded-labor, or 18–36-month parity estimates. Mastermind is not greenfield: autonomous coding agents can implement independent lanes in parallel against existing repositories, tests, deployment machinery, and product primitives. Progress is governed by contracts and acceptance gates—identity, provenance, correction replay, quality, and premium UX—rather than a speculative staffing table.

The correct planning unit is a mergeable, testable build lane. Global five-second live coverage remains out of scope because it is a different product objective, not because the core Mastermind suite requires an institutional organization.

### 15.7 Steady-state maintenance

Recurring work includes:

- issuer IR URL and HTML changes;
- SEC/source schema drift;
- fiscal calendar and identity exceptions;
- missing, duplicate, rescheduled, amended, and corrected events;
- provider contracts and entitlements;
- transcript speaker/timestamp quality;
- PDF, table, scan, and OCR failures;
- search relevance and topic drift;
- relationship false positives and expiry;
- theme lineage calibration;
- correction and public trust operations;
- peak-season capacity;
- UX/performance regressions as payloads grow;
- SEO indexation and thin-page pruning;
- model/prompt version evaluation and cost routing.

### 15.8 Cost controls that are architectural

1. Parse and embed each immutable source version once.
2. Build one structured event extraction, not one prompt per product tab.
3. Store compact digests and retrieve raw spans on demand.
4. Route strong writing only to Tier A.
5. Use deterministic templates for routine Tier B and all charts/tables.
6. Generate channel derivatives from `canonical_story.v1`.
7. Hash source sets, prompts, processors, and outputs for exact reuse.
8. Batch historical and non-urgent work.
9. Keep heavy compute off nightly render.
10. Measure cost per useful event and per retained/converted user, not only per token.

---

## 16. Execution order and critical path

Use dependency-complete build waves, not institutional calendar estimates. Agents may run independent lanes in parallel after their producer contracts stabilize.

### Wave A — shipped baseline

- Stage identity-safe reconciliation, health, R2 publication, and responsive UI are live;
- Terminal transcript discovery, archive UI, source links, and evidence-bound speaker roles are live;
- preserve those contracts while later lanes enrich the same archive.

### Wave B — continuous forward intake

- Terminal [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303), Macro [#4192](https://github.com/chriswong6031-creator/macro/pull/4192), and telemetry hardening [#4201](https://github.com/chriswong6031-creator/macro/pull/4201) are merged; the revision-aware producer, durable consumer, and clean self-updating appliance are operational;
- the live index has complete one-to-one body/revision/date coverage for 25,438 records, and the commissioned worker detects new/corrected revisions by stable content hash while retaining durable retry and last-good state;
- generation `90595cb8924f2ef3992f4e16` is promoted with 3,620 score rows/3,558 tickers and 50,982 history rows/3,529 tickers; all currently causal real calls are drained;
- `HCM/2026Q2` remains correctly pending because its 2026-08-06 call date is still in the future, proving the causality gate instead of manufacturing a completed event;
- the launchd fallback schedule is loaded at 17:45/20:45/23:45 America/Vancouver, the ops clone is clean, and bootstrap `--check` passes;
- switch provider priority to the Windows Qwen endpoint only when that endpoint is continuously reachable; continue watching the next scheduled new/corrected call as recurring-service evidence, not as a prerequisite for calling the current causal drain complete.

### Wave C — evidence and digest plane

- merge core identity/event/source/span schemas;
- review and ship the locally validated projection of each healthy R2 earnings score into a byte-stable, committed
  `earnings.call_event.v1` Chronicle source carrying stable record identity,
  transcript URL, source hash, model/prompt lineage, summary, highlights, and
  context-only status; never make Chronicle read the mutable R2 parquet directly;
- add immutable documents, correction replay, deterministic facts, one structured extraction, lexical search, and compact ticker/event manifests;
- freeze and evaluate the golden corpus with adversarial correction drills.

### Wave D — premium product and distribution

- ship Terminal Brief/Sources/search/cross-quarter UX and Neural Web context keys; the source-grounded Brain call packet, correction-safe Press bridge, and deterministic X derivative are already implemented and validated locally but remain unshipped;
- fan one approved canonical story into Event Briefs, SEO, X, alerts, and short form;
- measure retrieval, digest, latency, conversion, and UX quality before expanding publication volume.

### Wave E — differentiated intelligence

- add Narrative Timeline, commitments, Peer Topics, Mentioned By, relationship receipts, and residual-theme lineage/dislocation joins;
- expand issuer coverage only after quality and operating scorecards clear;
- add slides, Key Slides, History Mode, and more event types only when their incremental value clears the gate.

The critical path is rights → identity/event/source spans → deterministic facts/digest → compact contracts → premium UX. Theme graphs, articles, and AI cleverness cannot rescue a weak critical path.

---

## 17. Risk register

| Risk | Probability | Impact | Control |
|---|---:|---:|---|
| Transcript/consensus rights are too restrictive or expensive | High | Critical | Provider bakeoff, modular adapters, free-source fallback, no premature feature promise |
| Issuer/security/event identity contaminates history | High | Critical | Exchange-qualified issuer keys, source IDs, golden adversarial fixtures, separate listing/issuer health |
| Silent missing/collapsed inputs erase production | Medium | Critical | Atomic last-good, shrink floors, producer/consumer manifests, fail-closed deployment |
| Fiscal-period errors fabricate comparisons | High | High | Validated fiscal periods, distinct-period pairing, quarantine invalid FY, deterministic tests |
| AI prose fabricates or fuses claims | High without gates | Critical | Claim allowlist, exact spans, deterministic verifier, public block on failure |
| Corrections do not reach derivatives | Medium | High | Source-version dependency graph, invalidation, story correction state, replay drills |
| Topic/relationship graph looks convincing but is wrong | Medium | High | High-precision public threshold, receipts, internal candidate tier, expiry and review |
| Jodie-style groups are mistaken for alpha | High | High | Context namespace, nondirectional UI, authority ledger, separate Prophet gauntlet |
| Product becomes a vendor-feature collage | Medium | High | Dedicated experience architecture, one interaction grammar, premium rubric, commissioner review |
| Long documents make Terminal slow | High | High | Compact manifest, progressive load, virtualization, server search, performance budgets |
| Programmatic SEO creates thin/duplicate pages | High | Medium | A/B/C promotion, canonical event routes, noindex gates, quality/traffic pruning |
| X network repeats the same story | High | Medium | Canonical story lock, account jobs, near-dup gates, distinct derivative evaluation |
| Peak earnings season overwhelms queues | Medium | High | Priority queues, burst capacity, Tier routing, backpressure, age SLOs |
| One provider becomes irreplaceable | Medium | High | Internal contracts, raw exit rights, adapter conformance, dual-source calibration |
| Maintenance cost grows with issuer-specific crawlers | High | Medium | Universe ladder, source templates, coverage economics, buy rather than heroic scraping |

---

## 18. Already covered, reused, and excluded

### 18.1 Already covered or in active repair

Do not re-propose:

- the Stage “Warming up” diagnosis and basic health/source ladder;
- the shipped identity-safe Stage reconciliation repair;
- the Terminal's live 25,438-body/3,288-symbol transcript corpus;
- the shipped fail-closed transcript index and Transcripts tab;
- the in-progress forward adapter, which should be completed rather than duplicated;
- the frozen EquityDesk delta export and migration seed;
- current EDGAR, market-data, 13-F, ticker dossier, theme, R2, and static-site substrate;
- existing Research Vault ingestion/search/governance;
- existing Signal Bus and Brain gateway;
- existing X Growth outbox, approval, persona, cadence, story lock, media, publisher, and telemetry systems;
- existing public navigation, authentication, billing, subscription, watchlist, and Terminal shell.

The new spine integrates these. It does not replace them with a competitor-shaped stack.

### 18.2 Explicitly excluded from the core build

- literal cloning of competitor code, private prompts, private scores, or visual identity;
- scraping or bulk-copying Jodie, Struct, Quartr, EarningsCall.ai, or expired EquityDesk access;
- a new standalone application, auth system, billing plan, transcript database, publisher, or chat runtime;
- Quartr-scale 65-market coverage;
- five-second live transcription and universal audio;
- full global issuer crawler coverage;
- in-house consensus-estimate reconstruction;
- a long article for every filing or call;
- two SEO URLs with duplicate transcript/analyze intent;
- opaque sentiment, confidence, operating-quality, or theme scores presented as alpha;
- 13-F as a fresh-flow or directional signal;
- discovered co-movement or relationships as automatic capital deployment;
- LLM-originated rank, size, gate, trade, or Prophet escalation;
- article generation inside nightly render;
- raw licensed corpus in browser-public R2;
- universal OCR and slide ingestion in the first release;
- generic collaboration/workspace features before evidence quality and user demand.

### 18.3 Relationship to the three evidence dockets

- The Jodie/Struct docket remains the detailed reverse-engineering, marketing, and method evidence.
- The Quartr docket remains the detailed event/content lifecycle, search, Timeline, Topics, Mentioned By, slides, contract, and commercial evidence.
- The EarningsCall.ai docket remains the detailed transcript/search architecture, analysis-type inventory, SEO estate, frontend/API behavior, and quality audit.
- This docket is the sole active implementation sequence. Builders should cite the appendix that informs their lane but follow this docket's contracts, authority, phase, and exclusion decisions.

---

## 19. Final recommendation

**Build it.** The economics are favorable enough that declining the suite on token or infrastructure grounds would be a category error: the same event object improves paid research, ticker dossiers, Stage, Neural Web/Brain context, public search acquisition, X distribution, alerts, and short form. A standalone Jodie-sized subscription need not pay for the data plane because Mastermind already owns the surfaces that compound its value.

But build the evidence-addressed Company Event Spine first, not a gallery of competitor features. Mastermind should be able to ingest an event once, know exactly when every source became available, preserve every correction, calculate every number deterministically, attach every narrative claim to a receipt, and then let the rest of the system exploit that truth.

That gives Mastermind three advantages the individual competitors do not combine:

1. **A premium primary-source research product:** transcript archive, search, event digest, Timeline, Topics, Mentioned By, relationships, slides, and cited Brain.
2. **A richer intelligence substrate:** event and narrative context joins directly into sectors, themes, price, flow, dossiers, Neural Web, and governed Prophet research.
3. **A low-marginal-cost acquisition engine:** the same corrected digest produces useful ticker pages, earned articles, charts, X posts, alerts, and short form without redoing the research.

The thin clone is easy. The durable system is hard. The hard part—identity, rights, source spans, correction replay, and operating health—is also the part that becomes a moat.

The immediate order is binding:

1. preserve the shipped Stage and Terminal repair contracts;
2. preserve and monitor the now-commissioned continuous forward adapter so manual backfill stays ended;
3. review, merge, deploy, and production-prove the locally validated Chronicle/Brain/Press/X consumer bridge;
4. freeze the golden corpus and complete experience architecture;
5. build identity → event → document → span contracts;
6. produce deterministic facts, one structured extraction, and one cited digest;
7. put the premium Mastermind-native experience in the Terminal and compact context in Brain/Neural Web;
8. add narrative, relationships, and residual-theme joins;
9. fan approved canonical stories into public SEO and X;
10. add slides and any Prophet authority only after their separate gates pass.

If scope must be cut, cut global coverage, live audio, consensus, slides, and article volume. Do not cut identity, point-in-time timestamps, source receipts, corrections, health, rights, evaluation, or experience quality. Those are the product.

---

## 20. Status ledger

Update this table with PR and live evidence as lanes actually complete. “Implemented locally” is not “shipped.”

| Lane | State at 2026-08-01 memo refresh | PR / merge / live evidence |
|---|---|---|
| REPAIR-S Stage recovery | **Shipped/live:** corrected v3 generation `ready`/manifest-valid; 50,982 accepted history rows; 3,529 listing views; latest call date 2026-07-31; 17 fiscal anomalies quarantined; zero invalid QoQ joins | Macro [#4181](https://github.com/chriswong6031-creator/macro/pull/4181); responsive follow-up [#4187](https://github.com/chriswong6031-creator/macro/pull/4187); [live Stage](https://www.mastermind-x.com/stage_analysis.html) |
| REPAIR-T Terminal transcript discovery | **Shipped/live:** 25,438 transcript bodies, 25,438 revision hashes, and 25,438 dates across 3,288 symbols in the live index generated `2026-08-01T14:41:55Z`; per-ticker Transcripts UI and evidence-bound speaker roles live | Terminal [#295](https://github.com/chriswong6031-creator/mastermind-terminal/pull/295); role repair [#299](https://github.com/chriswong6031-creator/mastermind-terminal/pull/299); revision/date producer [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303); [live Terminal](https://app.mastermind-x.com/terminal) |
| FORWARD-E Terminal-to-earnings adapter | **Merged, deployed, and commissioned for the current causal backlog:** generation `90595cb8924f2ef3992f4e16` atomically promoted at 09:07 America/Vancouver with 3,620 score rows/3,558 tickers and 50,982 history rows/3,529 tickers; latest causal call date 2026-07-31. The completed drain attempted 29, succeeded on 28, and leaves only future `HCM/2026Q2` pending by `source_future_call_date`. R2 reports current; ops clone clean; launchd last exit 0; 17:45/20:45/23:45 schedule loaded; bootstrap `--check` passes. | Terminal [#303](https://github.com/chriswong6031-creator/mastermind-terminal/pull/303); Macro [#4192](https://github.com/chriswong6031-creator/macro/pull/4192), merge `903cca72892ba4d1c0e27856ad1d7d270cb5b3ed`; telemetry/appliance hardening [#4201](https://github.com/chriswong6031-creator/macro/pull/4201), merge `fdd75709f79dbd19a6456ff1b954e3e9dec89d1a` |
| CEI-C Chronicle/Brain/Press/X bridge | **Implemented and post-rebase validated locally; not shipped:** committed causal/revision-aware Chronicle projection, latest cited Brain packet, correction-safe Press staging/emission, and deterministic correction-safe X derivative. No X scheduler is armed. | Local branch `codex/earnings-consumers-integrated-20260801`; 477 focused and 1,794 broad tests passed; compile and diff checks clean; no PR at memo refresh |
| CEI-00A rights/source decision | Current corpus and intended redistribution posture resolved; retain the gate for any newly added source | User-authorized program constraint; per-source evidence remains required for expansion |
| CEI-00B golden corpus | Not started | — |
| CEI-00C experience architecture | Not started | — |
| Remaining CEI-01 through CEI-18 work | Roadmap, excluding the partial CEI-C implementation recorded above | — |

### Evidence links

- [Jodie Method](https://jodie.ai/method)
- [Jodie Methodology](https://jodie.ai/methodology)
- [Jodie Pricing](https://jodie.ai/pricing)
- [Jodie Data License](https://jodie.ai/data-license)
- [Struct](https://struct.news/)
- [Quartr Pro](https://quartr.com/products/quartr-pro)
- [Quartr API](https://quartr.com/products/quartr-api)
- [Quartr legal terms](https://quartr.com/legal)
- [EarningsCall.ai](https://www.earningscall.ai/)
- [EarningsCall.ai transcript search architecture](https://www.earningscall.ai/blog/How-We-Built-Our-Earnings-Call-Transcript-Search-Stack)

Detailed citations, source snapshots, frontend observations, methodology reconstruction, terms, cost references, and competitor-quality audits live in the three evidence appendices linked at the top of this docket.
