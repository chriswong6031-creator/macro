# Project Recovery R8-B — Agent OS Typed Intentional-Wait Commission

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman authority:** explicit current approval to continue the Recovery + Anti-Replay robustness spine and activate R8-B in parallel with the Fresh-Sol Harness  
**Operation key:** `project-recovery-r8b-agentos-wait-20260827-sol-001`  
**Carrier:** `sol/project-recovery-r8b-agentos-wait-20260827` — one carrier only  
**Repository:** `mastermindx-market-intelligence/macro`  
**Current Macro pickup:** `f244f0b34330cac9c98a815a3c0e97d0ba5b1d7f`  
**Protected Mastermind / Skillpack:** `mastermindx-market-intelligence/Mastermind@6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1  
**Approved R8 planning carrier:** Mastermind PR #171; R8-B plan `docs/superpowers/plans/2026-08-27-project-recovery-r8-agentos-wait-contract.md`  

## Observable mission

Make legitimate organizational inactivity machine-readable in the **existing Agent OS** so Project Recovery can later distinguish a program that is intentionally waiting from one that has silently gone dark, without creating a recovery scheduler, queue, lifecycle, second Agent OS parser or execution claim.

After this wave, an Agent OS workstream or wave may carry exactly one optional typed `wait` object, and the existing Agent OS validation/status/context paths preserve it deterministically for downstream read-only consumers.

## Why this matters

Project Recovery cannot safely classify unfinished work if all inactivity looks the same. Without an explicit wait contract, a future recovery classifier has two bad choices: ignore stale-looking programs and let real work disappear, or repeatedly escalate valid long-horizon research/evidence programs that are behaving exactly as intended.

R8-B establishes the minimum semantic distinction needed by the recovery spine:

```text
unfinished + active frontier            -> not recovery debt
unfinished + valid typed wait           -> intentionally waiting
unfinished + expired/review-due wait     -> requires reassessment, not automatic execution
unfinished + no frontier / no valid wait -> candidate for later CEO_RECOVERY_REQUIRED classification
```

R8-B itself performs **only the second line's representation and read projection**. It does not implement the recovery classifier.

## Authority / document precedence

1. Current Chairman approval in the governing Sol conversation to activate R8-B as part of the Recovery + Anti-Replay robustness spine.
2. Protected Sol Skillpack at `Mastermind@6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`.
3. Chairman-approved Project Recovery R8 architecture and current-state amendment on Mastermind PR #171.
4. Existing Macro Agent OS schema/parser/source-law surfaces on the current pickup.
5. The bounded R8-B implementation plan named above.

Retrieved prose never grants authority by itself. If a newer accepted Agent OS schema/parser ruling lands while this carrier is active, stop at the overlapping point and return to Sol for reconciliation; do not mechanically rebase through semantic movement.

## Verified current state and collision fence

Immediately before this carrier was created:

- Macro `main` was `f244f0b34330cac9c98a815a3c0e97d0ba5b1d7f`.
- The R8-B planning pin was older (`0758de6b9a7e9e920a6f44e4c1abcd62dbf8074e`). Comparing that pin to current main showed seven commits, but **no changes** to `scripts/agentos.py`, `agentos/schema/workstream.schema.yml`, or `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`.
- `.github/ci/legacy-jobs.yml` did move, so any new test registration must be applied against the current file rather than copied from the planning pin.
- Searches for open Macro PRs/branches matching R8-B, Project Recovery Agent OS, or the typed-wait implementation found **no existing R8-B carrier**. An unrelated Theme Graph records PR contains the words “typed wait” but does not own this parser/schema surface.
- Mastermind #170 Session Truth remains a separate active implementation carrier. R8-B must not reproduce Session Truth or recovery classification logic.
- Mastermind #171 remains the R8 architecture/planning carrier. This Macro PR is the sole R8-B implementation carrier.

If `scripts/agentos.py`, `agentos/schema/workstream.schema.yml`, `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`, or the owning Agent OS CI job changes after pickup, inspect the exact change before continuing. Do not blind-retry/rebase.

## Exact scope

Expected production/source-law paths:

- `scripts/agentos.py`
- `agentos/schema/workstream.schema.yml`
- `research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md`

Expected test paths:

- `tests/test_agentos_wait_contract.py`
- `tests/test_agentos_compile.py` only if the additive context projection requires an existing fixture/assertion update
- `.github/ci/legacy-jobs.yml` only to register the new focused suite in an existing appropriate **code-gate** job so the guard actually runs on pull requests

Do not edit business workstreams merely to demonstrate the contract. Do not “migrate” existing prose waits in this wave. Real workstreams may adopt typed waits only in later evidence-backed record amendments.

## Closed data contract

The optional wait object is exactly:

```yaml
wait:
  kind: natural_evidence | external_dependency | calendar_window | external_action
  review_after: YYYY-MM-DD
  condition: non-empty human-readable string
