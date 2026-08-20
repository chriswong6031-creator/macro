# Runner Fleet Resilience M0 — adversarial architecture amendment

**Date:** 2026-08-20  
**Authority:** Sol adversarial review before M0 acceptance  
**Amends:** `research/RUNNER_FLEET_RESILIENCE_ARCHITECTURE_FREEZE_2026-08-20.md`  
**Workstream:** `WS:RUNNER-FLEET-RESILIENCE`

## Finding A1 — generic `macstudio` is a capability grant, not a capacity slot

The first architecture freeze correctly separated physical failure domains but made one
unsafe inference in §4.3 Stage B and §6 W4: it proposed restoring the generic
`macstudio` label to one guarded M1 listener as the first production-capacity step.

That is too broad.

GitHub label routing is positive matching. Adding `macstudio` does not mean “give the M1
one nightly job.” It makes the M1 eligible for **every current workflow job whose route
contains `macstudio`**, including jobs added since the historical M1 audit. The M1 Max is
10 cores / 32 GB; the M2 Ultra is 24 cores / 192 GB. Historical evidence that
`mac-builder-1/2` once ran collect/engine is not a current resource/capability proof for
the whole `macstudio` consumer set.

The same mechanism behind the 2026-08-20 incident would therefore be repeated in a new
form: a label intended as “extra capacity” would silently grant an entire workload class
to hardware with a materially different envelope.

## Binding replacement for §4.3 Stage B

Replace the original Stage B bullets with:

**Stage B — capability-specific production after soak:**

1. Before any M1 production routing, enumerate every current literal/dynamic consumer of
   `macstudio` and record its execution wall, peak RSS/memory class, local-store needs,
   architecture/OS assumptions, secrets/tool requirements, and whether the job has ever
   run successfully on the M1-class host under its current implementation.
2. The first production admission uses an **existing capability-specific M1 label**, not
   generic `macstudio`:
   - `m1-nightly` for one explicitly selected, measured-safe production lane; and/or
   - `theta-m1` only on the real store-bearing listener after the Theta/store probe and
     existing probe-only laws pass.
3. The production workflow is modified narrowly so only that selected job can target the
   M1 capability. No expression may silently widen other `macstudio` consumers onto it.
4. `codex` remains separate and returns only after its host-local CLI/auth/runtime proof.
5. Generic `macstudio` on the M1 is **not authorized by W4**. It requires a later Sol
   decision after the full consumer/resource census demonstrates that broad eligibility is
   lawful and useful.
6. A second M1 production lane is likewise a measured follow-up, not implied by three
   diagnostic listener processes being online.

The PC remains the default target for routine full rendering after W3. The M1 is not a
render spillway in this amendment.

## Binding replacement for §6 W4

**Mission:** return one independently useful M1 production capability without granting the
M1 the whole M2 production workload class.

**Sequence:**

1. Complete the `macstudio` consumer/resource census described above.
2. Rank candidate lanes by user/machine value unlocked per unit of M1-specific risk.
3. Select exactly one lane whose current requirements fit the guarded M1 envelope.
4. Route it using `m1-nightly` (or restore `theta-m1` for the store-bound lane) with an
   explicit workflow change and test that no other production job can match the route.
5. Run one natural production occurrence while the M2 executes sibling work.
6. Accept only if the M1 lane completes with no disk-guard refusal, ENOSPC, memory pressure,
   store mismatch, or materially worse data/product outcome.

**Stop condition:** if the census cannot identify a bounded safe lane, W4 stops. Do not
fall back to adding `macstudio` broadly just to make the M1 appear utilized.

## Why this amendment is stronger than the original

It preserves the original objective—recover owned compute and create a physically
independent production plane—while applying the program's own core law consistently:
**routing authority must match measured capability, not the number of listener processes.**

It also reuses the labels already introduced by the Wave B/C runner substrate instead of
inventing a second M1 scheduling vocabulary.

## No other M0 ruling changes

W1 hosted merge-control separation, W2 guarded diagnostic restoration, W3 PC render
cutover, W5 live fleet observation/M2 role retirement, and W6 nightly critical-path work
remain unchanged.

This amendment is binding over the conflicting generic-`macstudio` sentences in the
original freeze. The Agent OS workstream has been updated to encode this amended W4 as the
machine-readable next-action law.