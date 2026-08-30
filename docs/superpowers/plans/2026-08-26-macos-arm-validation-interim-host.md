# MacBook macOS/ARM Validation and Mini Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task-by-task. Do not enter a registration
> credential or perform an administrator ceremony through chat.

**Goal:** Add one sealed, dispatch-only `macos-arm-validation` listener on the stationary
M4 Pro MacBook for the next six months, while making its contract reconstructable on a
replacement M4 mini without changing Linux/x86 CI, render, merge control, or generic Mac
routes.

**Architecture:** Declare the role in the existing runner policy and existing
`macro-home-canary` group. Add a dedicated main-only diagnostic workflow, one immutable
admission profile, a root-owned macOS LaunchDaemon, a non-login runner account, a one-job
listener, strict cleanup, a root-owned read-only Git cache, and macOS-native resource
admission. Do not extend the historical M1 user LaunchAgents or copy Linux/systemd code.

## Preconditions and hard boundaries

- Wait for #6505/P4 and re-pin the live runner policy and admission contract.
- Do not touch the three current M4 minis. They are replacement candidates only after the
  accepted MacBook contract is frozen.
- The role never acquires `ci-linux`, `ci-linux-canary`, `macstudio`, `macstudio-light`,
  `render-heavy`, `render-linux`, `theta-m1`, `merge-control`, or generic overflow labels.
- Its workflow is `workflow_dispatch` only, main-gated by a GitHub-hosted trust job, has no
  production routing, and publishes no required check.
- First privileged boundary: create a dedicated non-login account and sealed directories.
  Install and statically validate the runner binary/configuration, admission hook, wrapper,
  cleanup tool, resource guard, cache updater, ownership, and modes while the new
  LaunchDaemon remains **unbootstrapped**. Installing the plist is not permission to start
  it.
- First GitHub-state boundary: add the exact main workflow identity to the existing group
  and register one exact-label runner application using a fresh short-lived credential in
  a native administrator surface. “Registered but offline” means configuration exists but
  the LaunchDaemon has not been bootstrapped; it never means `--disableupdate`. Stop for
  explicit authorization before this act. Enable/bootstrap the service only after the
  registration receipt and a local resource preflight pass. The first dispatch is a
  separate authorized act.

---

### Task M1: Freeze the role in red policy/workflow tests

**Files:**
- Modify: `tests/test_runner_policy.py`
- Modify: `tests/test_ci_canary_workflows.py`
- Modify: `scripts/check_runner_policy.py`
- Create: `tests/test_macos_arm_validation_runner.py`
- Modify after tests fail: `.github/runner-policy.yml`
- Create after tests fail: `.github/workflows/macos-arm-validation-canary.yml`

Tests require dispatch-only main admission, exact labels
`[self-hosted, macOS, ARM64, macos-arm-validation]`, one declared slot, no checkout or
secret context in the host probe, no production/merge/render route, and rejection of
every forbidden label. Add the workflow to the policy-test fixture inventory so the
negative tests execute against real bytes. The checker must enforce the exact main-pinned
workflow identity and custom route/job/event/label tuple; reject PR,
`pull_request_target`, reusable-caller, schedule, computed-label, and generic-label
bypasses; and require an explicit registry lifecycle. The code carrier declares the new
label `orphaned` before registration. Only a real GitHub roster plus service-binding
receipt may move it to `live`; the intermediate registered-but-unbootstrapped state is
`offline`.

### Task M2: Add one immutable admission profile

**Files:**
- Modify: `ops/runner-host/common/runner_admission.py`
- Modify: `ops/runner-host/common/runner_admission_hook.js`
- Modify: `tests/test_ci_canary_tools.py`
- Modify: `tests/test_macos_arm_validation_runner.py`

Allow exactly the Macro repository, `workflow_dispatch`, `refs/heads/main`, the exact
workflow reference, the exact canary job, and profile `macos-arm-validation`. Every
independently mutated fact must refuse. The root-owned hook basename is the only profile
selector; a job environment cannot select another profile. Reconcile #6505's trusted
fact-forwarding changes on its merged head rather than overwriting them.

### Task M3: Build the root daemon and one-job lifecycle

