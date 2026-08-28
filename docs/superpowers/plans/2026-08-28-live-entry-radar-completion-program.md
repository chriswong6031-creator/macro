# Live Entry Radar Completion Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Live Entry Radar from its existing commissioned live engine to a secure, dark-gap-recoverable, prospectively evaluated, Research-Priority-ranked and production-browser-proven U.S. tactical entry product without changing Prophet or duplicating canonical owners.

**Architecture:** Extend the existing Radar evaluator/spool/W5/qledger/product owners in bounded verticals. First secure the existing raw evidence transport, then prove cold/full-RTH reliability, reconnect the existing W5 prospective consumer, accept W6 on real developing episodes, reconcile existing W8, ship W9 and only then adjudicate W7 when honest prospective sample permits it.

**Tech Stack:** Python, pandas/parquet, existing Macro live systemd/VPS deployment, existing Cloudflare R2/boto3 seam, FastAPI/static-product serving patterns, Jinja/static HTML/CSS/JS as already used by Macro, pytest, Playwright/RIG, Agent OS, Evaluation OS/qledger.

**Spec:** `research/live_entry_radar/LIVE_ENTRY_RADAR_COMPLETION_ARCHITECTURE_MASTERPLAN_2026-08-28.md`

## Global Constraints

- Preserve protected Sol Skillpack procedure and re-pin it before each modifying child.
- Preserve `DEC:LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE` and all Prophet protected paths.
- Preserve all published Radar detector hashes; no formula retuning in infrastructure/product waves.
- Preserve expert-event family identity; no generic `entry_signal` flattening.
- Reuse the existing quote/snapshot plane, `engine/entry_radar/spool.py` client/credential owner, W5 sole durable writer, qledger and product-serving patterns.
- Missing/stale/unavailable/raw-basis/correction states remain typed and never become numeric zero or healthy silence.
- One independently useful capability per PR; one logical modifying child per stable operation key/carrier.
- Real production/browser proof is required where named; fixtures and green CI cannot substitute.
- Temporary dialogue watchers are attention-only and must be stopped explicitly at each child terminal boundary.

---

### Task 1: Land the completion freeze and reconcile program state

**Files:**
- Create: `research/live_entry_radar/LIVE_ENTRY_RADAR_COMPLETION_ARCHITECTURE_MASTERPLAN_2026-08-28.md`
- Create: `agentos/decisions/DEC-LER-END-TO-END-COMPLETION-ARCHITECTURE-FREEZE.md`
- Create: `agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-28-fable-coo-program.md`
- Modify: `agentos/workstreams/WS-LIVE-ENTRY-RADAR.md`
- Create: `docs/superpowers/plans/2026-08-28-live-entry-radar-completion-program.md`

**Interfaces:**
- Consumes: current `WS:LIVE-ENTRY-RADAR`, PR #5737, current `data/entry_radar/ledger_state.json`, W4.1/Day-5 security/cadence records.
- Produces: one canonical remaining-wave graph and sustained-COO handoff; no runtime capability.

- [ ] Re-pin current protected Skillpack, Macro main, #5737 and all open `entry_radar` carriers immediately before final review.
- [ ] Confirm current W5 durable ledger still truthfully describes current production evidence state; do not copy a historical value if nightly state has advanced.
- [ ] Ensure W4.1 historical receipts remain preserved while stale global next-action language is superseded.
- [ ] Run `python3 scripts/agentos.py validate` on the exact records head.
- [ ] Run exact-head hosted CI/fences required for the records carrier.
- [ ] Sol reviews the exact records head and merges only if it remains records-only and current.
- [ ] Commit/merge receipt must state that zero implementation/product/runtime capability is made live by Task 1.

### Task 2: LER-C1 — make the Radar evidence spool private

**Files:**
- Expected modify/factor territory: `engine/entry_radar/spool.py`
- Expected consumers to inspect and modify only if required: `engine/prophet_lab/sources.py`, `engine/prophet_lab/response.py`, `scripts/reconcile_entry_radar.py`
- Expected deployment/config territory: existing R2 delivery-plane configuration/runbooks already owning private/public classification
- Tests: existing `tests/test_entry_radar_w4_lane.py`, `tests/test_entry_radar_w41_transport.py`, `tests/test_prophet_lab_commissioning.py`, `tests/test_entry_radar_w5_reconciler.py` plus one focused security-boundary suite if no canonical one exists

