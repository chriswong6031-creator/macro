---
key: RUNNER-FLEET-W3-DEFAULT-RENDER-CUTOVER-HANDOFF-2026-08-22
program: project-active-build-control
workstream: RUNNER-FLEET-RESILIENCE
owner: ceo-sol
status: authorized_for_operator
class: operator_handoff
reversible: true
---

# Runner Fleet W3 — default routine render cutover

**Date:** 2026-08-22  
**Repository:** `mastermindx-market-intelligence/macro`  
**Authority:** Chairman incident commission → `DEC:RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS` → M0 #6094 → Sol W3 acceptance review on #6094  
**Operator mission:** one route-only vertical slice

## Observable mission

Move the **routine `render.yml` default route** off the M2 physical failure domain and onto the already-proven PC `render-linux` fleet, without changing render semantics.

The user-visible/machine capability unlocked is simple: ordinary source merges that trigger `render.yml` no longer occupy the M2 `render-heavy` listener by default, so M2 nightly/production work can coexist with site repainting instead of sharing the same physical failure domain.

This wave is not complete merely when YAML changes. It is complete only after a **natural push-triggered render** (no dispatch runner input) is observed executing successfully on an expected `pc-render-*` listener and publishing through the existing production path.

## Why this matters

The 2026-08-20 incident showed that logical labels on one M2 do not create physical isolation. W1 has now removed merge arbitration from the M2. W3 diagnostics have independently proven the PC can execute both real render pipelines end to end. The remaining routine contention source is `render.yml` defaulting to `render-heavy` on the M2 for both manual dispatch and push-triggered ordinary renders.

## Authority / precedence

1. `agentos/decisions/DEC-RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS.md`
2. `research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md`
3. `research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md`
4. Sol W3 acceptance review on PR #6094, review id `5000381758`
5. `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
6. this handoff

If a lower item conflicts with a higher item, stop and return the conflict to Sol.

## Verified current state

### W1 is complete

W1-B merged in PR #6222 as `578b66eb2c469859ab2a6a05cf63d5f235bd01fd` and has production proof. `merge-on-green.yml:sweep` now runs on `ubuntu-latest`; a real armed PR (#6226) was merged by the hosted sweeper while M2 `mac-builder-light` was actively rendering. Hosted pickup was 2 seconds; decisive-green→merge was 28 seconds. `merge-control` remains live on `mac-builder-4` as rollback-only capacity through W5.

Do not reopen W1 in this mission.

### W3 diagnostic admission is accepted

The architecture freeze required all of the following before changing the default route. They are now proven:

1. **At least two live `render-linux` listeners:** four distinct PC listeners were observed live:
   - `pc-render-1` — root `/home/longr/actions-runner`, GitHub runner id 15 when executing accepted jobs;
   - `pc-render-2` — root `/home/longr/actions-runner-2`, repository runner id 32;
   - `pc-render-3` — root `/home/longr/actions-runner-3`, repository runner id 33;
   - `pc-render-4` — root `/home/longr/actions-runner-4`, repository runner id 34.
2. **Real engine-render:** run `32563891953`, job `97010206947`, `scope=all`, `runner=render-linux`, success on `pc-render-1`. Checkout, bootstrap, caches, recompute, guards, R2 publication, site commit and push all passed.
3. **Real full render:** run `32569518013`, job `97024264867`, `scope=all`, `runner=render-linux`, success on `pc-render-1`. Persisted checkout, pull, bootstrap, caches, full render, guards, R2 publication, site commit and push all passed.
4. **Physical-domain separation:** the accepted PC engine-render overlapped a real M2 `render-heavy` job naturally; no load was manufactured.
5. **Resource envelope:** RAM, swap and disk remained safe during both accepted PC runs.

The earlier `pc-render-4` stale `.git/shallow.lock` failure is historical evidence and a W5 checkout-hygiene finding. It is not the current W3 acceptance state because a later full production render completed successfully through the same workflow contract.

### W2 is independent and still open

M1 listeners, no-op canary and crash recovery are proven, but the 12-hour soak terminal receipt is still outstanding and the M1 disk guard reports `full_work_allowed=false` because free space is below the 200 GiB full-work floor. W4 production admission is not authorized. W2 does **not** block this W3 route-only cutover.

## Current production contract to change

On current `main`, `.github/workflows/render.yml` has two separate defaults that must move together:

```yaml
on:
  workflow_dispatch:
    inputs:
      runner:
        default: render-heavy
        options: [render-heavy, render-linux, macstudio]
...
jobs:
  render:
    runs-on:
      - self-hosted
      - ${{ github.event.inputs.runner || 'render-heavy' }}
