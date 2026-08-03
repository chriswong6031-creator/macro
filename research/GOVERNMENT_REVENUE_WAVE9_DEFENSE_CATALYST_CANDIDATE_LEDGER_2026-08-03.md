# Government Revenue Wave 9 — Defense Catalyst Candidate Ledger

Status: CANONICAL NEXT-BUILD DOCKET

Date: 2026-08-03

Authority: display and research only; this docket does not promote a trade signal

Predecessor: research/GOVERNMENT_REVENUE_WAVE8_HANDOFF_2026-08-02.md

## 0. Acceptance gates

Wave 9 is complete only when every gate below is true.

1. Exact issuer gate: no ticker research candidate exists without a receipt-bound
   source event and a time-valid exact UEI, CAGE, or USAspending recipient identifier
   resolving through the reviewed ownership graph to one public-company issuer.
2. Point-in-time gate: effective_at, known_at, analysis_as_of, source receipt time,
   issuer-map knowledge time, and artifact generation time remain separate. A candidate
   cannot exist before the latest evidence needed to construct it was knowable. A
   cross-check without its own receipt-bound known_at is live context only and becomes
   not_observed in replay; as_of never substitutes for knowledge time.
3. Evidence gate: every candidate carries immutable event references, receipt
   references, source artifact content IDs, and the exact issuer-resolution reference.
4. Truthful-empty gate: an empty reviewed issuer graph produces zero exact-linked
   candidates and a visible mapping backlog. It never falls back to company-name,
   description, query-scope, NAICS, or keyword matching.
5. Authority gate: every Wave 9 artifact keeps can_rank, can_size, can_gate,
   can_originate_signal, can_add_candidates, and can_escalate false. A Government
   Revenue research candidate is not a Neural Web trade candidate.
6. Integration gate: Government Revenue cannot change the ticker set or order produced
   by Neural Web or Prophet. Context is attached only after those systems admit the
   same ticker through their own governed paths.
7. No-fusion gate: technicals, valuation, earnings, alternative data, regime, and
   geopolitics remain named cross-check legs. No blended alpha, confidence, conviction,
   or buy score is created.
8. Projection gate: canonical candidate_queue.json and the public candidate twin are
   byte-identical, content-addressed, schema-validated, freshness-checked, capped, and
   pair-verified. Each file is written atomically on its own path; readers fail closed
   during any transient absence or mismatch.
9. UI gate: a user can find every covered defense ticker, distinguish exact-linked
   candidates from mapping-needed coverage names, understand the observed catalyst,
   and know the stance within five seconds on desktop and mobile.
10. Historical gate: no present-day USAspending response is backdated into a trading
    test. Formal performance claims require archived point-in-time receipts or forward
    ledger observations.
11. Release gate: focused tests, contract and DAG checks, template/site synchronization,
    browser QA, merge, production health, API truth probes, and the changed live surface
    all pass.

## 1. Product verdict

Government Revenue should become a ticker-first defense catalyst radar, not a prettier
procurement search page.

The product job is:

- detect an official procurement change before its possible financial-statement effect
  is obvious;
- prove which listed issuer is economically connected to the recipient;
- explain the plausible backlog, revenue, margin, cash, or narrative transmission path;
- show whether independent Mastermind evidence agrees, conflicts, or is unavailable;
- preserve the observation so the hypothesis can be graded later; and
- surface the name for research without pretending it is already a buy.

The useful output is a possible earnings or rerating research candidate with auditable
evidence. Prophet remains the trade-plan consumer only when its existing engine has
already selected the same ticker. Neural Web supplies independent context; it does not
launder procurement salience into conviction.

## 2. Current truth at the Wave 8 production boundary

As of the 2026-08-03 Wave 8 generation:

- Government Revenue publishes 21 named defense and aerospace company dossiers.
- The company rows contain useful descriptive award velocity, capacity, recompete, and
  opportunity context, but their collection queries are not issuer attribution.
- The reviewed recipient entity graph is intentionally empty: zero companies, legal
  entities, identifiers, and ownership edges.
