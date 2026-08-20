# Runner Fleet Resilience — architecture freeze and execution program

**Date:** 2026-08-20  
**Authority:** Chairman escalation → Sol architecture freeze  
**Workstream:** `WS:RUNNER-FLEET-RESILIENCE`  
**Decision:** `DEC:RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS`  
**Amendment record:** `research/RUNNER_FLEET_RESILIENCE_M0_ADVERSARIAL_AMENDMENT_2026-08-20.md`

## 0. Frozen outcome

Mastermind must be able to ship correct PRs while authoritative nightly production is running. A multi-hour render, collector, or local Git/I/O storm on one physical machine must not be able to starve production, merge arbitration, and interactive development at the same time.

Done means all four conditions are proven in production:

1. **Shipping control is independent of M2 production load.** `merge-on-green` runs outside the M2 physical failure domain and still drains armed PRs during a real heavy nightly/render window.
2. **Routine full render is independent of M2 production load.** PC/WSL owns the normal `render.yml` and `engine-render.yml` route after live proof; M2 remains explicit break-glass Mac fallback.
3. **Owned Mac capacity is actually usable.** The M1 returns through the existing guarded service/canary contract, then receives only capability-specific production authority that has been measured safe on its 32 GB envelope.
4. **Fleet health is reasoned about by physical host.** Four listeners on one Mac never count as four independent failure domains.

No new scheduler, queue, runner database, merge implementation, or lifecycle store is authorized. GitHub Actions remains the scheduler, `.github/runner-policy.yml` remains the checked-in routing declaration, and Agent OS remains durable organizational state.

## 1. Intent recovery

The Chairman's symptom is recurring overnight `SHIP LOOP BLOCKED`: the M2 Ultra is heavily occupied by collect/render work while the M1 and PC appear comparatively idle, and multiple sessions cannot get PRs merged.

The user job is not “make GitHub faster.” It is:

> A session that has completed correct work should be able to ship while production is baking, and production should not lose its session because a long render or control-plane job consumed the same physical machine.

The machine job is to move portable work away from scarce/store-bound Mac capacity, recover owned hardware safely, preserve canonical control planes, and expose capacity at the physical-host level.

## 2. Verified current state

### 2.1 Runner starvation is proven live

PR #6089 records the 2026-08-20 production incident:

- `macstudio` capacity was starved for about four hours;
- multi-hour render work occupied `mac-builder-light` while production/intraday work cycled on `mac-builder-5`;
- one-minute Asia gate jobs waited 15–58 minutes for a runner;
- the queue delay exposed a separate gate-classification bug and the settled CN/HK builders missed their session.

#6089 fixed the gate's starvation blindness. It did **not** fix the capacity starvation.

### 2.2 Logical labels share one M2 failure domain

The checked-in runner registry currently maps:

- `macstudio` → `mac-builder-5`, `mac-builder-light`;
- `render-heavy` → `mac-builder-light`;
- `merge-control` → `mac-builder-4`;
- `macstudio-light` → `mac-builder-3`.

Those are separate listener identities on the same physical M2 Ultra. Label isolation prevents GitHub from assigning the wrong job to a listener; it does not isolate CPU, memory, SSD bandwidth, filesystem pressure, Git object traffic, or the operator's own worktrees.

### 2.3 The M1 failed from service recovery, not lack of hardware

The Aug-14 fleet audit proved:

- M1 Max Studio, 10 cores / 32 GB;
- three configured runner services but zero listener processes after an Aug-13 ENOSPC crash;
- disk later recovered to roughly 168 GiB free;
- the old service arrangement did not recover the listeners after the disk recovered.

The repository already contains the safer recovery substrate:

- `ops/runner-host/m1/run_guarded_runner.sh`;
- `ops/runner-host/m1/actions-runner.plist.template` with launchd restart semantics;
- disk and diagnostic-log guards;
- `.github/workflows/m1-runner-canary.yml`, which proves three exact service/root/registration mappings with distinct live listener PIDs and performs no checkout or secret read.

Therefore the M1 return substrate is **BUILT_NOT_PROVEN**, not “not built.”

### 2.4 The PC has proven render capacity, but live status must be re-proven

The Aug-14 audit proved four PC/WSL listeners and recent `engine-render` work. `render.yml` records a full PC render around 81 minutes, and `engine-render.yml` already defaults to `render-linux`.

The Aug-17 static registry later records `render-linux` offline. That registry is declaration, not live observation. W3 must prove current listener identity and execution rather than infer from either the old audit or the static status field.

### 2.5 Most PR proof is already hosted

Macro ordinary PR CI/fences, Terminal CI, Mastermind CI, and Macro `integration-baseline` all use GitHub-hosted runners. The remaining shipping-control exception is Macro `merge-on-green`, still routed to `[self-hosted, macOS, ARM64, merge-control]` on the M2.

### 2.6 M2 I/O already affects interactive shipping

PR #5967 measured a full-worktree `git status --porcelain` taking 161 seconds under fleet I/O load and hardened the ship loop against timeout/index-lock damage. The interactive session plane and Actions listeners therefore share a meaningful physical I/O failure domain even when runner labels differ.