```

The first controls an operator dispatch that omits an explicit runner. The second is load-bearing for `push` events because there is no workflow-dispatch input on a push. Changing only one would leave half of routine rendering on the M2 and would not satisfy the physical-failure-domain outcome.

The canonical route pin currently lives in `tests/test_render_canada_scope.py`:

- `test_automatic_render_uses_reserved_heavy_runner`
- `test_shared_mac_and_render_linux_remain_explicit_fallbacks`

Those assertions must be updated rather than bypassed or deleted.

## Exact scope

Expected changed files are **three** unless current-main drift proves a directly coupled fourth file is required:

1. `.github/workflows/render.yml`
2. `tests/test_render_canada_scope.py`
3. `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`

### Required `render.yml` semantic delta

Change exactly these default routing semantics:

1. `workflow_dispatch.inputs.runner.default`
   - from `render-heavy`
   - to `render-linux`

2. `jobs.render.runs-on` event fallback
   - from `${{ github.event.inputs.runner || 'render-heavy' }}`
   - to `${{ github.event.inputs.runner || 'render-linux' }}`

Keep the operator options available:

```yaml
options: [render-heavy, render-linux, macstudio]
```

Their order may remain unchanged. `render-heavy` is now the explicit M2 rollback/reserved fallback; `macstudio` remains an explicit shared-Mac fallback. Do not remove either in W3.

Update only the nearby comments/description necessary to state the new truth. Remove stale prose that calls `render-linux` merely a fallback or claims automatic render is reserved to the M2.

### Required test delta

Update the existing route tests in `tests/test_render_canada_scope.py` so they prove:

- workflow-dispatch default is `render-linux`;
- the push/no-input fallback is `render-linux`;
- `self-hosted` remains part of the route;
- options still contain `render-heavy`, `render-linux`, `macstudio`;
- prose no longer claims `render-linux` is only a fallback;
- `render-heavy` and `macstudio` remain explicit rollback/fallback choices.

Do not create a second route-test file merely to avoid editing the existing owner.

### Required workstream delta

Update `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md` truthfully:

- W1 → `done`, with #6222 and production proof named;
- W2 → `in_progress` / diagnostic proof healthy but 12-hour soak terminal receipt still owed; W4 still blocked;
- W3 → `in_progress` while the route PR is unmerged, then `done` only after post-merge automatic push proof;
- replace the stale top-level `next_action` that still says to land W1-A;
- preserve W4/W5/W6 sequencing and all no-rebuild landmines.

Do not use the workstream edit to claim W5 live-registry reconciliation is done.

## Explicit non-goals

Do **not**:

- edit `engine-render.yml` — its `render-linux` posture is already proven;
- change render scope selection, builders, guard semantics, publication, R2, commit/push logic or retry behavior;
- change `permissions`, workflow concurrency or `timeout-minutes`;
- change persisted-checkout/cache/bootstrap logic;
- add, remove, restart or relabel any PC runner;
- change WSL CPU/RAM/swap settings;
- edit M1 services or labels;
- add generic `macstudio` to M1;
- change nightly `daily.yml` routes;
- change merge-control or `scripts/merge_on_green.py`;
- delete `render-heavy` or `macstudio` fallback options;
- retire M2 runner labels/services; W5 owns retirement;
- buy hardware;
- create another fleet registry, scheduler, queue or control plane.

## Static runner-policy drift — binding handling

Current `.github/runner-policy.yml` is known stale about PC liveness (`pc-render.slots`, `Linux/X64/render-linux status`, carrier list). W3 acceptance is based on timestamped host + GitHub job receipts, which are stronger for liveness than the operator-maintained static registry.

**Do not widen this PR into W5 by rewriting those liveness fields.** Preserve the contradiction explicitly in the workstream/handoff as W5 debt. The existing label declaration is sufficient for route legality; W5 will reconcile live fleet-health projection and obsolete M2 roles as one coherent later wave.

If a current runner-policy test unexpectedly makes the route change impossible without editing liveness census fields, stop and return the exact failing contract to Sol rather than silently broadening scope.

## Deterministic vs observed method

Deterministic:

- parsed workflow route/default values;
- operator fallback option set;
- existing render semantics, permissions, concurrency and timeout;
- test assertions and workstream state transitions;
- rollback shape.

Observed:

- actual runner assignment for post-merge render;
- queue/pickup timing;
- checkout/bootstrap/cache outcome;
- render/guard/publication/commit success;
- resource pressure or recurrence of stale workspace metadata.

No model judgment substitutes for Actions/job receipts.

## Ordered implementation sequence

1. Fetch current `main`; record exact base SHA and confirm no open PR owns the same `render.yml` default route.
2. Re-read #6094 Sol W3 acceptance review and #6222 W1 production proof.
3. Parse current `render.yml`; capture before-values for both defaults and the option set.
4. Edit only the two default selectors plus adjacent truth comments/description.
5. Update the existing tests in `tests/test_render_canada_scope.py` to pin both default selectors and both rollback/fallback choices.
6. Update `WS-RUNNER-FLEET-RESILIENCE.md` with W1/W2/W3 current truth without claiming production proof early.
7. Run focused local tests and workflow parser/runner-policy checks.
8. Open one PR. Do not arm or merge until exact-head required CI/fences conclude clean under the repository’s current authority rules.
9. Adversarially review the parsed workflow delta. The only intended behavior change is the two default selectors; all render semantics below runner selection must remain identical.
10. Merge through the ordinary current merge-control path once exact-head proof is accepted.
11. Obtain post-merge automatic production proof from a **natural `push`-triggered `render.yml` run** caused by a normal render-owned source/template merge. Do not manufacture product churn solely to create the proof.
12. Verify that push-triggered job has no dispatch runner input, lands on `pc-render-*`, carries `render-linux`, completes checkout/pull/bootstrap/cache, render, guards, R2 publication and site commit/push.
13. Update durable W3 status to `done` only after that proof. Stop.

## Pre-merge acceptance tests

At minimum:

```text
render.yml parses
workflow_dispatch.inputs.runner.default == render-linux
jobs.render.runs-on fallback == render-linux
options still include render-heavy, render-linux, macstudio
render-heavy remains explicit fallback
macstudio remains explicit fallback
permissions unchanged
concurrency unchanged
timeout-minutes unchanged
checkout/cache/bootstrap/render/guard/publication step bodies unchanged except route-adjacent comments if needed
```

Run the canonical owner suite including:

```bash
python3 -m pytest tests/test_render_canada_scope.py -q
```

Also run current repository workflow/runner-policy validation required by CI. If a route-policy check introduces a new failure, determine whether it is caused by the intended default change; do not paper over inherited failures.

Exact-head GitHub fences and semantic CI remain the merge acceptance authority.

## Production proof after merge

The accepted production witness must be a `render.yml` **push event**, not a manual dispatch with `runner=render-linux`.

Return at least:

```text
workflow run id
job id
trigger event = push
head SHA / causing merge
created_at
job started_at
job completed_at
runner_name
runner_id if available
runner_group
labels including render-linux
conclusion
persisted checkout result
git pull result
bootstrap/zstd/cache results
render result
all guard results
R2 publication receipt
site commit/push SHA
any queue delay explanation
any stale-lock / sparse / promisor / early-EOF / index-pack warning
```

Acceptance requires:

- expected PC `pc-render-*` physical host identity;
- no hidden M2 fallback;
- job success;
- ordinary existing render/publication semantics preserved;
- no resource or checkout failure that required manual repair during the accepted run.

A manual default dispatch with no explicit `runner` is useful supplemental evidence for selector (1), but it cannot replace the push-run proof of selector (2).

## Failure states

Stop and return evidence if:

- fewer than two PC listeners are currently live when post-merge proof is attempted;
- automatic push run lands on `render-heavy`/M2 after the cutover;
- push run queues indefinitely despite live PC listeners;
- checkout/persisted metadata fails and requires host mutation;
- cache/zstd/bootstrap changes semantics or falls back unexpectedly;
- render/guard/R2 publication/site push fails;
- route change requires edits to render implementation or data/authority semantics;
- another PR concurrently owns `render.yml` routing;
- runner-policy static-liveness reconciliation becomes entangled with the cutover beyond the already-declared label.

Do not retry repeatedly to manufacture a green. Preserve every failed attempt.

## Rollback

Rollback is route-only and does not require undoing any render logic:

```yaml
workflow_dispatch.inputs.runner.default: render-heavy
jobs.render.runs-on fallback: render-heavy
```

Keep the option set unchanged. M2 `render-heavy` remains available through W5 specifically so rollback does not require runner re-registration.

## Stop condition

Stop after:

1. the W3 route PR is merged on accepted exact-head proof; and
2. one natural push-triggered production render proves the automatic fallback now lands on PC and publishes successfully; and
3. durable W3 state is updated with that receipt.

Do not continue into W4 M1 production admission or W5 fleet-health/retirement work.

## Required continuation handoff

Return to Sol:

- PR URL / number;
- exact base/head/merge SHAs;
- exact changed-file set;
- parsed before/after route values;
- focused/local and exact-head CI receipts;
- post-merge push-run/job/runner receipt;
- publication commit/push receipt;
- any failed attempts;
- rollback state;
- single next action.

Final statement must distinguish:

```text
W3 default-render cutover production proof complete|blocked.
W2 M1 12-hour soak remains separately pending unless a terminal receipt has since been supplied.
No W4 or W5 production change was made.
```