**New family:**
- `ops/runner-host/macos-arm/actions-runner-launchdaemon.plist.template`
- `ops/runner-host/macos-arm/run_macos_arm_validation_runner.sh`
- `ops/runner-host/macos-arm/macos_arm_runner_cleanup.py`
- `ops/runner-host/macos-arm/install_macos_arm_validation_runner.sh`

The LaunchDaemon runs without GUI login under an explicit `UserName`-bound non-login
service account and invokes `Runner.Listener --once`. It uses an always-restart contract
with a bounded `ThrottleInterval`: a normal zero exit after one job must start a second
listener, while cleanup/resource refusal is throttled and cannot form a tight loop. The
wrapper owns the process group, traps exit/signals, terminates and waits for all
descendants, then exits so launchd may restart it. Tests model both a successful zero-exit
listener turnover and repeated refusal/failure.

Cleanup runs before every listener, permits only the one role root, refuses symlink
escape, recreates private `_temp` and `_home`, and proves no descendant remains before
the next listener. Freeze and statically test this permissions contract:

| Object | Owner/mode contract | Candidate access |
|---|---|---|
| LaunchDaemon plist, wrapper, admission hook/policy, cleanup and resource guard | root-owned; not group/job writable | read/execute only where required |
| runner binary and external toolchain | root-owned; immutable to service account | read/execute |
| `.runner` and credential-bearing configuration | `0600` equivalent, outside workspace, never copied into job artifacts | same service UID; protected from other users, not sandboxed from arbitrary same-UID code |
| cache identity, updater, refs, config, objects and maintenance state | root-owned; group read/traverse only where required | no writes or updater execution |
| `_work`, `_temp`, `_home` | service-account-owned, role-root confined, recreated/cleaned per contract | writable for one job |
| `_diag` | service-account append/write with bounded retention; no executable/config authority | bounded diagnostics only |

The installer refuses before bootstrap if any object is writable outside this table. The
threat model is deliberately narrow: this host executes only the exact main-defined,
no-secret diagnostic workflow in Task M6. A GitHub Actions job child shares the listener's
service UID and therefore cannot be claimed unable to read same-UID runner configuration;
root ownership or `0600` is not process isolation. No arbitrary PR, untrusted candidate,
production overflow, or secret-bearing workload may be admitted without a new design that
separates listener credentials from the job process.

### Task M4: Port the immutable cache contract

**New files:**
- `ops/runner-host/macos-arm/macos_arm_ci_prewarm.py`
- `ops/runner-host/macos-arm/macos_arm_ci_cache_update.sh`
- `ops/runner-host/macos-arm/macos-arm-ci-cache-update.plist.template`
- `ops/runner-host/macos-arm/macos-arm-ci-cache-identity.json`

Reuse the PC cache semantics, not its Linux paths. Root alone updates the bare cache;
the runner has read/traverse access only. Verify origin, identity, ownership, mode, bare
state, exact immutable base/tree, and complete objects before creating `.git`. Missing or
writable cache fails closed with the existing refusal class and never silently fetches
from origin. The macOS updater must additionally:

- serialize with one macOS-available root-only lock and explicit stale-lock refusal/
  recovery rules;
- advance only the cache's `refs/heads/main` through a verified temporary ref and atomic
  ref update;
- leave the prior verified cache intact on fetch/fsck/identity failure;
- prohibit candidate invocation and prohibit prune, repack, GC, or background maintenance
  during the interim role;
- include repository, canonical origin, frozen base/tree, updater schema, runner profile,
  and sanitized update time in the identity/receipt;
- prove group access permits object reads but not ref/config/object/maintenance writes.

### Task M5: Add macOS-native resource admission

**New file:** `ops/runner-host/macos-arm/macos_arm_resource_guard.py`

Split three kinds of proof rather than treating one preflight as a future guarantee:

- per-listener fail-closed guard: current disk/inodes, memory pressure, swap/compression,
  AC state, network reachability, and thermal state;
- host admission: explicit `pmset`/power-policy receipt for sleep, Power Nap, automatic
  restart, and AC behavior;
- soak: observed reboot plus AC-loss, network-recovery, and sustained thermal behavior.

Each field has one named macOS-native read-only source and a sanitized schema. Unsupported
or unparsable facts refuse instead of mapping to healthy. Thresholds come from the actual
M4 Pro inventory and sustained-load receipt, not from M1, M2, or PC constants. Tests cover
every refusal and bounded backoff.