### 2.7 Adjacent CI checkout latency is real but is not this fleet program

During M0 acceptance, hosted `ci-plan` demonstrated a separate long-checkout class. The current planner uses `fetch-depth: 0` and materializes the full repository; a successful control run checked out roughly 74,562 paths and spent minutes before planning. That problem belongs to `WS:CI-MERGE-CONTROL-PLANE`. It must not be blurred into self-hosted runner starvation or used to widen this fleet PR.

## 3. Capability ledger

| Capability | State | Evidence / ruling |
|---|---|---|
| Macro ordinary PR CI on hosted | **PROVEN_LIVE** | current runner policy / CI workflow |
| Terminal + Mastermind CI on hosted | **PROVEN_LIVE** | repository CI workflows |
| Hosted integration baseline | **PROVEN_LIVE** | current `integration-baseline.yml` |
| M2 `merge-control` listener | **PROVEN_LIVE** | current merge workflow / registry |
| Merge control physically independent of M2 | **NOT_BUILT** | current route is M2 |
| M2 default full render | **PROVEN_LIVE / REJECTED_BY_DESIGN as end-state** | #6089 contention |
| PC engine render | **PROVEN_LIVE historically / current liveness unproven** | Aug-14 audit vs Aug-17 static registry |
| PC full render | **PROVEN_LIVE historically / current liveness unproven** | measured PC full render |
| M1 guarded launcher + disk/log law | **BUILT_NOT_PROVEN** | `ops/runner-host/m1/*` |
| M1 three-listener diagnostic canary | **BUILT_NOT_PROVEN** | `m1-runner-canary.yml` |
| Generic `macstudio` authority on M1 | **REJECTED_BY_DESIGN in W4** | M0 adversarial amendment |
| Capability-specific M1 production return | **NOT_BUILT / NOT_AUTHORIZED until W2 + W4 census** | this freeze |
| Live physical-host fleet projection | **NOT_BUILT** | static registry is not liveness |
| Physical-failure-domain admission law | **SPEC_ONLY until M0 merges** | DEC + this freeze |
| Nightly critical-path shortening | **PARTIAL** | Aug-13 compute audit; later wave |

## 4. Frozen target topology

### 4.1 GitHub-hosted — portable proof/control plane

Owns ordinary PR CI, fences, integration baseline, liveness/watchdogs, and `merge-on-green` **only after W1 canary acceptance**. Production collectors and host-local data/capability lanes remain self-hosted where required.

### 4.2 PC/WSL — routine render / portable Linux compute plane

After W3 acceptance:

- `engine-render.yml` remains default `render-linux`;
- automatic/default `render.yml` changes from `render-heavy` to `render-linux`;
- at least two distinct PC render listeners must be proven so ordinary render and engine-render can overlap without falling back to M2;
- ordinary PR CI remains hosted; PC CI canaries are a separate program concern.

There is no automatic M2 fallback. A manual, explicit Mac fallback may remain as break-glass behavior.

### 4.3 M1 Max — guarded, capability-specific Mac/store capacity

Return in two stages only.

**Stage A — diagnostic:** restore the three guarded listener identities under the existing diagnostic labels. No production label changes.

**Stage B — bounded production:** before any production authority is added, census every current consumer of the proposed label and its memory, local-store, credential, OS, and runtime assumptions. Then:

- admit **one explicitly selected measured-safe production lane** through a capability-specific M1 route such as `m1-nightly`;
- restore `theta-m1` only on the proven real store-bearing listener after the existing store/probe laws pass;
- do **not** add the generic `macstudio` label in W4;
- do not add `render-heavy`;
- do not restore `codex` without independent host-local CLI/auth preflight;
- keep unused M1 listeners diagnostic until independently commissioned.

Generic `macstudio` on the M1 is a later explicit architecture decision because it grants eligibility to every current `macstudio` consumer, not merely “one more capacity slot.” Historical compatibility is not current proof.

### 4.4 M2 Ultra — authoritative production + break-glass Mac plane

Retains authoritative existing `macstudio` production while M1 capability-specific return is proven, `macstudio-light` until separately measured, operator/session worktrees, and explicit break-glass Mac render fallback.

Retires from routine duty after proof:

- `merge-control` after W1 production proof;
- default `render-heavy` after W3 production proof.

Never orphan a scheduled/default label to force migration. Host/API label removal happens only after its consumers have a proven destination and rollback window.

## 5. Authority and no-rebuild boundaries

1. `WS:CI-MERGE-CONTROL-PLANE` keeps semantic authority over `.github/workflows/merge-on-green.yml` and `scripts/merge_on_green.py`. W1 changes environment/routing only; no forked merge logic.
2. `docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md` and `ops/runner-host/**` remain the canonical self-hosted safety substrate. Do not create another installer, cleanup daemon, cache authority, or canary protocol.
3. `.github/runner-policy.yml` remains the checked-in declaration. Future live health is an observation layer, not a second mutable registry.
4. GitHub Actions remains the scheduler. No side queue or fleet database.
5. Ship-loop semantics are outside this program unless separate evidence proves a guard bug. The primary goal is to remove the infrastructure conditions it is correctly reporting.
6. The hosted `ci-plan` checkout latency discovered during M0 stays under `WS:CI-MERGE-CONTROL-PLANE`; do not make runner-fleet recovery depend on solving it.

