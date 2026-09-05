---
workstream: WS:LIVE-ENTRY-RADAR
session: cursor/entry-radar-w8-rig-9f9d
model: local
ended_because: ci_handoff

mission: >
  Commission W8 / PR #5737 as a reference-only Live Entry Radar UX + RIG
  package. Issue PASS / PASS WITH REQUIRED CORRECTIONS / FAIL against the
  frozen artifact. Do not start W9. Do not create production UI.

state_before: >
  PR #5737 was open and draft. Freeze 9c8990d was blocked by independent
  product and visual critics: overlay PRE-CANDIDATE painted under the price
  quote; P11 compared two chips in the same left rail (always 0). W8
  in_progress. W9 todo. No production entry_radar.html.

changed:
  - path: mockups/refs/entry_radar/radar.css
    what: "Hide overlay LIFECYCLE axis (R2b); stance min-width 0; wrap
      container min-width 0. Pre-candidate fits the 122px quote reserve."
  - path: mockups/refs/entry_radar/tools/verify.py
    what: "P11 compares .er-lifechip vs .pv-quote plus rail overflow at
      1024/1280/1440. R27b pins the hidden axis. R29 pins the P11 predicate."
  - path: mockups/refs/entry_radar/tools/mutation_test.py
    what: "M29 catches restoring the overlay axis. Battery 28/28."
  - path: tests/test_entry_radar_w8_rig.py
    what: "Live geometry test serves the ref tree and runs verify.py --url
      when Playwright is present; skip is not a pass."
  - path: mockups/refs/entry_radar/crops/
    what: "24 crops recaptured after the overlay repair."
  - path: research/reference_integrity/entry-radar-w8/
    what: "Freeze a8c763dc. Dual critic PASS_WITH_CONDITIONS. Design-authority
      APPROVE_WITH_CONDITIONS. approval.yml present. Manifest approved.
      Reference-only; W9-COND-1..5."
  - path: mockups/refs/entry_radar/W9_IMPLEMENTATION_HANDOFF.md
    what: "W9 conditions: omit hidden axis span; 2.2px headroom is not a
      budget; choose lifecycle-word owner; P11 skip is not a pass; amber
      is not single-meaning."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W8 still in_progress until #5737 merges. Do not auto-roll W9."

verified:
  - claim: "Artifact freeze SHA is a8c763dc3dea094fb7c3201e5c3953b921b45464."
    command: "git log -1 --format=%H a8c763dc"
    result: "a8c763dc3dea094fb7c3201e5c3953b921b45464 radar(w8): stop overlay Pre-candidate from painting under the quote"
  - claim: "Live RIG with Playwright is 146/146 including P11/P11b/P11c."
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python mockups/refs/entry_radar/tools/verify.py --url http://127.0.0.1:8793"
    result: "146/146 passed"
  - claim: "Mutation battery catches restoring the overlay axis."
    command: "/opt/homebrew/Caskroom/miniconda/base/bin/python mockups/refs/entry_radar/tools/mutation_test.py"
    result: "28/28 mutations caught including M29-stance-unbreakable by R27b"
  - claim: "No production Radar template on the branch."
    command: "git ls-files templates/entry_radar.html.j2 site/entry_radar.html"
    result: "empty"
  - claim: "Independent product critic measured 0 occlusions on a8c763dc and 68 on an axis-restored mutant."
    command: "independent Playwright probe by opus-reviewer-w8-reattest-5737-A (338 card-measurements; mutant on :8794)"
    result: "freeze 0/338 occlusions; mutant 68 occlusions + 176 rail overflows / 180"

unverified:
  - claim: "PR #5737 is squash-merged and the reference tree is on origin/main."
    what_would_verify: "gh pr view 5737 --json state,mergedAt; this handoff is written before the merge lands."
  - claim: "Live P11 executes in GitHub Actions."
    what_would_verify: "The signal-contract job does not install Playwright, so test_verify_live_geometry skips in CI. W9-COND-2."

prs: [5737]

unresolved:
  - "W8 is not done until #5737 is squash-merged. Manifest approved does not mean W8 wave done."
  - "W9 is a separate commissioning and depends on W4, W6, and merged W8. Do not auto-roll."
  - "W9-COND-1..5 must be closed by id in a successor RIG set if W9 opens a production reference."

next_actions:
  - "Stay on #5737 until squash-merge and live verification of the reference-only tree on origin/main."
  - "Do not open W9. Next parallel wave is W6 Research Priority."
  - "When W9 is commissioned, close W9-COND-1..5 by id in continuity.yml."

do_not_redo:
  - "Do not reverse featured=Best. That equality was the commissioned PRC-004 fix."
  - "Do not restore P11 to comparing .er-lifechip vs .er-xchip in the same rail."
  - "Do not restore the overlay LIFECYCLE axis; it overflowed Pre-candidate under the quote."
  - "Do not pin 390 with overflow-x: hidden."
  - "Do not create templates/entry_radar.html.j2 or site/entry_radar.html in this PR."
  - "Do not invent a Priority number or Opportunity probability."
  - "Do not start W9 from a W8 merge."

danger_areas:
  - "2.2px overlay-rail headroom at 1024 against PRE-CANDIDATE. Font-stack change re-opens RGXB-001."
  - "CI live geometry skip looks like a floor and is not. Static R29 is the CI pin."
  - "macro-main is a linked worktree of Macro Dashboard/.git. Never delete or relocate that folder."
  - "Prophet engine paths and the occupied primary checkout are off-limits."
---

# W8 commissioning — freeze a8c763dc APPROVE_WITH_CONDITIONS

Reference-only. No production Radar page. W9 stays stopped.

Independent critics of freeze `9c8990d` both BLOCKED: the overlay lifecycle chip painted under the price, and P11 could not see it. Repair on `a8c763dc` hides the duplicate overlay LIFECYCLE axis (visual critic R2b). Product critic proved causality with a mutant that restored the axis (68 occlusions) against 0 on the freeze.

Receipts bind to `a8c763dc3dea094fb7c3201e5c3953b921b45464`. Do not approve a later SHA with these receipts.