- The prime-award dossier contains 1,934 bounded awards.
- The official IDV generation selected and count-verified 24 parents, retrieved complete
  detail for 15, and observed 452 exact relationships.
- No IDV child currently bridges by exact generated award ID into the prime-award
  dossier. That bounded non-observation is not proof that no relationship exists.
- The DoD P-1/R-1 graph is unavailable by design until real PDF acquisition, durable
  storage, and extraction receipts exist.
- All Government Revenue authority flags are false.

Therefore Wave 9 must ship useful ticker visibility and a mapping work queue before it
can honestly show a non-zero exact catalyst queue.

## 3. Already built, reused, and excluded

### Reuse — do not rebuild

- Official USAspending snapshot/action rails and immutable receipts.
- Award-change event normalization and point-in-time event history.
- Prime-award, subaward, IDV, SAM opportunity, and company dossier surfaces.
- Precision-first recipient resolution in
  engine/government_revenue/entity_resolution.py.
- Reviewed-event federation in engine/government_revenue/federation.py.
- Existing Government Revenue annotation blocks in
  engine/neuralweb/mastermind_context.py and engine/prophet_bridge.py.
- Current premium Government Revenue workbench, dossier inspector, evidence drawers,
  source clocks, and responsive shell.
- Existing Earnings, Company Intelligence, Fundamental Forensics, technical, regime,
  geopolitical, and alternative-data products. Wave 9 consumes their governed public
  artifacts; it does not create parallel engines.

### Excluded from Wave 9

- Competitor code, private data, copied assets, reverse-engineered endpoints, or
  authenticated HigherGov/GovTribe material.
- Fuzzy recipient-to-ticker attribution or a likely-bidder probability.
- Treating search terms, company aliases, program keywords, NAICS, or PSC overlap as
  issuer proof.
- Relabeling contract ceiling, unfunded option, budget request, authorization,
  appropriation, obligation, award value, or backlog as revenue.
- Activating DoD P-1/R-1 data before the Wave 8 acquisition fence is satisfied.
- Altering Prophet's selected ticker population, selection order, confidence, geometry,
  horizon, options, source_engines, or management state.
- A single Government Revenue conviction, attractiveness, undervaluation, buy, or
  rerating score.
- Retrospective candidate issuance from evidence first collected after the claimed
  decision date.
- Front-facing falsifier, refutation, gauntlet, lobe, display-tier, or other internal
  vocabulary. Full methodology and measurement verdicts belong below the fold.

## 4. Vocabulary and authority boundary

### Research candidate

A ticker with an official observed procurement event, an exact reviewed issuer path,
and a documented financial-transmission hypothesis. It earns a place in the Government
Revenue investigation queue only.

### Mapping-needed coverage name

One of the 21 company dossiers whose collection-scope evidence is useful for discovery
but lacks the exact reviewed source-recipient-to-issuer path required for a research
candidate. It remains fully searchable and visible.

### Cross-check match

The same ticker appears in a governed external artifact at a compatible point-in-time.
Each leg is shown separately with its own state and receipt. A match is not a fused
signal and does not raise another system's confidence.

### Prophet annotation

Government Revenue evidence attached after Prophet's existing select_candidates call
has admitted the ticker. The annotation may enrich thesis and provenance only.

### Trade signal

A separately governed output with authority to originate, rank, size, gate, or
escalate. Wave 9 does not create one.

## 5. Target architecture

~~~text
official receipt
  -> source-native snapshot or action
  -> immutable procurement event
  -> exact temporal recipient resolution
  -> Government Revenue research-candidate observation
  -> append-only candidate ledger
  -> current candidate queue + public byte twin
  -> Candidate Radar and company dossier

current candidate queue
  -> Neural Web shadow cross-checks by exact ticker and compatible clock
  -> named leg states and receipts
  -> Government Revenue dossier enrichment

existing Prophet selection
  -> post-selection Government Revenue lookup
  -> thesis and provenance annotation only
~~~

No edge in this graph points from Government Revenue into Prophet selection or Neural
Web candidate-universe construction.

## 6. New contracts and artifacts

### Contracts

