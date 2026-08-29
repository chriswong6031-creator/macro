---
workstream: WS:EVAL-OS-MEASUREMENT-LAW
session: pending-placement
model: Opus preferred
ended_because: not_started
mission: >
  Close the remaining E1 production-truth gap without redoing the proven stock leg: classify the
  real US thematic zero-output path, obtain the first lawful thematic_desk prospective qledger claim
  and general clock only when the desk genuinely makes one (or repair only a demonstrated blocker),
  and produce explicit real grader/cohort proof that pre-clock rows cannot enter the authority cohort.
state_before: >
  Old E1 child terminally stopped for stale worker continuity. #6598/#6607 merged. stock_desk general
  clock PROVEN_LIVE; stock matched-control NOT STARTED; thematic_desk general clock absent.
changed: []
verified:
  - "Protected Skillpack at recovery freeze: Mastermind@c924b37188df2437057b5fd7bfc00ce0db91a1f1, v1.0.1/bootstrap 1."
  - "Macro recovery base: b2c82f52b73871ce73955ff58399d4b53a0d621e."
  - "stock_desk clock starts 2026-08-29T11:08:11.609328+00:00, 20 trading days."
  - "thematic_desk evidence-clock file is absent on recovery base."
  - "qledger run_status generated 2026-08-29T14:56:46.111593+00:00 with 264 grades."
  - "Canonical nightly thematic path is already wired through daily engine -> cl_baskets -> build_baskets -> build_allocation -> _run_thematic_desk -> thematic_desk.run."
unverified:
  - "Exact reason the real US thematic path produced no registrable thesis/claim."
  - "First lawful thematic_desk clock receipt."
  - "Explicit real post-clock grader/cohort receipt proving pre-clock exclusion."
unresolved:
  - "Classify zero-US output as A transient/no-call, B scorability/proxy refusal, C model/provider/parse/fail-soft suppression, or D genuine policy/product defect."
next_actions:
  - "Await lawful concrete Opus-capable Claude placement, then DIRECT_TARGETED handoff on one new Slack parent."
  - "Worker must ACK, arm exact-thread watcher, emit WATCH_ARMED, then START only after fresh pins/collision checks."
do_not_redo:
  - "Do not redo #6598/#6607 or rewrite stock_desk's clock."
  - "Do not synthesize a thematic thesis merely to start a clock."
  - "Do not invent a second producer/scheduler, clock store, qledger, grader, registry or authority plane."
danger_areas:
  - "LLM fail-soft behavior can look identical to an honest zero-thesis decision unless logs/output are traced precisely."
  - "A missing runner-local control-clock file is not proof a control clock never existed."
---

# Operation

`eval-os-e1-thematic-cohort-recovery-20260829-sol-001`

This is a fresh child under the existing Eval OS parent. It is not a continuation of the terminal
worker runtime from `eval-os-e1-clock-accrual-20260827`.

## Placement / receiver state