**Interfaces:**
- Consumes: existing `EventSpool`/R2 client/credential seam and current authenticated Lab reader.
- Produces: same semantic event envelope available to authenticated canonical consumers but anonymous public access structurally refused.

- [ ] Before code, prove the current exposure state with a privacy-safe probe against one known historical key and current delivery configuration; record `200` only if still true.
- [ ] Map every current writer/reader of `live_flow/entry_radar_events/` and confirm there is exactly one client/credential family.
- [ ] Write a RED regression that fails if a future producer can route Radar raw evidence through an explicitly public delivery classification.
- [ ] Implement the smallest structural private-boundary change through the accepted R2/delivery owner; do not create a second boto3 client/config family.
- [ ] Preserve event key/identity semantics where possible; if object location must change, provide an authenticated read migration/compatibility path without making old public keys canonical again.
- [ ] Prove writer success, Lab read success and W5 read success on the private destination.
- [ ] Prove anonymous GET of a known current/private envelope is non-200.
- [ ] Prove public product paths contain no raw evidence URL/private object locator.
- [ ] Run focused tests, full Radar/Prophet-Lab adjacent suites, exact-head hosted CI/security review.
- [ ] Return to Sol for security acceptance; terminal STOP after this child even if the same Fable session will continue.

### Task 3: LER-C2 — dark-gap recovery, current coverage and full natural RTH cadence

**Files:**
- Expected inspect/modify: `engine/entry_radar/live_pack.py`, `engine/entry_radar/live_eval.py`, existing Radar substrate helpers, `scripts/entry_radar_live.py`, `scripts/entry_radar_live_pack.py`
- Deployment: existing `app/deploy/` and Radar systemd unit/drop-in owner only when causally required
- Tests: existing W4/W4.1 suites plus focused cold-start/cadence instrumentation regressions

**Interfaces:**
- Consumes: final private spool from Task 2, current Terminal slice owner, current quote plane.
- Produces: a service that autonomously cold-starts and then sustains accepted warm cadence.

- [ ] Capture a genuine dark-gap baseline with phase-by-phase wall time, CPU, RSS, I/O and refusal state before changing implementation.
- [ ] Measure source/slice discovery, pack build/inversion, quote load, minute/path loads, detector evaluation, ledger diff and spool/publish separately.
- [ ] Write a discriminating regression or deterministic benchmark around the identified dominant recomputation/I/O behavior.
- [ ] Implement the smallest owner-compatible cache/prewarm/bootstrap repair using fingerprinted/correction-safe substrate; do not weaken freshness or PIT gates.
- [ ] Prove a dark-gap service start reaches its first valid envelope without manual timer stop/start, overlap or timeout.
- [ ] Record current probe-set population, quote availability, usable share and every refusal class; do not treat low coverage as a code failure unless owner semantics say so.
- [ ] Run one full natural U.S. RTH session with pass timings, event/transition counts, basis audits, stale/degraded states and overlap checks.
- [ ] Exercise cold restart, stale quote, raw-basis mismatch, unavailable confirmed lane, empty-delta and writer-failure states.
- [ ] Verify pack-service memory ceilings under a real in-service build rather than an unconstrained manual build.
- [ ] Run full Radar tests, exact-head hosted CI, production deploy proof and independent reliability review.
- [ ] Return exact dark-start + full-RTH receipts to Sol; terminal STOP after acceptance.

### Task 4: LER-C3 — reconnect W5 prospective Evaluation OS evidence

**Files:**
- Modify/factor: `scripts/reconcile_entry_radar.py`
- Modify existing nightly workflow only where required to expose the accepted private spool through the existing nightly owner
- Reuse: `engine/entry_radar/spool.py`, `engine/qledger.py`, `engine/ledger_lane.py`
- Test: `tests/test_entry_radar_w5_reconciler.py`, `tests/test_entry_radar_w41_transport.py` and focused nightly/private-spool integration coverage