1. contracts/government_revenue/government_revenue_candidate.v1.schema.json
2. contracts/government_revenue/government_revenue_candidate_queue.v1.schema.json

The candidate schema must require:

- candidate_id and observation_id;
- candidate_scope with constant government_revenue_research and
  is_neuralweb_trade_candidate with constant false;
- ticker and issuer_company_id;
- issuer_resolution_ref and ownership_path_refs;
- candidate_family and candidate_state;
- transmission_direction and mechanism;
- event_refs, source_receipt_refs, and artifact_content_ids;
- effective_at, known_at, analysis_as_of, generated_at;
- freshness and coverage;
- materiality;
- earnings_transmission;
- crosscheck_state;
- counterevidence and internal_watch_conditions;
- authority and limitations.

Stable identity:

- candidate_id is a digest of candidate_family, issuer_company_id, and the immutable
  anchor event ID;
- observation_id is a digest of candidate_id, known_at, state, and source content IDs;
- revisions append a new observation and never mutate an old ledger row.

Allowed candidate_state values:

- detected;
- awaiting_crosscheck;
- active;
- matured;
- superseded;
- withdrawn;
- blocked.

Allowed transmission_direction values:

- possible_positive;
- possible_negative;
- mixed;
- unknown.

These labels describe a research hypothesis, not a market-direction call.

### Canonical artifacts

1. data/government_revenue/candidate_ledger.jsonl
2. data/government_revenue/candidate_queue.json
3. data/government_revenue/candidate_projection_state.json
4. data/government_revenue/candidate_projection_status.json

### Public artifact

1. site/government-revenue-data/candidates.json

The public artifact must be byte-identical to candidate_queue.json. Raw source bodies,
private analyst notes, credentials, signed URLs, internal filesystem paths, and
unredacted headers remain excluded.

### Queue envelope

candidate_queue.json contains:

- schema_version, contract, content_id, generated_at, as_of, and known_at;
- source_generation_ids and source_content_ids;
- candidates, mapping_backlog, and recently_matured;
- counts by family, state, freshness, and exact-link status;
- coverage and freshness receipts;
- a deterministic sort declaration;
- authority with all six powers false; and
- limitations.

The current queue projection keeps at most 250 candidates, 250 mapping-backlog rows, and
100 matured rows. Sort order is known_at descending, candidate_id ascending. Recency is
navigation, not rank.

The exact candidate namespace is separate from existing latest.json company-scope
context. A discovery-scope company row can remain visible in Companies mode, but it
cannot populate candidate proof, Candidate Radar evidence, or the new exact-candidate
Prophet annotation.

## 7. Deterministic candidate eligibility

Every emitted research candidate must pass all checks:

1. The source event exists in a contract-validated, current official-source generation.
2. The event carries at least one immutable receipt and one source artifact content ID.
3. Event known_at is no later than analysis_as_of.
4. Recipient resolution is confirmed or reviewed at analysis_as_of.
5. Resolution began from an exact UEI, CAGE, or USAspending recipient identifier.
6. The exact identifier resolves to one reviewed legal entity.
7. A non-empty, time-valid reviewed ownership path terminates at one reviewed public
   company with ticker and company ID.
8. No visible recipient, ownership, or issuer block/conflict is active.
9. The resolution evidence and ownership path are included by reference.
10. The candidate family has its required source semantics.
11. Authority is the complete all-false display contract.

Failure produces a reason-coded mapping or evidence backlog row, never a lower-confidence
ticker candidate.

Required backlog reason codes include:

- recipient_identifier_missing;
- recipient_unresolved;
- ownership_path_missing;
- issuer_conflicted;
- source_receipt_missing;
- source_stale;
- event_semantic_unsupported;
- coverage_not_comparable;
- program_bridge_unreviewed.

## 8. Candidate families

### Wave 9A — eligible once exact issuer paths exist

1. award_obligation_change
   - Source: exact USAspending award action or snapshot change.
   - Positive and adverse obligations remain distinct.
   - Corrections and deobligations never inherit positive wording.

