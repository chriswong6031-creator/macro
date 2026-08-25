---
key: INSTITUTIONAL-PRODUCT-EXPERIENCE-V2
title: XPV2 — institutional product experience v2 (LENS + Sector Central reference program)
objective: >
  Produce approved, production-truth-bound visual references for the XPV2 surfaces
  (Mastermind LENS, Sector Central US) that preserve every current capability and never
  invent authority. Done = a Reference Integrity Gate-approved R3 Sector Central reference
  built on the R3A binding pack with zero guessed actions, scores, rows, routes, access
  behaviors, clocks, or failure states.
status: done
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
    # R3B.2 carrier narrowed/translated the predecessor mandate and were explicitly
    # ratified to supersede the older #6313 squash for this continuation.
  - id: R3B.2
    title: Final surgical closure + four fresh final critics
    status: done
    pr: 6337
    depends_on: [R3B.1]
    next_action: >
      None. Sol issued APPROVE_WITH_CONDITIONS for REFERENCE LAW ONLY on PR #6337
      issuecomment 5404196829. The sanitized exact head
      f400e8b4df4d05434b74b8d50dd7e3ae37405342 passed fences 32801298636 and
      semantic CI 32801298582, then merged as
      8b303a58e8c0b807ef34d1913c4cacf5bb346e2d on 2026-08-25. Frozen candidate
      sha256 4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c
      remains the approved reference identity. This is reference-law completion only;
      no production migration or R3C authority follows from it.
next_action: >
  This bounded XPV2 design/reference workstream is complete under its own declared
  completion law. Preserve the approved R3B.2 reference and its five production-migration
  conditions. Do not start R3C, mutate production, or reopen this completed design identity
  implicitly. Any Sector Central production migration requires a fresh explicit Chairman/Sol
  commission, current production archaeology, a separately bounded carrier, and proof against
  the five carried conditions.
---

# XPV2 — institutional product experience v2

The program exists because the Turn-3 R2 Sector Central mockup looked better but mixed or
invented authority, lost working journeys, and could not prove access/state behavior — all
four independent critics returned BLOCK (`research/reference_integrity/mastermind-xpv2-turn3-r2/README.md`).
R3A (PR #6122) built the binding substrate that makes a repeat structurally hard: every
R3-visible field is bound to its producer, path/key, authority class, clock, access tier,
destination, and null/stale behavior, and 59 attack tests red anyone who changes what those
mean.

R3B and R3B.1 are completed predecessor reference cycles. R3B.2 is also complete: Sol's final
design-authority verdict on PR #6337 is `APPROVE_WITH_CONDITIONS` for **REFERENCE LAW ONLY**,
and the exact approved head `f400e8b4df4d05434b74b8d50dd7e3ae37405342` merged as
`8b303a58e8c0b807ef34d1913c4cacf5bb346e2d` after hosted fences and semantic CI both passed.
The frozen R3B.2 candidate remains sha256
`4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c`.

The design/reference workstream is therefore `done`, but the actual Sector Central product
capability remains **SPEC_ONLY** with respect to this reference: no production template,
producer, route, registry, deployment, or user journey was migrated by #6337. Reference-law
completion must never be projected as production completion.

The five binding conditions that any future production-migration commission must carry are:

1. heatmap colour-field legibility remains **UNMEASURED**, never PASS until measured on the real path;
2. real auth plus `/premiumdata/sector_central.json` hydration and failure-state proof;
3. real Time Machine end-to-end proof;
4. resolve production-owned `Validated` / unproven 21d semantics while preserving the narrower
   5d/context-only disclosure; and
5. do not invent unsupported Baskets/correction UI or local rank/state/score/producer truth.

Authority precedence remains: current production producers/payload contracts > current
user-facing production behavior > durable critic/verdict/approval records > Design Doctrine /
Master Product Design System / RIG. Rejected/superseded reference HTML is evidence, never source
authority.

Carrier law is closed: #6337 was the sole R3B.2 carrier and is merged; #6336 is explicitly
superseded and closed without merge. F1 was ratified as a non-substantive top-level
`artifact_sha` mirror while preserving the original Visual/Taste receipt as evidence. F2 was
ratified so the later branch-side R3B.1 verdict amendments (`3a6638d2d15b` /
`da2df767af77` lineage) supersede the older #6313 squash for this continuation and lawfully
rode to main. Unrelated Government Revenue side-lineage was removed before the final hosted
proof.

Verified_by for terminal state: GitHub #6337 exact approved head
`f400e8b4df4d05434b74b8d50dd7e3ae37405342`; Sol final ruling issuecomment `5404196829`;
HOLD-release comment `5404462128`; fences run `32801298636` success; semantic CI run
`32801298582` success; merge `8b303a58e8c0b807ef34d1913c4cacf5bb346e2d`; Linear child
MAS-133 completed only after that canonical merge. No open R3C carrier existed at closeout.
