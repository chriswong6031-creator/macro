---
workstream: WS:LIVE-ENTRY-RADAR
session: cursor-entry-radar-w8-rig-9f9d
model: opus
ended_because: complete

mission: >
  W8 / PR-8: approved reference UX + Reference Integrity Gate package for
  entry_radar.html. Sister language of the current R4-resolved Prophet Board;
  Radar information architecture only. REFERENCE ONLY — no production UI.
  STOP after W8. Isolated reviewable PR; do not merge from this session.

state_before: >
  origin/main pinned at cc6f53f619f439683a4da7aa366843aef6079768 after fetch.
  W3 done (PR #5724). W8 was todo. No colliding open W8 PR. No production
  entry_radar.html.j2 or site/entry_radar.html on main. Prophet Board R4
  reference tree still d540f493a097cb37f3f91e4c7bc81a39b876d069 (PR #5560
  squash 168a9be006914441051cff393927ce465e39138e).

changed:
  - path: mockups/refs/entry_radar/
    what: "Founding reference tree — HTML/CSS/JS, synthetic fixtures, 24 crops,
      DESIGN_NOTES, inventories, data-to-UI map, W9 handoff, author critique,
      verify + 13-mutation battery, capture harness."
  - path: research/reference_integrity/entry-radar-w8/
    what: "RIG set status in_review, scope full, no predecessor (continuity
      omitted). No approval.yml / no APPROVE verdict — commissioning reviews."
  - path: tests/test_entry_radar_w8_rig.py
    what: "Pins the reference tree, forbids production paths, pins Prophet SHAs,
      runs verify.py and mutation_test.py."
  - path: .github/ci/legacy-jobs.yml
    what: "Adds test_entry_radar_w8_rig.py to the existing Radar pytest line."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W8 in_progress; next_action names the open review, not W9."

verified:
  - claim: "Pinned Prophet Board on origin/main is PR #5560 squash 168a9be0 / tree d540f493."
    command: "git rev-parse origin/main:mockups/refs/institutionalize/us_stocks && git log -1 --format=%H origin/main -- mockups/refs/institutionalize/us_stocks"
    result: "d540f493a097cb37f3f91e4c7bc81a39b876d069 ; 168a9be006914441051cff393927ce465e39138e"
  - claim: "Static RIG + 13/13 mutations green; no production Radar template."
    command: "python3 mockups/refs/entry_radar/tools/verify.py && python3 mockups/refs/entry_radar/tools/mutation_test.py && python3 -m pytest tests/test_entry_radar_w8_rig.py -q"
    result: "verify exit 0; 13/13 mutations caught; pytest passed"
  - claim: "RIG repo-mode accepts the in_review set (schema + continuity only)."
    command: "python3 scripts/check_reference_integrity.py"
    result: "exit 0; entry-radar-w8 present; 0 approved"
  - claim: "Agent OS records validate."
    command: "python3 scripts/agentos.py validate"
    result: "exit 0"
  - claim: "Diff is clean on Prophet engine paths and production Radar templates."
    command: "git diff --stat origin/main -- engine/prophet_ engine/entry_signal.py templates/entry_radar.html.j2 site/entry_radar.html"
    result: "empty"

unverified:
  - claim: "Quarantined independent Opus CRITIC_A / CRITIC_B two-pass receipts."
    what_would_verify: "Commissioning session runs the CRITIC_A / CRITIC_B templates against the frozen SHA and writes reviews/*.yml with independent_of_author: true."
  - claim: "Playwright visual checks in CI (local Playwright was green this session)."
    what_would_verify: "CI job or a commissioning `verify.py --url` on a served tree."

prs: [5737]

unresolved:
  - "Author-session critique is not an independent RIG receipt. Do not approve from this PR's author."
  - "W4 live fields, W6 Priority, and W7 Opportunity are not in this package and must not be invented to fill slots."

next_actions:
  - "Commissioning session: quarantined product + visual critics on PR #5737, then a design-authority verdict. Leave the PR open until that review. Do not arm merge-on-green unless house law is forced over the flagship-review hold."
  - "W9 is a separate commissioning after W4 + W6 + this reference is approved. Copy from W9_IMPLEMENTATION_HANDOFF.md only."
  - "W4 and W5 remain the next engine waves; they do not wait on W8 merge."

do_not_redo:
  - "Do not re-pin the Prophet Board from memory or from PR #5560's pre-squash SHA 9995603e — that blob is not on origin/main. Current pin is squash 168a9be0 / tree d540f493."
  - "Do not create templates/entry_radar.html.j2 or site/entry_radar.html in a W8 PR."
  - "Do not bind candidate/featured hues to --pv-buy (ZH 红涨绿跌). Mutation M13."
  - "Do not flatten G0/C1/C2/C3/C5, present C4 as a fire, print a Priority number, or drop false-start history."
  - "Do not auto-roll into W9 from this session."

danger_areas:
  - "A write into a sparse mockups/ tree truncates committed crops. This package needs the mockups tree present."
  - "RIG status is in_review. Adding reviews/*.yml without matching frozen_sha will fail later completeness, not now."
  - "Featured aura and candidate chips must stay direction-neutral; tape change is the only --up/--down channel."
---

# W8 return

Reference lives at `mockups/refs/entry_radar/`. Serve with
`python3 -m http.server 8793 --directory mockups/refs/entry_radar`.

W9 copy/wait split is in `mockups/refs/entry_radar/W9_IMPLEMENTATION_HANDOFF.md`.
Author critique + dispositions are in that tree. RIG set:
`research/reference_integrity/entry-radar-w8/` (`status: in_review`).
