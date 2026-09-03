# Policy Turn Clock — Executable CI and Runtime Ownership Amendment

Date: 2026-09-03  
Status: **CONSOLIDATED BINDING REPAIR / RECORDS ONLY / SPEC_ONLY**  
Parent carrier: Macro PR #6788  
Implementation carrier: Macro issue #6787  
Operation: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`  
Protected procedure at repair: `mastermindx-market-intelligence/Mastermind@c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1 compatible.  
Macro observation at repair: `main@16aac3be6a7e8790af0aee75ab1d44ac43eecfab`.

This document replaces the prior contents of this path. It binds both halves of executable ownership: the real hourly/nightly runtime paths and the canonical logical CI job that must execute every new suite.

## 1. Defects repaired

The earlier plan had three linked contradictions:

1. It created four new test suites while unconditionally forbidding `.github/ci/legacy-jobs.yml`, even though that manifest names the executable logical-job commands.
2. It declared a nightly prospective ledger but concretely invoked the clock only in the hourly sentinel with `COLLECT_LANE=hourly`; `config/dag.yml` was treated as though declaration implied execution.
3. It allowed independently scheduled hourly/nightly publication without a single-writer/no-regress rule and required wall-clock attempt timestamps that would make every healthy quiet hour produce changed tracked bytes.

The repaired architecture resolves them without another workflow, job, scheduler, queue, lock service, CI planner or publisher.

## 2. Precedence

This amendment controls runtime and CI behavior if older text conflicts. The consolidated W1 design and implementation plan now carry the same rules and should be read first. This file remains the narrow provenance record for why those rules are mandatory.

## 3. Current shared-path collision truth

A previous draft named PR #6721 as the remaining `.github/ci/legacy-jobs.yml` owner after PR #6658 released the path. Independent review performed a broader current open-PR census and found additional open candidates referencing the path, including:

```text
#6791
#6721
#6706
#6651
#6625
#6514
#6389
#6296
```

This list is an observation, not a durable lock registry. Open PRs, heads and path deltas move. W1 must perform a fresh complete census immediately before START and again before every shared-manifest edit/reconciliation.

A clean START requires:

- architecture accepted and merged;
- no prior W1 START/effect uncertainty;
- every current active owner of `.github/ci/legacy-jobs.yml` terminally released, merged or reconciled by an explicit Sol composition ruling;
- one clean current-main worktree/branch;
- exact planned-path census posted before edit.

If any owner remains:

```text
BLOCKED PATH_COLLISION
operation=policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001
owner=<current carrier>
path=.github/ci/legacy-jobs.yml
effect=NONE
```

Do not bypass the hold with another workflow, job, branch, carrier, test runner or unrun-test exemption.

## 4. Real runtime ownership

### 4.1 Hourly single writer

Existing owner:

```text
.github/workflows/whitehouse-sentinel.yml
```

Hourly is the sole writer/publisher of:

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
site/policy_turn_clock.json
```

Required order:

```text
python -m collectors.policy_event_clock
COLLECT_LANE=hourly python -m scripts.build_policy_turn_clock --mode publish-current
focused policy-clock validation
stage only owned official/status/current-artifact paths
existing rebase/push procedure
```

The collector and builder must produce byte-stable tracked outputs on a healthy semantic no-op. Ephemeral attempt telemetry belongs in logs, not in tracked status fields that force hourly churn. Genuine source failure, source recovery, parser-shape change, correction, cancellation, watermark advance or freshness transition remains a semantic change and must publish.

Before staging/push, `publish-current` compares incoming method/input/source-watermark/evidence-cutoff identity with the current published artifact after a fresh source read:

- older evidence: refuse overwrite and report `NO_REGRESS_REFUSAL`;
- equal semantic identity: no-op;
- newer valid evidence: publish;
- meaningful source failure/staleness: publish degraded status while preserving last-good evidence.

The current Policy Watch turn-clock component reads the same-origin JSON at runtime. A static shell/fallback may be built by other lanes, but no other lane embeds or publishes an independent current clock payload.

### 4.2 Nightly ledger-only advancer

Existing real owner:

```text
scripts/ci/daily_engine_regional_desk_builders.sh
```

The parent daily workflow already supplies `COLLECT_LANE=nightly`. Immediately before the existing `scripts.build_policy_watch` invocation, add one buffered builder call:

```text
scripts.build_policy_turn_clock --mode ledger-only
```

Ledger-only mode:

- performs no official-source network call;
- does not write or stage `site/policy_turn_clock.json`;
- does not publish Policy Watch current data;
- reads current official evidence and fresh after-close canonical option/Treasury/flow/futures/market artifacts;
- appends at most one keep-FIRST prospective receipt through `engine.ledger_lane.nightly_advance_enabled()`;
- reruns idempotently.

If the ledger-only call fails, the existing buffered regional-desk runner records the bounded failure; it does not create another scheduler or silently run publish mode.

### 4.3 DAG is a mirror

`config/dag.yml` must declare the real hourly and nightly invocations and modes. It is not an executor, scheduler or evidence that a command runs. `scripts/check_dag_conformance.py` and related tests compare declarations with the actual workflows/scripts.

## 5. Canonical logical CI ownership

The new suites are:

```text
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

