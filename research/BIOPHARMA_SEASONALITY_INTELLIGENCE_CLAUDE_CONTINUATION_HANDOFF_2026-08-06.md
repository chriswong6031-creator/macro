# Biopharma Seasonality Intelligence — Claude continuation handoff

| Field | Binding value |
|---|---|
| Status | Canonical execution handoff; implementation is sequenced below and authority remains shadow/unapproved |
| Decision | Extend the shipped Calendar Clock and Neural Web shadow lobe; do not rebuild them |
| As of | 2026-08-06 |
| Audited baseline | `origin/main` at `981d8851e0b43c89532be54e3488a2bd8e57dccc` |
| Audience | Claude/Fable commissioner, builders, reviewers, and operator |
| Canonical execution file | **SUPERSEDED for status/sequencing** by `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_CONTINUATION_HANDOFF_2026-08-07.md` (Waves 1-7 implemented 2026-08-07). This file remains authoritative for §1 binding gates, §13 exclusions, and all statistical/product law. |
| Detailed product and statistical specification | `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md` |
| Binding cross-program seam | `research/SEASONALITY_BIOCATALYST_INTEGRATION_SEAM.md` |
| Shipped Calendar Clock design contract | `research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md` |
| Historical operational baton | `research/SEASONALITY_PROGRAM_HANDOFF_2026-08-02.md` |
| Clean-room boundary | Public behavior, separately licensed/public data, and published methods only |
| Authority ceiling | Shadow/context only; no positive decision authority |

> **Precedence.** This file supersedes the current-state claims and remaining-work
> sequence in the August 1 Seasonax docket and the August 2 operational handoff.
> Those files remain authoritative for the teardown, formulas, UI research,
> original product design, and historical implementation evidence. If status or
> sequencing differs, this file wins. Claude must still re-query `origin/main`,
> open PRs, source rights, and live artifacts at the start of every wave.

---

## 0. Executive directive

The program is not at “foundation only.” The honest calendar product and its
first Neural Web connection are already live. The remaining job is to turn that
descriptive base into a point-in-time, event-aware, probability-calibrated,
operator-grade biopharma research system without laundering calendar patterns
into trading authority.

Do not restart the Seasonax investigation. Do not create a second calendar
engine, a second ClinicalTrials/FDA collector, a Seasonality-owned security
master, a parallel validation constitution, a second user-state store, or a
second Prophet selector. Extend the canonical implementations named here.

The build has three distinct finish lines:

1. **Product completion:** contracts, data planes, engines, interfaces, APIs,
   ledgers, monitoring, and honest unavailable states exist and run.
2. **Evidence accrual:** prospective predictions and outcomes accumulate under
   frozen versions and predeclared horizons. Nightly remains the sole forward-
   ledger advancer.
3. **Authority promotion:** a separate review may increase authority only after
   preregistered point-in-time evidence clears the applicable gate. Product and
   context work do not wait for promotion, and product completion is not itself
   promotion evidence.

First freeze and land the W1B input schema plus pointer/receipt contract under
the BioCatalyst owner. The immediate next **Seasonality** slice is W2A0, a
contract-only `biopharma.event.v2` temporal model; W2A's dark, fail-closed
consumer adapter follows in another fresh PR. Neither creates a live graph or
new collector. W1A identity work and the W1B live producer/transport
implementation can continue in parallel after the schema is pinned.

---

## 1. Binding gates

### 1.1 Clean-room and no-rediscovery gate

- Never copy Seasonax source, CSS, text, assets, icons, formulas, data, private
  endpoints, or bulk outputs.
- Never call Seasonax from production or use its account as a data source.
- Functional parity means independently solving the same user jobs.
- Preserve the evidence labels in the detailed dossier: official, observed,
  inferred, or target design.
- Do not repeat competitor forensics unless a specific unresolved product job
  requires fresh public evidence.

### 1.2 One-writer and transport gate

- BioCatalyst owns clinical and regulatory source acquisition, immutable
  receipts, revision history, and its public/private read projection.
- The market-data/security plane owns issuer/security identity, ticker history,
  corporate actions, listings, and historical membership.
- Terminal/Supabase owns saved patterns, watchlists, baskets, alerts, and other
  tenant state.
- Neural Web owns cross-lobe context and authority. Prophet owns selection,
  ranking, geometry, and trade-plan lifecycle.
- Seasonality owns only calendar/event/regime measurement, market-response
  forecasts conditional on those clocks, its product projections, its shadow
  state, and its consumer adapters. It never owns clinical event-timing or
  clinical/regulatory outcome probabilities.
- Do not make the Mac Studio scrape the authenticated user-facing BioCatalyst
  API. The cross-host seam must be a producer-owned, versioned, bounded machine
  projection: preferably an immutable private BioCatalyst R2 artifact plus a
  receipt-bound pointer and read-only consumer credential. A reviewed internal
  service endpoint with machine authentication is an acceptable fallback. The
  existing `site_full` user route is not.
- `known_at` maps from BioCatalyst `transaction_from`, never from
  `knowledge_cutoff`. Unknown or conflicting time semantics are quarantined.

### 1.3 Point-in-time and provenance gate

Every real observation or forecast must bind, as applicable:

- canonical issuer, security, program, trial, indication, and source-native ID;
- effective time, published time, retrieved/ingested time, first-seen time,
  transaction interval, and the exact knowledge cutoff;
- source URI, source class, raw/content hash, parser version, projection
  version, and data snapshot hash;
- date precision and bounds rather than a fabricated exact day;
- corporate-action and adjustment vintage;
- membership/listing interval, liquidity rule, coverage class, stale state,
  contradiction state, and quarantine reason; and
- the exact trial family, model/calibration version, and outcome policy.

Unknown, unavailable, unresolved, censored, stale, contradicted, or
not-yet-observed are output states. None may silently become zero, neutral,
no-event, a current ticker join, or a midpoint date.

### 1.4 Statistical gate

- The unit of independence is a year, issuer, event cluster, conference/date
  cluster, or another preregistered cluster—not a chart point.
- Register the complete hypothesis family before inspecting winners.
- Calendar scans retain their independent per-year circular-shift maxT null and
  BY sensitivity. Do not revert to the stale synchronized-shift wording.
- Event work must use time-aware AR/CAR, event-induced variance treatment,
  rank-based sensitivity, issuer/time clustering, contamination flags,
  matched/placebo controls, costs, and date perturbations.
- `DNR:LAW-TIME-CLUSTERED-CI` forbids ticker-cluster-only confidence intervals.
- `DNR:LAW-ERA-SPLIT` requires an era split when the evidence spans the 2010
  structural break. A post-2010-only panel must disclose that missing regime
  evidence rather than invent an impossible split.
- Use the genuinely generic primitives in `engine/validation.py` and
  `engine/trial_ledger.py`; extend or extract a shared primitive only after its
  reuse is proven. `engine/event_window.py` is a macro-calendar module, not the
  biopharma event-study extension seam, and remains unchanged.
- A historical up-share with a Wilson interval is not a calibrated forecast.
  The UI/API must preserve that distinction.
- A challenger stays shadow unless chronological OOS performance, holdouts,
  calibration, perturbations, and economics beat a declared baseline.