### Task M6: Prove the diagnostic role

The future authorized canary sequence is exactly:

1. no-checkout service, account, PID, label, and non-secret host-fact proof;
2. writable-cache negative control;
3. exact immutable-base materialization;
4. two-tree contamination and one-job teardown proof;
5. selected native validation parity on the exact immutable tree using only
   `python3 scripts/check_runner_policy.py` and
   `python3 -m pytest -q tests/test_runner_policy.py tests/test_ci_canary_workflows.py`;
6. reboot, AC/network recovery, and sustained thermal soak.

A GitHub-hosted job in the same main-defined diagnostic workflow executes the exact two
commands on the same tree first. Parity compares exit status and normalized pytest
pass/fail/skip counts; timing and OS-specific path text are reported but are not semantic
equality. The commands receive no production secrets and may not write `data/`, `site/`,
publication, deployment, or mutable shared state. No candidate product execution or
production route is part of the first canary.

### Task M7: Freeze the transfer contract

Add `docs/CI_MACOS_ARM_VALIDATION_RUNBOOK.md` and
`research/MACOS_ARM_INTERIM_TO_MINI_TRANSFER_CONTRACT.md`. Freeze semantic role ID,
labels, group, allowed workflow/job tuple, runner version/hash, daemon/helper hashes and
modes, directory/cleanup/cache/resource contracts, and sanitized inventory. On transfer,
recreate registration, cache packs, `_work`, `_temp`, `_home`, and `_diag`; do not copy
mutable host state.

The replacement mini is first registered under a distinct, temporary
`macos-arm-validation-candidate` label admitted only by an exact temporary main-only
candidate workflow/job; it does not carry the live semantic role label. After its host,
cache, cleanup, reboot, thermal, and parity receipts pass: drain the MacBook, prove no
active job/listener, remove the mini candidate registration, register/activate the mini
under the final `macos-arm-validation` label, and prove the exact mini identity on the
first final-role receipt. Then retire the MacBook registration. A two-host live-role soak
is forbidden; any dual-host comparison uses the distinct candidate identity.

Freeze ordered rollback for every state:

1. code merged but group path absent — revert the declarative role only;
2. group admitted but no runner registration — remove only that exact workflow identity;
3. runner registered but daemon unbootstrapped — deregister only that exact offline runner
   and retain sanitized install diagnostics;
4. listener online but no dispatch — boot out only the new LaunchDaemon, verify offline,
   then deregister if rollback is final;
5. failed canary/unclean job — boot out the exact daemon, preserve `_diag` and the sealed
   cache for investigation, clean only the role-owned mutable roots, then either re-prove
   or deregister;
6. mini candidate/cutover — remove only the candidate/final mini registration implicated
   by the failed state and restore the already accepted drained MacBook role if its exact
   manifest still matches.

Generic Mac, PC, M1, render, and merge-control registrations are never rollback targets.

The temporary mini lane is a separately authorized future code carrier. Before any mini
registration, it must add `.github/workflows/macos-arm-validation-transfer-canary.yml`, an
exact `workflow_dispatch`/main/custom-route entry, the main-pinned workflow identity in the
existing runner group, an initially orphaned `macos-arm-validation-candidate` registry
entry, and negative tests in `tests/test_runner_policy.py`,
`tests/test_ci_canary_workflows.py`, and `tests/test_macos_arm_validation_runner.py`.
The workflow selects exactly `[self-hosted, macOS, ARM64,
macos-arm-validation-candidate]`, admits only the same non-secret Task M6 proof, and cannot
publish a required check or acquire the final/live role. After cutover, a cleanup carrier
removes the temporary workflow, route, group identity, and candidate registry entry.
No mini registration, canary, or cutover may occur until that future lane is merged and
policy-validated.

## Code proof and delivery

```bash
python3 scripts/check_runner_policy.py
python3 -m pytest -q \
  tests/test_runner_policy.py \
  tests/test_ci_canary_workflows.py \
  tests/test_ci_canary_tools.py \
  tests/test_macos_arm_validation_runner.py
```

Ship code before host installation. After merge, take a sanitized pre-mutation inventory,
perform the one explicitly authorized admin/registration ceremony, and return one exact
acceptance or rollback receipt. Never expose credentials in chat or logs.
