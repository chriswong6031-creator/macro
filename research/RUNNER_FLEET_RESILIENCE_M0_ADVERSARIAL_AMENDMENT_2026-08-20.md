# Runner Fleet Resilience M0 — adversarial architecture amendment

**Date:** 2026-08-20  
**Authority:** Sol adversarial review before M0 acceptance  
**Amends:** `research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md`  
**Workstream:** `WS:RUNNER-FLEET-RESILIENCE`

## Finding A1 — generic `macstudio` is a capability grant, not a capacity slot

The first architecture freeze correctly separated physical failure domains but made one unsafe inference: it proposed restoring the generic `macstudio` label to one guarded M1 listener as the first production-capacity step.

That is too broad.

GitHub label routing is positive matching. Adding `macstudio` does not mean “give the M1 one nightly job.” It makes the M1 eligible for **every current workflow job whose route contains `macstudio`**, including jobs added since the historical M1 audit. The M1 Max is 10 cores / 32 GB; the M2 Ultra is 24 cores / 192 GB. Historical evidence that `mac-builder-1/2` once ran collect/engine is not a current resource/capability proof for the whole `macstudio` consumer set.

The same mechanism behind the 2026-08-20 incident would therefore be repeated in a new form: a label intended as “extra capacity” would silently grant an entire workload class to hardware with a materially different envelope.

## Binding replacement

The canonical freeze has now been rewritten to incorporate this ruling directly. W4 therefore means:

1. Before any M1 production routing, enumerate every current literal/dynamic consumer of the proposed capability and record execution wall, memory class, local-store needs, architecture/OS assumptions, secrets/tool requirements, and current M1 compatibility evidence.
2. The first production admission uses an **existing capability-specific M1 route**, not generic `macstudio`:
   - `m1-nightly` for one explicitly selected, measured-safe production lane; and/or
   - `theta-m1` only on the real store-bearing listener after the Theta/store probe and existing probe-only laws pass.
3. The production workflow is modified narrowly so only that selected job can target the M1 capability. No expression may silently widen other `macstudio` consumers onto it.
4. `codex` remains separate and returns only after its host-local CLI/auth/runtime proof.
5. Generic `macstudio` on the M1 is **not authorized by W4**. It requires a later Sol decision after the full consumer/resource census demonstrates that broad eligibility is lawful and useful.
6. A second M1 production lane is likewise a measured follow-up, not implied by three diagnostic listener processes being online.

The PC remains the default target for routine full rendering after W3. The M1 is not a render spillway.

## Why this amendment matters

It preserves the objective—recover owned compute and create a physically independent production plane—while applying the program's core law consistently: **routing authority must match measured capability, not the number of listener processes.**

It also reuses the labels already introduced by the Wave B/C runner substrate instead of inventing a second M1 scheduling vocabulary.

## No other M0 ruling changes

W1 hosted merge-control separation, W2 guarded diagnostic restoration, W3 PC render cutover, W5 live fleet observation/M2 role retirement, and W6 nightly critical-path work remain unchanged.

This document remains the provenance record of the adversarial correction. The canonical architecture freeze and Agent OS workstream now contain the corrected rule directly, so there is no longer a conflicting live instruction.