## 6. Frozen execution sequence

### M0 — architecture freeze / work identity

**Observable capability:** a cold session can distinguish logical listeners from physical capacity, recover the target topology, and commission only the next bounded wave.

**Scope:** Agent OS records + research only.

**Acceptance:** Agent OS/schema, hosted CI and fences green on the exact accepted head; no path collision; no workflow/label/runtime change.

### W1-A — hosted merge-control environment canary

**Mission:** prove GitHub-hosted runners satisfy the merge controller's runtime contract without giving the canary merge authority.

Requirements: dispatch-only; `contents: read` only; production-shape sparse checkout first; system Python/PyYAML/import closure proven before any test-only environment changes; merge-control tests executed in a separate test phase/job; no `MERGE_TOKEN`, `ADMIN_GH_TOKEN`, label mutation, update-branch, dispatch, or merge execution.

Run three canaries, including one in the nightly/render congestion window. Require pickup under 60 seconds and clean environment proof each time.

**Stop:** any canary waits >=60 seconds, flakes materially on checkout, or shows missing runtime parity. Do not cut over.

### W1-B — merge-control route cutover

Only after W1-A accepts. Change the real sweeper runner route to hosted and update its runner-policy/tests/comments. Keep `scripts/merge_on_green.py` semantics unchanged.

**Production proof:** a real armed PR merges through the hosted sweeper while M2 is busy; runner evidence is GitHub-hosted; no new merge-control failure; decisive-green-to-merge latency stays within the existing event-driven expectation.

**Rollback:** restore the `merge-control` route. No state migration exists.

### W2 — guarded M1 diagnostic restoration

Restore the existing guarded services only. Acceptance requires exact M1 hardware identity; healthy disk guard; three expected service/root/registration mappings; three distinct live listener PIDs; no historical production labels during diagnostic acceptance; kill/restart proof for one listener; and no ENOSPC/log-growth recurrence during soak.

**Stop:** identity collision, disk refusal, or failed restart. Add no production labels.

### W3 — PC render proof and default-render cutover

Before changing defaults require at least two live `render-linux` listeners on the PC; one real `engine-render` on PC with cache/zstd parity; one scope-all `render.yml` dispatch on PC; successful guarded push/publication; and resource receipt inside proven memory/disk bounds.

Then change automatic/default `render.yml` to `render-linux`, retaining only explicit manual Mac fallback.

**Production proof:** an automatic render executes on a PC listener while M2 accepts production work without that render occupying its host.

### W4 — capability-specific M1 production admission

First perform the current `macstudio` consumer/resource census. Then choose exactly one safe lane and give it a capability-specific M1 route. Restore `theta-m1` only to the proven store-bearing listener. Generic `macstudio` remains forbidden in W4.

**Production proof:** one natural production job executes on M1 while an independent sibling executes on M2, both complete, and no resource/disk guard breaches.

### W5 — retire obsolete M2 roles + live fleet projection

After W1/W3/W4 production proof, retire M2 `merge-control` after rollback soak; retire automatic M2 `render-heavy` duty; and add a hosted read-only live runner projection if lawful admin-token access exists. The projection may report physical host, runner identity, labels, online/busy state, queue age and route health. It must never become scheduler state.

### W6 — nightly critical-path reduction

Only after allocation is stable. Reopen the Aug-13 compute audit and reduce serial collection/engine time using measured timing receipts, respecting API rate limits, file ownership, and production truth. Do not mix this work into fleet recovery PRs.

## 7. SLOs and failure behavior

- **Shipping control:** after W1, no self-hosted runner availability is required merely to merge a green ordinary PR.
- **Routine render:** after W3, M2 routine render occupancy is zero unless an operator explicitly selects break-glass Mac fallback.
- **M1 safety:** unsafe disk/resource state makes the listener unavailable; it does not run anyway and hope.
- **Dead labels:** a scheduled/default capability with zero live eligible runners is an incident, not a normal queue state.
- **Degraded capacity:** queue optional work rather than silently stealing the protected M2 production plane.
- **No false completion:** configuration is not acceptance; each cutover needs a real job through the real route and its visible/machine consumer.

## 8. Explicit non-goals

M0–W5 do not redesign collectors or intelligence logic; alter signal/rank/trade authority; move ordinary PR CI to self-hosted machines; make the repository private; buy hardware; create another lifecycle store or runner scheduler; or solve the separate hosted `ci-plan` checkout/materialization problem.

## 9. Exact next action

Merge M0 only after its corrected exact head is green. Then execute W1-A: land the read-only hosted merge-control environment canary, prove it three times, and only then consider the W1-B route cutover. W2/W3 host work may prepare in parallel only while it remains diagnostic and changes no production/default labels.