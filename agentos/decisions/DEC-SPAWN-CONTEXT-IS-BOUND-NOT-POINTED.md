---
key: SPAWN-CONTEXT-IS-BOUND-NOT-POINTED
question: >
  When commissioning build work to a spawned, chipped, or cross-repo session, is a
  correct masterplan pointer plus correct model tiers sufficient context?
answer: >
  No. Quality does not travel by pointer — it must be BOUND into the commission:
  (1) acceptance gates INLINE in the spawn prompt, phrased "not done unless"; (2)
  reference images as COMMITTED files (`mockups/refs/<program>/`) with paths in the
  prompt, never prose descriptions of a look; (3) design-spec-first for flagship
  surfaces — exact markup/CSS pinned before builders assemble; (4) no child-agent
  self-merge of a flagship UI first pass — the PR and visual artifact return to the
  commissioning session; (5) masterplans for user-facing builds carry acceptance gates
  as §0, not buried mid-doc; (6) audit the target repo's CLAUDE/AGENTS laws before
  spawning — if it has no design/verification laws, fix that first; (7) the build
  surface follows the user FUNNEL, not the plumbing.
rationale: >
  Onboarding-flow postmortem, 2026-07-23: the flow shipped broken-and-ugly DESPITE a
  correct masterplan AND correct tiers (frontier main loop + Opus builders). The failure
  was context binding, not model quality — reference shots existed only as prose the
  spawned session could never see; acceptance gates sat at §6/§7 of a referenced doc the
  session skimmed; the target repo's agent laws were 5 lines of Next.js scaffold
  warnings; and the PR self-merged with no visual artifact, closing the review window.
  Each clause of the answer maps to one observed failure in that postmortem. The
  spawned-session context model makes this structural: a child starts with ONLY its
  prompt + the target repo's agent files, so anything not in those two places does not
  exist for it.
alternatives:
  - option: Masterplan pointer + tier upgrade (the arrangement that failed)
    why_not: >
      The postmortem case had a correct plan and top tiers and still shipped broken —
      tiering is not the quality lever, binding is.
  - option: Catch it in review after the child ships
    why_not: >
      The child self-merged; the review window never opened. The gate must live in the
      commission (no-self-merge + artifact-in-PR-body), not in hoped-for hindsight.
evidence:
  - "Macro CLAUDE.md §Spawn-handoff law (STANDING — onboarding postmortem 2026-07-23); section entered 2026-07-23 (git log -S)"
  - "charting-app terminal/AGENTS.md agent-laws block — '<!-- BEGIN:mastermind-agent-laws (added 2026-07-23 after the onboarding-flow postmortem) -->', seeded by its PR #173"
  - "mockups/refs/<program>/ committed-reference convention (Macro CLAUDE.md §Spawn-handoff law item 2)"
affects: ["CLAUDE.md", "research/*MASTERPLAN*.md", "mockups/refs/**"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-07-23
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1) from the standing spawn-handoff law, which was
written directly out of the 2026-07-23 postmortem; the Terminal repo's agent-laws block
carries the same date in its BEGIN marker, so both repos pin the same event.

## What would reopen this

A harness change that gives spawned sessions ambient access to the commissioning
session's artifacts (screenshots, open buffers) would relax clause 2's mechanism — but
not the principle: gates stay inline because pointers rot even when access exists.
