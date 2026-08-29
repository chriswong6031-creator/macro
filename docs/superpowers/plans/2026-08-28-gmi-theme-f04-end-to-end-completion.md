# GMI Theme + F04 End-to-End Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the unique GMI Theme/Sector/Neural Graph substrate and state layers, then complete the user/machine-facing ontology/transmission/opportunity workflow through the existing MarketOntology F04 owner without creating any duplicate graph, ThemeState, sector master, measurement engine, grader, ranker or control plane.

**Architecture:** GMI remains the canonical theme/local-theme topology, PIT/correction, probation, measurement-eligibility, ThemeState and cohort-context owner. The GMI development frontier is D2C + D2D -> D2E -> W3B -> W3C. After W3C, downstream product composition belongs to the existing F04 parent operation, consuming GMI plus K3-D/TXI/incorporation/specialist owners by reference. Fable is the sustained principal/COO for cross-owner continuity and delegates architecture-frozen child engineering to less-scarce workers.

**Tech Stack:** Python; Parquet/JSON/YAML graph artifacts; existing `engine/theme_graph/`, `engine/neuralweb/`, Market OS/site builders, Agent OS records, GitHub Actions/house CI.

**Spec:** `research/theme_graph/THEME_GRAPH_END_TO_END_COMPLETION_FREEZE_2026-08-27.md`

## Global Constraints

- Protected Sol procedure pin at commission: `mastermindx-market-intelligence/Mastermind@038d1271b98e88b24e039c1ce4127d6503945845`, Skillpack v1.0.1 / bootstrap-major 1 compatible.
- Re-pin current Skillpack and Macro main before each modifying child carrier; later accepted source law wins on conflict.
- One canonical GMI graph/store; no second sector/industry master.
- One owner-produced ThemeState; reconcile the existing Neural Web thematic-state lineage instead of adding another producer.
- No fuzzy/mechanical/embedding-only canonical mapping. Probation/adjudication controls semantic equivalence.
- Graph 1 economic relationship, Graph 2 similarity and Graph 3 residual-market context remain distinct. Theme co-membership never proves economic causality.
- GMI/W3C has zero upstream stock-selection/ranking authority.
- F04 composes owner facts; it does not rewrite owner truth.
- One independently useful modifying capability per PR/carrier.
- Builder and independent reviewer should differ for consequential children when practical.
- Fable is parent principal capacity; route frozen child engineering to Codex/Terra/Sonnet/Luna/Opus according to difficulty.
- Slack/watchers are transport/attention only. Every watcher-enabled return obeys explicit CONTINUE/STOP law.
- Green CI is not production acceptance. User-facing work requires real browser proof; machine work requires real producer->reader proof.

---

### Task 0: F04 parent pickup and current-state reconciliation

**Files:**
- Read: `agentos/handoffs/MARKET-ONTOLOGY-F04-ONTOLOGY-TRANSMISSION-OPPORTUNITY-FABLE-COO-2026-08-26.md`
- Read: `agentos/handoffs/GMI-THEME-GRAPH-2026-08-28-f04-autonomous-coo-commission.md`
- Read: `agentos/workstreams/WS-GMI-THEME-GRAPH.md`
- Read: `agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md`
- Read: `research/theme_graph/THEME_GRAPH_END_TO_END_COMPLETION_FREEZE_2026-08-27.md`
- Read: current PR #6514 and current Macro main/open PRs.

**Interfaces:**
- Consumes: existing F04 operation `marketontology-f04-ontology-transmission-20260826-fable-001`.
- Produces: exact pickup SHA, owner/collision census, chosen child routing, `PICKUP_ACK`, truthful watcher receipt and separate start receipt for the first modifying child.

- [ ] **Step 1: Re-pin the protected Skillpack and current Macro main.** Record exact SHAs in the F04 thread/handoff; do not execute from this document's historical pins if they have moved.
- [ ] **Step 2: Reconcile open reciprocal dialogue.** Read the complete F04 Slack thread and confirm there is no earlier unresolved `BLOCKED`, `DECISION_REQUEST`, `RESULT` or terminal STOP for the parent operation.
- [ ] **Step 3: Run a fresh collision census.** Inspect D2C/D2D target paths, PR #6514, current MarketOntology/F04 carriers, current Neural Web work, and any new theme_graph PR/branch. Do not reset/rebase unknown work.
- [ ] **Step 4: Route the first children.** Use Fable only as parent principal. Prefer Codex/Terra/Sonnet for D2C/D2D implementation if their contracts are sufficiently frozen; record `WHY NOT FABLE` for each child builder or `WHY FABLE` if a child truly needs principal intervention.
- [ ] **Step 5: Emit separate pickup/watch/start states.** Parent pickup ACK is not start. Arm the exact-thread watcher before ending the turn. Start D2C/D2D only after collision gates clear.

