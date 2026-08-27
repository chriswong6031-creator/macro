---
workstream: WS:PROPHET-HK-CA-REVAMP
session: worktree-stock-dashboard-v38-848171 (Fable principal builder, carrier stock-dashboard-v38-hk-ca-fable-20260826-sol-001)
model: fable
ended_because: complete
prs: [6515]
decisions: []
mission: >
  Execute V38-R1: restore the What to Act On Now customer job at rest above
  Prophet on HK, separate Leadership & Rotation (explicit RS basis) from
  action timing, under the frozen V3.8 architecture, through adversarial
  review, exact-head CI, merge, deploy, and entitled production proof.
state_before: >
  V3.8 architecture frozen (PR #6456, DEC:V38-ACTION-IS-NOT-LEADERSHIP);
  implementation SPEC_ONLY. HK/Canada V3.7 PROVEN_LIVE historically. Sol
  handoff STOCK-DASHBOARD-V38-ACTION-LEADERSHIP-2026-08-26-sol-architecture
  commissioned one Fable HK→Canada carrier. Collision census at pickup
  (main@854c2764): zero open PRs on either composer, zero v38 branches.
changed:
  - path: site/hk-stock-v36.js
    what: >
      V3.8 correction (PR #6515, merged 5dad2bd41326, head cd6c4657bc16):
      at-rest What to Act On Now panel above Prophet (owner anv2 lanes, 3-row
      cap + View all, per-row group-research routes, mobile segmented
      one-lane grammar); Leadership & Rotation with RS #N + visible
      Relative-strength-vs-HSI basis (all rank language gated on
      state.hasRankOwner); rank synthesis deleted (null rank renders em
      dash); Prophet/候选 count label gated on canonical membership
      (missing != zero; known-zero gets quiet copy + route); Leading Now
      strip absorbed (sig-gated flow cue in Leadership header); modal
      action band removed.
  - path: tests/test_hk_v37_composer.py
    what: >
      26 discriminating pins (V3.7 pins preserved + V3.8 pins incl. review
      repairs and pin-evasion hardening); 18/18 in-file mutations killed.
  - path: research/STOCK_DASHBOARD_V38_HK_ACCEPTANCE_2026-08-27.md
    what: HK V3.8 PROVEN_LIVE acceptance record (this records PR) with full entitled production matrix.
verified:
  - claim: Merged as the exact reviewed head with green CI
    command: gh pr view 6515 --json headRefOid,mergeCommit; gh run view 33043046945
    result: head cd6c4657bc16 merged 5dad2bd41326; ci.yml SUCCESS on that head; only red = non-binding merge-queue-pilot
  - claim: Production serves the merged bytes
    command: "ssh VPS: git log -1 + shasum site/hk-stock-v36.js; entitled fetch in production browser"
    result: VPS at 5dad2bd4; sha256 f0befc369afd… identical local/VPS; entitled 200 private,no-store with V3.8 body; anonymous 401
  - claim: Entitled production matrix passes (architecture §14)
    command: entitled Claude-in-Chrome probes on www.mastermind-x.com/hk_stocks.html (see acceptance record)
    result: >
      All items PASS incl. live contradiction case (RS #1 Healthcare &
      Pharma · Reduce/Avoid), population law end-to-end (Consumer zero-case
      → deliberate switch → 2020.HK), known-zero Healthcare route,
      production sm-hidden rescue under resize x3, dark/light, ZH, zero
      console errors. One residual: exact-390px production pixels (OS
      ignores automation-tab resize — same class as V3.7); 390 grammar
      proven in a local real browser on byte-identical content.
  - claim: Pre-merge adversarial review dispositioned
    command: independent opus reviewer on da456970; repairs at cd6c4657
    result: REQUEST_CHANGES (3 MAJOR, 0 BLOCKER) — all MAJORs repaired + receipts; clean bill on §11/§13.4/§13.7
unverified:
  - claim: Exact-390px production pixel pass
    what_would_verify: any human view at 390px on production (V3.7-class residual; code/bytes proven locally)
unresolved:
  - "Deferred nonblocking follow-ups from review: (a) per-group membership keying — global membershipKnown flag + display-name join can render a false 0 on a one-sided rename (stable sectorIdFromHref key exists); (b) lane header count recomputed vs owner .anv2-lane-count; (c) Act-Now tablist focus management (re-render drops focus) — design-system-level, fix both markets at once with the V3.7 modal focus-trap residue"
next_actions:
  - "V38-R2 Canada on THIS carrier: restore at-rest action lanes above Prophet in site/canada-stock-v36.js, keep owner themes[].rank, REMOVE traversal sector rank (collectSectors out.length+1), absorb Leading Now, remove modal action band; tests in tests/test_canada_v36_composer.py; adversarial review → CI → merge → entitled production proof"
  - "If a canonical Canada sector-rank owner is discovered: STOP and return to Sol with producer/contract/basis — do not silently widen authority"
  - "After Canada PROVEN_LIVE: final HK+Canada return packet to Sol; China stays a separate future carrier; US decoupled"
do_not_redo:
  - "Do not re-add rank synthesis anywhere (lane traversal is never rank; test-pinned both member-access and subscript forms)"
  - "Do not put group action back modal-only; the at-rest panel is the one home (test-pinned)"
  - "Do not port HK's pv-featured Top Picks law to Canada — Canada's first-five is the accepted projection (§8.2)"
  - "Do not touch dashboard-icons.js (edge-immutable pair; no re-stamp owed this wave)"
  - "All V3.7 do-not-redo entries stand (no LIVE on HK, sig-neu suppression, sm-hidden rescue, no-slice HK Top Picks)"
danger_areas:
  - "state.hasRankOwner gates ALL rank language — a future edit adding a rank surface must consult it"
  - "anLaneItems() sorts by laneIdx (action owner order); state.sectors stays rotation-rank-sorted for Leadership — do not conflate the two orders"
  - "The known-zero empty state keys on item.members.size === 0 with membership known; unknown membership must stay null members/count, never an empty Set"
  - "Local main ref in the shared clone is diverged and cannot fast-forward — branch records/work from origin/main directly, never from local main"
---

# V38-R1 HK — closeout

Capability delta: entitled HK users now answer "what can I act on now" at
rest above Prophet (owner-native lanes, capped rows, research routes) and
independently read explicitly-based RS leadership below Prophet, with action
stance a separate axis — the live board renders RS #1 Reduce/Avoid beside
lower-RS Buy Now without contradiction. HK V3.8 = PROVEN_LIVE (2026-08-27).
Canada V38-R2 is next on this same carrier; China/US untouched.
