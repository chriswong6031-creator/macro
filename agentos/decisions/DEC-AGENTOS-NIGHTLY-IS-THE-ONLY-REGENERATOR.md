---
key: AGENTOS-NIGHTLY-IS-THE-ONLY-REGENERATOR
question: >
  Who regenerates data/governance/agent_os_state.json and docs/AGENT_OS_STATE.md —
  the nightly, or every PR that touches a record?
answer: >
  The nightly, and only the nightly. There is no drift guard, no CI regeneration check,
  and no requirement that a record-touching PR commit a regenerated view. The artifacts
  may therefore be up to ~24h stale, and the generated header prints the age of every
  input so a reader can see exactly how stale.
rationale: >
  Both writers cannot be right. Per-PR regeneration is fresher, but it makes two
  independent record edits collide on a SHARED generated file: two sessions each adding
  a workstream would each regenerate the whole state document, and the merge conflicts
  on a file neither session authored. That is precisely the shared-write failure
  invariant I2 (one writer per fact, one file per record) exists to prevent, and
  re-introducing it through the back door of a drift guard would be worse than the
  original, because the conflict would appear in CI on a file the author never opened.
  Nightly-only keeps exactly one writer. The cost is bounded and visible: the artifact
  is a VIEW, it is regenerable at any moment by hand with one command, and staleness is
  printed rather than hidden. The precedent is already load-bearing in this repo —
  docs/ACTIVE_BUILD_MAP.md and data/governance/active_builds.json are nightly-written by
  build_active_build_map.py in daily.yml, with no per-PR guard, for the same reason.
alternatives:
  - option: Per-PR regeneration enforced by a drift guard (the check_*.py --fix pattern)
    why_not: >
      Reintroduces the shared-write conflict I2 exists to prevent. Every record-touching
      PR would have to commit a regenerated shared document, so two concurrent record
      edits conflict on a file neither author wrote. It also makes a knowledge record's
      CI outcome depend on join inputs (active_builds age, worktree census) that the
      author does not control.
  - option: Both — nightly plus an on-demand per-PR refresh
    why_not: >
      Two writers for one fact. The nightly would silently revert a PR-time regeneration
      whenever the join inputs differed, which produces churn commits that look like
      real state changes.
  - option: Do not commit the artifacts at all; generate on demand only
    why_not: >
      Then the CEO view does not exist for anyone who has not run the command, and the
      human mirror cannot be linked to or read on GitHub. Committing a derived view with
      a DO-NOT-EDIT banner is the existing house pattern (ACTIVE_BUILD_MAP,
      MASTERMIND_SYSTEM_MAP).
evidence:
  - "research/MASTERMIND_AGENT_OS_ARCHITECTURE.md §2 I2 — one writer per fact, one file per record"
  - "scripts/build_active_build_map.py docstring — nightly-written, fail-open, advisory, no per-PR guard"
  - ".github/workflows/daily.yml — the `generate active build map` step this one is wired beside"
  - "scripts/agentos.py cmd_status — writes both artifacts, exits 0 unconditionally"
affects: [WS:AGENT-OS, "docs/AGENT_OS_STATE.md", "data/governance/agent_os_state.json"]
confidence: high
reversibility: easy
decided_by: opus-agentos-phase2-session
decided_at: 2026-08-12
---

## Grounds

Determinism and freshness were traded against each other explicitly. The generator is a
pure function of its inputs — proven by a byte-identity test over the records section —
so nothing is lost by regenerating less often except recency, and recency is exactly the
thing the artifact prints about itself.

The partition matters here. `generated_at`, `inputs.worktrees`,
`inputs.active_builds_age_hours` and parent `inputs.degraded` live in an envelope that is
excluded from the byte-identity comparison; workstream records, `needs_ceo`, warnings,
and the identity-sorted `agentos.readiness.v1` envelope are the pure part. Readiness
degradation is pure because it is restricted to invalid workstream authoring, never
volatile PR/P0/worktree joins. Without that split the test would need a frozen clock to
say anything at all, and a frozen clock would hide real nondeterminism in the records
themselves. The former `start_next` surface was retired by Phase 2b.

## What would reverse this

A measured case where a 24h-stale CEO view caused a wrong call that a fresher view would
have prevented. The fix then is a second nightly slot or an evening refresh — still one
writer — never a per-PR guard.
