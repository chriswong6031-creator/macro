# PC CI Fourth Slot and Aggregate Resource Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task-by-task, with
> one implementer and one reviewer per task.

**Goal:** Add exactly one fourth sealed Linux/x86 CI slot to the existing PC pool and
prove that all four CI candidates remain inside one enforced aggregate resource envelope
while the independent render route remains healthy.

**Architecture:** Reuse the existing #6351/#6434 runner group, main-owned workflow,
root-owned read-only Git cache, admission hook, one-job listener, cleanup helper, receipt
schema, and Agent OS workstreams. Add one aggregate systemd slice for `pc-ci-*` only; do
not add a scheduler, queue, runner registry, cache plane, or retry service. Preserve every
render listener, label, service, and cgroup outside the CI slice.

**Tech Stack:** GitHub Actions YAML, Python 3.12, pytest, systemd/cgroup v2, GitHub
organization runner groups, existing self-hosted canary receipt tooling.

**Spec:** `research/CI_LATENCY_AND_AUTONOMOUS_HEALING_MASTERPLAN.md`, current-state
amendment and revised execution order.

## Preconditions and stop boundaries

- Do not begin code changes until P3B-B PR #6505 has merged or closed and P4 has accepted
  three natural product PRs on the three-slot production route.
- Re-pin `origin/main` immediately before creating the carrier; use one fresh sparse
  worktree under `.claude/worktrees/` on a `claude/<task>` branch.
- Re-run the live PR collision census for every path below. A collision on runner policy,
  canary workflow, admission/cleanup helpers, or fleet records is a hard stop.
- The host-capacity carrier does not change production concurrency. Current trusted
  execution remains `max-parallel: 3`. A separate promotion carrier may change that one
  production limit to four only after the four-slot diagnostic plus real-render receipt is
  accepted. Hosted planner/gate/fences, merge control, selected-workflow list, repository
  visibility, M1 routing, and render routing remain unchanged in both carriers.
- The first security-sensitive stop is the organization runner registration and group
  membership act for `pc-ci-4`. Never request, paste, print, or store a registration token
  in a PR, issue, receipt, terminal transcript, or chat.
- Do not change WSL's current 16-CPU / 44-GiB / 8-GiB-swap allocation in this wave.
- The fourth-slot starting envelope is the slice `/mastermind-ci.slice` with
  `CPUQuota=800%`, `CPUQuotaPeriodSec=100ms`, `MemoryHigh=10G`, `MemoryMax=12G`, and
  `MemorySwapMax=2G`. Accounting for CPU, memory, I/O, and tasks is enabled. `AllowedCPUs`,
  `CPUWeight`, `IOWeight`, and `TasksMax` remain deliberately unset/inherited in this first
  wave; their counters are receipted. This bounds CI to eight vCPU-equivalents and 12 GiB
  inside the 16-vCPU/44-GiB guest while leaving the renderer outside the slice. Any change
  to these exact values requires a new measured carrier.
- Code support and live capacity are distinct. The code carrier declares one pending
  fourth-slot architecture while the live `ci-linux` carrier list remains exactly
  `pc-ci-1..3`. Register and bootstrap `pc-ci-4` first with platform/architecture identity
  only—**without** `ci-linux`—so the roster, service, PID, root, and cgroup can be proved
  online but unroutable. Keep the static `ci-linux.carried_by` list and live slot count at
  three through that proof and through the pending-capacity code activation. Add
  `pc-ci-4` to the live carrier list only in the same narrowly audited final activation act
  that confirms its existing `ci-linux` label is present and GitHub reports the exact
  runner online/idle. Policy must never claim a live fourth carrier before that receipt.
- Version the guard thresholds separately from slice ceilings: require guest-wide
  `MemAvailable >= 20 GiB`, swap use `<= 512 MiB`, and memory/I/O PSI `full avg10 < 0.10`
  before the four-slot canary. During acceptance, require minimum `MemAvailable >= 8 GiB`,
  swap delta `<= 512 MiB` and growth `<= 64 MiB/min`, no memory/I/O `full avg10 >= 1.00`
  sustained for 30 seconds, and zero `memory.events` high/max/oom/oom_kill delta. CPU
  acceptance ignores windows shorter than ten quota periods and otherwise requires both
  `nr_throttled_delta / nr_periods_delta <= 0.25` and
  `throttled_usec_delta / candidate_window_usec <= 0.25`.