**Interfaces:**
- Consumes: canonical private `entry_radar.events/v1` envelopes.
- Produces: existing `data/entry_radar/forward.parquet`, qledger registration log/state and nonzero truthful ledger state.

- [ ] Reproduce current `spool_dir=null` / `WAITING_FOR_LIVE_SOURCE` behavior under the actual nightly environment and identify why the canonical reader cannot see the private spool.
- [ ] Write a RED integration test using the same read-side seam the final nightly uses; no fake parallel reader.
- [ ] Rebind/factor the existing W5 reconciler onto the canonical private spool ladder.
- [ ] Preserve `read_spool_events()` validation, event-id dedup, earliest valid envelope clock, no-backfill and sole-writer law.
- [ ] Preserve one `register_batch()` call and existing qledger horizon/control policy.
- [ ] Run the real nightly path on a genuine current-session event and require nonzero observed/live-forward totals, `forward.parquet` row and qledger outcome.
- [ ] Re-run the same input and prove idempotence/keep-first behavior.
- [ ] Prove malformed/torn/private-read-error cases remain fail-closed and do not rewrite prior evidence.
- [ ] Run focused + full Radar/Eval adjacent suites and hosted CI.
- [ ] Return the real event -> spool -> forward row -> qledger receipt to Sol; terminal STOP after acceptance.

### Task 5: LER-C4 — close W6 Research Priority on real developing episodes

**Files:**
- Primary implementation under review: existing `engine/entry_radar/research_priority.py` and its current projection consumer
- Tests: existing `tests/test_entry_radar_w6_priority.py` plus production acceptance receipt under `research/live_entry_radar/`

**Interfaces:**
- Consumes: real current developing episodes from Tasks 3/4.
- Produces: non-empty deterministic Research Priority board/projection with explainable decomposition.

- [ ] Do not inspect outcomes to redesign/retune the score before the acceptance run.
- [ ] Run the current exact W6 method on a genuine non-empty developing-RTH population.
- [ ] Verify one unique current name snapshot per ticker and `snapshot_conflict` fail-closed behavior.
- [ ] Verify percentile-each-submeasure-before-combine and unit invariance still hold.
- [ ] Verify `priority_value`, ordinal and presentation index semantics are consistent.
- [ ] Verify every rankable row carries provenance/decomposition and every unrankable row carries a reason.
- [ ] Verify no Prophet protected path or authority field changed.
- [ ] Sol performs the W6 scientific/methodological acceptance; if a genuine implementation defect is found, issue one bounded repair on the same child carrier before terminal STOP.

### Task 6: LER-C5 — reconcile existing W8 #5737

**Files:**
- Existing carrier only: PR #5737 / branch `cursor/entry-radar-w8-rig-9f9d`
- Reference tree: `mockups/refs/entry_radar/`
- RIG: `research/reference_integrity/entry-radar-w8/`, `tests/test_entry_radar_w8_rig.py`

**Interfaces:**
- Consumes: accepted W8 freeze/reference.
- Produces: reference/RIG on current main; no production page.

- [ ] Re-pin current main and compare every #5737 changed path against changes landed since its ancient base.
- [ ] Do not reset/replace the carrier; reconcile it history-preservingly or return a collision if semantic source law moved.
- [ ] Re-run static RIG, mutation battery and real Playwright geometry; a Playwright skip is not a geometry pass.
- [ ] Recheck pinned Prophet sister-language assumptions; preserve explicit W9 conditions if newer Prophet work does not supersede them.
- [ ] Merge only as reference completion after exact-head CI/review.
- [ ] Do not start W9 inside this child; terminal STOP.

### Task 7: LER-C6 — ship the production Entry Radar page

**Files:**
- Create: `templates/entry_radar.html.j2`
- Create/generated: `site/entry_radar.html`
- Create/modify the smallest existing server/read-model path required to project safe real Radar data; reuse current Macro serving/auth/build patterns
- Tests: production page contract + browser tests and adapted W8 RIG floor

**Interfaces:**
- Consumes: secure live Radar state, accepted W6 Research Priority, W8 reference, W5 evidence status.
- Produces: real user-facing Entry Radar surface.