- Thin, stale, extrapolative, structurally broken, or unestimable cases abstain.

### 1.5 Authority gate

The current authority ceiling is binding: all decision-authority booleans are
false, while the two context behavior flags remain true:

- may explain: yes;
- may flag attention: yes;
- may rank, gate, size, originate, rewrite geometry, or boost confidence: no;
- may de-escalate: no; current calendar/event-window constructions are not
  eligible for that gate.

Positive seasonality is narrative/context only. It cannot create a candidate,
improve candidate order, lift conviction, enlarge size, loosen invalidation, or
alter option structure. `DNR:KILL-LLM-ORIGINATION`,
`DNR:KILL-POSITIONING-FUSION`, `DNR:KILL-OFFHORIZON-VERDICTS`, and
`DNR:KILL-CALENDAR-GATED-RISK` apply.

The dormant `CAP_CONFIDENCE` contract branch is a fail-closed schema shape, not
authorization. Under `DNR:KILL-CALENDAR-GATED-RISK`, calendar or event proximity
alone may never cap Prophet confidence or change a risk state. Do not build or
enable that action in this program under current law. Reopening any genuinely
non-window adverse de-escalation construction requires an explicit architecture
ruling that reconciles the DNR, then a separate preregistration, evidence gate,
contract migration, and authority PR. A narrative overlay and an authority
change must never share a PR.

### 1.6 UI and product gate

- Keep one seasonality operating system. Extend `stock_seasonality.html`; do
  not create a separate catalyst, screener, or pattern-finder page unless a
  later architecture ruling explicitly changes the shell.
- Keep `seasonality.html` separate: it is the older Ken French factor-climate
  page, not the instrument Calendar Clock.
- User-facing waves must read `docs/DESIGN_DOCTRINE.md`, use the repo's
  frontend-design workflow/skill, commit production-shaped reference states,
  and receive independent browser/visual review.
- Design dark/light, EN/ZH, desktop/tablet/mobile, keyboard, touch, screen-reader,
  reduced-motion, loading, empty, stale, partial, outage, conflict, historical,
  and recovery states before implementation.
- The five-second view must answer: what is the setup, how much evidence exists,
  what was searched, what the system is watching or what would update the read,
  and what research action comes next. Formal falsifiers/invalidation stay in
  Calibration Lab, methodology, and receipts—not front-facing copy.
- Never show a causal claim where the engine measured association.
- Never render synthetic fixtures as live facts or use placeholder scores.

### 1.7 Operations and freshness gate

- Heavy scans, resampling, fitting, and backfills stay off the render path.
  Publish bounded artifacts to the appropriate private/public store.
- Forward ledgers are append-only and nightly is their sole advancer.
- Every source or model lane needs cadence, rights status, watermark, retry,
  idempotency, dead-letter/quarantine, freshness budget, last-good behavior,
  incident state, and rollback/replay proof.
- Target cadences are contracts, not current claims: calendar artifacts nightly
  after adjusted prices; event projections after complete BioCatalyst source
  runs; public/UI projections after their producers; model refits weekly or
  monthly off render; outcome grading nightly at declared horizons.
- Never flip `live_event_graph`, `live_forecasts`, or `live_screener` merely
  because code merged. Flip only after real production artifacts and their
  exact anonymous/authenticated boundary checks pass.

### 1.8 Delivery gate

Each implementation lane uses a fresh worktree and branch from current
`origin/main`, stages only its paths, passes focused and downstream tests,
pushes, opens a PR, clears genuine CI failures, squash-merges, verifies
`origin/main`, waits for the required render/deploy, checks production ancestry,
and smoke-tests the exact changed surface. One governed deliverable per PR.

Never combine source ingestion, model fitting, flagship UI, and authority in a
single PR. Shared high-collision files—`.github/workflows/daily.yml`,
`config/dag.yml`, `config/synapse.yml`, `docs/SIGNAL_BUS.md`, Caddy, and
`config/site_access.yml`—belong in small, late wiring PRs rebased onto fresh
main.

---

## 2. Current state freeze — extend this, do not rebuild it

Audit snapshot: `origin/main` at `981d8851e0b`; no open PR with “seasonality”
in its title was found at the handoff audit. Re-run the live census because the
repo has many adjacent active lanes.

| Capability | State | Canonical implementation | Preserve / remaining |
|---|---|---|---|
| Clean-room contracts | Shipped in #4193 | `engine/seasonality/contracts.py`, `foundation.py`, `multiplicity.py` | Preserve authority ceiling and bitemporal validators |
| Calendar panel | Shipped in #4235 | `engine/seasonality/panel.py`, `calendar.py` | Complete-year discipline exists; PIT adjustment and dead-name history do not |
| Window family | Shipped in #4235 | `engine/seasonality/scanner.py` | 2,645 fixed windows, 5–90 day horizons, stability and lookback panels exist |
| Selection accounting | Shipped in #4235 | `scanner.py`, `multiplicity.py`, `data/seasonality/selection/` | Independent per-year circular-shift joint maxT and BY sensitivity exist; broader TrialLedger/OOS/SPA program does not |
| Nightly builder | Shipped | `scripts/build_stock_seasonality.py`, workflow/DAG entries | Runs before the shadow emitter; heavy entity tree publishes to R2 |
| Public Calendar Clock | Shipped in #4236; polished through #4598 | `templates/stock_seasonality.*`, `scripts/build_stock_seasonality_page.py`, `site/stock_seasonality.*` | Keep and extend the shell |
| Public data | Live | `site/seasonalitydata/index.json`, `entities/<SYM>.json`, `methodology.json` | Snapshot has 224 entities; 35/224 raw and 24/223 market-neutral symbols have registered-family per-symbol FWER `p <= 0.05`; across-symbol multiplicity is disclosed, not controlled |
| Neural Web shadow lobe | Shipped in #4370 | `engine/seasonality/state.py`, `scripts/build_seasonality_shadow_state.py`, `engine/neuralweb/mastermind_context.py` | 28 Health Care states, 48h expiry, context-only candidate annotations |
| Forward ledger | Live, immature | `data/seasonality/nw_forward_ledger.jsonl` | 28 registrations and zero matured grades at audit; keep accruing |
| Methodology truth | Correct | `site/seasonalitydata/methodology.json` | Calendar + selection correction true; forecast, screener, and event graph false |
| Factor climate | Separate existing product | `engine/factor_seasonality.py`, `site/seasonality.html` | Do not merge or replace it |
| BioCatalyst seam | Contract exists | `research/SEASONALITY_BIOCATALYST_INTEGRATION_SEAM.md` | Real machine transport and Seasonality adapter remain absent |
| Prophet overlay | Contract only | `build_prophet_overlay` / `validate_prophet_overlay` in `contracts.py` | No operational bridge, snapshot, or experiment |

### 2.1 What the Calendar Clock already does

- 365-slot annual normalization with explicit leap-day and missing-session rules;
- complete-year panel and capped lookbacks;
- raw, market-neutral, and detrended views;
- month, weekday, and trading-day summaries;
- draggable date window, yearly strands/window fan, current-year overlay, and
  discovery panels;