**Acceptance:** one F04 principal is lawfully assigned and has a current collision map; no duplicate parent lane or child carrier is created.

---

### Task 1: D2C — point-in-time vintage completion

**Files:**
- Required spec: `agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-d2c-pit-vintage-commission.md`
- Expected modify after archaeology: `engine/theme_graph/**`, `scripts/build_theme_graph.py`, existing source-vintage/materialization seams only.
- Generated proof: existing `data/theme_graph/**` outputs/receipts only.
- Test: focused `tests/test_theme_graph*.py`, temporal/source-specific graph tests, `scripts/check_theme_graph_contracts.py`.

**Interfaces:**
- Consumes: W3A append-only/bitemporal graph, current source receipts, existing identity seams.
- Produces: forward-replayable memberships or explicit pre-observation unavailable state for every D2C in-scope plane.

- [ ] **Step 1: Enumerate only the current-snapshot families that still fail D2 PIT gate 3.** Preserve already-correct Finviz vintage behavior unless evidence shows a defect.
- [ ] **Step 2: Write failing no-lookahead tests.** Cover first-observed boundary, later member leakage, disappearance, reappearance, missing vintage and deterministic rerun.
- [ ] **Step 3: Run the focused failing tests.** Confirm each red fails for the intended missing PIT behavior, not unrelated environment drift.
- [ ] **Step 4: Implement the smallest additive vintage/materialization change through existing owner seams.** Never reconstruct pre-observation history or mint a new history store.
- [ ] **Step 5: Run focused tests and strict graph contracts.** Use `python scripts/check_theme_graph_contracts.py --strict` plus the affected theme-graph pytest files.
- [ ] **Step 6: Run a real source build and two historical as-of queries across a known first-observed/change boundary.** Record exact inputs, graph generation identity and output rows.
- [ ] **Step 7: Independent adversarial review.** Attack lookahead, build-time/source-time laundering, interval overlap, append-only mutation and duplicate-store creation.
- [ ] **Step 8: Merge under house law, then obtain natural-nightly proof.** Do not promote from `BUILT_NOT_PROVEN` until the natural generation demonstrates correct accrual/no false movement.
- [ ] **Step 9: Update Agent OS and return D2C result to the F04 principal.** The principal decides D2E eligibility only after D2D is also accepted.

---

### Task 2: D2D — ontology and probation completion

**Files:**
- Required spec: `agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-d2d-ontology-probation-commission.md`
- Expected modify after archaeology: existing `engine/theme_graph/**`, probation/adjudication artifacts under `data/theme_graph/**`, `config/theme_crosswalk.yml` only where current owner law permits curated mapping.
- Protected: no second ontology store, no Prophet ranker/UI, no fuzzy auto-map service.
- Test: graph/probation/crosswalk contract tests and coverage harness under `research/prophet_v4/d1/build/`.

**Interfaces:**
- Consumes: source-local Finviz/THS concepts, current canonical crosswalk, probation schema, Data OS/graph identity.
- Produces: typed adjudication/probation outcomes, increased lawful navigability, explicit still-unmapped legal states and coverage delta.

- [ ] **Step 1: Re-run the current ontology/probation census.** Count source concepts, canonical-mapped concepts, unresolved/probation rows and structural-owner seams before editing.
- [ ] **Step 2: Write failing tests for forced-mapping attacks.** Include near-label collisions, multi-parent overlap, unmapped legal outcome, source-local identity preservation and caller-injected mapping refusal.
- [ ] **Step 3: Run the failing tests and record the exact red behavior.**
- [ ] **Step 4: Implement only curated/adjudication and typed relationship improvements through the existing graph/probation contract.** Preserve local identity even when a canonical parent exists.
- [ ] **Step 5: Run focused tests, graph strict checks and the D1 coverage harness.** Report coverage change without engineering toward an arbitrary target count.
- [ ] **Step 6: Mutation review.** Prove fuzzy/embedding-only labels cannot silently become accepted semantic equivalence and one company/local concept can preserve multiple memberships/parents.
- [ ] **Step 7: Independent adversarial review and merge.** Rights, identity and PIT semantics remain unchanged except where their current owner contract explicitly permits the edit.
- [ ] **Step 8: Update Agent OS and return D2D result to F04.** Do not start ThemeState from this child.

