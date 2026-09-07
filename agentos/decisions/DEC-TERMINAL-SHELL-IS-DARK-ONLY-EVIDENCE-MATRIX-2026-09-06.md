---
key: TERMINAL-SHELL-IS-DARK-ONLY-EVIDENCE-MATRIX-2026-09-06
type: decision
status: active
workstream: MARKET-OS
question: >
  The theme art-direction law (TP-0, 2026-08-27) requires every material UI packet to
  evidence BOTH a dark and a light treatment (dark/light x EN/ZH x 1440/390). The Terminal
  shell (charting-app/terminal) is dark-only by construction: terminal/app/globals.css
  ("Terminal is dark-only (see app/settings.css), so there is no light branch to carry") and
  terminal/app/settings.css carry no `[data-theme]` selector anywhere. Packet B-F08-3 (alerts
  cockpit, terminal#517) shipped a guarded light block that can never render. Does a Terminal
  packet owe the light half of the evidence matrix, and if not, what does it owe instead?
answer: >
  A Terminal-shell packet owes the DARK half only — dark x EN/ZH x 1440/390 — plus one
  explicit sentence in its PR body naming this record and stating that the light treatment
  is not applicable because the shell is dark-only by design. A packet may NOT invent a
  page-local light theme inside the dark shell (that is the third-header/local-material fork
  the design constitution forbids), and may NOT ship inert guarded light CSS as "evidence":
  such blocks are deleted, not kept. Every other half of the theme law stays binding in the
  Terminal: hierarchy, material depth, semantic colour, responsive composition and EN/ZH
  parity are judged as a DESIGN on the dark treatment, and functional browser success is
  still necessary but never sufficient. The exemption is scoped to the Terminal shell as it
  exists; it ends the day a Terminal-wide light theme program lands (a separate, explicitly
  commissioned program — not something a feature packet may start). Reversal is easy: a
  ratified Terminal light-theme program record supersedes this one automatically.
rationale: >
  The law exists to stop "token substitution" from passing as a light design. In a shell
  that has no light tokens and no theme switch, there is nothing to substitute and no user
  who can ever see a light treatment; demanding crops of an unreachable state produces either
  fabricated evidence or a permanently PARTIAL packet, and the reviewer of terminal#517
  correctly refused PASS on exactly that ground. Ratifying the dark-only fact for the
  Terminal keeps the evidence demand truthful (what a user can see) while keeping every
  judgment half of the law intact. Meta-CEO B (Claude3 seat, Chairman override 2026-09-06)
  takes the decision because F08's holdings-coupled surfaces are bound to the Terminal shell
  by the F08 architecture freeze and cannot move to the macro site to satisfy the matrix.
alternatives:
  - option: "Build a page-local light theme for /alerts so the matrix can be evidenced."
    why_not: "A local material fork inside a dark shell is precisely the third-header / local-resize failure the navigation and design constitution forbid; it would also be unreachable by any user control."
  - option: "Commission a Terminal-wide light theme now."
    why_not: "A shell-wide theme is a program (globals.css, observatory.css, every workspace), not a feature packet; it is not in the Market Ontology charter and would stall every Terminal-shell packet behind it."
  - option: "Keep the guarded light CSS in the packet as a forward-looking hedge."
    why_not: "Inert CSS that has never rendered is unreviewable and reads as evidence it is not; when a light program lands it will design the treatment, not inherit a guess."
evidence:
  - "terminal/app/globals.css:1253 and terminal/app/settings.css:32 on origin/master (charting-app): explicit dark-only comments; grep for '[data-theme' in terminal/app returns nothing (reviewer of terminal#517, 2026-09-06)"
  - "terminal#517 reviewer verdict 2026-09-06: light art direction cannot be evidenced in this repo; packet PARTIAL never PASS under TP-0 as written"
  - "research/MARKET_ONTOLOGY_F08_ARCHITECTURE_FREEZE_2026-09-05.md §9: holdings-coupled surfaces live in the Terminal shell"
affects:
  - "terminal#517 (B-F08-3) and every later Terminal-shell packet's evidence matrix and review standard"
  - "macro CLAUDE.md §Theme art direction is unchanged for the macro site (both treatments still owed there)"
confidence: high
reversibility: easy
decided_by: "Meta-CEO B (Claude3 seat), session 7cd4fae1-1ed9-41c2-adb4-1e5c6b0fbc5b, under DEC:CHAIRMAN-OVERRIDE-CLAUDE-META-CEO-REGIME-2026-09-06"
decided_at: 2026-09-06
review_by: 2026-12-06
related:
  - "DEC:CHAIRMAN-FRONTEND-PLAIN-LANGUAGE-LAW-2026-09-06"
  - "WS:MARKET-OS"
---

Terminal-shell packets evidence the dark treatment only (dark x EN/ZH x 1440/390) and say
so, citing this record. Every judgment half of the theme law still applies to that dark
treatment. No page-local light theme, no inert guarded light CSS. The exemption ends when a
separately commissioned Terminal-wide light theme program lands.
