---
workstream: WS:PROPHET-HK-CA-REVAMP
session: worktree-stock-dashboard-v38-848171 (Fable principal builder, carrier stock-dashboard-v38-hk-ca-fable-20260826-sol-001)
model: fable
ended_because: complete
prs: [6545, 6541, 6515]
decisions: []
mission: >
  Complete the regional V3.8 correction: after HK V38-R1 PROVEN_LIVE, carry
  Canada V38-R2 (restore at-rest What to Act On Now, keep owner theme rank,
  remove presentation-owned sector rank) through adversarial review, CI,
  merge, deploy, and entitled production proof, then close the regional
  packet for Sol.
state_before: >
  HK V3.8 PROVEN_LIVE (2026-08-27, PR #6515 merged 5dad2bd41326, records
  #6541 merged 38b8ef1c1471). Canada still V3.7: action lanes modal-only,
  sector rank minted from lane traversal, BOARD count label.
changed:
  - path: site/canada-stock-v36.js
    what: >
      V3.8 correction (PR #6545, merged 1276333b37b9, head b924678a87a9):
      at-rest What to Act On Now above Prophet (owner anv2 lanes, 3-row cap
      + View all, owner research routes, mobile one-lane grammar, null-only
      lane election); traversal sector rank DELETED and theme rank owner-
      only (no positional fallback) with Theme-rank basis gated on
      state.hasThemeRank; Leadership & Rotation THEMES ONLY incl. modal
      (§8.2.4 — an action-ordered sector list is a covert rank); membership
      per-group via the board's sector vocabulary (no false zeros across
      the lane/board taxonomy mismatch); activation affordances gated on
      canonical membership on all surfaces; known-zero quiet state + route;
      fresh-signals cue in the Prophet header, absent at zero; BOARD label
      → Prophet/候选. Frozen untouched: first-five Top Picks projection,
      LIVE quote plane, XOR/sm-hidden, Track Record, Terminal routes,
      artifact fetches, loader.
  - path: tests/test_canada_v36_composer.py
    what: >
      17 discriminating pins (V3.7 pins preserved; modal-lane-band pin
      rewritten as the at-rest pin; new V3.8 + review-repair pins);
      20/20 in-file mutations killed.
  - path: research/STOCK_DASHBOARD_V38_CANADA_ACCEPTANCE_2026-08-27.md
    what: Canada V3.8 PROVEN_LIVE acceptance record (this records PR) with the full entitled production matrix.
verified:
  - claim: Merged as the exact reviewed head with green CI
    command: gh pr view 6545 --json headRefOid,mergeCommit; gh run view 33059279089
    result: head b924678a87a9 merged 1276333b37b9; ci.yml SUCCESS on that head; only red = non-binding merge-queue-pilot
  - claim: Production serves the merged bytes
    command: "ssh VPS: git log + shasum; entitled fetch with cache:'reload'"
    result: VPS at 1276333b37b9; sha256 ff38a3cc33e5… identical local/VPS; entitled 200 private,no-store V3.8 body; anonymous 401
  - claim: Entitled production matrix passes (§14)
    command: entitled Claude-in-Chrome probes on www.mastermind-x.com/canada_stocks.html (see acceptance record)
    result: >
      All items PASS incl. per-group membership live (in-vocab groups
      actionable with real counts; out-of-vocab disabled route-only rows),
      themes-only Leadership (Theme #1..#5 + basis, stance separate),
      population law on sector AND theme filters, XOR + 6 live quote cells
      after filter, single-pane modal, truthful empty Buy Now lane, fresh
      cue hidden at zero, dark/light + EN/ZH, zero console errors. Residual:
      exact-390 production pixels (same class as V3.7/HK; local real-browser
      390 pass on byte-identical content).
  - claim: Pre-merge adversarial review dispositioned
    command: independent opus reviewer on 8c86aef24c0c; repairs at b924678a87a9
    result: REQUEST_CHANGES (2 MAJOR, 0 BLOCKER) — false-zero membership grain and covert action-ordered sector leadership both repaired + receipts
unverified:
  - claim: Exact-390px production pixel pass
    what_would_verify: any human view at 390px on production (recurring V3.7-class residual)
unresolved:
  - "Cross-market nonblocking residue (both composers): Act-Now tablist focus management + modal focus trapping — design-system-level, fix both markets at once"
  - "HK deferred follow-ups from its review remain open: per-group membership keying by stable id (HK still joins by display name), owner lane-count read-through"
  - "Canada theme rows carry no href, so a known-zero THEME cannot offer a research route (sectors can); a theme-detail route owner would close it"
next_actions:
  - "Return the complete HK+Canada V3.8 packet to Sol for final regional acceptance (carrier stop condition reached)"
  - "China V3.8 follower: separate future carrier, fresh producer/collision census first (§8.3); US: decoupled, unauthorized"
do_not_redo:
  - "Do not render ANY sector rank number for Canada on any surface, and do not restore a sector column/pane to Leadership & Rotation without a canonical sector-rank owner adjudicated by Sol"
  - "Do not regress membership to a page-global flag — knowledge is per group via the board's own sector vocabulary"
  - "Do not give unknown-membership groups a filter affordance — route only"
  - "Do not port HK's pv-featured law to Canada (first-five is the accepted projection) or Canada's LIVE treatment to HK"
  - "All prior V3.7 and HK V3.8 do-not-redo entries stand"
danger_areas:
  - "The lane/board taxonomy mismatch is REAL data today (lane 'Communication Services' vs board 'Communication') — any future join must go through the vocabulary gate or a stable owner key, never bare display-name equality assumed known"
  - "state.hasThemeRank gates ALL theme-rank language; the 2.5s basket-fetch degrade leaves it false and every rank surface must stay silent"
  - "anLaneItems() sorts by laneIdx (action owner order); state.themes stays owner-rank-sorted — never conflate the axes"
---

# V38-R2 Canada — closeout (regional V3.8 COMPLETE)

Capability delta: entitled Canada users now get the at-rest owner action map
above Prophet with truthful per-group counts and research routes, and a
Leadership & Rotation surface that carries ONLY the owner-ranked themes
under an explicit basis — no presentation-minted number anywhere. Canada
V3.8 = PROVEN_LIVE (2026-08-27). With HK V3.8 PROVEN_LIVE the same day, the
regional V3.8 Action ≠ Leadership correction is COMPLETE; the carrier stops
here for Sol's final HK+Canada acceptance. China/US untouched.
