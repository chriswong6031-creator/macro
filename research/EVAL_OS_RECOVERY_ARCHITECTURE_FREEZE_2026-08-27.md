# Intelligence Evaluation OS — Recovery Capability Ledger + Architecture Freeze

**Status:** CEO architecture freeze / records-only  
**Chairman intent:** end-to-end CEO ownership of Intelligence Evaluation OS until measurement, health, promotion law and evidence clocks are complete and proven in real use.  
**Recovered:** 2026-08-27 America/New_York / 2026-08-28 UTC  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@d508e30c865bd2425bb551650b71381b7eb6d4f8` (`mastermind.sol_skillpack.v1`, v1.0.0, bootstrap-major 1)  
**Macro freeze base:** `d84468e41f40f8dfb2404b2f51be557aade8f0ec`

This record supersedes stale *next actions* in the 2026-08-14 Eval OS workstream/handoff records. It does not erase their evidence or change historical rulings. It creates no runtime, score, monitor, registry, promotion authority or generated state.

## 1. Outcome and completion law

Evaluation OS exists to make one answer defensible: **which Mastermind intelligence outputs are working, what exactly was measured, on what clock/ruler, and what authority may that evidence lawfully support?**

Completion is not “the library exists”, a merged PR, a green CI run, or a Slack delivery. Complete means real producers register claims prospectively, real grading runs mature those claims under their declared clocks, illegal readings/promotions fail closed, operators can see output health and evidence status in the existing admin surface, and no second evaluation/control plane was created.

## 2. Recovered capability ledger

| Capability | State | Recovered truth |
|---|---|---|
| T0 metric-validity substrate | `PARTIAL` | #5471 landed the auditor and core invariants, but `scripts/check_qledger_metric_validity.py` remains WARN-tier by default; the planned T3 hardening is not complete. |
| T1 canonical engine registry | `PROVEN_LIVE` for its bounded registry/guard law | #5620 / `d13259abc51c` landed the derived `producer::owner_program` registry, fail-closed integrity guard and isolated CI. W3 curated 107/109 output classes with two deliberate nulls. Agent OS and Linear MAS-131 were later reconciled to `done`. |
| Qledger horizon-unit + market-ruler law | `PROVEN_LIVE` on qledger path | Explicit `trading_days` / `calendar_days`, market resolution, maturity/check-by/grading window and rendered ruler are resolved centrally for qledger claims. Current production track record emits clock-basis metadata. |
| Cross-clock pooling refusal | `PROVEN_LIVE` on current qledger track-record path | Current `site/qledger/track_record.json` selects a single legal basis and emits `pooling_refused: true` where legacy and explicit bases coexist. |
| Direction-correct / output-class metric legality as a fleet-wide hard gate | `PARTIAL` | Core fixes exist (#5519/#5572/#5573 and later clock work), but the top-level metric-validity gate still deliberately exits warn-tier by default. |
| Append-only assertion law | `PROVEN_LIVE` for repository guard law | #5534 merged; stale Agent OS text still says to merge it. |
| Forward-only desk adapters | `PARTIAL` | #5577 merged adapters for `stock_desk`, `thematic_desk`, `demand_chain`; actual clock evidence proves only `demand_chain` began prospective accrual. |
| General forward evidence clock | `PARTIAL` | `demand_chain` started `2026-08-19T08:10:37.995754+00:00`, 126 trading days, trigger git SHA `34899ec5235884e183be86088ab01f81e34a693f`. No current tracked clock exists for `stock_desk` or `thematic_desk`. No backfill is permitted. |
| Legacy evidence promotion firewall | `BUILT_NOT_PROVEN` as a complete end-to-end authority refusal | #5584 prevents legacy-clock evidence from originating new authority after the clock discontinuity and forbids mixing legacy with explicit evidence. It still needs one unified adversarial/consumer proof on the final path. |
| CEO control-leg policy | `PARTIAL` in live accrual, **decision resolved** | P0d/#5609 established benchmark universal baseline; matched control only where a defensible counterfactual exists. `stock_desk` and `demand_chain` are matched-control-required; `thematic_desk` is benchmark-only. #5665/#5672 repaired demand-chain wiring and replay clock consistency. |
| Matched-control evidence clock | `PARTIAL` | Historical production receipt proves `demand_chain` started `2026-08-19T08:10:37.332100+00:00`, control `XLU`, 126 trading days. #5970 then correctly untracked/ignored control-clock files because the canonical file is runner-local/write-once. Current runner-local persistence must be verified on the production host; no second persisted copy may be invented. `stock_desk` has no proven start. |
| Promotion readiness consumer | `PARTIAL` | Current qledger nightly runs and emits readiness; 2026-08-27 production `run_status.json` reports 1,250 grades that run, zero promotion-ready families, and `radar@21d` approaching. Readiness remains advisory; existing authority/promotion owners remain canonical. |
| T4 per-output health resolver | `BUILT_NOT_PROVEN` | Old branch is gone. #5721 merged as `a77d874a1c23c7e4e2db0000db75164fcc56bcc2` after adversarial HOLD/fixes. Health is derived on demand over T1 + Synapse + existing evidence providers; no generated health state. Real deployed admin proof is still missing. |
| Existing admin Intelligence OS health page | `BUILT_NOT_PROVEN` | #5721 added read-only admin routes/page, in-memory cache only. No accepted production-browser/operator receipt was found. |
| T7 per-engine evidence scorecard | `NOT_BUILT` | Code search finds the required Validated/Accruing/Ungraded/Degraded/Disproven semantics only in architecture/plans, not implementation. |
| T8 global CEO evidence view | `NOT_BUILT` | Same: still plan/spec. It must rank by evidence strength and show empty/negative states honestly. |
| T9 qledger adoption / real evidence accrual | `PARTIAL` | qledger is active at scale, but focal desk adoption is incomplete and the original “every directional engine” adoption law has not been proven. |
| T10 contradiction classification addition | `NOT_BUILT` as the Eval-OS addition | The pre-existing contradiction detector remains the canonical detector; Eval OS must not rebuild it. The planned healthy-tension/impossible-contradiction classification layer is not proven implemented. |
| T11 deterministic numeric-source verification | `NOT_BUILT` as the planned addition | Existing response-eval rubric remains canonical and must not be replaced; deterministic number-to-source verification is still a separate missing layer. |
| T12 Agent OS tier interface | `NOT_BUILT` | `required_tier(diff)` is found only in the V1 plan. Eval OS may state required evidence tier; Agent OS remains the router/owner of work. |
| Executive OS current-state read / CEO admission from Personal-Pro | `DARK_OR_DISCONNECTED` for this session | C1 implementation #155 merged in Mastermind, and the Relay bot has joined `#sol-runtime`, but no `MMX/SOL_STATE_V1` frame exists yet. No current Executive Job/Attempt/Worker state can be canonically read, and no Executive modifying admission may be assumed. |