- 10/15/25/max lookbacks and lookback-specific nulls;
- bilingual, responsive, keyboard-aware public workstation; and
- explicit program-level false-discovery context rather than a lone winner.

### 2.2 What is still not built

- a true PIT price/universe/corporate-action spine with delisted, acquired,
  renamed, and historically eligible names;
- `engine/seasonality/event_clock.py` and `event_study.py`;
- a producer-owned BioCatalyst machine projection and PIT issuer/security join;
- a real catalyst graph/timeline and event-relative research engine;
- chronological OOS/SPA/Reality-Check governance for the full product;
- `model.py`, `calibration.py`, persistent prediction/calibration artifacts, or
  a calibrated market-response probability/distribution product;
- lawful regime-conditioned forecasts;
- real calendar-versus-event contradiction and momentum/covariance overlap;
- an Ask Brain/Cortex seasonality reader;
- `engine/seasonality/prophet_bridge.py` or a Prophet plan attachment;
- an honest cross-symbol screener/API;
- compare overlays, saved patterns/calendar, baskets, uploads, alerts, exports,
  portfolio event clustering, options-event geometry, or enterprise workflows.

The state payload's `p` is a historical positive-year share against a
same-length all-starts baseline. Its Wilson interval is uncertainty around that
descriptive share. It is not a live calibrated forecast. The legacy v1
`forecast.p` semantic is permanently frozen as `historical_up_share`; no
calibrated value may ever occupy that field. Any calibrated market-response
probability requires a v2 schema with a separately named and typed estimate
object plus a dual-read migration.

---

## 3. Remaining-work verdict and dependency graph

The fastest honest route is not a monolithic “complete Seasonax clone.” It is
two truth-plane prerequisites, then event evidence, then product/model/context
layers. Display-tier work can proceed while forward evidence accrues, but the
screener and authority gates remain downstream of PIT data and OOS calibration.

```text
SHIPPED S0  Calendar Clock + selection accounting + NW shadow base
   |
   +--> W1B producer schema/pointer --> W2A0 event temporal v2 contract
   |                                      |
   |                                      v
   |                                W2A dark adapter
   |                                      |
   |                                W2B fixture harness
   |
   +--> W1A PIT identity/price -----------+
   +--> W1B live producer/bytes ----------+--> W2B real-data/OOS studies
   |                                                   |
   +--> W3 calendar UX parity                         v
   |                                         W2C live Catalyst mode
   |                                                   |
   +---------------------------------------------------+
                                                       v
                                    W4 calibrated market-response forecasts
                                                       |
                                          +------------+-------------+
                                          v                          v
                                    W5 Neural Web v2          W7 screener/API
                                          |
                                          v
                                    W6 Prophet shadow
                                          |
                                          +--------------------------+
                                                                     v
                                                            W8 advanced frontier
```

### 3.1 PR-sized lane map

| ID | Deliverable | Primary owner/paths | Required proof |
|---|---|---|---|
| W0 | Fresh census and executable dependency freeze | docs/ownership/config only | Current main/PR audit; exact producer/consumer contracts; no duplicate owner |
| W1A | PIT security/universe/corporate-action read contract | canonical market-data/security owner; Seasonality consumes | Historical `asof` replay, ticker-change/split/delist fixtures, rights and vintage |
| W1B | BioCatalyst Seasonality event projection contract | BioCatalyst-owned schema/producer/transport | Pointer-bound immutable bytes, `transaction_from`, coverage and quarantine |
| W1C | Seasonality PIT panel consumer | `universe.py`, `panel.py`, stock builder | No current-ticker join; no survivorship claim; deterministic snapshot |
| W2A0 | Versioned event temporal contract | `engine/seasonality/contracts.py`, foundation tests | v1 unchanged; precision plus lower/upper bounds; no fabricated time |
| W2A | Dark event adapter | `event_clock.py`, contracts/tests | Pinned W1B/W2A0 inputs; pure injected bytes; no network/writes/live flag |
| W2B | Event-study core | `event_study.py`, existing validation/trial-ledger primitives | Cluster/time inference, full family registration, OOS/holdout/cost tests |
| W2C | Real event projection + Catalyst UI mode | producer artifacts, existing stock-seasonality shell | Real rows, provenance/revisions/precision, live boundary and visual matrix |
| W3 | Workstation parity excluding screener | existing shell + Terminal/Supabase adapters | Compare/save/basket/upload/calendar/alert/export jobs with honest states |
| W4 | Calibrated market-response forecasts and lawful regime features | `model.py`, `calibration.py`, forecast/outcome stores | Frozen OOS predictions, baselines, calibration, abstention, drift |
| W5 | Multi-clock Neural Web completion | existing state emitter/context/cortex/covariance seams | No origination; compact expiring state; contradiction and overlap measured |
| W6 | Prophet narrative/attention overlay | Seasonality bridge + existing Prophet bridge/build | Post-selection, all numeric/ordering invariants byte-identical |
| W7 | Honest screener and API | screener engine, API, existing shell | PIT universe, global selection accounting, calibrated disclosures, entitlement |
| W8 | Advanced biopharma edge and commercial hardening | options/analogue/portfolio/ops lanes | Separate gauntlets, licensed data, telemetry, no authority shortcut |

---

## 4. Wave 0 — re-freeze status and ownership

### Objective

Turn this handoff into an executable assignment against the latest code and
runtime. This is a short control step, not another research project.

### Required actions

1. Fetch current `origin/main`; inspect `docs/ACTIVE_BUILD_MAP.md` and
   `research/DO_NOT_REBUILD.md`; regenerate the active map only through its
   builder if a task requires it. Never hand-edit the generated map.
2. Query live open PRs and worktrees for collisions on Seasonality,
   BioCatalyst, identity, daily workflow, Synapse, site boundaries, and Prophet.
3. Re-read the four canonical files named in the metadata table.
4. Confirm current public artifacts and the shadow ledger counts.
5. Freeze the exact producer/consumer transport for W1B in a short ADR or
   contract note before building it.
6. Name one owner per PR and keep engine/contracts, runtime wiring, UI, and
   authority changes separate.

### Exit gate

The lane brief names its user job, non-goals, writer and readers, source rights,
clock semantics, schema/version/migration, authority ceiling, failure fixtures,
focused/downstream tests, activation state, and live verification plan.

---

## 5. Wave 1 — truth-plane prerequisites

W1A and W1B can run in parallel under their canonical owners. W1C consumes
W1A. Do not pause display/context infrastructure while these dependencies are
being built, but do block the cross-symbol screener and any promotion claim.

### 5.1 W1A — PIT security, universe, and corporate-action contract

**Owner:** the existing market-data/security plane, not Seasonality.

This is a real cross-program blocker, not an already callable plane.
`config/sector_intelligence_ownership.yml` currently marks
`biocatalyst_security_identity_pit_adapter.v1` as
`unavailable_bootstrap_roster_only`, with `module`/`callable` null and blocker
`complete_point_in_time_security_and_corporate_actions_contract`.
`collectors.symbol_directory` is explicitly a bootstrap roster, not an
acceptable PIT implementation or fallback.

Required output:

- stable issuer and security IDs;
- effective-dated ticker/listing/exchange mappings;
- split, dividend, merger, spin, rename, delist, and acquisition versions;
- historical biopharma/index membership and delisted/dead-name coverage;
- trading calendar, price basis, adjustment vintage, currency, liquidity, and
  snapshot hash; and