2. award_ceiling_change
   - Source: source-native ceiling or potential-value change with prior and current
     values.
   - Ceiling growth is funded-capacity context, not obligation, backlog, or revenue.

3. option_exercise
   - Source: an action whose source-native semantics identify an exercised option.
   - An unexercised option or future period cannot emit this family.

4. new_award
   - Source: first point-in-time observation of an exact award in the prospective
     ledger.
   - A historically old award first collected today is late_discovered, not a new
     award candidate.

### Wave 9B — shadow until comparable prospective history accrues

5. obligation_velocity_change
   - Requires exact issuer-attributed monthly observations with unchanged coverage.
   - Coverage changes, query rotation, or newly mapped subsidiaries break comparison.
   - Existing 20 percent descriptive company bands remain context only and do not
     become candidate rules automatically.

6. contract_capacity_step_up
   - Requires exact issuer attribution, stable award universe, and source-native
     current versus prior ceiling.
   - No conversion to GAAP backlog.

7. recompete_outcome
   - Requires an observed source-native successor award and reviewed incumbent/challenger
     relationship.
   - Response dates, likely bidders, and solicitation text alone cannot emit it.

### Later rails — blocked until their own evidence substrates exist

8. idv_to_child_conversion
   - Requires exact IDV parent/child relationship plus child award detail and exact
     issuer path.

9. sbir_to_production_transition
   - Requires a separate official SBIR lineage rail and documentary production-award
     bridge.

10. budget_program_change
    - Requires real P-1/R-1 receipts and a reviewed program-to-award bridge.
    - Request, enacted reference, execution, obligation, award, backlog, and revenue
      stages remain separate.

## 9. Materiality and earnings transmission

Wave 9 does not create an opaque materiality score. It publishes arithmetic a user can
inspect.

Each materiality object contains:

- observed event amount;
- reviewed economic_share when the issuer is not the direct recipient;
- attributable numerator equal to event amount times economic_share, or null when the
  share is unknown;
- numerator value, currency, date, known_at, receipt, and source semantic;
- denominator value, period, source, coverage, known_at, and receipt;
- ratio when numerator and denominator are comparable;
- comparison basis;
- coverage state;
- calculation version; and
- limitations.

Permitted examples:

- obligation delta divided by exact-mapped trailing-12-month federal obligations;
- ceiling delta divided by the same award's prior ceiling;
- later, official program request delta divided by the prior official program line.

Company revenue, market capitalization, backlog, and guidance may appear only as
separate point-in-time cross-check facts from their governed source artifacts. They are
never silently substituted into procurement math.

If economic_share, denominator receipt, denominator knowledge time, currency
comparability, or coverage comparability is absent, ratio is null and comparison state
is not_comparable. The UI may still show the observed source amount with its scope.

earnings_transmission is a structured hypothesis:

- observed_change;
- issuer_role: prime, reviewed_recipient_subsidiary, or unknown;
- possible_channels: backlog, revenue, margin, cash, guidance, narrative;
- mechanism_steps;
- timing_window as a plain research window, not a promised date;
- dependencies;
- counterevidence;
- what_we_are_watching; and
- evidence_refs.

The user-facing card says what changed and what to watch. Detailed counterevidence and
measurement receipts live in the inspector.

reviewed_subcontractor is prohibited in Wave 9A. It becomes eligible only through a
separate receipt-bound subaward family proving the subaward recipient, amount, prime,
issuer path, and source clock.

## 10. Neural Web cross-check contract

The cross-check engine joins only by normalized exact ticker and compatible knowledge
clock. Every leg has:

- leg_name;
- state: confirmed, supportive_context, conflicting_context, not_observed, stale,
  unavailable, or not_evaluated;
- observed_at and known_at;
- source_artifact and content ID;
- one plain-language observation;
- evidence_refs;
- freshness; and
- limitations.

Every usable leg also requires its own receipt-bound known_at and immutable source
content ID. A live snapshot lacking either may be shown as current-page context but
cannot be frozen as historical candidate evidence, cannot be used in replay, and must
project not_observed for any point-in-time evaluation.

Required legs:

1. technical structure;
2. valuation and fundamental context;
3. earnings, filings, and transcript evidence;
4. alternative data;
5. market and sector regime;
6. geopolitical and policy context.

No arithmetic combines these states. The UI can filter for completed cross-checks but
cannot sort names by a support count. Conflict is a first-class result, not an error.

The first implementation reuses these exact governed seams:

- technicals: site/factordata/us_standouts.json,
  site/neuralwebdata/bottom_sensors.json, and data/options_entry/state.parquet;
- valuation and fundamentals: the bottom_sensors valuation, leverage, structural, and
  dilution blocks plus data/edgar/rpo.parquet; data/analyst/targets.parquet is optional
  and currently absent, so absence is not_observed;
- earnings: data/earnings/earnings.parquet and
  engine/chronicle/earnings_calls.py latest_for_ticker over
  data/chronicle/earnings_call_events.jsonl;
- alternative data: data/altdata/by_ticker.json and, for universe context only,
  site/altdata/mastermind.json;
- market regime: data/regime/latest.json for live context and
  data/regime/regime_v2_pit.parquet for historical evaluation; and
- geopolitics: engine/chronicle/context_pack.py pack over
  data/chronicle/events.jsonl with bounded ticker/topic/as-of inputs.

Unmatched Chronicle coverage is not_observed, never no geopolitical risk. Generic news
cannot infer a defense beneficiary or directional outcome.

Several current live snapshots do not yet carry receipt-bound known_at. In particular,
the current standouts, bottom-sensors, alternative-data ticker map, regime latest, and
Chronicle context selection cannot be treated as replay-safe merely because they carry
an as-of date. W9D must either add an immutable availability receipt upstream or keep
that leg live-only and not_observed in historical reconstruction.

The cross-check builder reads these upstream artifacts directly, or shared pure
selectors extracted from their current consumers. It does not read
data/neuralweb/mastermind_context.json, because Neural Web will consume the candidate
queue and a mutual dependency would create a circular DAG. Each cross-check run appends
a new immutable candidate observation so the point-in-time view can be reconstructed.

engine/neuralweb/mastermind_context.py may add:

- Government Revenue candidate-queue health and counts to the lobe summary; and
- the exact candidate block to a ticker already present in candidate_context.

It must preserve the existing candidate universe:

~~~text
standouts tickers union alternative-data tickers union actionable radar tickers
~~~

Government Revenue is not added to that union in Wave 9.

## 11. Prophet contract

engine/prophet_bridge.py continues to load Government Revenue strictly after
select_candidates.

When an already selected ticker has a current exact-linked Government Revenue research
candidate, Prophet may add:

- candidate_id;
- candidate_family;
- observed procurement change;
- materiality arithmetic;
- earnings-transmission summary;
- cross-check states;
- source receipts and content IDs; and
- allowed_behavior: annotate_only.

It may enrich thesis text and provenance. It may not modify:

- selected ticker IDs or order;
- conviction or confidence;
- entry, trigger, invalidation, targets, or risk units;
- horizon or option contract;
- source_engines;
- management state; or
- any rank, size, gate, escalation, or notification priority.

Byte-comparison tests must prove candidate IDs/order and all protected plan fields are
identical with the Government Revenue queue present, absent, stale, malformed, or empty.

## 12. Backend implementation

### New modules

- engine/government_revenue/candidates.py
  - pure deterministic candidate construction;
  - exact issuer and event eligibility;
  - stable IDs, state transitions, dedupe, and bounded projection.

- engine/government_revenue/candidate_evaluation.py
  - point-in-time forward outcomes and event-study measurements;
  - no live scoring or promotion.

- engine/government_revenue/candidate_crosschecks.py
  - reads governed upstream artifacts through point-in-time selectors;
  - emits named leg states and source receipts without cross-leg arithmetic;
  - appends an enriched observation instead of mutating prior history.

- scripts/build_government_revenue_candidates.py
  - validates inputs and contracts;
  - is the sole legal writer of candidate_ledger.jsonl;
  - runs with one frozen run clock in the serialized government-revenue-live lane;
  - writes each canonical/public twin atomically on its own path and then verifies the
    pair;
  - fails closed on lineage, clock, twin, or authority drift.

