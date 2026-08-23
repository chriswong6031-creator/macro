---
workstream: WS:MARKET-OS
session: sol/market-os-a1a-merge-reconciliation
model: local
ended_because: complete
prs: [6098]
decisions:
  - DEC:MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED
discoveries: []
mission: >
  Reconcile canonical Market OS state after A1A merged, without converting a
  technically strong implementation into false product completion or opening
  A1B before the promised production truth is proven.
state_before: >
  Macro PR #6098 had merged the A1A deterministic Portfolio state-authority
  implementation, but WS:MARKET-OS still described A1A as todo and instructed
  Fable to start it. The PR's own return explicitly withheld production
  acceptance and named two remaining defects: false mixed-sizing copy for an
  insufficient same-book comparison, and stale Watchlist-derived Risk Center
  percentages after a same-session switch into Portfolio mode. No real
  authenticated cloud/Supabase production round-trip or Macro/Terminal
  conformance dossier had been accepted. A1B remained architecturally blocked
  but the stale workstream did not encode the actual merge/proof state.
changed:
  - path: agentos/decisions/DEC-MARKET-OS-A1A-MERGED-PRODUCTION-ACCEPTANCE-REQUIRED.md
    what: >
      Records #6098 as the merged implementation while preserving two bounded
      repairs plus real production acceptance as the A1A completion boundary.
      A1B stays unauthorized until separate Sol acceptance.
  - path: agentos/workstreams/WS-MARKET-OS.md
    what: >
      Moves A1A from todo to in_progress, attaches PR #6098, retires stale
      pre-build landmines as repaired history, names the two current defects,
      and makes repair + production proof the exact next action.
verified:
  - claim: A1A implementation is merged on Macro main.
    command: Read GitHub PR #6098 metadata and its merged return.
    result: >
      PR #6098 is merged and implements Portfolio-only population, unsaved
      temporary baskets, cloud-authority fail-closed behavior, separate save
      state, missing-aware weighting and no invented cluster.
  - claim: #6098 did not prove the real production journey.
    command: Read the PR's GAPS / production section.
    result: >
      The return explicitly says production round-trip with a real Supabase
      account and real cloud degradation was not done; local/browser harness
      evidence was the delivered proof.
  - claim: Two material user-facing defects remain after the merge.
    command: Read the PR's named gaps and browser observations.
    result: >
      A cross-book/single-comparable-position state can emit mixed-sizing copy,
      and switching from Watchlists to Portfolio can retain stale Watchlist
      concentration percentages in Risk Center.
  - claim: A1B is a hard dependency on accepted A1A, not a parallel wave.
    command: Read DEC:MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT and the architecture freeze.
    result: A1B begins only after Sol accepts A1A in production.
unverified:
  - claim: The bounded copy repair is correct in source or production.
    what_would_verify: >
      A focused repair and mutation test distinguishing `single_position` /
      insufficient comparison from mixed sizing, followed by browser proof.
  - claim: Risk Center never carries Watchlist-derived state into Portfolio mode.
    what_would_verify: >
      A focused mode-transition repair with end-to-end Watchlist→Portfolio→
      Watchlist tests and real browser proof across empty/one/many/degraded.
  - claim: A1A is production-proven.
    what_would_verify: >
      Real cloud Portfolio journeys for Watchlist-12/Portfolio-0, one/many
      positions, sizing states, first-load/cloud-failure/account-transition,
      write/readback, responsive UI, and Macro/Terminal membership conformance.
unresolved:
  - "A1A-R1 truthful insufficient-comparison reason/copy is not yet merged or proven."
  - "A1A-R2 stale cross-mode Risk Center state is not yet merged or proven."
  - "Real cloud/Supabase production acceptance and Macro/Terminal conformance are owed."
  - "A1B remains unauthorized and must not start from #6098's merge alone."
next_actions:
  - "Dispatch one bounded copy/state repair for the insufficient-comparison reason."
  - "Dispatch one bounded Risk Center mode-transition repair; do not alter risk formulas."
  - "After both repairs are accepted, execute the real A1A production dossier from the canonical handoff/decision."
  - "Return to Sol; only a separate acceptance may make A1B eligible."
do_not_redo:
  - "Do not rebuild the Portfolio/Watchlist state plane or create another store."
  - "Do not reintroduce Watchlist union, local-cloud fail-open or temporary-basket persistence."
  - "Do not treat #6098 merge, local crops or green CI as production acceptance."
  - "Do not start A1B, A2+, B/C/D/E/F waves before their frozen dependencies."
  - "Do not change risk formulas to clear a stale-consumer defect."
danger_areas:
  - "A correct abstention with false reason copy is still a factual product defect; repair the reason route, not the weighting law."
  - "Risk Center owns long-lived client state; clearing the visible card without resetting every consumer can leave hidden/stale factor weights active."
  - "Authenticated cloud failure must never become an empty Portfolio or anonymous local authority."
  - "Cross-user same-session tests are mandatory because last-good caches are useful only when bound to the same canonical user."
---

# Return point

A1A is **merged and independently useful**, but remains
`BUILT_NOT_PROVEN`. Repair the two named consumers, then prove the real cloud
journey and Macro/Terminal conformance. Do not start A1B from this records
merge.