---

### Task 3: D2E — substrate acceptance and rights/coverage closure

**Files:**
- Required spec: `agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-d2e-acceptance-commission.md`
- Read: `research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md`
- Read/run: D1 coverage harness under `research/prophet_v4/d1/build/`
- Read/run: `scripts/check_theme_graph_contracts.py`
- Records: `WS:GMI-THEME-GRAPH` + accepted D2 handoff/decision surfaces.

**Interfaces:**
- Consumes: accepted D2C + D2D, current natural graph, D2B3 completion law, source-rights registry.
- Produces: one explicit D2 acceptance verdict, current coverage/eligibility census, rights/display-tier truth and natural-nightly receipt.

- [ ] **Step 1: Verify both predecessors by immutable PR/merge/proof receipts.** Do not accept a child because Linear or Slack says done.
- [ ] **Step 2: Reconcile D2B3 natural proof against its exact acceptance clauses.** Check GOLD/IBIT lifecycle/refusal behavior and strict guard evidence; do not redo the implementation unless a defect is proven.
- [ ] **Step 3: Run the D1/D2 coverage and eligibility census on the accepted graph.** Preserve closed denominators and typed reasons for gaps.
- [ ] **Step 4: Resolve only the rights/display-tier decisions required by the claimed downstream product tier.** If legal/commercial authority is required, return a bounded executive/Chairman gate rather than inventing entitlement.
- [ ] **Step 5: Run strict graph contracts, focused D2 tests and a natural-nightly production cycle.** Record exact generation identity and current graph counts.
- [ ] **Step 6: Adversarial acceptance review.** Attack lookahead, forced mapping, rights laundering, identity ambiguity, stale-data acceptance and false-green completion.
- [ ] **Step 7: Record one D2 verdict.** `PROVEN_LIVE` only if the real completion law is met; otherwise preserve the correct nonterminal capability state and exact blocker.
- [ ] **Step 8: On PASS, authorize W3B as a fresh child operation/watch cycle.** Terminalize D2E and disarm its watchers first.

---

### Task 4: W3B — sole ThemeState producer and Neural Web reconciliation

**Files:**
- Required spec: `agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-w3b-themestate-commission.md`
- Read: `research/theme_graph/W3B_CONTINUATION_HANDOFF_2026-08-14.md`
- Read: `research/prophet_v4/D1_D3_W3B_MERGE_ORDER_RECOMMENDATION.md`
- Expected create/modify after archaeology: `engine/theme_graph/**`, canonical `data/theme_graph/state/**` or the exact current accepted state path.
- Reconcile/modify: `engine/neuralweb/thematic_state.py` and its current state/history projections only under the frozen one-producer ruling.
- Test: existing theme_graph/neuralweb thematic-state tests plus new eligibility/state/PIT tests.

**Interfaces:**
- Consumes: accepted D2 graph, existing owner measurement legs/readers.
- Produces: one canonical local+canonical `theme_state/v1`, eligibility/abstention results and PIT transition history; existing Neural Web becomes consumer/projection or the accepted owner implementation, never a rival producer.

- [ ] **Step 1: Census every existing theme-state producer/reader/history path before writing.** Freeze the exact supersede/extend/consumer decision for Neural Web.
- [ ] **Step 2: Preregister measurement eligibility using historical evidence/current owner law.** Include breadth, price/PIT depth, identity integrity, missingness, concentration, freshness, survivorship/era and incoherence abstention.
- [ ] **Step 3: Write failing eligibility and state-contract tests.** Fixtures must include China lithium, unmapped THS, Finviz local with/without canonical parent, sparse concept, overly broad incoherent theme, stale source, concentrated theme, reconstruction era, observed era and honest no-state null.
- [ ] **Step 4: Implement named state legs by reading owner statistics.** Do not recompute owner metrics or emit a fused `Theme Score`.
- [ ] **Step 5: Implement local+canonical state while preserving local distinctions.** Canonical aggregation may not overwrite local state.
- [ ] **Step 6: Reconcile Neural Web lineage.** End with exactly one owner producer/truth and explicit projections/readers; add hostile tests that fail if both old and new producers can independently author state.
- [ ] **Step 7: Run focused/full affected tests and strict graph contracts.**
- [ ] **Step 8: Natural-nightly proof.** Demonstrate accrual/transition behavior plus stale/sparse abstention on the real path.
- [ ] **Step 9: Real reader proof.** At least one current machine consumer must read the canonical state contract; no docs-only completion.
- [ ] **Step 10: Independent adversarial review, merge and Agent OS closeout.** Then terminalize W3B/watchers before opening W3C.