### Existing modules to extend

- scripts/build_government_revenue.py
  - invoke candidate projection after award events and issuer resolution only in the
    serialized live materialization mode;
  - render and site-only modes verify and mirror the current projection but cannot
    append, retime, or backfill ledger rows.

- engine/government_revenue/federation.py
  - add a selector for current exact candidate context; keep annotate-only behavior.

- engine/neuralweb/mastermind_context.py
  - add queue health and post-universe ticker annotation.

- engine/prophet_bridge.py
  - add post-selection candidate evidence without changing protected fields.

- app/government_revenue.py
  - serve bounded verified queue, candidate detail, and history routes.

- app/deploy/update.sh
  - restart macro-api when candidates.py, candidate_crosschecks.py,
    candidate_evaluation.py, their contracts, or serving routes change;
  - extend the deployment self-heal tests for every new serving module.

- config/synapse.yml
  - register contracts, producers, consumers, freshness, replay class, authority,
    canonical/public twin, and failure behavior.

Do not route investment research candidates through engine/metabolism/insight_bus.py;
that bus is for system health and governance alerts.

### Read-only API

- GET /api/government-revenue/candidates
- GET /api/government-revenue/candidate/{candidate_id}
- GET /api/government-revenue/candidate/{candidate_id}/history
- GET /api/government-revenue/company/{ticker}/candidates
- GET /api/government-revenue/mapping-backlog

All list routes are bounded and cursor-paginated. Every list, detail, history, company,
and mapping-backlog route verifies both twins and their bytes/content IDs before
serving. Either twin absent, stale, malformed, or mismatched returns an explicit
unavailable response, never an empty success.

## 13. Premium ticker-first product specification

Wave 9 restores the useful V1 company visibility without restoring its epistemic
shortcuts. Candidate Radar and Companies become persistent top-level modes.

### Glance tier

Header question: Which defense names just changed?

Always visible:

- source clock;
- exact-linked active candidate count;
- mapping-needed company count;
- a compact 21-name ticker filmstrip with exact-link, new-change, and quiet states;
- stance: Research now, Watch for confirmation, Mapping needed, or No fresh change.

The empty state reads: No exact-linked changes yet. Company coverage is live; issuer
mapping is still being verified.

No raw scores, internal state names, unexplained acronyms, or stacked disclaimers appear
at rest.

### Candidate Radar

Filters:

- all;
- fresh changes;
- exact linked;
- needs cross-check;
- matured;
- positive transmission;
- adverse transmission;
- family;
- agency;
- program;
- ticker.

Default order is newest known evidence, not attractiveness.

Each row shows:

- ticker and company;
- one-line observed change;
- possible statement channel;
- transparent magnitude;
- cross-check chips with independent states;
- source age;
- stance; and
- one action: Open investigation.

### Investigation inspector

Progressive sections:

1. What changed.
2. Why this ticker is linked.
3. How it could reach earnings.
4. Materiality math.
5. What other Mastermind evidence says.
6. Company history and prior procurement changes.
7. Sources, clocks, receipts, limitations, and full measurement record.

Issuer proof displays the source identifier, legal entity, ownership path, effective
window, review state, and receipt chain. Users never have to trust a hidden match.

### Companies mode

All 21 coverage tickers remain searchable even when the exact candidate queue is empty.
Each dossier separates:

- exact issuer-linked observations;
- collection-scope descriptive history;
- mapping status;
- government exposure;
- award and modification timeline;
- earnings and transcript context;
- valuation context;
- technical, alternative-data, regime, and geopolitical cross-checks; and
- not-yet-observable gaps.

The page must never visually blend exact-linked facts and discovery-scope estimates.

### Visual and interaction bar

- Preserve the existing dark investigation-cockpit family and shared design tokens.
- Use one strong visual hierarchy, restrained accent colors, and evidence-density
  through alignment rather than card clutter.
- Desktop uses a stable queue plus inspector; mobile uses a full-height inspector sheet
  with preserved back position and no horizontal overflow.