### Current qledger production evidence

At the recovery base, `data/qledger/run_status.json` is a real active-run artifact (`as_of: 2026-08-27`): 68,291 open, 1,250 graded in the run, 37,014 blocked by coverage, 4 ungradeable, 83,568 already graded; 14 claims are clock-unresolvable and are disclosed rather than guessed. Readiness reports zero families ready. This proves the grading plane is alive; it does **not** prove Evaluation OS complete.

## 3. Stale records and carriers

1. `WS:EVAL-OS-MEASUREMENT-LAW` W4 still says “merge #5534/#5577/P0c-2”; all are already merged. Its W5 still says control-leg CEO ruling is unresolved; P0d/#5609 and the preregistered control contract already resolved it.
2. `WS:EVAL-OS-OUTPUT-HEALTH` still says T4 is on `claude/eval-os-t4-output-health` awaiting adversarial review/PR. That branch no longer exists; #5721 merged on 2026-08-15 after adversarial review and repair.
3. T1 continuation material from 2026-08-12/14 is historical archaeology only. T1 itself was later reconciled to done by #6392 / MAS-131.
4. #5512’s recommendation to defer T7/T8 because the validated list would be nearly empty was a then-current planning judgment, not a permanent prohibition. An honest L4 must be useful precisely when Validated is empty and Accruing/Degraded dominate.
5. No current Eval OS implementation PR or Slack carrier was found at recovery. Never revive an old branch name as a carrier.

## 4. CEO rulings — frozen

### R1 — one ruler means one declared claim clock

A claim’s evaluation identity includes its declared horizon value, horizon unit and resolved market calendar. Qledger’s resolver is canonical for qledger claims. `check_by`, maturity, grade window and displayed ruler must come from that contract; no caller may silently substitute calendar days for trading days or another market’s session calendar.

The existing 5/21/63 grade ladder remains binding. A claim declared beyond 63 sessions (for example `demand_chain` at 126 trading days) may have a 126-day check-by but does **not** gain an own-horizon grade merely because 5/21/63 grades exist. Do not extend the ladder in this program without a separate explicit ruling.