- [ ] Freeze the production DTO/read model field-by-field from existing owners; do not expose raw spool bodies or private evidence locators.
- [ ] Write RED contract tests for one card per `(ticker, expert)`, explicit lifecycle/freshness, false-start preservation, Research Priority provenance, W7 `NOT YET MEASURED`, and typed degraded states.
- [ ] Implement real page rendering using accepted W8 sister-language without copying synthetic fixtures as product truth.
- [ ] Reserve every §14 slot: populate from owner data when present; otherwise print typed `ACCRUING`/`UNAVAILABLE`, not an invented value.
- [ ] Preserve C4 as context-only, multi-expert tickers as multiple observations and no full-card fake ticker link.
- [ ] Verify private/security data never reaches anonymous/product payloads.
- [ ] Run production browser acceptance at 1440, 1280, 1024, 720 and 390; EN/ZH; dark/light; keyboard/reduced-motion; console/network/overflow/occlusion checks.
- [ ] Exercise real healthy, empty, stale, raw-basis mismatch, unavailable confirmed-lane, evaluator-degraded and evidence-consumer-degraded states.
- [ ] Deploy through the existing production path and repeat browser proof on the deployed bytes.
- [ ] Return to Sol for product acceptance; terminal STOP.

### Task 8: LER-C7 — adjudicate W7 Opportunity research when sample-ready

**Files:**
- Define only after current W7 contract/prereg/owner census at pickup; stay under `engine/entry_radar/`, `research/live_entry_radar/` and existing Eval OS owners unless Sol explicitly widens scope

**Interfaces:**
- Consumes: prospective W5/qledger evidence and frozen outcome definitions.
- Produces: scientifically adjudicated Opportunity research or an explicit sample-gated accrual state.

- [ ] Check the preregistered sample/readiness gate before model construction or confirmatory inspection.
- [ ] If not sample-ready, return `ACCRUING` with exact missing N/time/coverage; do not manufacture a model.
- [ ] If sample-ready, freeze model/calibration method and evaluation law before reading confirmatory results.
- [ ] Run outcome leakage, PIT, name concentration/effective-N, calibration and comparison falsifiers required by the frozen research law.
- [ ] Keep display/research authority separate from Prophet/trade authority.
- [ ] Sol adjudicates accepted/rejected/accruing scientific state.
- [ ] Terminal STOP after the scientific decision; any promotion is a separate future operation.

### Task 9: LER-C8 — integrated end-to-end acceptance and Stock Identity handoff

**Files:**
- Primarily receipts/Agent OS closeout; implementation files only if a bounded defect is discovered and separately commissioned
- Update: `agentos/workstreams/WS-LIVE-ENTRY-RADAR.md`
- Update/create: final `research/live_entry_radar/` production/research acceptance receipt
- Create/update: final Agent OS handoff/decision as required

**Interfaces:**
- Consumes: accepted Tasks 2-8.
- Produces: recoverable final program state and read-only Stock Identity boundary.

- [ ] Run one real current RTH input through quote/substrate -> evaluator -> private spool -> W5/qledger -> W6 Research Priority -> deployed page.
- [ ] Attach the accepted dark-gap and full-RTH receipts to the final acceptance packet.
- [ ] Re-probe anonymous evidence access and product payload leakage.
- [ ] Re-run desktop/narrow browser acceptance on the final deployed generation.
- [ ] Verify current W5 ledger is non-disconnected and forward evidence is accruing.
- [ ] Record W7 as accepted, rejected or honestly accruing; do not call research complete if its declared gate is still silently unaddressed.
- [ ] Freeze the Radar -> Stock Identity read-only expert-event handoff and confirm no Radar per-security expert router exists.
- [ ] Reconfirm Prophet protected paths/behavior remained outside the program.
- [ ] Sol performs final outcome-based acceptance using `REVIEW_RETURN.md` and `CLOSEOUT.md`.
- [ ] Update Agent OS and repair Linear projections only after canonical final evidence is known.
- [ ] Send terminal STOP to the final COO child, verify both watchers disarmed, and record any `WATCH_STOP_FAILED` without reopening the child.
