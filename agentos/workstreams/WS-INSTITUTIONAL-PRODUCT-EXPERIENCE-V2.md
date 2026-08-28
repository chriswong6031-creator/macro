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
    # REVISE record followed through #6309/#6313. The branch-side later R3B.1
    # verdict amendments were finally ratified over the older #6313 squash by the
    # explicit F2 ruling inside merged #6337.
  - id: R3B.2
    title: Final surgical closure + four fresh final critics
    status: done
    pr: 6337
    depends_on: [R3B.1]
    # COMPLETED AND MERGED as merge 8b303a58e8c0b807ef34d1913c4cacf5bb346e2d
    # (exact approved head f400e8b4df4d05434b74b8d50dd7e3ae37405342; Sol final
    # ruling issuecomment 5404196829; HOLD-release issuecomment 5404462128; fences
    # run 32801298636 success; semantic CI run 32801298582 success). Sol final
    # design-authority ruling: APPROVE_WITH_CONDITIONS — reference law only, no
    # production migration, no R3C authorization. F1 (top-level artifact_sha mirror
    # on the Visual/Taste receipt, reviewer original preserved) and F2 (branch-side
    # R3B.1 verdict amendments supersede the older #6313 squash) both closed inside
    # the merge. Four fresh final critic receipts durable under
    # research/reference_integrity/mastermind-xpv2-sector-r3b-2/reviews/;
    # verdict.yml + approval.yml landed; manifest status approved; candidate sha256
    # 4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c unchanged.
    # Five carried conditions, all R3C-owned: R3C-HEATMAP-LEGIBILITY (colour-field
    # legibility remains UNMEASURED, never PASS), R3C-AUTH-PREMIUM, R3C-TIME-MACHINE,
    # R3C-VALIDATED-21D, R3C-NO-UNSUPPORTED-INVENTION. MA2-001 refuted, not carried.
next_action: >
  Take no XPV2 execution — the declared reference objective is complete and R3C is
  explicitly not authorized. If and when the Chairman/Sol authorizes a successor wave,
  open it as a fresh commission via COMMISSION_WAVE (CONTINUATION_DELTA against merged
  #6337, pickup 8b303a58e8c0b807ef34d1913c4cacf5bb346e2d) with the five carried
  R3C-owned conditions as its acceptance floor; until that authorization exists, do not
  treat those conditions as open executable work.
do_not_redo:
  - "Redispatch R3B / R3B_HANDOFF_DRAFT.md, redo R3B.1, or redo F1/F2 — all completed and ratified through merged #6337 (full protected list in the 2026-08-25 handoff)."
  - "Rerun the four final R3B.2 critics absent a named receipt-invalidating event — receipts are durable under research/reference_integrity/mastermind-xpv2-sector-r3b-2/reviews/."
  - "Start R3C or surface the five carried R3C-owned conditions as open work — R3C implementation is explicitly not authorized."
---

# XPV2 — institutional product experience v2

The program exists because the Turn-3 R2 Sector Central mockup looked better but mixed or
invented authority, lost working journeys, and could not prove access/state behavior — all
four independent critics returned BLOCK (`research/reference_integrity/mastermind-xpv2-turn3-r2/README.md`).
R3A (PR #6122) built the binding substrate that makes a repeat structurally hard: every
R3-visible field is bound to its producer, path/key, authority class, clock, access tier,
destination, and null/stale behavior, and 59 attack tests red anyone who changes what those
mean.

R3B, R3B.1, and R3B.2 are completed reference cycles. The program's declared objective is
COMPLETE: Sol issued the final design-authority ruling APPROVE_WITH_CONDITIONS on the
corrected R3B.2 Sector Central reference, and canonical carrier #6337 merged as
`8b303a58e8c0b807ef34d1913c4cacf5bb346e2d` (2026-08-24, final head `f400e8b4df4d`).
Reference law only — the approval is NOT production deployment, NOT a production migration,
and NOT R3C authorization. The frozen approved candidate is sha256
`4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c`.

Reference-law completion must never be projected as production completion: the Sector
Central product capability remains SPEC_ONLY with respect to this reference — no production
template, producer, route, registry, deployment, or user journey was migrated by #6337.

Five carried conditions ride with the approval, all R3C-owned and non-executable until an
explicit R3C authorization exists — a condition existing does not make its work OPEN
(Continuation Delta Law): R3C-HEATMAP-LEGIBILITY (colour-field legibility remains UNMEASURED,
never PASS until measured on the real path); R3C-AUTH-PREMIUM (real auth plus
`/premiumdata/sector_central.json` hydration and failure-state proof); R3C-TIME-MACHINE
(real Time Machine end-to-end proof); R3C-VALIDATED-21D (resolve production-owned
Validated/unproven-21d semantics while preserving the narrower 5d/context-only disclosure);
R3C-NO-UNSUPPORTED-INVENTION (no invented Baskets/correction UI or local
rank/state/score/producer truth). MA2-001 was refuted and is not carried.

Authority precedence remains: current production producers/payload contracts > current
user-facing production behavior > durable critic/verdict records > Design Doctrine / Master
Product Design System / RIG > the active Sol adjudication. Rejected/superseded reference HTML
is evidence, never source authority.

Carrier history: #6337 was canonical and is now merged; #6336 was explicitly superseded and
closed without merge. The F2 ruling inside #6337 ratified the branch-side later R3B.1 verdict
amendments over the older #6313 squash — that resolution is settled history, not an open
question. The 2026-08-21 handoff and the pre-#6337 revisions of this record are preserved
history: they described real state when written and are superseded, not rewritten.

Verified_by for terminal state: GitHub #6197/#6248/#6313/#6337 exact PR records; exact
approved head `f400e8b4df4d05434b74b8d50dd7e3ae37405342`; Sol final ruling issuecomment
`5404196829`; HOLD-release issuecomment `5404462128`; fences run `32801298636` success;
semantic CI run `32801298582` success; merge commit
`8b303a58e8c0b807ef34d1913c4cacf5bb346e2d` (its message carries the full gate receipts: RIG
clean, --evaluate 0 findings approvable-shape, --mandate exactly the required 12 obligations,
--selftest passed, verify_reference.py 23/23 ALL GREEN, R3A floor 59 passed, zero
production-path diff, 22 pull_request checks green); reconciliation lineage #6388
(merge `4faf00a44510a41f968a272a6fae5d8acb7890be`) then this record.