### R2 — clock bases never launder into one sample

`legacy_calendar_unstamped` and `explicit_unit_v1` are different evidence bases. Explicit bases further distinguish horizon unit and market. Mixed bases may be displayed side-by-side but never pooled into one promotion statistic. Legacy evidence may remain visible historically but cannot originate post-discontinuity authority; explicit evidence must independently satisfy the gate.

### R3 — control policy is resolved

Benchmark-relative evidence is the universal baseline. A matched-control leg is required only for families whose governed policy says a defensible matched counterfactual exists. Current required families are `stock_desk` and `demand_chain`; `thematic_desk` is benchmark-only. Missing/unpriceable required controls reduce coverage and cannot silently fall out of the denominator. Policy is governed by the one existing qledger policy table; it may never be inferred from which rows happen to contain controls.

### R4 — runner-local control clocks stay runner-local

#5970 is correct. `data/qledger/control_evidence_clock_start/` is a write-once operational clock, not a Git-tracked knowledge store. Do not solve observability by committing another canonical copy. Admin/diagnostic views may read and render the same operational source or a non-authoritative receipt, but only the write-once runtime clock decides cohort membership.

### R5 — no new promotion authority

Qledger promotion/readiness calculations remain measurement/advisory evidence. Existing canonical lifecycle/authority owners (`config/qual_ladder.yml`, species/prereg/gauntlet laws and their governed consumers) remain the authority plane. Eval OS may refuse an illegal measurement from supporting promotion; it does not create another promotion database/service.

### R6 — output health is a view, not a monitor

T4 remains pure/derived over T1, Synapse and existing evidence providers. No committed health artifact, second freshness registry, watchdog, graph, dead-man switch or health score store. `could_not_look` is a first-class assessment result and never becomes healthy/neutral.

### R7 — L4 uses the existing admin Intelligence OS surface

T7/T8 extend the existing read-only Intelligence OS admin page/API. They do not create a second admin product or score store. Per-engine metrics are selected by T1 `output_class`; null class stays null. “Cannot claim yet” must carry the same visual weight as positive evidence.

### R8 — Eval OS does not route work

T12 may deterministically derive the evidence/review tier required by a changed engine/authority surface and emit a structured finding. Agent OS owns durable workstreams and routing. Eval OS does not create a queue, worker lifecycle or priority authority.

## 5. Architecture freeze — canonical flow

```text
Synapse + existing authority sources
        |
        v
T1 derived engine registry  -------------------------------+
        |                                                  |
        +--> T4 derived output health <--- existing health evidence providers
        |
real engine producer
        v
qledger claim (prospective, declared horizon/unit/market/control policy)
        v
write-once evidence clocks + shared resolver
        v
qledger grade (shared subject/benchmark/control window)
        v
legal metric contract + single-clock partition
        v
promotion-readiness / existing gauntlet authority checks
        |
        +--> T7 per-engine evidence scorecard
        +--> T8 global CEO evidence view
        +--> T12 evidence-tier finding (Agent OS routes, not Eval OS)
```

**Forbidden forks:** second engine registry; second claims/grades store; second health monitor/store; second promotion authority; hand-maintained score database; retrospective “prospective” rows; new hidden clock store; a public/internal score that pools different clock bases.

## 6. Completion map / bounded waves

### E1 — Real desk clock recovery and accrual proof — first critical path

Observable mission: a real scheduled/production run causes `stock_desk` and `thematic_desk` to register truly prospective claims and mint their first general evidence clocks; `stock_desk` also starts its matched-control evidence clock if and only if the first valid controlled prospective claim exists; `demand_chain` current runner-local control-clock state is verified without recreating it.

Non-goals: no retrospective rows, no backfilled flag, no clock timestamp copied from this document, no qledger redesign, no grade-ladder extension, no authority change.

Proof: exact trigger rows, clock timestamps originating from trigger claim timestamps, next real grading run sees them under the correct basis, and negative proof that pre-clock rows cannot enter the new authority cohort.

### H1 — T4 deployed/admin proof and blindness census — may run in parallel with E1

Observable mission: exact merged T4 code is verified on the real deployed admin path and real Synapse estate; operator sees healthy/degraded/stale/unavailable/could_not_look states, output-class nulls and dependency bounds without persisted health state.

Non-goals: no monitor, no scorecard authority, no T7/T8 performance ranking yet, no healing source declarations inside the proof wave unless a specific declaration defect prevents truthful rendering.

Proof: browser/API receipt on production, real artifact census, representative degraded/blind/unavailable cases, and fixture/reflection controls on the exact implementation head/release.