---

### Task 1: Freeze the post-P4 topology and write the red policy tests

**Files:**
- Modify: `tests/test_runner_policy.py`
- Modify: `scripts/check_runner_policy.py`
- Modify later, after the tests are red: `.github/runner-policy.yml`

**Interfaces:**
- Consumes: accepted three-slot policy and exact P4 receipts.
- Produces: a failing contract for one pending fourth-slot architecture while the live
  inventory remains exactly three, without any new route or label family.

- [ ] **Step 1: Record the exact base and collision receipt**

Run:

```bash
git fetch origin main --prune
git rev-parse origin/main
git status --short --branch
gh pr list --repo mastermindx-market-intelligence/macro --state open \
  --json number,headRefOid,files
```

Expected: clean new worktree; P3B-B/P4 accepted on current main; no open carrier owns the
files in this task.

- [ ] **Step 2: Add failing four-slot and hostile-route tests**

Add tests that distinguish pending capacity from current live carriers, require exactly
one pending `pc-ci-4`, and still reject:

- `render-linux` on any CI slot;
- a new CI label family or generic `self-hosted` route;
- a new selected workflow or scheduled consumer;
- a fork/untrusted route to home hardware;
- a fifth CI slot hidden in YAML;
- `pc-ci-4` in the live carrier list before a roster/service-binding receipt.

Run:

```bash
python3.12 -m pytest -q tests/test_runner_policy.py
```

Expected: RED because policy and guard have no pending-capacity contract. Confirm the
failure names the missing pending fourth-slot capability, not an unrelated fixture error.

- [ ] **Step 3: Implement the smallest policy/guard change**

Extend the exact-three invariant in `scripts/check_runner_policy.py` and the declared
topology in `.github/runner-policy.yml` with one explicitly pending fourth-slot contract.
Keep live slots and the `ci-linux.carried_by` roster at three. Preserve all workflow,
group, fork, render, production, and visibility fields.

Run:

```bash
python3.12 -m pytest -q tests/test_runner_policy.py
python3.12 scripts/check_runner_policy.py
git diff --check
```

Expected: focused tests and guard pass; the diff contains no production route or selected
workflow expansion.

- [ ] **Step 4: Commit the topology contract**

```bash
git add -- .github/runner-policy.yml scripts/check_runner_policy.py tests/test_runner_policy.py
git diff --cached --check
git commit -m "ci: declare a guarded fourth PC slot"
```

---

### Task 2: Extend the diagnostic interface to four slots

**Files:**
- Modify: `.github/workflows/selfhosted-ci-canary.yml`
- Modify: `scripts/select_ci_canary_packs.py`
- Modify: `tests/test_ci_canary_workflows.py`
- Modify: `tests/test_ci_canary_tools.py`

**Interfaces:**
- Consumes: one exact hosted plan and four non-empty pack identities.
- Produces: a diagnostic-only four-slot matrix; production routing remains unchanged.

- [ ] **Step 1: Write failing four-slot selection and workflow tests**

Pin the accepted input set to `1`, `3`, and `4`; prove four distinct non-empty packs are
selected; require the hosted-control and compare matrices to contain all four corresponding
pack identities; preserve the independent render reservation for both `slots == '3'` and
`slots == '4'`; and ensure four-slot failures are surfaced rather than swallowed by logic
that currently names only `slots == '3'`.

```bash
python3.12 -m pytest -q \
  tests/test_ci_canary_workflows.py \
  tests/test_ci_canary_tools.py -k "slot or select or render or failure"
```

Expected: RED on the missing `4` input/selector and receipt behavior.

- [ ] **Step 2: Implement the four-slot diagnostic path**

Extend only the canary input, selection count, full per-pack hosted/self-hosted/compare
matrices, render-reservation condition, and failure-preservation conditions. Keep the same
main-defined workflow, hosted planner, semantic plan, cache, labels, and render-reservation
job.