`tests/test_policy_watch_ui.py` is an existing suite modified by W1.

After the shared path is collision-free, extend one existing compatible policy/front-facing logical job in `.github/ci/legacy-jobs.yml`. Do not create a new logical job when the existing owner can carry the dependency/install/runtime closure.

Preferred executable command shape:

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

When `tests/test_policy_watch_ui.py` remains in its current existing command, do not duplicate it without a documented runtime reason. Every new suite must have exactly one intended executable owner.

The owning job’s path closure must include the precise tests and subjects it validates, including at minimum:

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

Include these only in the exact job/conformance closure that inspects them:

```text
config/dag.yml
.github/workflows/whitehouse-sentinel.yml
scripts/ci/daily_engine_regional_desk_builders.sh
.github/workflows/ci.yml
.github/ci/legacy-jobs.yml
```

Do not use an indiscriminate broad glob to hide a missing dependency.

## 6. Pull-request trigger ownership

`.github/workflows/ci.yml` is the complementary trigger owner:

- test-only edit triggers the logical owner;
- source-only edit triggers the logical owner;
- template/builder edit triggers the UI/contract owner;
- workflow/nightly-script/DAG edit triggers the conformance owner;
- manifest and trigger path closures agree.

Adding a suite to the manifest without a source/test trigger is incomplete. Adding only a trigger without an executable manifest command leaves a dark suite.

## 7. Required validation

Before any success claim:

```bash
python -m pytest tests/test_policy_event_clock.py \
  tests/test_futures_roll_calendar.py \
  tests/test_policy_turn_clock.py \
  tests/test_build_policy_turn_clock.py \
  tests/test_policy_watch_ui.py \
  tests/test_dag_conformance.py -q
python -m scripts.run_ci_pack --validate-only
python -m scripts.audit_unrun_tests
git diff --check
```

Run the exact selected logical job through the canonical pack runner, not only direct pytest.

## 8. Required mutation proof

| Mutation | Required failure |
|---|---|
| Remove one new suite from all manifest commands | unrun-suite/contract-delta failure |
| Keep suite command but remove one source subject from owner paths | manifest scope/dependency failure |
| Keep manifest owner but remove matching `ci.yml` trigger | trigger-coverage failure |
| Add a duplicate logical owner for the suite | duplicate/plan ownership finding |
| Add suite to unrun baseline | explicit policy-clock CI test failure |
| Delete an unrelated current-main manifest marker | current-base integration regression |
| Remove nightly ledger-only invocation | DAG/runtime conformance failure |
| Change nightly mode to publish-current | single-writer/lane test failure |
| Change hourly `COLLECT_LANE` to nightly | ledger-lane test failure |
| Advance only wall-clock attempt time on a healthy quiet hour | semantic no-op/byte-stability failure |
| Attempt older-cutoff current publication | no-regress refusal test |

Restore each mutation before final verification.

## 9. Forbidden changes

W1 may not:

- add another workflow or scheduler;
- add a CI logical job when an existing compatible owner suffices;
- add a second pack planner/manifest;
- change trusted-executor admission;
- change permissions, secrets, runners, labels, concurrency or merge policy;
- add tests to `config/unrun_test_baseline.json`;
- run official collection nightly;
- publish current JSON from nightly;
- add a cross-lane lock service or queue;
- touch RIC F3 source paths while composing the shared manifest;
- infer product or production completion from green CI.

## 10. Effect

Merging this records amendment would make only the architecture executable and reviewable. It would not:

- release any current shared-path owner;
- assign or START W1;
- execute a test or workflow;
- collect an official source;
- create `policy_turn_clock.v1`;
- change Policy Watch;
- append a prospective receipt;
- merge or deploy implementation;
- create product, production or capital effect.

PR #6788 remains `SPEC_ONLY`; issue #6787 remains `NOT_BUILT / PRE_START` until every entrance gate is separately proven.