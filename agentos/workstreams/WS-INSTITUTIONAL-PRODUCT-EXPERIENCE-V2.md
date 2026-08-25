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
  - research/reference_integrity/mastermind-xpv2-sector-r3b-1/
  - research/reference_integrity/mastermind-xpv2-sector-r3b-2/
  - mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-2/
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
    # MERGED 2026-08-20T20:16:40Z, merge commit f4305a4485f6df061f3a55ca6f1b0e3e53c06f66.
    # Six archaeology dossiers, ADJUDICATIONS.md A1-A10, 92-capability disposition
    # ledger, producer binding matrix, 18-receipt frozen fixture, routing/access
    # contracts, R3 design brief, and 59-test attack floor.
  - id: R3B
    title: R3 Sector Central design reference (six views) on the frozen R3A substrate
    status: done
    pr: 6197
    depends_on: [R3A]
    # Frozen reference landed as merge f5b0094614b688e8b66552e35ac65d23656fbc64.
    # Reference-only; zero production-path migration. Fresh critic adjudication later
    # returned REVISE and commissioned R3B.1; therefore 'done' here means this bounded
    # predecessor cycle completed, not that XPV2 or production migration completed.
  - id: R3B.1
    title: Surgical successor correction + fresh final critic adjudication
    status: done
    pr: 6248
    depends_on: [R3B]
    # Successor reference `mastermind-xpv2-sector-r3b-1` landed as merge
    # 780cbcf6d2d2c7b32b87a4674929e1732e5ad036. Durable critic recovery and Sol
    # REVISE record followed through #6309/#6313. Later Sol S3 amendments on the
    # active R3B.2 branch narrowed/translated the predecessor mandate; those newer
    # amendments are part of the current #6337 conflict-resolution ruling and are
    # not silently replaced by the older #6313 squash.
  - id: R3B.2
    title: Final surgical closure + four fresh final critics
    status: in_progress
    pr: 6337
    depends_on: [R3B.1]
    next_action: >
      Sol reviews canonical carrier #6337 at head
      90ce21ac977209370b57b2ef1af7331cebb25861. Fresh critic receipts are durable,
      exact-head CI 32727024895 is green, candidate sha256
      4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c is frozen,
      and current-main drift through 2026-08-25 is nonmaterial to Sector Central/RIG.
      Before any approval/merge: (F1) normalize the Visual/Taste receipt by mirroring
      its already-bound identity.artifact_sha at the schema-required top level without
      changing critic judgment; (F2) explicitly ratify that the branch-side later R3B.1
      verdict amendments (3a6638d2d15b / da2df767af77 lineage) supersede the older
      #6313 squash for this continuation and may ride to main. Resolve the add/add
      conflict accordingly, re-run RIG + exact-head hosted CI on the resulting head,
      then issue the final Sol design-authority verdict. R3C remains unauthorized.
next_action: >
  Stay on canonical R3B.2 carrier #6337 only. Resolve F1/F2, reconcile it onto current
  main without changing the frozen candidate, re-run the reference/RIG/hosted gates,
  and return to Sol for the final design-authority verdict. Do not start R3C or mutate
  production. Superseded duplicate #6336 was closed without merge on 2026-08-24/25.
---

# XPV2 — institutional product experience v2

The program exists because the Turn-3 R2 Sector Central mockup looked better but mixed or
invented authority, lost working journeys, and could not prove access/state behavior — all
four independent critics returned BLOCK (`research/reference_integrity/mastermind-xpv2-turn3-r2/README.md`).
R3A (PR #6122) built the binding substrate that makes a repeat structurally hard: every
R3-visible field is bound to its producer, path/key, authority class, clock, access tier,
destination, and null/stale behavior, and 59 attack tests red anyone who changes what those
mean.

R3B and R3B.1 are completed predecessor reference cycles, not production completion. The
current live organizational object is R3B.2 on Macro #6337. It is reference-only and remains
`SPEC_ONLY` / `in_review`: the final four critic receipts exist, but no final `approval.yml`,
no production migration, and no R3C authority exist yet. The frozen R3B.2 candidate is
sha256 `4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c`.

Authority precedence remains: current production producers/payload contracts > current
user-facing production behavior > durable critic/verdict records > Design Doctrine / Master
Product Design System / RIG > the active Sol adjudication. Rejected/superseded reference HTML
is evidence, never source authority.

Current carrier law: #6337 is canonical. #6336 is explicitly superseded and closed without
merge. The branch-side R3B.1 verdict on #6337 contains later Sol-authorized amendments than
the older #6313 squash on main; resolving the conflict by blindly taking main would regress
the ratified continuation shape and is forbidden pending the explicit F2 ruling recorded
above.

Verified_by for current state: GitHub #6197/#6248/#6313/#6337 exact PR records; #6337
exact-head CI run 32727024895; current-main drift comparison from `ba44b49b0d97` through
`0c0c0f491832` showing no material R3B.2/Sector Central/RIG/design-law collision; and the
R3B.2 durability return persisted on #6337.