- an arbitrary-`asof` read adapter with explicit unavailable states.

Seasonality-side implementation, after the contract exists:

- add `engine/seasonality/universe.py`;
- extend `engine/seasonality/panel.py` and
  `scripts/build_stock_seasonality.py`;
- evolve `config/seasonality_universe.yml` from a current coverage catalog into
  a consumer configuration, not an identity source;
- add `tests/test_seasonality_pit_spine.py`; and
- remove methodology limitations only after replay proof closes them.

Acceptance cases:

- split and special-dividend vintage changes;
- ticker rename with one stable security ID;
- acquired/delisted name present in historical membership;
- listing gap and dual-class ambiguity;
- QUBT-like dormant shell handled by a declared liquidity/identity rule, never
  a ticker blacklist;
- no current ticker or current sector can leak backward; and
- current-vintage artifacts remain explicitly labeled until migration ends.

### 5.2 W1B — BioCatalyst machine event projection

**Owner:** BioCatalyst writes; Seasonality reads.

Preferred contract:

- a bounded `biocatalyst_seasonality_event_projection.v1` generated only from a
  committed BioCatalyst generation;
- a versioned JSON Schema, at least one canonical valid fixture, adversarial
  invalid fixtures, and a frozen pointer/receipt contract must merge before
  W2A starts; the live producer may follow;
- immutable projection bytes, content hash, generation ID, coverage epoch,
  created time, last complete source run, and manifest/pointer binding;
- source-native IDs, event/revision lineage, exact system transaction/retrieval
  timestamps, original source temporal values, date precision, lower/upper
  bounds, source URI/hash, contradiction state, and rights/redistribution class;
- private R2 publication under BioCatalyst credentials and a distinct read-only
  consumer identity for the Mac Studio; and
- no issuer/security/ticker field unless the reviewed PIT identity adapter
  supplied it.

Likely owner paths are `contracts/biocatalyst/`, a bounded producer in
`engine/biocatalyst/`, `config/sector_intelligence_ownership.yml`, fixtures, and
BioCatalyst tests. Exact names must follow the current BioCatalyst generation
contract; do not casually expand its public user API or weaken its atomic
publisher.

Inventory `engine/biocatalyst/sector_packet.py` first. It already compiles a
bounded, attested, facts-only `sector_intelligence_packet.v1`; it is neither the
required event view nor a live cross-host transport. W1B must reuse or extend
its bounds, canonical-byte attestation, authority, and pointer-binding pattern,
or write an ADR explaining why a distinct event view is required and how it
avoids a second competing read plane.

The first allowed source classes are only those whose real, current rights and
projection gates pass. ClinicalTrials current facts, exact history, prospective
first-seen rows, Drugs@FDA, openFDA, PDUFA, issuer announcements, and conference
events must each preserve their actual coverage. A dark source stays dark.

The current `biopharma.event.v1` requires timezone-bearing timestamps for
published/effective time, while BioCatalyst source temporal values may be null,
date-only, year-month, year, or ranges. W1B must pin that mismatch rather than
leaving it to the adapter. The preferred follow-on W2A0 contract-only PR creates
`biopharma.event.v2` with exact UTC system times kept separate from source-time
objects carrying original value, precision, lower bound, upper bound, and
unavailable state. Keep v1 unchanged for exact-timestamp compatibility. If a
different lower-bound indexing convention is proposed, document and test it
without representing the bound as an exact event time.

### 5.3 W1C — Seasonality PIT panel consumption

Preserve the existing curve and page contracts during migration. Dual-publish
or add versioned fields until consumers move; do not silently reinterpret old
numbers under the same schema. The selection cache and source snapshot must be
bound to the same membership and adjustment vintage.

### Wave 1 exit gate

- arbitrary-`asof` membership and event replay is deterministic;
- no source owner is duplicated;
- unresolved identity is quarantined rather than ticker-guessed;
- a source revision cannot rewrite an older known-at view;
- licenses and public/private boundaries are recorded; and
- current-vintage/survivorship disclosures stay true until empirically closed.

---

## 6. Wave 2 — event clock, event studies, and Catalyst mode

### 6.1 W2A0 — versioned event temporal contract

After the W1B producer schema/pointer PR merges, fetch the new `origin/main`
and use a second fresh worktree/branch for this contract-only Seasonality PR.

Extend `engine/seasonality/contracts.py` and its foundation tests with
`biopharma.event.v2` while leaving the v1 validator/builder unchanged. The v2
contract keeps exact UTC `known_at` and `ingested_at` separate from source
temporal objects. Each source temporal object carries:

- original source value or explicit unavailable state;
- precision (`exact_time`, `exact_date`, `month`, `quarter`, `year`, `range`,
  or `unknown`);
- lower and upper bounds in a representation appropriate to that precision;
- source timezone only when the source supplied one; and
- the rule used to derive bounds, never a fabricated midpoint/exact time.

Require ordered bounds, compatible precision/value types, and a usable
effective-time bound for event-study eligibility. Preserve unknown publication
time as unknown; the exact system knowledge clock still governs leakage.
Include round-trip, canonical-hash, date-only, partial-date, range, timezone,
leap-day, null/unavailable, invalid-bound, and v1-compatibility tests. This PR
contains no BioCatalyst producer, adapter, data, workflow, or public flag.

### 6.2 W2A — dark event-clock adapter — after W1B and W2A0 contracts are pinned

Create:

- `engine/seasonality/event_clock.py`;
- `tests/test_seasonality_event_clock.py`; and
- only the additive contract/ownership declarations required for a read
  consumer.

The adapter accepts injected canonical BioCatalyst projection bytes or a typed
reader. It has no network client, source collector, local source store, or
workflow entry. It maps eligible facts into the pinned Seasonality event
contract—normally `biopharma.event.v2`—and produces a structured quarantine
ledger for everything it refuses. It never coerces partial source dates into v1
midnight timestamps.

Binding mapping:

- `known_at <- transaction_from`, never `knowledge_cutoff`;
- `ingested_at <- retrieved_at`, subject to the event contract's timestamp
  ordering check;
- source-published and effective values map to typed temporal objects preserving
  original value, precision, and lower/upper bounds; exact instants remain
  instants, exact dates remain date bounds, and partial/range values never gain
  a fabricated time or midpoint;
- an unavailable source-published value remains explicitly unavailable while
  the exact system `known_at`/`ingested_at` still enforce anti-leakage; an event
  with no usable effective-time bound is quarantined from event study;
- `issuer_id` comes only from the reviewed PIT identity adapter; unresolved is
  quarantine, never a ticker inference;
- `event_id` derives deterministically from source-native event and revision
  identity, never presentation order or current ticker;
- `event_type` and `status` use an explicit versioned allowlist; unknown values
  quarantine rather than collapsing to “other” or “active”;
- `date_precision`, `scheduled_start`, and `scheduled_end` preserve the source
  precision and bounds without midpoint synthesis;
- `source_hash <- canonical_content_sha256` with `sha256:` prefix;
- source URL/class resolve through the registered source attribution; and
- certainty/status never manufacture clinical meaning from registry fields.