```text
PREFERRED_AVENUE: Opus
WHY: difficult but bounded production/log/model-fail-soft/scorability diagnosis plus qledger proof under frozen measurement law
WHY NOT FABLE: architecture and authority boundaries are already frozen; no sustained cross-repo principal ambiguity remains
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

This document is durable scope, **not an unbound worker commission**. Grok Secretary may coordinate
availability and nominate an eligible Opus-capable Claude session. Sol makes the direct-targeted
assignment only after a concrete receiver is resolved.

## Observable mission

A real production path either (a) truthfully demonstrates that no US thematic call was made and
identifies the exact lawful no-call/scorability reason, or (b) after the smallest proven blocking
defect is repaired, registers a genuinely prospective US `thematic_desk` claim and mints the first
write-once general evidence clock. In either case, the worker also proves through a real grader/cohort
execution that rows before each family's evidence-clock start cannot enter the new authority cohort.

## Why it matters

E1 is the remaining measurement-law critical path. `demand_chain` and now `stock_desk` have real
forward starts. A fabricated thematic clock would be worse than no clock; a permanently silent real
producer would make Eval OS incomplete. The product needs honest forward evidence, not decorative
coverage.

## Authority / precedence

1. Current live Chairman continuation intent for Intelligence Evaluation OS.
2. CURRENT protected Mastermind Skillpack at pickup; do not freeze the recovery SHA as future authority.
3. `research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md`.
4. `agentos/decisions/DEC-EVAL-OS-DARK-WORKER-RECOVERY-2026-08-29.md`.
5. `agentos/workstreams/WS-EVAL-OS-MEASUREMENT-LAW.md`.
6. Existing qledger evidence-clock, horizon/ruler and P0d matched-control contracts.

If a newer accepted source changes this boundary or a colliding implementation PR appears, stop and
return `DECISION_REQUEST`; never force-reconcile over it.

## Verified current state

Recovery-base facts:

- #6598 merged: stock/thematic claims anchor at registration while preserving `state_asof_source`;
  the forward-only gate itself was not weakened.
- #6607 merged: the stock-brief production commit now persists `data/qledger`.
- Current `stock_desk.json` clock:
  - `first_prospective_registration_utc = 2026-08-29T11:08:11.609328+00:00`
  - horizon = 20 `trading_days`.
- Stock matched-control is not started because the accepted stock claims had no valid governed
  control. That is a truthful coverage state, not a defect to hide.
- Current `thematic_desk.json` does not exist.
- The first clean post-repair production observation executed the existing thematic chain and
  produced fresh non-US thematic output but no registrable US thematic qledger claim.
- The generic scheduler/band hypothesis is therefore rejected. The remaining seam is within the
  already-wired US thematic decision/registration path.
- Current qledger grading is live after the stock clock, but run-status counts alone do not prove
  the required pre-clock cohort exclusion.

## Exact scope

Primary read/diagnosis surfaces:

- `.github/workflows/daily.yml`
- `scripts/ci/daily_engine_regional_desk_builders.sh`
- `scripts/build_baskets.py`
- `scripts/build_allocation.py`
- `engine/thematic_desk.py`
- `engine/qledger_desk_adapter.py`
- `engine/qledger_evidence_clock.py`
- `engine/qledger.py`
- `scripts/grade_qledger.py`
- relevant existing tests and production logs/receipts.

Mutation is **not pre-authorized merely because these paths are listed**. Diagnose first. If and only
if B/C/D below is proven to be a real blocker within existing E1 authority, implement the smallest
repair on one bounded carrier and add a discriminating regression.

## Explicit non-goals

- no stock-desk anchor/persistence redo;
- no stock clock rewrite/re-mint;
- no synthetic/historical/retrospective thematic rows;
- no forced thematic thesis or model prompt designed to guarantee a call;
- no second thematic producer or scheduler;
- no qledger redesign, grade-ladder extension, new clock DB/store or committed control-clock copy;
- no new promotion authority or T7/T8/A1 work;
- no fleet-wide T9 adoption work;
- no change to `demand_chain` clock basis.

## Complete machine journey

```text
real authoritative nightly
-> cl_baskets
-> build_baskets
-> build_allocation
-> _run_thematic_desk(us,...)
-> gather current US state
-> model/decision path truthfully returns zero or N theses
-> append only genuinely new thesis rows
-> qledger adapter translates only written, scorable US rows
-> unchanged forward gate
-> accepted claim
-> write-once thematic evidence clock
-> canonical persisted qledger state
-> real grader/cohort selects only legally post-clock evidence
```

A zero-thesis run is valid when it is an honest no-view. It is not permission to fabricate evidence.

## Required A/B/C/D classification

Before modifying anything, classify the observed zero-US path using exact production evidence:

- **A — transient / honest no-call:** the current US state/model adjudication lawfully returned zero
  theses. Preserve it. State what future real condition/run can naturally create the first claim.
- **B — scorability / proxy refusal:** a thesis existed but lacked a lawful scalar proxy/falsifier or
  failed the existing US qledger eligibility contract. Name the exact row/gate and whether the
  refusal is intended policy or a real mapping defect.
- **C — model/provider/parse/fail-soft suppression:** the desk intended to run but provider/key/model
  response, parsing, panel/adjudication or fail-soft behavior prevented a real decision from reaching
  the ledger. Name the exact failure state and whether it is transient infrastructure or code defect.
- **D — genuine product/policy defect:** the current architecture makes lawful US prospective accrual
  impossible even though the desk is expected to make calls. Prove the contradiction and propose the
  smallest repair; do not redesign the desk.

Unknown/unobservable is not A. Return a typed blocker when the evidence cannot discriminate.

## Time / null / correction law

- evidence-clock timestamp = first accepted prospective **registration instant**, never thesis/state
  date;
- `state_asof_source` remains provenance only;
- claim fill must still be strictly after registration under the canonical market calendar;
- `thematic_desk` is benchmark-only under P0d; do not invent a matched control requirement;
- stock matched-control stays NOT STARTED until a real valid controlled stock claim exists;
- legacy and explicit bases never pool;
- >63 declared horizons do not become own-horizon grades under the unchanged 5/21/63 ladder;
- no backfill/correction may rewrite an existing clock.

## Method law

The production-path classification is deterministic evidence archaeology. The thematic desk's thesis
content may be model-generated, but the model has zero authority to weaken registration, clock,
cohort or promotion law. Grader/cohort acceptance is deterministic.

## Failure states

- honest no-thesis;
- proxy/scorability refusal;
- missing model credential/provider outage;
- model response/JSON parse failure;
- partial panel/adjudication failure;
- state/allocation artifact absent or stale;
- qledger translation/refusal;
- persistence failure;
- current-main/source collision;
- real grader unavailable;
- clock already exists unexpectedly;
- watcher/session loss.

Each must be reported distinctly. Do not collapse them into `no output`.

## Ordered execution

1. `PICKUP_ACK` on the exact direct-targeted Slack parent with actual receiver identity.
2. Re-pin current protected Skillpack/current Macro main and reread this packet + the full Slack thread.
3. **MUST arm an actual watcher on that exact Slack thread and emit `WATCH_ARMED` before START.**
   If the host cannot arm one after the required tool-first checks, return `WATCH_UNAVAILABLE`; do
   not START and disappear.
4. Fresh open-PR/path collision census.
5. Emit separate `START` only when gates are clear.
6. Reconstruct the newest real US thematic production path and classify A/B/C/D with exact receipts.
7. If A: make no code change; continue observing only through a lawful already-scheduled real run.
8. If B/C/D and a bounded defect is proven: RED-first discriminating test -> smallest GREEN repair ->
   exact-head hosted CI; no adjacent cleanup.
9. Obtain the first real thematic accepted claim + clock only through a real production run that
   naturally emits a lawful US thesis.
10. Execute/observe the real grader/cohort and return explicit evidence that pre-clock rows are
    excluded; counts alone are insufficient.
11. Return HOLD/RESULT to Sol on the same thread and re-arm the watcher after every nonterminal return.

## Acceptance / real proof

E1 recovery is complete only when all are true:

- `thematic_desk` has a real durable prospective general-clock receipt linked to the exact accepted
  real claim that started it **or**, if the desk lawfully remains no-call at the current run, the
  child remains nonterminal rather than fabricating completion;
- the observed zero-output cause has been classified truthfully;
- stock general clock remains unchanged/proven;
- stock matched-control is truthfully started or not-started from real governed evidence;
- explicit real grader/cohort receipt proves rows before the relevant clock start are excluded;
- no duplicate registry/ledger/clock/promotion/scheduler plane was created;
- any repair has exact-head hosted CI and independent review before Sol acceptance.

## Stop condition / continuation

Stop at the E1 measurement/accrual boundary. Do not absorb P1, A1, T9 or later Eval OS waves.
Return: exact current head, changed files (if any), CI, production run/job IDs, exact thesis/claim IDs,
clock timestamps, A/B/C/D classification, cohort/grader proof, unresolved blockers and watcher state.
Only an explicit Sol STOP closes this child.