- Keyboard navigation, visible focus, semantic headings, reduced-motion support, and
  AA contrast are release requirements.
- Loading, unavailable, stale, empty, partial, and error states are individually
  designed and browser-tested.
- Before UI implementation, load docs/DESIGN_DOCTRINE.md and the current frontend
  design skill. Produce desktop and mobile screenshots before code review.

## 14. Historical and forward evaluation

The candidate ledger starts prospective accrual immediately. Historical studies may use
only archived evidence with a defensible availability clock; otherwise they are labeled
exploratory and non-point-in-time.

One family, horizon, and outcome definition is preregistered at a time.

Market outcomes:

- next available bar after known_at;
- 5, 21, 63, and 126 trading-day returns;
- defense-peer-relative and broad-market-relative returns;
- maximum favorable and adverse excursion; and
- corporate-action-adjusted prices with point-in-time ticker mapping and delistings.

Fundamental outcomes:

- next one and two reported quarters;
- revenue, backlog, funded backlog, margin, cash, and guidance changes when available;
- transcript or filing confirmation of the program or contract;
- first statement date and source receipt; and
- whether the hypothesized transmission channel appeared, conflicted, or remained
  unobservable.

Method:

- issuer-month clustered or time-block bootstrap, never ticker-only confidence intervals;
- overlapping-event embargoes;
- matched defense peers and size/liquidity controls;
- regime slices declared before the read;
- publication lag, revisions, corrections, and deobligations retained;
- train, test, out-of-sample, and forward cohorts separated;
- Benjamini-Hochberg false-discovery control across tested families; and
- null and adverse results printed.

Reuse engine/grading.py for forward outcomes and engine/neuralweb/constitution.py for
promotion evidence. Research Factory may own a family-level hypothesis and preregistered
study, but individual ticker observations stay in the Government Revenue ledger.

## 15. Promotion ladder

1. Research display
   - exact evidence, current freshness, all authority false.

2. Cross-check shadow
   - independent leg states and later outcomes recorded;
   - no change to any candidate set.

3. Family evidence review
   - point-in-time preregistered study, independent out-of-sample or forward cohort,
     multiple-testing control, and economically meaningful effect.

4. Prophet annotation
   - still post-selection and annotate-only.

5. Separate authority proposal
   - required before any deterministic adapter can propose admission to a governed
     signal surface;
   - cannot be inferred from this docket, a good case study, or UI usefulness;
   - LLM text never originates or escalates the signal.

At no stage does Government Revenue directly emit a trade, position size, or buy order.

## 16. Ordered build lanes

### W9A — contracts, ledger, and honest empty projection

- Add candidate and queue schemas.
- Add pure builder, append-only ledger writer, state/status, public twin, DAG entries,
  and bounded APIs.
- Project zero candidates plus the mapping backlog from the current empty strict graph.
- Add corruption, clock, authority, and twin-failure tests.

### W9B — reviewed issuer graph

- Curate exact source-recipient identifiers and time-valid ownership paths for the
  existing 21-company coverage universe.
- Require official identifiers and documentary ownership receipts.
- Expose review coverage and conflicts.
- Rebuild Wave 9; candidate counts may advance only from exact eligible events.

### W9C — ticker-first Candidate Radar

- Implement the filmstrip, queue, inspector, Companies mode, mapping states, and
  desktop/mobile interaction.
- Preserve existing dossiers and evidence drawers.
- Run design-doctrine review, visual screenshots, accessibility checks, and browser QA.

### W9D — Neural Web shadow cross-checks

- Attach exact candidates to already admitted tickers.
- Build immutable named-leg snapshots from the exact upstream technical, fundamental,
  earnings, alternative-data, regime, and Chronicle seams in section 10.
- Persist named leg states and receipts; no fused score.
- Keep the Government Revenue projection independent of
  data/neuralweb/mastermind_context.json to avoid a circular producer graph.
- Reject any source artifact whose known_at is after the frozen candidate run clock;
  keep no-known-at snapshots live-only and not_observed in replay.

### W9E — Prophet annotation

