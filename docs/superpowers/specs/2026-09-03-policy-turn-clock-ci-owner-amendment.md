# Policy Turn Clock — Executable CI Ownership Amendment

Date: 2026-09-03  
Status: **BINDING PRE-IMPLEMENTATION ARCHITECTURE REPAIR / RECORDS ONLY**  
Parent carrier: Macro PR #6788  
Implementation carrier: Macro issue #6787  
Operation: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`  
Protected procedure at repair: `mastermindx-market-intelligence/Mastermind@c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1 compatible.  
Macro observation at repair: `16aac3be6a7e8790af0aee75ab1d44ac43eecfab`.

## 1. Defect repaired

The frozen implementation plan creates four new test suites:

```text
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

It also modifies `tests/test_policy_watch_ui.py`.

The plan correctly includes `.github/workflows/ci.yml` for pull-request path triggering, but it absolutely forbids `.github/ci/legacy-jobs.yml` and even requires a test asserting that the manifest is absent from the implementation diff.

Current repository truth makes those requirements incompatible. Macro’s semantic CI executes the logical jobs declared in `.github/ci/legacy-jobs.yml`. The existing front-facing/policy job explicitly runs:

```text
python -m pytest \
  tests/test_front_facing_register.py \
  tests/test_policy_watch_register.py \
  tests/test_policy_watch_ui.py \
  tests/test_chat_plain_words.py -q
```

None of the four new W1 suites is currently named by an existing run step. The repository’s contract-delta/unrun-suite guard is designed to reject exactly this class of dark test. Editing only `.github/workflows/ci.yml` can cause CI to start, but it cannot make a logical job execute a suite that no job command owns.

A plan that insists on both “four new suites” and “the job manifest must remain untouched” can therefore produce green-looking implementation with unexecuted tests, or fail contract-delta after the code is written. This amendment removes that contradiction before W1 starts.

## 2. Precedence

This file amends only CI ownership and collision sequencing in:

- `docs/superpowers/specs/2026-09-03-actor-liquidity-monthly-transition-clock-design.md`;
- `docs/superpowers/plans/2026-09-03-actor-liquidity-monthly-transition-clock-implementation.md`;
- `agentos/decisions/DEC-POLICY-PRETURN-CALENDAR-FLOW-COMPOSITION.md`;
- `agentos/handoffs/RATES-INFLATION-COMMAND-2026-09-03-actor-liquidity-monthly-transition-clock.md`;
- Macro issue #6787.

Where an earlier record says `.github/ci/legacy-jobs.yml` is an unconditional no-edit path or must be absent from the W1 implementation diff, this amendment controls.

The path is **conditionally authorized only for the smallest existing-owner composition described below**. It does not become general CI-refactor scope.

## 3. Current owner and collision truth

### 3.1 Former PR #6658 collision

PR #6658 previously owned `.github/ci/legacy-jobs.yml`, which justified the original no-edit boundary. Its current exact five-file delta no longer contains that path. The old collision is released.

### 3.2 Active RIC F3 composition

RIC F3 PR #6721 already contains a published manifest change and its exact post-START worker has now been continued on the original carrier to compose that change onto current Macro main. Until that child returns terminally or explicitly releases the manifest path, W1 must not START on `.github/ci/legacy-jobs.yml`.

This is sequencing, not abandonment:

```text
RIC F3 current-base manifest composition/release
    ↓
W1 fresh exact path census
    ↓