Adversarial tests must cover null publication time, future effective date,
after-hours time, month/quarter/range precision, correction/retraction,
conflicting revisions, unresolved issuer, duplicate event, corrupt hash,
unknown schema, stale generation, path traversal, oversized payload, and replay
determinism.

Because W1A is still blocked, include one explicitly synthetic,
identity-resolved compatibility fixture solely to exercise W2A's success path.
Mark it `fixture_only` and non-publishable. Pair it with unresolved-identity
quarantine fixtures; never introduce a live ticker map to make the test pass.

`DNR:KILL-PHASE3-START-WEIGHT` is binding: Phase-3 START may remain a
display/context chip but cannot become a scored leg. HALT remains an open
caution hypothesis only when Record History supplies a real halt-onset time.

This PR must not edit collectors, enable a source, create ticker inference,
write public artifacts, wire a workflow, or set `live_event_graph=true`.
It also must not edit `engine/biocatalyst/**`, `collectors/biocatalyst/**`,
`contracts/biocatalyst/**`, or `config/biocatalyst_*.yml`; W1B owns those paths.

### 6.3 W2B — event-study and research-governance core

Create/extend:

- `engine/seasonality/event_study.py`;
- existing generic `engine/validation.py` primitives;
- existing `engine/trial_ledger.py`;
- `scripts/build_seasonality_event_studies.py`;
- `tests/test_seasonality_event_study.py`; and
- versioned research artifacts under `data/seasonality/` for hypotheses,
  patterns, outcomes, and run receipts.

Required mechanics:

- two explicitly separate estimands: (a) an ex-post reaction study around a
  realized effective event and (b) an ex-ante tradable forecast using only
  schedules and facts known before the decision timestamp; realized outcomes
  and revisions may never leak into the ex-ante feature cut;
- every ex-ante row freezes `prediction_issued_at`, the exact feature snapshot,
  risk set, event/outcome policy, and availability receipt; execution is the
  next eligible tradable bar after the maximum of the decision cutoff and every
  source fact's `known_at`/published/available timestamp;
- exchange-session event mapping with before/after-close policy only when time
  precision supports it; month, quarter, and range observations require
  interval/range sensitivity or abstention, never midpoint imputation;
- raw, SPY, XBI, and IBB abnormal returns where licensed and eligible;
- AR/CAR and distribution/barrier/drawdown targets;
- BMP/event-induced-variance treatment and Corrado/rank sensitivity;
- issuer and date/conference clustering with time-clustered resampling;
- matched controls, synchronized cluster bootstrap, placebo dates, contamination
  and overlapping-event flags;
- next-bar execution, spread/slippage assumptions, and ±2/±5-day date
  perturbations;
- chronological walk-forward, purge/embargo, issuer holdout, therapeutic-class
  holdout, and untouched epoch holdout; and
- complete search-family registration before any winner is inspected, with BY,
  joint maxT, SPA/Reality Check, and TrialLedger accounting as applicable.

Before inspection, freeze the primary estimand, direction, horizon, benchmark,
estimation window, risk set, and correction family. Benchmark returns and beta
estimation end before the event cutoff. SPY/XBI/IBB alternatives are declared
sensitivity legs, not a menu from which to select the best result. Each
multiplicity method needs a family-appropriate joint null plus nominal-error
simulation; never stack or choose corrections opportunistically after seeing
the result.

Descriptive build floors—not promotion gates—are at least 50 eligible events,
20 issuers, and 20 date clusters. Events inside those clusters are not called
independent. The real evidence gate is preregistered power/precision and enough
independent time and issuer clusters for the chosen robust estimator, with
confidence bounds and an economically material effect. Use a justified
small-cluster method or abstain when clusters are inadequate. Selection-adjusted
evidence, positive chronological OOS skill/economics versus a declared
baseline, stable folds, and perturbation survival remain required. A fixture-
only implementation can merge earlier but must say `fixture_only`/shadow and
publish no live conclusion.

### 6.4 W2C — commission the event projection and Catalyst mode

Blocked until W1B supplies real projection bytes and identity resolution is
honest enough for a symbol surface.

Backend deliverables:

- versioned index/per-entity event artifacts;
- source and model receipts, freshness/SLA, coverage and quarantine counts;
- Synapse/Signal Bus registration and declared readers;
- atomic publish/last-good behavior; and
- a truthful methodology availability transition only after production proof.

Preserve the current public artifact topology: index, methodology, and the
default entity remain committed/VPS-served; heavy per-entity payloads publish
through the existing R2 `DATA_BASE` pattern. Do not commit the full generated
event tree, expose private BioCatalyst projection bytes, or blur the private
source projection with the bounded public Seasonality view.

Frontend deliverables:

- extend the existing Calendar Clock with Calendar / Catalyst modes;
- use `templates/stock_seasonality.html.j2`, `.css`, `.js`,
  `scripts/build_stock_seasonality_page.py`, matching `site/` artifacts, and
  existing page tests;
- show original date wording, revision history, precision/range, evidence,
  contamination, sample/cluster counts, and abstention; and
- use “historically associated” language, never causal or predictive wording
  unsupported by the artifact.

No synthetic event row, placeholder probability, or fabricated PDUFA calendar
may appear in the live product.

---

## 7. Wave 3 — complete the operator workstation, excluding the screener

This wave can begin on the existing calendar data while W1/W2 progress. Keep
the product display/research-tier and reuse Terminal/Supabase for tenant state.

Build as separate PRs:

1. **Compare:** instrument/benchmark overlays, aligned windows, preregistered
   cohort compare, and explicit covariance/overlap warnings. Post-hoc cohorts
   are labeled exploratory and spend a new search budget.
2. **Pattern browser:** registered discoveries only, full family/search budget,
   stability and lookback evidence, with exploratory windows visually distinct.
3. **Research persistence:** saved patterns, notes, calendars, watchlists, and
   baskets through existing tenant-scoped user-state contracts.
4. **Uploads/custom universes:** isolated licensed/private data, explicit owner,
   no redistribution, schema/quality report, and no mixing with public models.
   Every new cohort/universe spends a new search budget and cannot inherit an
   existing evidence label, null, p-value, or calibration claim.
5. **Calendar and alerts:** idempotent notifications on source revisions,
   approaching windows, stale coverage, and pattern retirement—not “buy” alerts.
6. **Export:** bounded CSV/JSON/PDF research packets carrying methodology,
   provenance, search accounting, freshness, and entitlements.
7. **Missing calendar views:** biotech-neutral comparison and dedicated
   turn-of-month/quarter-end studies where the same honesty rules apply.

Every submode must work with missing event data and cannot imply that a saved or
popular pattern is stronger evidence.

---

## 8. Wave 4 — calibrated market-response forecasts and lawful regime clock

### 8.1 Files and artifacts

Create/extend, using exact names only after the contract freeze:

- `engine/seasonality/model.py`;
- `engine/seasonality/calibration.py`;
- a narrow regime-feature adapter such as `engine/seasonality/regime.py`;
- `scripts/build_seasonality_forecasts.py`;
- `tests/test_seasonality_model.py` and
  `tests/test_seasonality_calibration.py`;