---

### Task 5: W3C — U.S./China Selection Cohort Intelligence

**Files:**
- Required spec: `agentos/handoffs/GMI-THEME-GRAPH-2026-08-27-w3c-cohort-intelligence-commission.md`
- Consume current incumbent U.S./China selection artifacts via their owner readers.
- Expected create/modify after archaeology: bounded GMI cohort reader/composer contract under `engine/theme_graph/**` or current owner-approved namespace; existing site/machine projection only as a real consumer.
- Test: identity/order/no-authority/PIT-overlap fixtures plus real selected-set controls.

**Interfaces:**
- Consumes: already-finalized selection set + exact identity + PIT local memberships + ThemeState + canonical relations.
- Produces: descriptive overlap/neighborhood/cohort context preserving source selection order and exact input selection.

- [ ] **Step 1: Freeze exact U.S. and China input contracts.** Capture artifact ID/schema/as-of/selection timestamp/instrument IDs/source ordering/reason where allowed.
- [ ] **Step 2: Write failing tests proving output cannot add/remove/reorder selected instruments.** Also cover unresolved identity, no-overlap and overlapping-microtheme preservation.
- [ ] **Step 3: Implement deterministic join composition.** Identity -> PIT membership -> ThemeState -> canonical relationship -> descriptive overlap; no model-generated membership or selection authority.
- [ ] **Step 4: Prove one real U.S. cohort and one real China cohort.** Include a no-cohort/null control.
- [ ] **Step 5: Add a real machine/product consumer projection at the truthful display/research tier.** Do not pull F04 opportunity/ranking semantics into W3C.
- [ ] **Step 6: Adversarial review.** Attack order mutation, selection leakage, current-membership lookahead, coarse-theme flattening and unearned rank language.
- [ ] **Step 7: Merge and production-proof the consumer path.** On acceptance, terminalize W3C and close the unfinished GMI development frontier in Agent OS.

---

### Task 6: F04-A — canonical theme/cohort explanation product

**Files:**
- Parent spec: `agentos/handoffs/MARKET-ONTOLOGY-F04-ONTOLOGY-TRANSMISSION-OPPORTUNITY-FABLE-COO-2026-08-26.md`
- Consume: accepted GMI graph/ThemeState/cohort readers; current Market OS / Neural Web product surfaces.
- Expected modify: current F04/Market OS composition and publication surfaces only after archaeology; never GMI truth tables directly except through owner readers/contracts.
- Test: product contract + browser/machine projection tests at the selected surface.

**Interfaces:**
- Consumes: canonical GMI state/cohort objects.
- Produces: researcher can start from a theme/selected cohort and see local/canonical context, current state, evidence, overlap, null/degraded reasons and drilldown.

- [ ] **Step 1: Freeze one concrete user surface and one machine projection.** Reuse current product shell; do not create a new theme portal unless current owner architecture explicitly requires it.
- [ ] **Step 2: Write failing contract/UI tests for canonical-source-only reads, stale/null display and evidence drilldown.**
- [ ] **Step 3: Implement the smallest vertical from GMI reader -> F04 composer -> current product projection.**
- [ ] **Step 4: Prove a real U.S. and China example plus degraded/no-state control.**
- [ ] **Step 5: Browser proof at relevant breakpoints for user-facing output.** Capture real data, no fixture-only acceptance.
- [ ] **Step 6: Independent review and production proof.** Continue parent F04; do not terminalize the program yet.

---

### Task 7: F04-B — transmission / second-order explanation over existing owners

