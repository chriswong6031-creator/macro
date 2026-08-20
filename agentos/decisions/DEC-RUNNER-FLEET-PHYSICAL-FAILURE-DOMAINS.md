---
key: RUNNER-FLEET-PHYSICAL-FAILURE-DOMAINS
question: >
  Should Mastermind keep treating disjoint GitHub runner labels on the same physical
  host as independent capacity for production, render, and merge-control scheduling?
answer: >
  No. Physical hosts are the capacity and failure-domain boundary. Merge control moves
  off the M2 Ultra after a hosted environment canary; default full render moves to the
  PC after render-linux recovery proof; the M1 returns only through the existing guarded
  canary before any production label is restored.
rationale: >
  The 2026-08-20 incident proved that label isolation does not isolate CPU, memory,
  filesystem, SSD, Git object traffic, or host scheduling: the two-runner macstudio pool
  was starved for about four hours while mac-builder-light performed multi-hour render
  work and mac-builder-5 cycled production jobs, with one-minute Asia gate jobs waiting
  15-58 minutes. The same physical M2 also carries merge-control and the operator/session
  worktree estate, so logical isolation leaves the shipping control plane inside the
  production workload's failure domain. Existing M1 and PC hardware is sufficient but
  disconnected or under-routed; restoring and separating it is lower-risk than buying
  compute or adding more listener processes to the M2.
alternatives:
  - option: Keep current routing and add more runner processes on the M2 Ultra
    why_not: >
      More listeners increase logical slots without adding physical CPU, memory, SSD,
      filesystem, or Git-I/O capacity, and therefore amplify the same contention class.
  - option: Immediately restore the M1's historical macstudio/codex/theta-m1 labels
    why_not: >
      The M1 fleet died after ENOSPC and its old registrations include stale identity.
      The repository already defines guarded launchd recovery and a no-production-label
      canary specifically so host recovery cannot silently change production routing.
  - option: Buy another machine before changing routing
    why_not: >
      The fleet audit found sufficient existing compute: the PC proved render capability
      and the M1 historically ran nightly work. Current binding failures are service
      recovery, routing, and physical failure-domain mixing rather than raw hardware.
  - option: Move every workload to GitHub-hosted runners
    why_not: >
      PR proof/control workloads are portable and should use hosted capacity, but
      production collectors and store-bound lanes depend on host-local data, credentials,
      or macOS capabilities. The architecture separates portable control from host-bound
      production instead of pretending all workloads are fungible.
evidence:
  - "PR #6089: macstudio pool starved ~4h; gate jobs queued 15-58m before execution."
  - ".github/runner-policy.yml: render-heavy and macstudio share mac-builder-light; merge-control is another listener on the same M2 physical host."
  - "research/PRIVATE_REPO_RUNNER_STORAGE_ALLOCATION_AUDIT_2026_08_14.md: M1 services dead after ENOSPC; PC four-listener render capacity proven; BUY NOTHING verdict."
  - "docs/CI_SELFHOSTED_WAVE_BC_RUNBOOK.md: guarded M1 return and PC isolation/canary contracts already exist."
  - ".github/workflows/render.yml: scope=all render measured ~81m on pc-render-1; render default currently render-heavy."
  - ".github/workflows/engine-render.yml: render-linux is already the default express-engine route."
affects:
  - WS:RUNNER-FLEET-RESILIENCE
  - WS:CI-MERGE-CONTROL-PLANE
  - .github/runner-policy.yml
  - .github/workflows/merge-on-green.yml
  - .github/workflows/render.yml
  - .github/workflows/engine-render.yml
  - ops/runner-host/**
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Operating law

A runner process is not a failure domain. Capacity planning, queue SLOs, and admission
must be reasoned about at the physical-host level first and runner-label level second.

The immediate consequence is a four-plane topology:

- **GitHub-hosted:** PR CI, fences, integration baseline, merge-control, watchdogs.
- **PC/WSL:** default full render and engine-render after live recovery proof.
- **M1 Max:** guarded production/store capability restored in bounded stages.
- **M2 Ultra:** authoritative production/break-glass Mac compute; no routine heavy render
  and no merge arbiter after their respective cutovers.

This decision does not itself change runner labels or workflow routing. Each cutover needs
its own proof wave and rollback.