- append-only `data/seasonality/forecasts.jsonl` and outcome ledger; and
- versioned `data/seasonality/calibration.json` plus model/run receipts.

### 8.2 Keep three probabilities and their owners separate

1. **Event occurrence/timing:** whether and when a catalyst is likely to occur;
   BioCatalyst owns this artifact and model if it is ever authorized.
2. **Event outcome:** a clinical/regulatory outcome conditional on an event;
   BioCatalyst owns this artifact and model if it is ever authorized.
3. **Market response:** return, barrier, drawdown, volatility, or distribution
   conditional on the known calendar/event/regime state; this is the only
   probability family Seasonality may train and own.

Seasonality may consume a versioned, calibrated, read-only BioCatalyst timing or
outcome probability as display/context only by default; it never recomputes,
relabels, or trains those clinical artifacts. Using one as a market-response
model feature requires its own preregistration, point-in-time issuance
alignment, model-family/multiplicity accounting, and authority ruling. If the
owner artifact is absent, the UI says unavailable. Do not multiply unrelated
raw scores into one scientific-looking number.

### 8.3 Model ladder

- transparent empirical and shrinkage baselines remain visible;
- market outcomes use hierarchical issuer/event/therapeutic pooling with strong
  shrinkage and an explicit benchmark;
- calibration is fit on prior OOS predictions only;
- challengers may include nonlinear models only after the baseline and frozen
  feature store exist; and
- binary market-response targets return probability, like-for-like baseline,
  edge, and typed uncertainty;
- continuous/distributional targets return expectation and/or quantiles or a
  distribution, plus a like-for-like baseline and edge—not a forced
  probability field; and
- every output returns effective N, issuer and date-cluster counts, extrapolation flags,
  calibration/model version, data cutoff, and abstention reasons.

Every uncertainty field names its semantics: parameter confidence/credible
interval, predictive interval, or outcome quantiles. Do not collapse them into
one generic `interval` label.

Required evaluation includes Brier score, log score, CRPS where distributional,
reliability diagrams, calibration slope/intercept, chronological baseline
comparison, issuer and therapeutic holdouts, drift/break detection, decision
economics after costs, and explicit nulls.

Calibration is strict forward chaining or nested OOS: the calibrator sees only
predictions issued before the scored fold, never the fold it evaluates.
Overlapping horizons use cluster-aware uncertainty. If a future BioCatalyst-
owned occurrence/timing model is consumed, its contract must declare time
origin and risk set and handle left truncation, censoring, competing risks,
interval-censored dates, and only covariates available at issuance; Seasonality
does not implement that hazard model.

### 8.4 Regime law

Consume only explicitly authorized market, biotech, liquidity/rates, issuer,
and volatility fields through reviewed PIT adapters. Do not create another
fused regime score. Positioning and financing keys remain display/context-only
unless a house-law ruling explicitly authorizes the exact model feature; merely
avoiding the name “regime score” does not make positioning fusion lawful.

`DNR:KILL-REGIME-SCORECARD`,
`DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR`, and
`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` apply. An interaction is eligible only
after `engine.regime_conditioning_coverage.assess()` returns `estimable` for
the exact axis and a new preregistration names the interaction as primary. Use
strong hierarchy/shrinkage; otherwise show the regime as context and abstain
from an interaction estimate.

### 8.5 Promotion boundary

At audit the forward ledger has zero matured grades. Historical development and
shadow forecasts may proceed, but neither “live probability” nor authority may
be promoted from an empty forward record. Retire or recalibrate patterns under
predeclared drift rules; never hide a failed champion.

---

## 9. Wave 5 — complete the Neural Web lobe

Extend #4370; do not build a second emitter or candidate join.

Primary paths:

- `engine/seasonality/state.py`;
- `scripts/build_seasonality_shadow_state.py`;
- `engine/neuralweb/mastermind_context.py`;
- read-only additions following `engine/neuralweb/ask_brain.py` and
  `engine/neuralweb/cortex.py`;
- the existing `engine/neuralweb/covariance_spine.py`; and
- current Lane 6 tests plus version-migration fixtures.

Deliverables:

- calendar, event, and lawful regime clocks in one compact state;
- a real contradiction between calendar context and a BioCatalyst-owned,
  authorized event-timing probability when one exists; Seasonality never
  estimates event hazard. When it does not exist, show only known event timing,
  source uncertainty, or an explicit unavailable state;
- measured overlap with momentum, sector, and other existing features, exposed
  as redundancy annotations; context-only Seasonality computes no combined
  weight, discount, or fused score;
- freshness, coverage, conflict, extrapolation, calibration, and abstention;
- Research Factory routing for unstable hypotheses;
- an evidence-bounded read-only Ask Brain/Cortex query; and
- continued nightly registration and horizon grading.

A calibrated market-response estimate categorically requires a versioned v2
state with a separately named/typed estimate object. Multi-clock additions use
that reviewed v2 migration when they change semantics. Dual-read during
migration and preserve v1's permanent historical-up-share meaning until all
registered consumers move. Do not smuggle calibrated or multi-clock semantics
under the v1 `forecast.p` name.

Acceptance:

- the emitter continues to build the full eligible covered Health Care state
  map; only the Mastermind consumer attaches a sparse block to candidates that
  another system already admitted;
- expired/invalid states fail open as structured gaps;
- identical inputs produce identical state and derivation/provenance traces;
- no new name, rank, gate, size, geometry, confidence boost, or trade action;
- all decision-authority booleans remain false; `may_explain` and
  `may_flag_attention` remain the only true behavior flags; and
- positive and adverse context remain visible side by side; the renderer places
  adverse/contradictory context first so it cannot be hidden, while neither
  suppresses, numerically outweighs, or arithmetically fuses with the other.

---

## 10. Wave 6 — Prophet narrative and attention overlay

Create `engine/seasonality/prophet_bridge.py` and extend the existing
`engine/prophet_bridge.py` only after candidate selection. Use the already
shipped `prophet.seasonality_overlay/v1` validator/builder.

Initial actions are only `NONE`, `NARRATE`, and `ATTEND`.

`ATTEND` means a human-facing UI attention marker only. It cannot change a
machine queue, candidate prompt, plan ordering, management, alerts, retraining
set, feature store, future plan decision, or any other feedback path.

Required implementation:

- read only unexpired, contract-valid, non-abstaining Seasonality states;
- join by reviewed PIT security identity and plan `asof`;
- calculate horizon match, event-inside-horizon, and overlap flags;
- attach a bounded overlay after the candidate set and ordering are frozen;
- snapshot the exact overlay/state/model versions without assuming a plan
  field or public projection contract already exists; and
- make absence, expiry, or invalidity equivalent to no overlay.

There is a known workflow-order defect to solve: `build_prophet` currently runs
before the daily cluster containing `build_stock_seasonality` and
`seasonality_shadow`. A same-night overlay needs a reviewed dependency/order
change or an equivalent same-night prerequisite. Preserve the shadow ledger's
single-writer law and keep workflow edits in a small rebased wiring PR.