```bash
python3.12 -m pytest -q tests/test_ci_canary_workflows.py tests/test_ci_canary_tools.py
python3.12 scripts/select_ci_canary_packs.py --help
git diff --check
```

Expected: tests pass; `slots=4` selects four non-empty pack indices; CI and render labels
remain disjoint.

- [ ] **Step 3: Commit the diagnostic extension**

```bash
git add -- \
  .github/workflows/selfhosted-ci-canary.yml \
  scripts/select_ci_canary_packs.py \
  tests/test_ci_canary_workflows.py \
  tests/test_ci_canary_tools.py
git commit -m "ci: admit a four-slot capacity canary"
```

---

### Task 3: Add aggregate CI-slice evidence before enforcing limits

**Files:**
- Modify: `scripts/monitor_ci_host_resources.py`
- Modify: `scripts/capture_ci_canary_receipt.py`
- Modify: `tests/test_ci_canary_tools.py`

**Interfaces:**
- Consumes: cgroup v2 paths for one named CI slice.
- Produces: bounded existing-receipt fields for slice CPU, memory, swap, processes,
  pressure, and limit events.

- [ ] **Step 1: Add failing receipt fixtures**

Create fixtures for readable and unreadable aggregate cgroup files. Require, when
available:

- `cpu.stat` and `cpu.max`;
- `memory.current`, `memory.peak`, `memory.events`, and `memory.swap.current`;
- `pids.current` and `pids.events`;
- CPU, memory, and I/O pressure values.

Every candidate derives its actual cgroup from `/proc/self/cgroup` and must bind to the
immutable expected `/mastermind-ci.slice/...service` hierarchy. A candidate still in
`system.slice`, an unexpected path, or unreadable slice evidence produces an explicit
degraded/refused result, never a host-global green substitute. Fixtures distinguish a
kernel field that is unavailable from an observed zero.

```bash
python3.12 -m pytest -q tests/test_ci_canary_tools.py -k "cgroup or slice or pressure"
```

Expected: RED because current monitoring contains only global host metrics.

- [ ] **Step 2: Extend the existing monitor and reducer**

Add slice fields to the existing JSONL/reducer. Capture pre-run and post-run snapshots and
deltas for `cpu.stat`, `memory.events`, `pids.events`, and pressure totals. Treat
`memory.peak` as a cgroup-lifetime fact unless the privileged ceremony resets it; never
present it as a run-local peak without that receipt. Preserve the current receipt schema
if the extension is backward compatible. If a new schema version is unavoidable, add
explicit comparator migration tests so P1/P2 receipts remain honestly readable.

```bash
python3.12 -m pytest -q tests/test_ci_canary_tools.py
python3.12 -m pytest -q tests/test_ci_canary_workflows.py
git diff --check
```

Expected: focused suites pass; no new monitor, database, or receipt plane exists.

- [ ] **Step 3: Commit the evidence extension**

```bash
git add -- scripts/monitor_ci_host_resources.py scripts/capture_ci_canary_receipt.py tests/test_ci_canary_tools.py
git commit -m "ci: receipt aggregate PC CI resource use"
```

---

### Task 4: Add the aggregate systemd slice and fourth-root lifecycle

**Files:**
- Create: `ops/runner-host/pc/mastermind-ci.slice.template`
- Modify: `ops/runner-host/pc/actions-runner-ci.service.template`
- Modify: `ops/runner-host/pc/mastermind_ci_resource_guard.py`
- Modify: `ops/runner-host/common/runner_cleanup.py`
- Modify: `tests/test_ci_canary_tools.py`

**Interfaces:**
- Consumes: one approved slice envelope and one sealed runner root.
- Produces: `pc-ci-1..4` inside the same CI-only slice, with render outside it.

- [ ] **Step 1: Write failing service, cleanup, and guard tests**

Require the service template to join the named CI slice while preserving all current
sandboxing, read-only cache, and `KillMode=control-group`. Add `/opt/mastermind-ci/runner-4`
as the sole new cleanup root and prove an arbitrary fifth/foreign root is refused. Add
guard fixtures for render-aware memory floor, slice pressure, swap growth, and cgroup
limit events.

