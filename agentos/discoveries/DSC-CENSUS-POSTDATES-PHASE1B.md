---
key: CENSUS-POSTDATES-PHASE1B
claim: >
  The Executive OS Phase 0 census merged at 2026-08-11 21:01, which postdates Phase 1A and 1B,
  so its §6 non-goals are the current governing word rather than a superseded pre-build plan.
falsifier: >
  git log -1 --format=%ai -- research/EXECUTIVE_OS_PHASE0_CENSUS.md (Macro) compared with
  git log --format=%ai in the phase1b worktree — an earlier census timestamp disproves this.
so_what: >
  A session designing anything Executive-OS-adjacent must treat census §6 as binding and not
  assume the shipped Phase 1A/1B code supersedes it. Specifically: no second control plane, no
  worker/session tracking service, no new schedulers or queues, no auto-arming authority.
kind: constraint
verified_at: 2026-08-12
verified_by: "census #5356 at 2026-08-11 21:01:07 -0700; phase1b commits at 11:02, 13:27, 13:38 same day; phase1c-A at 2026-08-12 03:53"
scope: [macro, mastermind, "WS:AGENT-OS"]
confidence: verified
---

## Detail

Timeline, all verified by git log this session:

| When (local) | What |
|---|---|
| 2026-08-11 11:02 | Phase 1A runtime proof (#20) |
| 2026-08-11 13:27 | Phase 1B strategic state + worker contract (#21) |
| 2026-08-11 13:38 | Phase 1B durable Codex worker core |
| **2026-08-11 21:01** | **Phase 0 census merged (#5356)** |
| 2026-08-12 03:53 | Phase 1C-A secure launchd supervisor (#25) |

The ordering matters because the census reads as a pre-build planning document but is not one.

## Tension worth noting, not resolved here

Phase 1B shipped a durable SQLite job queue with lease tokens, and census §6.4 forbids "new
schedulers, queues, or buses". These are reconcilable — §6.4 is about org-level work dispatch,
while executive_runtime.py is per-process lifecycle on one machine — but the tension is real
and belongs to the Executive OS workstream to rule on, not to Agent OS.