- Attach current exact candidate evidence only after selection.
- Prove protected plan fields and candidate population are byte-identical.

### W9F — forward grader and first preregistered family

- Start prospective accrual.
- Freeze one candidate family and ruler.
- Publish outcomes only when the predeclared maturity and sample gates are met.

### W9G — new official-source catalyst rails

- Exact IDV child detail expansion.
- SBIR-to-production lineage.
- Real DoD P-1/R-1 acquisition and program bridges.
- Observed recompete outcomes and displacement.

## 17. Test and release matrix

Extend:

- tests/test_government_revenue_entity_resolution.py
- tests/test_government_revenue_award_events.py
- tests/test_government_revenue_neuralweb.py
- tests/test_prophet_government_revenue_context.py

Add:

- tests/test_government_revenue_candidates.py
- tests/test_government_revenue_candidate_projection.py
- tests/test_government_revenue_candidate_api.py
- tests/test_government_revenue_candidate_ui.py
- tests/test_government_revenue_candidate_evaluation.py

Required adversarial cases:

- company name matches but exact identifier is absent;
- exact identifier maps to two issuers;
- ownership path was not yet known;
- ownership becomes effective after the event;
- issuer mapping is later corrected;
- source receipt or content ID is missing;
- cross-check source is future-known relative to the candidate clock;
- cross-check carries as_of but no receipt-bound known_at;
- stale source and fresh cross-check clocks disagree;
- late-discovered historical award;
- deobligation mislabeled positive;
- ceiling increase mislabeled obligation or backlog;
- mapping backlog mislabeled candidate;
- discovery-scope latest.json context appears as exact Candidate Radar or Prophet proof;
- candidate queue added to Neural Web's candidate union;
- Government Revenue changes Prophet order, confidence, geometry, horizon, or options;
- canonical/public twin mismatch;
- one candidate twin is temporarily absent;
- ledger truncation or mutation;
- generic render, site-only render, or replay appends or retimes a ledger row;
- deployment updates a candidate serving module without restarting macro-api;
- hidden zero-to-one fallback through fuzzy matching; and
- mobile overflow, focus trap, or inaccessible evidence drawer.

## 18. Immediate blockers and honest first release

The first exact-linked queue will remain empty until W9B populates the reviewed issuer
graph. That is the principal product blocker, not UI or scoring.

Other blocked families:

- IDV conversion: exact child details do not yet intersect the bounded prime dossier.
- DoD budget: real acquisition/storage/extraction receipts are absent.
- SBIR progression: official lineage rail is not built.
- deep SAM coverage: credentialed collection depends on SAM_API_KEY.
- historical alpha claims: prospective or archived point-in-time observations are not
  yet mature.

The honest first release is still valuable: all covered tickers are visible, mapping
work is explicit, exact eligibility is executable, evidence cannot be laundered, and
the forward ledger begins accumulating immediately.

## 19. Resume commands

~~~bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard"
git fetch origin main
git worktree add ".claude/worktrees/government-revenue-wave9-candidate-ledger" \
  -b claude/government-revenue-wave9-candidate-ledger origin/main
cd ".claude/worktrees/government-revenue-wave9-candidate-ledger"

sed -n '1,240p' research/GOVERNMENT_REVENUE_WAVE9_DEFENSE_CATALYST_CANDIDATE_LEDGER_2026-08-03.md
sed -n '1,220p' research/GOVERNMENT_REVENUE_WAVE8_HANDOFF_2026-08-02.md
sed -n '1,220p' research/DO_NOT_REBUILD.md
rg -n -i 'government revenue|candidate|prophet|earnings' docs/ACTIVE_BUILD_MAP.md

pytest -q tests/test_government_revenue*.py tests/test_prophet_government_revenue_context.py
python3 -m scripts.check_template_site_sync
python3 -m scripts.check_government_revenue_projection
git diff --check
~~~

## 20. Non-negotiable sentence

Government Revenue may discover and preserve an auditable defense research candidate;
it may not turn incomplete procurement evidence into a ticker attribution, a buy score,
or a Prophet trade.