`prophet.trade_plan/v1` has no established Seasonality overlay field at this
handoff. Before writing plans or ledgers, choose and test either (a) a separate
bounded overlay artifact keyed to immutable `plan_id`—preferred for the first
shadow tranche—or (b) an explicit additive plan-schema migration plus reviewed
public/private projection and entitlement decision. Do not append an
unregistered field or invent a “public whitelist” by convention.

Hard invariant test: with and without the Seasonality overlay, candidate IDs,
candidate order, direction, trigger, target, invalidation, horizon, size,
confidence, option selection, and geometry are byte-identical. Only the bounded
narrative/attention attachment may differ.

Do not create a `CAP_CONFIDENCE` experiment under the current calendar/event-
window construction. The contract branch remains unreachable. Only an explicit
future architecture ruling that identifies a lawful, non-window adverse
construction may authorize a separate preregistration/evaluation harness;
passing that would still require a deliberate contract/authority migration.

---

## 11. Wave 7 — honest screener, API, and functional parity

This wave is blocked on W1 PIT membership and W4 calibrated/OOS artifacts. A
calendar-only research browser may ship earlier, but it must not masquerade as
this screener.

Likely paths:

- `engine/seasonality/screener.py`, reusing the existing per-symbol scanner;
- `app/seasonality.py` plus reviewed router/auth/entitlement registration;
- `tests/test_seasonality_screener.py` and `tests/test_seasonality_api.py`;
- the existing stock-seasonality shell and page tests; and
- the W3 Terminal/Supabase saved-state adapters, reused rather than rebuilt.

Build in order:

1. cross-symbol screener with a declared research utility;
2. a PIT cross-symbol query engine and authenticated versioned API/embed
   contract over the same result schema;
3. entitlement, cache, deterministic-pagination, and incremental-sync layers;
4. integration adapters that reuse W3 compare, Pattern browser, saved-state,
   basket/universe, alert, and export components rather than rebuilding them;
   and
5. live methodology and scorecard surfaces.

Every result row exposes probability or descriptive statistic type, baseline,
edge, typed uncertainty semantics, sample, issuer/date clusters, search family, multiplicity,
costs, OOS epoch, freshness, extrapolation, and abstention. Historical members
and dead names participate where eligible. Ranking may help a user organize
research; it is not Neural Web or Prophet authority and cannot be consumed as a
system score.

Here “ranking” means user-controlled sorting/grouping inside a research-only
schema. It never means engine conviction rank. Descriptive and calibrated
estimate types are not placed on one score axis. Synapse declares no Neural Web
or Prophet score consumer for the screener artifact, and contract tests reject
machine-authority reads.

API requirements include explicit `asof`, deterministic pagination, bounded
payloads, model/data versions, source entitlements, no-store for private data,
incremental synchronization, rate limits, stale/partial states, and identical
server/UI semantics.

---

## 12. Wave 8 — advanced biopharma edge and commercial hardening

Build only after the core product has real ledgers and stable operations:

- options-implied event geometry and scenario distributions from separately
  licensed options data;
- read-only integration of BioCatalyst-owned comparable/analogue artifacts by
  mechanism, indication, phase, endpoint, sponsor, financing pressure, and
  market state; Seasonality does not create the clinical comparable-set owner;
- portfolio event clustering, correlated exposure, overlapping catalyst
  windows, and scenario concentration over tenant/portfolio-owner state;
  Seasonality contributes derived context but owns no portfolio book;
- read-only integration of Corporate/BioCatalyst-owned evidence-span and
  qualitative-claim artifacts with contradiction handling and human
  correction; Seasonality creates no second document/span extraction owner;
- custom enterprise universes, team research workflows, audit logs, and
  entitlement-safe collaboration;
- source/model/freshness/coverage scorecards, incident tooling, replay, backup,
  restore, and retirement workflows; and
- usage telemetry that measures completed research jobs rather than vanity
  clicks.

Each advanced family gets its own contract, baseline, preregistration, forward
ledger, and release gate. “Superintelligence” means better evidence synthesis,
uncertainty, contradiction handling, and learning—not one opaque master score.

---

## 13. Already covered / excluded / never rebuild

### 13.1 Already covered — extend in place

- clean-room Seasonax teardown and product map;
- bitemporal event, Neural Web state, and Prophet overlay contracts;
- BY and joint-maxT primitives;
- Calendar Clock panel, curve, 2,645-window family, selection cache, artifacts,
  and public workstation;
- Neural Web nightly shadow emitter, Mastermind candidate annotation, Synapse
  registration, and forward ledger;
- existing validation, TrialLedger, covariance, Neural Web, and Prophet planes;
  `engine/event_window.py` remains the separate macro-calendar module;
- BioCatalyst collector/contracts, immutable-receipt, current read-model,
  trial screen/history/change-tape, sector-packet, and prospective substrates;
  several lanes remain dark/partial, and these substrates do not imply W1B
  event bytes or live source coverage; and
- Terminal/Supabase tenant state.

### 13.2 Explicit exclusions

- competitor code/assets/private API/data or visual duplication;
- another CT.gov, FDA, openFDA, AACT, conference, filing, price, or corporate-
  action collector owned by Seasonality;
- a Seasonality security master or local user database;
- current ticker joins presented as PIT identity;
- fabricated PDUFA dates, midpoint dates, missing-event zeros, or placeholder
  probabilities;
- a Phase-3 START score (`DNR:KILL-PHASE3-START-WEIGHT`);
- election/midterm seasonality as a standalone signal
  (`DNR:KILL-ELECTION-CYCLE`);
- ad hoc bull/bear cohort filters, combinatorial regime factories, or a new
  composite regime/reliability score;
- a screener ranked primarily by in-sample return or unadjusted win rate;
- positive Seasonality authority over Neural Web or Prophet;
- LLM-created facts, probabilities, scores, escalations, or source timestamps;
- hidden nulls, silent pattern retirement, or “validated” language without the
  repo's guarded evidence; and
- public forecast/screener/event-graph flags before real production proof.

### 13.3 Construction-specific kills are not universal bans

A killed Phase-3 START weight does not ban display of the official registry
event. A killed composite regime score does not ban lawful, estimable regime
context. A null standalone family may remain a confluence/display input. Reopen
only the exact tested construction under its documented prerequisites and a
fresh preregistration.

---

## 14. Parallelization and collision discipline

- W1A and W1B may run in parallel under different canonical owners.
- W2A can proceed against exact fixtures and injected bytes only after both the
  W1B schema/pointer/receipt contract and W2A0 event temporal contract are
  merged and pinned.
- W3 calendar-only UX lanes can proceed while truth-plane work runs.
- W2B begins on fixtures but cannot publish live conclusions before real W1
  data and identity.
- W4 begins after the market-response outcome definition and frozen feature store; it
  remains shadow while evidence accrues.
- W5 follows stable W2/W4 contracts. W6 follows W5.
- W7 waits for W1 PIT data and W4 calibrated/OOS evidence.
- W8 splits by independent source/model family and never blocks core product.

Before every lane, re-run the PR/worktree collision census. Pure contracts and
engines land first. Generated registries, workflows, nav, serving boundaries,
and public artifacts land last in small rebased PRs. Never let two agents own
the same writer or high-collision file.

Every lane brief must name:

- the user job and explicit non-goals;
- canonical writer and every reader;
- source rights and public/private boundary;
- event/knowledge/market clock semantics;
- input/output schema, version, migration, and fixtures;
- authority ceiling and forbidden consumers;
- missing/stale/conflict/quarantine behavior;
- focused, downstream, adversarial, and live tests;
- activation state and rollback; and
- exact ship-loop proof.

---

## 15. Exact first mission for the next Claude session

Copy this assignment verbatim after Claude reads the canonical files:

> Continue the Biopharma Seasonality Intelligence program from
> `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_CLAUDE_CONTINUATION_HANDOFF_2026-08-06.md`.
> Start from freshly fetched `origin/main` in a new `.claude/worktrees/...`
> worktree and a fresh `claude/...` branch. Re-query open PRs and the active
> build map; preserve the shipped Calendar Clock and Lane 6 shadow lobe.
>
> First verify that the W1B BioCatalyst event-projection schema plus
> pointer/receipt contract is merged and pin its exact version/hash. If it is
> absent, land that contract-only W1B PR under the BioCatalyst owner before
> touching Seasonality. After that PR merges, fetch the new `origin/main` and
> create a second fresh worktree/branch. If `biopharma.event.v2` is absent,
> land W2A0 as its own Seasonality contract-only PR, preserving v1 and adding
> typed source temporal precision plus lower/upper bounds. After W2A0 merges,
> fetch the new `origin/main` again and create a third fresh worktree/branch.
> Your first Seasonality adapter PR is then W2A only: a dark, pure, fail-closed
> `engine/seasonality/event_clock.py` adapter plus
> `tests/test_seasonality_event_clock.py`. Accept injected canonical
> BioCatalyst projection bytes/a typed reader; map `known_at` from
> `transaction_from`, never `knowledge_cutoff`; preserve source hashes,
> precision, bounds, revisions, and structured quarantine reasons. Phase-3
> START is display/context-only. Do not create a source collector, ticker
> inference, live event graph, workflow, public artifact, Prophet wire, or
> authority change. Do not edit `engine/biocatalyst/` or
> `collectors/biocatalyst/`, `contracts/biocatalyst/`, or
> `config/biocatalyst_*.yml` in this PR.
>
> Add adversarial fixtures for null/ambiguous time, future effective dates,
> after-hours policy, range precision, corrections, contradictions, duplicate
> events, unresolved identity, corrupt hash, stale/unknown schema, oversized
> payload, and deterministic replay. Include one explicitly synthetic,
> identity-resolved `fixture_only`/non-publishable success row and pair it with
> unresolved-identity quarantine fixtures; do not invent a live ticker map.
> Run the focused Seasonality foundation,
> stock engine/page, shadow-state, and relevant contract tests. Ship the normal
> branch → PR → merge → production-ancestry loop. Because this PR is dark,
> verify that the live Calendar Clock/methodology remain unchanged and no live
> availability flag moved.
>
> After the W1B schema/pointer contract is pinned, continue W1A and the W1B live
> producer/transport under their canonical owners in parallel with W2A. Do not
> solve a missing identity or transport dependency with a temporary local
> ticker map, authenticated self-scrape, or second collector. End with the exact
> commit, PR, merge SHA, tests, production health SHA, and remaining blocker for
> W2B. Treat W1A as the registered cross-program blocker
> `complete_point_in_time_security_and_corporate_actions_contract`;
> `collectors.symbol_directory` is bootstrap-only and is not a fallback.

Baseline regression pack to preserve through the program:

```bash
python3 -m pytest -q \
  tests/test_biopharma_seasonality_foundation.py \
  tests/test_stock_seasonality_engine.py \
  tests/test_stock_seasonality_page.py \
  tests/test_seasonality_shadow_state.py \
  tests/test_mastermind_context.py \
  tests/test_signal_bus_doc.py \
  tests/test_synapse_read_gate.py \
  tests/test_dag_conformance.py

bash scripts/verify_stock_seasonality_live.sh
```

The live verifier is diagnostic and currently can exit zero after printing
failures. Acceptance requires its printed final summary to say `0 failed`; exit
status alone is not proof. Fixing that verifier to fail nonzero is a separate
small ops PR, not part of the dark W2A adapter.

Add the focused tests for each wave; do not treat this list as the complete
repository gate.

---

## 16. Definition of full completion

### Data and operations

- point-in-time security/universe/corporate-action and BioCatalyst event seams
  are live, licensed, versioned, replayable, monitored, and last-good safe;
- event revisions, identity ambiguity, missingness, contradictions, and stale
  states are visible;
- nightly and source-run cadences meet measured SLOs; heavy work is off render;
- append-only forecast/outcome ledgers accrue without duplicate or rewritten
  rows; and
- recovery, replay, retention, backup, and incident drills have production
  evidence.

### Engines

- calendar, event, and lawful regime clocks run from frozen PIT inputs;
- complete trial families, selection correction, chronological OOS, holdouts,
  costs, contamination, perturbations, drift, and calibration are implemented;
- baselines remain visible, weak/thin states abstain, and failed champions
  retire transparently; and
- probabilities are separated by occurrence, event outcome, and market
  response, with the first two BioCatalyst-owned and only the last
  Seasonality-owned.

### Product

- the single workstation supports Calendar, Catalyst, compare, pattern
  research, evidence, saved work, baskets/universes, calendar/alerts, exports,
  and an honest screener/API;
- every state works across EN/ZH, dark/light, desktop/tablet/mobile,
  accessibility, reduced motion, outages, partial coverage, conflicts, and
  historical mode; and
- user-facing numbers disclose type, baseline, interval semantics, sample, clusters,
  search budget, OOS, costs, cutoff, model/data version, freshness, and
  abstention.

### Neural Web and Prophet

- Neural Web consumes one compact, expiring, multi-clock state with measured
  contradictions and overlap, a read-only operator query, and no candidate
  origination;
- Prophet receives a post-selection, frozen narrative/attention overlay with
  byte-identical selection, ranking, plan numbers, geometry, confidence, size,
  and options; and
- the current calendar/event program has no confidence-cap authority; any
  future non-window proposal first receives an explicit DNR architecture ruling
  and only then its own preregistered gate, migration, audit trail, and rollback.

### Commercial and advanced product

- tenant data, entitlements, rate limits, uploads, exports, alerts, APIs, and
  audit logs are secure and contract-tested;
- options, analogue, qualitative, and portfolio layers use licensed sources and
  independent evaluation; and
- methodology and health surfaces match actual availability byte-for-byte.

Full product completion does **not** automatically authorize signal promotion.
If promotion gates remain unpassed, the completed system stays a superior
context and research product—and says so plainly.

---

## 17. Canonical reading order

1. `CLAUDE.md`
2. `docs/ACTIVE_BUILD_MAP.md` and `research/DO_NOT_REBUILD.md`
3. this file
4. `research/SEASONALITY_BIOCATALYST_INTEGRATION_SEAM.md`
5. `research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md`
6. `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md`
7. `research/SEASONALITY_PROGRAM_HANDOFF_2026-08-02.md` only for historical
   operational evidence
8. current code, contracts, artifacts, tests, live PR census, and production

The source of truth is always the current validated implementation plus its
versioned contracts and production evidence. This handoff is the execution map,
not permission to override newer repo law.