```bash
python3.12 -m pytest -q tests/test_ci_canary_tools.py -k "service or cleanup or resource or slice"
```

Expected: RED on the missing slice/root/guard behavior.

- [ ] **Step 2: Implement the CI-only slice and admission guard**

Add one slice template with the exact aggregate values in the preconditions and point only
the CI service template to it. The prestart guard requires the expected cgroup binding and
the exact separately versioned memory, swap, PSI, event, and CPU-throttling thresholds in
the preconditions. Extend the existing guard; do not change, stop, restart,
relabel, or move any render unit.

Static and host tests must prove every `pc-ci-1..4` unit uses
`Slice=mastermind-ci.slice`, no CI unit remains in `system.slice` after migration, and
`pc-render-1` plus every remote render roster entry remains outside the CI slice with its
existing service/label/resource semantics. Do not copy CI's `KillMode=control-group` or
slice limits onto render units.

```bash
python3.12 -m pytest -q tests/test_ci_canary_tools.py
python3.12 -m pytest -q tests/test_runner_policy.py tests/test_ci_canary_workflows.py
git diff --check
```

Expected: all focused tests pass; `runner_admission.py` remains unchanged unless a failing
test proves a concrete fourth-root binding is missing.

- [ ] **Step 3: Commit the host substrate**

```bash
git add -- \
  ops/runner-host/pc/mastermind-ci.slice.template \
  ops/runner-host/pc/actions-runner-ci.service.template \
  ops/runner-host/pc/mastermind_ci_resource_guard.py \
  ops/runner-host/common/runner_cleanup.py \
  tests/test_ci_canary_tools.py
git commit -m "ops: isolate four PC CI slots in one resource slice"
```

---

### Task 5: Reconcile documentation, review, and merge the code carrier

**Files:**
- Modify: `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md`
- Modify: `agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md`
- Create: one dated handoff under `agentos/handoffs/`

- [ ] **Step 1: Record the code boundary without claiming host installation**

Document four-slot code readiness, the unchanged WSL allocation, the approved slice
envelope, the absent host root/unit/registration, the security-sensitive registration
stop, and the exact rollback. Keep the capability `BUILT_NOT_HOST_PROVEN`.

- [ ] **Step 2: Run all governing proof**

```bash
python3.12 -m pytest -q \
  tests/test_runner_policy.py \
  tests/test_ci_canary_workflows.py \
  tests/test_ci_canary_tools.py
python3.12 scripts/check_runner_policy.py
python3.12 scripts/agentos.py validate
python3.12 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-count 12 --validate-only
git diff --check
git status --short --branch
```

Expected: focused tests pass, policy guard passes, Agent OS has zero errors, manifest
validates, diff is clean except intended files.

- [ ] **Step 3: Adversarial review and full delivery chain**

Use `superpowers:requesting-code-review`, repair findings under TDD, fetch/re-pin main,
push one PR linked to #6351/#6434, conclude binding CI, squash-merge without bypass, and
verify the merged files on current `origin/main`. Do not apply host changes from an
unmerged branch.

---

### Task 6: Perform the privileged host installation and four-slot acceptance

**Host paths (not committed):**
- Create: `/opt/mastermind-ci/runner-4`
- Create: `/etc/systemd/system/mastermind-ci.slice`
- Replace from the exact pre-change snapshot after a natural drain:
  `/etc/systemd/system/actions.runner.mastermindx-market-intelligence-macro.pc-ci-{1,2,3}.service`
- Create: `/etc/systemd/system/actions.runner.mastermindx-market-intelligence-macro.pc-ci-4.service`

- [ ] **Step 1: Stop for the security-sensitive authority act**

Obtain explicit Chairman/Sol confirmation for one new organization runner registration
and group membership. The user performs any native authorization ceremony; no secret is
entered through chat.

- [ ] **Step 2: Snapshot and install after a natural drain**

Snapshot runner-group membership, labels, selected workflows, `pc-ci-1..3` unit bytes and
cgroups, render unit/roster/cgroups, root permissions, cache identity/bytes, admission
helper hashes, and rollback commands. The privileged packet binds every installed helper
hash to the exact merged main commit and records owner/group/mode for the new sealed root,
`_work`, `_temp`, `_home`, `_diag`, and cache access. It proves the selected-workflow list
and single existing runner-group consumer are unchanged.

