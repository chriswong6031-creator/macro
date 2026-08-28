---
workstream: WS:INTRADAY-FLOW-P0-RECOVERY
session: sol/intraday-pr2-out-of-order-reconciliation
model: local
ended_because: complete
prs: [6014, 6073]
decisions: []
discoveries: []
mission: >
  Reconcile canonical Agent OS after OPEX PR #6073 merged before the workstream's
  explicitly ordered PR-1 production-browser proof, without retroactively claiming
  the sequence gate was satisfied or reverting a useful merged repair just to restore order.
state_before: >
  Main contained PR #6014 (boot null-safety) and PR #6073 (future-expiry tail-clamp
  repair), but the direct workstream still said PR-2 was TODO and its top-level next
  action said to browser-prove PR-1 before opening PR-2. Linear had therefore exposed
  a genuine GitHub-vs-AgentOS disagreement.
changed:
  - path: agentos/workstreams/WS-INTRADAY-FLOW-P0-RECOVERY.md
    what: >
      Records PR-2 as merged/done, preserves the fact that its ordered prerequisite
      production receipt was not completed first, keeps PR-1 production proof open,
      adds the post-merge OPEX production proof, and prevents PR-3 from compounding the drift.
verified:
  - claim: PR #6073 is merged on main.
    command: Inspect GitHub main / PR #6073.
    result: Merge commit b90011f5d37dc3851f2fe17ad7845e6a2fb480a6 is on main.
  - claim: The direct workstream was stale after that merge.
    command: Read agentos/workstreams/WS-INTRADAY-FLOW-P0-RECOVERY.md on pre-repair main.
    result: PR-2 remained todo and next_action still ordered PR-1 production proof before PR-2.
  - claim: PR-1's real production browser proof is still not present in the workstream.
    command: Read PR-1 wave and current handoff state.
    result: Implementation is merged, but post-merge RTH desktop+narrow console/DOM proof remains owed.
unverified:
  - claim: Production Intraday Flow paints correctly during RTH after PR-1.
    what_would_verify: >
      Real production desktop+narrow browser receipt during RTH with names painted and no boot throw.
  - claim: Production OPEX glance is corrected after PR-2.
    what_would_verify: >
      Covering normal builder/render receipt plus production reader/browser showing no false 0d/quad on a non-expiry day.
  - claim: Live Theta/M1/R2 plane is healthy.
    what_would_verify: >
      Separate PR-3 source-clock adjudication after the two user-facing receipts close.
unresolved:
  - "PR-1 production browser proof remains open."
  - "PR-2 post-merge production OPEX proof remains open."
  - "PR-3 source-clock verdict remains TODO; host-side launchd/options fleet stays disarmed."
next_actions:
  - "First close the PR-1 RTH browser receipt."
  - "Close the PR-2 normal-render production OPEX receipt."
  - "Only then start PR-3 source-clock adjudication; do not re-arm com.mastermind.liveflow."
do_not_redo:
  - "Do not claim the original sequence gate was satisfied just because PR #6073 merged."
  - "Do not revert #6073 solely to recreate the intended order."
  - "Do not hand-edit generated site artifacts to prove OPEX."
  - "Do not collapse missing live-flow evidence into a frontend/OPEX verdict."
danger_areas:
  - "GitHub execution truth can outrun Agent OS; the repair is canonical reconciliation, not historical rewriting."
  - "Two user-facing proof gaps are now simultaneous; closing one does not close the other."
  - "A stale live-flow plane is independent of both merged fixes and must remain separately adjudicated."
---

# Return point

Two implementation PRs are on main. P0 is not complete. Close the real PR-1 browser
receipt and the post-#6073 OPEX production receipt before starting the source-clock wave.
