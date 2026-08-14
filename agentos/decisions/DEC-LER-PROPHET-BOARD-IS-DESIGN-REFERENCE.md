---
key: LER-PROPHET-BOARD-IS-DESIGN-REFERENCE
question: >
  What visual language does entry_radar.html use — a bespoke new design, or an existing
  house surface as reference?
answer: >
  The new Prophet Board is the direct design reference. Live Entry Radar is built as a
  sister product in that exact card/layout language — reference artifacts
  templates/_prophet_card.html.j2 + templates/_prophet_receipts.html.j2 and the
  reference-integrity evidence chain research/reference_integrity/prophet-board-5514-* —
  with ONLY the information architecture changed. PR-8 pins against the then-current
  R4-resolved reference (R3 verdict was REVISE; R4 closure is PR #5560); known
  R3/R4-flagged defects are not inherited; Prophet's seven-cell plan lifecycle and product
  semantics are not inherited; the Radar reference itself still runs the RIG process
  before production migration.
rationale: >
  Direct operator directive (2026-08-13): "Take yesterday's new Prophet Board as the
  direct design reference. Live Entry Radar should look like a sister product built from
  that exact card/layout language, with only the information architecture changed." This
  supersedes the commissioning handoff's softer "reuse the visual DNA, don't treat the
  unapproved reference as constitutional" stance: the card/layout language is now binding,
  while defect non-inheritance and RIG review are retained from the handoff.
alternatives:
  - option: Bespoke new visual language for Radar
    why_not: Rejected by the operator directive; also violates the design-system archetype law.
  - option: Freeze on the R3 reference as-is, defects included
    why_not: >
      R3's formal verdict was REVISE; inheriting known defects into a new surface is
      exactly what the handoff forbids.
alternatives_rejected_note: >
  "Sister product" binds card anatomy, layout grammar, density, and component vocabulary —
  not Prophet's information model. Lanes, lifecycle vocabulary, provisional-bar visual
  language, and freshness semantics are Radar's own (contract §13–§14).
evidence:
  - "Operator directive in-session 2026-08-13 (quoted verbatim in research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §14)"
  - "templates/_prophet_card.html.j2, templates/_prophet_receipts.html.j2 — the card language partials (included from dashboard.html.j2 and intl boards)"
  - "research/reference_integrity/prophet-board-5514-r3/evidence/r3_6ad6b51/DESIGN_NOTES.md — R3 evidence chain home"
affects: ["templates/entry_radar.html.j2", "site/entry_radar.html", "mockups/refs/entry_radar/"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-13
---

## Grounds

Directive arrived mid-session during PR-0 orchestration, while the Prophet Board R4 cycle
(PR #5560) was still open. Binding consequence for sequencing: backend PRs (1–5) do not
wait on R4; PR-8 resolves "then-current R4-resolved reference" at its own start date.

## What would reopen this

A later operator design directive, or the Prophet Board reference failing its own RIG
closure in a way that leaves no resolved reference to pin (PR-8 would then escalate rather
than improvise).