At a natural drain, install the merged slice and rendered units for `pc-ci-1..3`, reload
systemd, restart only those three listeners, and prove their new slice membership. Create
the sealed fourth root and configure/register `pc-ci-4` with platform/architecture labels
only—no `ci-linux`. Install/bootstrap its rendered unit and prove the exact online but
unroutable roster/service/PID/root/cgroup binding. Land only the pending-capacity code
support while live policy remains three. At the final natural drain, add the existing
`ci-linux` label, confirm the exact runner online/idle, and update the live slot/carrier
inventory to four as one audited activation packet before candidate dispatch. Never
restart or rewrite a render unit.

- [ ] **Step 3: Prove identity and negative authority before traffic**

Require exact agreement among GitHub runner name/status/labels, service unit, listener
PID/cgroup, root, immutable helper hashes, cache permissions, and one-job teardown. Before
candidate traffic, prove `pc-ci-1..4` are all descendants of `/mastermind-ci.slice`, none
remain in `system.slice`, and `pc-render-1` remains in its exact pre-change cgroup. Prove
the remote render runner roster/labels and every route/group/workflow/visibility field are
unchanged. This is the first live slice evidence; repository tests alone remain
`BUILT_NOT_HOST_PROVEN`.

- [ ] **Step 4: Run one four-slot canary plus natural-render acceptance**

Run exactly one authorized `slots=4` diagnostic while an independently occurring real
production render is active. The diagnostic includes four hosted controls, four
self-hosted candidates, four comparisons, and the render-reservation probe. Require
semantic parity, clean cache and workspace state, trusted cgroup identity, every exact
memory/swap/PSI/event/CPU-throttling threshold from the preconditions, and an unchanged successful
render route. This proves four-host capacity; it does **not** claim ordinary production CI
used four slots while the executor remains capped at three.

- [ ] **Step 5: Roll back or accept**

On any isolation, pressure, cleanup, cache, parity, or render failure:

1. remove `pc-ci-4` eligibility first and prevent new CI admission during the reversal;
2. preserve its root, registration, cache, and diagnostics pending an approved retirement;
3. at a drain, restore the exact prior `pc-ci-1..3` unit/helper bytes, reload systemd, and
   restart only those three listeners into their pre-change cgroups;
4. verify all three are back in `system.slice`, the server-side live carrier inventory is
   restored to three, and render remained in its original cgroup and roster throughout;
5. remove the unused slice only after no process references it.

On success, record the exact capacity receipt in the existing workstream. Do not infer six
slots or expand WSL from this one receipt.

---

### Task 7: Promote ordinary production concurrency from three to four

This is a separate fresh carrier after Task 6 acceptance, not part of the host-capacity
PR. Re-pin current main and the accepted runner roster; re-run the collision census.

**Likely files after the re-pin:**
- Modify: `.github/workflows/trusted-ci-executor.yml`
- Modify: production-route tests and policy tests named by the current tree
- Modify: the existing runner-fleet workstream/handoff

- [ ] Write a red test requiring the trusted pack matrix's sole concurrency change from
  `max-parallel: 3` to `max-parallel: 4`, while preserving group, labels, admission,
  hosted planning, semantic fragments, cleanup, render, and fork boundaries.
- [ ] Make only that bounded route change and ship it through concluded CI.
- [ ] Accept a named natural-traffic corpus with at least three ordinary PRs, including one
  simultaneous-PR overlap window and one independently active real render. Measure queue,
  pack, slice, teardown, cache, and render receipts; do not substitute a diagnostic canary.
- [ ] Roll back production concurrency to three on any semantic, pressure, cleanup, cache,
  queue, or render regression while retaining the already proven but idle fourth host.

Only after this promotion succeeds may the system claim four ordinary production CI
slots. A later WSL/core/memory or six-slot proposal requires a new host-wide Windows,
WSL, renderer, GPU/local-LLM, memory, swap, and pressure baseline; nominal 24-core hardware
is not that receipt.