W1 smallest additive existing-job composition
```

If RIC F3 still owns the path at W1 pickup, return:

```text
BLOCKED PATH_COLLISION
owner=Macro PR #6721
path=.github/ci/legacy-jobs.yml
effect=NONE
```

Do not create a second W1 carrier, alternate workflow or test runner to bypass the hold.

## 4. Exact W1 CI path ceiling

The W1 existing-source list is amended to include:

```text
.github/ci/legacy-jobs.yml
```

under all of these conditions:

1. the records architecture is accepted and merged;
2. PR #6721’s manifest ownership is terminally released or a later Sol ruling supplies a collision-free composition boundary;
3. a fresh START-time path census finds no other active owner;
4. the change is additive to one existing logical job whose dependency/install closure already fits the suites, or is minimally widened without creating a new job;
5. current-main manifest additions are preserved byte-for-byte outside the exact W1 hunks;
6. no gate, runner, permission, trusted-executor, secret, branch, concurrency or merge policy is changed.

No other `.github/ci/**` file enters W1.

## 5. Existing-owner composition law

W1 must extend the existing logical job that already runs `tests/test_policy_watch_ui.py`, unless current-main archaeology proves another existing job owns the exact source/test closure more precisely.

The preferred additive command shape is:

```yaml
- name: policy event and monthly transition clock contracts
  run: >-
    python -m pytest
    tests/test_policy_event_clock.py
    tests/test_futures_roll_calendar.py
    tests/test_policy_turn_clock.py
    tests/test_build_policy_turn_clock.py
    tests/test_policy_watch_ui.py
    -q
```

If `tests/test_policy_watch_ui.py` remains in its pre-existing run step, it need not be duplicated in the new command. The implementation must choose one deterministic owner per suite and avoid running the same file in two logical jobs without a documented reason.

The owning job’s declared `paths:` must include every new suite and the source subjects it tests, at minimum:

```text
collectors/policy_event_clock.py
engine/futures_roll_calendar.py
engine/policy_turn_clock.py
engine/event_calendar.py
scripts/build_policy_turn_clock.py
scripts/build_policy_watch.py
templates/partials/_policy_turn_clock.html.j2
templates/policy_watch.html.j2
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
tests/test_policy_watch_ui.py
```

Include `config/dag.yml`, `.github/workflows/whitehouse-sentinel.yml` and `.github/workflows/ci.yml` in the job scope only when the tests executed by that job directly inspect them. Do not use a broad `**` pattern merely to silence scope validation.

## 6. Pull-request trigger law

`.github/workflows/ci.yml` remains in the W1 path ceiling for the complementary half of ownership:

- a test-only edit must trigger the logical owner;
- a source-only edit must also trigger the logical owner;
- workflow/DAG changes must trigger the conformance owner;
- the path trigger and the manifest owner must describe the same dependency closure.

Adding a suite to `legacy-jobs.yml` without the corresponding `ci.yml` trigger is incomplete. Adding only a `ci.yml` trigger without a run owner is also incomplete.

## 7. Plan corrections

### Global constraints

Replace the unconditional no-edit entry:

```text
.github/ci/legacy-jobs.yml
```

with:

```text
.github/ci/legacy-jobs.yml — NO EDIT until RIC F3 #6721 releases the path; after release, only the bounded existing-job composition in the CI ownership amendment is authorized.
```

### Exact implementation surface

Add under existing source files modified:

```text
.github/ci/legacy-jobs.yml  # conditional, existing logical job only
```

### Task 0

The collision census must identify current manifest ownership separately. W1 may ACK while dependency-gated, but it may not post START or create source effect until the path is released and the complete planned-path census is clean.

### Task 7

Delete these requirements:

```text
Assert `.github/ci/legacy-jobs.yml` is absent from the PR diff.
! git diff --name-only origin/main...HEAD | grep -Fx '.github/ci/legacy-jobs.yml'
```

Replace them with failing tests/validation that prove:

1. every new suite is named by exactly one executable manifest run step;
2. each owning job’s declared paths cover its tests and source subjects;
3. `.github/workflows/ci.yml` triggers on both tests and subjects;
4. no new logical job was created when the existing policy/front-facing owner is compatible;
5. the current-main TOP ANATOMY OOT manifest additions remain present;
6. no trusted-executor, permission, runner, concurrency or merge-control field changed.

Required commands:

```bash
python -m scripts.run_ci_pack --validate-only
python -m scripts.audit_unrun_tests
python -m pytest tests/test_dag_conformance.py -q
git diff --check
```

Run the exact selected logical job through the repository’s normal pack runner, not only direct pytest.

## 8. Discriminating regression and mutation proof

The implementation PR must show the guard can kill these defects:

| Mutation | Required failure |
|---|---|
| remove `tests/test_policy_event_clock.py` from every manifest command | unrun-suite/contract-delta failure |
| keep suite command but remove collector path from owner scope | manifest scope/dependency failure |
| keep manifest owner but remove test/source trigger from `ci.yml` | trigger-coverage failure |
| add a duplicate second logical owner | duplicate/plan ownership finding or explicit test failure |
| delete an unrelated current-main TOP ANATOMY OOT manifest line during composition | current-base integration/expected-line regression |
| switch hourly lane to `COLLECT_LANE=nightly` | ledger-lane test failure |

A generic “CI green” screenshot is not sufficient. Return the exact command/output or hosted job proving the new suites actually executed.

## 9. Authority and no-rebuild boundary

This amendment creates no second CI system. Macro’s existing `ci.yml` planner, `legacy-jobs.yml` logical manifest, pack runner, contract-delta and unrun-suite audit remain canonical.

W1 may not:

- add another workflow merely to run its tests;
- add a second pack planner or manifest;
- alter trusted-executor admission;
- change repository permissions or secrets;
- broaden runners or labels;
- weaken unrun-test or scope enforcement;
- add tests to `config/unrun_test_baseline.json` as a substitute for executable ownership;
- touch RIC F3 source paths while composing the shared manifest.

All product authority remains unchanged and false for rank, gate, size and trade.

## 10. Capability effect

Merging this amendment would only make the implementation plan executable under the current CI architecture. It would not:

- execute a test;
- release the active RIC F3 path;
- assign or START W1;
- create source/product behavior;
- prove `policy_turn_clock.v1`;
- merge or deploy any implementation;
- create production or capital effect.

PR #6788 remains `SPEC_ONLY`. Issue #6787 remains `NOT_BUILT / PRE_START` until architecture acceptance, path release, receiver assignment, ACK and separate START.