**Files:**
- Consume: accepted K3-D contract when Sol releases #6514; TXI/incorporation/dislocation/specialist-owner readers; GMI semantic/state context.
- Expected modify: F04 composition/product surfaces and bounded contract adapters only; no new graph/store.
- Test: Graph-1/2/3 laundering, unit/horizon, double-count, identity, rights, falsifier/expiry and typed-abstention tests.

**Interfaces:**
- Consumes: owner-backed economic/narrative/residual evidence with exact provenance/clocks.
- Produces: a researcher can inspect why a transfer/path is plausible, what evidence species support it, what is missing, what alternatives/falsifiers apply and what appears untransmitted/incorporated.

- [ ] **Step 1: Sol separately resolves K3-D #6514 exact-head hold before F04 treats it as accepted current semantics.** Until then, only independent F04 work proceeds.
- [ ] **Step 2: Freeze the owner-adoption matrix.** Every displayed leg maps to one native owner/construct/unit/horizon/right; Graph 2/3 can never fill missing Graph 1.
- [ ] **Step 3: Write hostile laundering/double-count tests before implementation.** Include honest no-Graph-1 case as a successful abstention.
- [ ] **Step 4: Implement one transmission/explanation vertical using only owner readers/contracts.** No generic `RELATED`, propagation scalar or causal DAG alpha.
- [ ] **Step 5: Prove one real positive path if current data lawfully supports it and one real abstention.** Do not widen scope merely to manufacture a positive example.
- [ ] **Step 6: Add Transmission Gap / second-order projection only where its semantics are transparent and non-authoritative.** Opaque `confidence`, `priced %` or trade claims remain refused absent promoted semantics.
- [ ] **Step 7: Browser/machine production proof and adversarial review.** Continue parent F04 to final integration.

---

### Task 8: F04-C — integrated Neural Web / Market OS continuity and final acceptance

**Files:**
- Consume all accepted GMI/F04/K3/TXI owner contracts.
- Modify current Market OS / Neural Web composition/navigation/publication paths only after exact owner archaeology.
- Records: `WS:GMI-THEME-GRAPH`, `WS:ALPHA-INTELLIGENCE-INTEGRATION`/F04, `MAS-145`, final handoffs/decisions.

**Interfaces:**
- Consumes: canonical context/path objects.
- Produces: coherent user journey from theme/event/selected cohort -> state -> relationship/transmission explanation -> evidence/falsifier/drilldown -> appropriate existing next-research surface, with no unearned trade authority.

- [ ] **Step 1: Run end-to-end source-owner census immediately before final integration.** Confirm no new competing theme/state/transmission product landed while the program ran.
- [ ] **Step 2: Wire one coherent navigation journey through current surfaces.** Preserve owner facts and null/degraded states; no parallel publication truth.
- [ ] **Step 3: Instrument learning/usage through existing telemetry/outcome infrastructure where already owned.** Do not create a new memory/grader plane.
- [ ] **Step 4: Run the three required production acceptance journeys:** one real U.S. journey, one real China journey and one real transmission/explanation journey.
- [ ] **Step 5: Run failure-state acceptance:** stale source, unresolved identity, unmapped concept, sparse/unmeasurable theme, absent Graph 1 and rights-blocked context each remain truthful.
- [ ] **Step 6: Browser proof at relevant breakpoints plus machine-reader receipts.**
- [ ] **Step 7: Reconcile Agent OS and Linear to actual capability states.** Close the legacy GMI Transmission TODO by supersession; do not false-green anything lacking production proof.
- [ ] **Step 8: Return the final milestone bundle to Sol.** Include accepted PR/merge SHAs, CI/adversarial reviews, production receipts, screenshots/browser proof, current capability ledger, remaining authority-gated experiments and no-rebuild evidence.
- [ ] **Step 9: On Sol acceptance, receive terminal `SOL ACCEPTED / STOP` for the F04 parent operation, disarm the Fable watcher and end the session.** If shutdown fails, report `WATCH_STOP_FAILED`; do not originate another wave.

## Master stop condition

The program is complete only when Tasks 1-8 meet their real proof laws, GMI has one reconciled ThemeState authority, F04 provides the coherent research workflow, the three real acceptance journeys pass, no duplicate graph/state/product truth exists, and Sol issues terminal acceptance for the parent operation. W7+ reranking/neighbor discovery remains separate future research and is not silently pulled into this program.
