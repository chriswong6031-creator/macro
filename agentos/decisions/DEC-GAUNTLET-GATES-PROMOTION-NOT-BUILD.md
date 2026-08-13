---
key: GAUNTLET-GATES-PROMOTION-NOT-BUILD
question: >
  Does the statistical gauntlet (pre-registered gates, held-out proof) gate BUILDING
  context/data/detection/tagging infrastructure — or only PROMOTION to authority
  (rank, size, gate)?
answer: >
  Promotion only. Display-tier infrastructure ships freely: a null result NEVER blocks
  building or accrual. A factor that is null as a STANDALONE signal is retained as a
  confluence input — non-standalone ≠ worthless. A kill closes the specific construction
  tested, never the search space ("not found yet" ≠ "does not exist"). The gauntlet
  applies at the moment a signal is promoted to authority: pre-registered gates, nulls
  printed rather than hidden, and the word "validated" in user-facing text is
  CI-enforced. LLMs may only de-escalate calibrated keys — never originate signals,
  scores, or escalations.
rationale: >
  The org's fundamental goal is context accrual: infrastructure that observes, tags, and
  stores reality has value independent of any single signal's current significance,
  because it is the substrate later rankers are found IN. Gating builds on significance
  would stop the accrual that makes any future ranker findable, and would convert every
  first-construction null into a prematurely closed search space. Authority is where an
  unvalidated claim does damage — sizing, ranking, gating, and user-facing "validated"
  language — so that is where the gauntlet sits. The two failure modes this splits
  apart: blocked accrual (gauntlet too early) and laundered authority (gauntlet absent).
alternatives:
  - option: Gauntlet as a build gate (validate before building anything)
    why_not: >
      Nulls would block the context accrual that is the point; a single null on the
      first construction would close a search space the ore law says to keep mapping.
  - option: No gauntlet anywhere (ship any signal at any tier)
    why_not: >
      Unvalidated authority misleads sizing and gating where users act on it; the CI
      guard on the word "validated" exists because that language leaked user-facing.
evidence:
  - "Macro CLAUDE.md §House laws — Epistemics (gauntlet = PROMOTION gate, NOT a build gate); law entered CLAUDE.md 2026-07-08 (git log -S)"
  - "scripts/check_validated_claims.py — CI enforcement of user-facing 'validated'"
  - "research/DO_NOT_REBUILD.md — kill rows name specific constructions, not topics, consistent with 'kill closes the construction'"
affects: ["engine/**", "signal promotion practice fleet-wide", "user-facing stat copy"]
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-07-08
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1). Dated to the law's entry into `CLAUDE.md`
(git-derived). Attribution: standing epistemics law with no single minting quote in the
prose → coo-fable. Reversibility is `costly` because the display-vs-authority boundary
is load-bearing across engine surfaces and user copy — moving the gauntlet earlier would
strand display-tier organs that were legitimately built ungated.

## What would reopen this

Evidence that display-tier surfaces are being READ as authority by users despite tiering
(the boundary failing socially rather than technically), or a promotion incident where
the gauntlet passed a signal the coverage pass should have caught — see
`DEC:CONCLUSIONS-NEED-A-COVERAGE-PASS`, which was added for exactly that class.