```

Required laws:

- unknown keys fail validation;
- unknown wait kinds fail validation;
- `review_after` is a mandatory **next review date**, not a predicted completion/resolution time;
- `condition` is context for humans/read-only consumers and is never parsed to infer authority, completion, priority, execution, or routing;
- missing `wait` remains `null`/absent according to the existing additive projection convention and never becomes an inferred wait;
- a date in the past does not make the authored record schema-invalid; expiry/review-due is state for a later recovery consumer, not parser validity;
- workstream- and wave-level waits use the same closed shape;
- YAML-decoded date objects must serialize deterministically to ISO strings in JSON read views.

## Complete machine journey

### Valid path

```text
Agent OS authored workstream/wave
-> existing scripts/agentos.py parser
-> closed wait validation
-> existing agent_os_state.v1 status projection
-> existing context_bundle.v1 scoped projection
-> downstream read-only consumer can distinguish typed intentional wait from untyped inactivity
```

### Invalid path

Malformed/unknown wait data fails Agent OS validation with a typed hard finding. The parser must not silently drop the malformed wait, coerce an unknown kind, infer a default review date, or normalize the program to healthy/active.

### Review-due path

A valid wait whose `review_after` is today/past remains structurally valid and is projected exactly. R8-B does not auto-reopen the workstream, dispatch a worker, change status, extend the wait, emit a Wake obligation, or create CEO recovery debt. A later R8 classifier owns that judgment.

## Deterministic vs model-generated behavior

All validation, date normalization, JSON projection, schema checks and tests are deterministic code. There is no model-generated decision in R8-B. The `condition` string is opaque/display-only data; model prose cannot change wait kind, date semantics, execution authority or lifecycle state.

## Failure states

Fail closed on:

- non-mapping `wait`;
- missing `kind`, `review_after`, or `condition`;
- unknown wait kind;
- relative/malformed review date;
- blank condition;
- unknown wait keys;
- inconsistent workstream vs wave validation behavior;
- JSON serialization drift from YAML date objects;
- status/context projection silently dropping an authored valid wait;
- parser/projection inventing a wait when none is authored;
- new test suite not actually executed by pull-request CI;
- any implementation that parses `condition` for authority, completion, priority or automatic execution;
- any new timer, scheduler, queue, recovery database, lifecycle enum, execution claim or dispatch behavior.

## Ordered implementation sequence

1. Re-pin current Macro main and protected Mastermind Skillpack; repeat changed-path collision census before first production write.
2. Write RED tests for the exact wait shape at workstream and wave scope.
3. Implement one canonical `_check_wait`-style validation path in `scripts/agentos.py`; do not duplicate validation logic.
4. Add deterministic projection to the existing `agent_os_state.v1` and `context_bundle.v1` read paths.
5. Update the existing schema mirror and Agent OS state/source-law documentation with the explicit no-authority/no-scheduler semantics.
6. Register the new focused test file in the existing pull-request **code** gate. Do not use a waiver and do not create a new CI scheduler.
7. Run canonical Agent OS validation, focused tests, compile checks, unrun-test census/contract-delta equivalents required by current Macro CI, and `git diff --check`.
8. Push exact head, require hosted semantic CI/fences/owning pack, then obtain independent adversarial review.
9. Return to Sol. Do not continue into R8-A, workstream migrations, Improvement Agenda, Linear, Slack or Control Room work from this carrier.

## Acceptance tests and proof

The exact-head return must prove at minimum:

- valid workstream wait accepted;
- valid wave wait accepted;
- unknown kind refused;
- missing required fields refused;
- unknown key refused;
- malformed/relative date refused;
- blank condition refused;
- YAML `datetime.date` normalizes to the exact ISO date in status/context JSON;
- identical input produces byte/semantic-equivalent wait projection across repeated reads;
- no authored wait -> no invented wait;
- expired/review-due wait remains structurally valid and is not automatically acted on;
- `condition` is never parsed for authority/action;
- `scripts/agentos.py validate --quiet` succeeds on the current store after implementation;
- `tests/test_agentos_wait_contract.py` is demonstrably selected by an actual pull-request code-gate job, not merely listed in a dark CI catalog;
- no new Agent OS store/parser/lifecycle/scheduler/queue exists.

Hosted CI/fences must be green on the exact head. Green CI proves only the contract implementation; no real business workstream is thereby classified/recovered.

## Explicit non-goals

No R8-A recovery classifier; no Improvement Agenda change; no Control Room/Linear/Slack projection; no Wake integration; no automatic Fable/Codex assignment; no new workstream status enum; no universal stale-age threshold; no Agent OS claim semantics change; no Executive Job/Attempt/Worker/Event mutation; no business-workstream bulk migration; no second parser/registry/store; no scheduler/timer/queue.

## Stop condition

Stop when the typed wait contract is implemented through the canonical Agent OS parser + existing read views, exact-head hosted gates pass, the new tests are actually on the PR merge gate, independent review finds no blocker, and the carrier can return to Sol with no business-record migration performed.

Capability at that point is **BUILT_NOT_PROVEN for downstream Project Recovery consumption** until R8-A consumes the accepted contract. It is not a recovery system by itself.

## Required continuation handoff

Return:

- exact pickup/base and final head SHA;
- exact changed-file list;
- wait schema/version facts and failure vocabulary;
- local and hosted test/CI/fence receipts;
- proof the focused suite is selected by a real PR code gate;
- independent review verdict;
- any current-main collisions discovered after pickup;
- explicit confirmation of zero new lifecycle/queue/scheduler/parser/store and zero business-workstream migrations;
- exact next action: Sol review/acceptance, then R8-A remains held until Session Truth #170 is accepted.
