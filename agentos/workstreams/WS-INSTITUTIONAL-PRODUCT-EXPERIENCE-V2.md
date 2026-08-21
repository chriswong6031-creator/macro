---
key: INSTITUTIONAL-PRODUCT-EXPERIENCE-V2
title: XPV2 — institutional product experience v2 (LENS + Sector Central reference program)
objective: >
  Produce approved, production-truth-bound visual references for the XPV2 surfaces
  (Mastermind LENS, Sector Central US) that preserve every current capability and never
  invent authority. Done = a Reference Integrity Gate-approved R3 Sector Central reference
  built on the R3A binding pack with zero guessed actions, scores, rows, routes, access
  behaviors, clocks, or failure states.
status: active
program: sector-rotation-intelligence
repos: [macro]
owner: coo-fable
class: design
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - research/reference_integrity/mastermind-xpv2-turn3-r2/
  - research/reference_integrity/mastermind-xpv2-sector-r3/
  - tests/test_xpv2_sector_r3_fixture.py
waves:
  - id: R2
    title: Turn-3 R2 freeze candidates + four independent critic reviews (all BLOCK)
    status: done
    # Frozen evidence bundle research/reference_integrity/mastermind-xpv2-turn3-r2/
    # (artifact commit da83976ece01). Every critic returned BLOCK; the bundle stops
    # before verdict.yml/approval.yml by design. R2 HTML is frozen evidence, never
    # source authority.
  - id: R3A
    title: Sector Central authority + capability binding pack (archaeology, fixture, contracts, attack tests)
    status: done
    pr: 6122
    depends_on: [R2]
    # MERGED 2026-08-20T20:16:40Z, merge commit f4305a4485f6df061f3a55ca6f1b0e3e53c06f66
    # (gh pr view 6122 --json state,mergedAt,mergeCommit). Six archaeology dossiers,
    # ADJUDICATIONS.md A1-A10 frozen rulings, 92-capability disposition ledger
    # (90 RETAIN / 2 BLOCKED_DATA), producer binding matrix, 18-receipt frozen fixture,
    # routing + access/hydration contracts, R3 design brief, 59-test attack suite in the
    # gate:code reference-integrity CI job. Opus adversarial review PARTIAL -> 4 BLOCKING
    # findings fixed with mutation-fire proofs before merge.
  - id: R3B
    title: R3 Sector Central design reference (six views) on the frozen R3A substrate
    status: todo
    depends_on: [R3A]
    next_action: >
      Dispatch research/reference_integrity/mastermind-xpv2-sector-r3/R3B_HANDOFF_DRAFT.md
      (marked DRAFT — DO NOT START) to a design session after commissioning review.
next_action: >
  Review and dispatch R3B_HANDOFF_DRAFT.md to a fresh design session; the R3A stop
  condition forbade starting R3B in the R3A wave.
---

# XPV2 — institutional product experience v2

The program exists because the Turn-3 R2 Sector Central mockup looked better but mixed or
invented authority, lost working journeys, and could not prove access/state behavior — all
four independent critics returned BLOCK (`research/reference_integrity/mastermind-xpv2-turn3-r2/README.md`).
R3A (PR #6122) built the binding substrate that makes a repeat structurally hard: every
R3-visible field is bound to its producer, path/key, authority class, clock, access tier,
destination, and null/stale behavior, and 59 attack tests red anyone who changes what those
mean.

Authority precedence (frozen in the R3A pack): current production producers/payload
contracts > current user-facing production behavior > the R2 review bundle > Design
Doctrine / Master Product Design System / RIG > Turn-4 Sol adjudication. The rejected R2
candidate HTML is never source authority.

Key rulings live in `research/reference_integrity/mastermind-xpv2-sector-r3/ADJUDICATIONS.md`
(A1–A10). Notable: A2 refuted the commissioning handoff's own premise — Moving does NOT
bind `si_handoff.json` (five nightly artifacts do); Money is the view that binds it.

Verified_by for wave states: `gh pr view 6122 --json state,mergedAt,mergeCommit`;
`git ls-tree origin/main research/reference_integrity/mastermind-xpv2-sector-r3/`;
`python3 -m pytest tests/test_xpv2_sector_r3_fixture.py -q` (59 passed on the merged tree).