### P1 — Unified promotion/clock-laundering adversarial acceptance — after E1 qledger-path changes settle

Observable mission: one acceptance suite demonstrates that illegal promotion evidence fails closed through the real readiness/consumer path, not merely inside helper functions.

Required mutations: legacy evidence treated as new authority; explicit+legacy pooling; unit/market basis stripped; 126d check-by mislabeled as own-horizon verdict; retrospective registration; control policy inferred from row availability; missing/unpriceable required control removed from denominator; replay maturity using wall clock; direction sign erased/pooled.

No new promotion authority or score store.

### A1 — T7 per-engine evidence scorecards + T8 CEO view — after H1, may consume E1 accrual state honestly

Observable mission: the existing admin Intelligence OS answers which engines are Validated, Accruing, Ungraded by design, Degraded, or Disproven, with per-engine evidence selected by output class and all claims linked to their legal ruler/basis.

The Validated list is allowed to be empty. Empty is evidence, not a product failure. Ranking is by evidence strength, never headline performance.

### G1 — Metric-validity strict promotion

Only after invalid live emitters/readers are repaired or explicitly exempted under source law: flip the existing metric-validity gate from fleet-wide warning to a real hard integrity gate. No performance threshold becomes a hard release gate merely because this wave exists.

### I1 — T12 narrow Agent OS evidence-tier interface

After T1/T4/L4 contracts are stable: implement the planned derived `required_tier` interface and structured finding. It may never route/prioritize work itself.

### Adjacent layers retained but not allowed to block the core clock/health/promotion program

T10 contradiction classification and T11 deterministic numeric-source verification remain valid Intelligence Reliability work from the original architecture, but neither may be used to delay E1/H1/P1/A1. They must extend the existing contradiction detector and response-eval system respectively, never rebuild them.

## 7. Definition of `PROVEN_LIVE` for Evaluation OS

The **program**, not just a component, may be called `PROVEN_LIVE` only when all of the following are true on current accepted production code:

1. **Truthful clocks:** at least the focal `stock_desk`, `thematic_desk`, and `demand_chain` producers have real prospective start receipts generated by real runs; every required matched-control family has a real control-clock start or an explicit truthful “not started” state. No clock is retrospective decoration.
2. **Correct grading:** real matured claims are graded using their declared unit/market ruler and one shared subject/benchmark/control window; >63 declared horizons are not mislabeled as own-horizon grades under the unchanged ladder.
3. **Basis integrity:** production track record/readiness never pools legacy with explicit evidence or different explicit market/unit bases. A deliberately mutated laundering path fails the acceptance suite.
4. **Promotion legality:** no new authority can originate from legacy-only, mixed-basis, insufficient-date, illegal-control or otherwise ineligible evidence. Promotion readiness and the actual authority owner agree on what the evidence may support.
5. **Real health:** T4 is exercised against the deployed real estate and visible in the existing admin console, including a real negative/blind state; no generated health store exists.
6. **Human answer layer:** T7/T8 are visible in that same admin surface and truthfully separate Validated / Accruing / Ungraded-by-design / Degraded / Disproven, including empty and null states.
7. **Adversarial proof:** exact final-head tests kill clock-basis laundering, retrospective clock creation and illegal promotion mutations; independent adversarial review finds no duplicate authority/control plane.
8. **Operational proof:** at least one subsequent real scheduled run advances claims/grades while preserving the same laws, and operator observability remains correct after that run.
9. **No duplicate system:** zero second engine registry, claims ledger, health monitor/store, promotion authority, work queue or hidden evidence-clock database.
10. **Durable reconciliation:** Agent OS, GitHub evidence and Linear projection all state the same terminal truth; Slack receipts are treated only as transport; Executive OS state is referenced only when its canonical production read is actually available.

Until then, the overall program remains `PARTIAL` even when individual substrate capabilities are `PROVEN_LIVE`.

## 8. Exact continuation

Freeze this architecture first. Then dispatch **E1** and **H1** to separate Fable COO main-loop carriers because their expected changed paths are disjoint. A Slack delivery is not execution: each carrier must return an explicit same-thread Fable ACK before its wave is considered started. If no main-loop Fable session ACKs, record `DELIVERY_ONLY / MANUAL_PICKUP_REQUIRED` and do not fabricate runtime execution.

P1 is held until E1’s qledger-path movement is returned/reconciled. A1 is held until H1 production truth is known. Sol reviews every returned PR/proof against this freeze and remains final acceptance owner.
