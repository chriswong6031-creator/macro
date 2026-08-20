---
workstream: "WS:MARKET-MEMORY-W2C"
session: claude/market-memory-m0c-source-qual-20260820
model: local
ended_because: complete
mission: >
  Fold post-merge M0C lane packets into the freeze: hybrid session-scope
  naming, v1 trusted-cap landmine, and M0D slice corrections. No runtime.
state_before: >
  PR #6078 merged as 36da0a3c. Source object already frozen single-ticker REST.
  Lane packets then showed the daily bar is RTH price / full-day activity, that
  grouped equals single-ticker on OHLCV/n, and that sharing technicals-v1 would
  destroy the v1 control arm.
changed:
  - path: agentos/discoveries/DSC-SPY-DAILY-AGG-IS-RTH-PRICE-FULLDAY-ACTIVITY.md
    what: Hybrid RTH-price / full-day-activity measurement.
  - path: agentos/discoveries/DSC-W2C-V1-TRUSTED-CAPTURES-THREE-PER-WINDOW.md
    what: v1 trusted pin-budget rate from the first three windows.
  - path: agentos/decisions/DEC-W2C-M0C-V2-HYBRID-PRICE-ACTIVITY-SCOPE.md
    what: Keep single-ticker source; version the contract as a hybrid, not a single RTH aggregate.
  - path: agentos/handoffs/MARKET-MEMORY-W2C-2026-08-20-v2-slice.md
    what: Hybrid profile name, 04:32 stagger, technicals-v1 isolation.
  - path: agentos/workstreams/WS-MARKET-MEMORY-W2C.md
    what: Cite new DEC/DSCs; landmines for spec-function freeze and trusted cap.
verified:
  - claim: >
      PR #6078 squash 36da0a3c is on origin/main and contains AgentOS only.
    command: gh pr view 6078 --json mergedAt,mergeCommit,files
    result: >
      mergedAt 2026-08-20T11:50:05Z mergeCommit 36da0a3c; eight agentos/ paths,
      no engine/app/config/scripts runtime.
unverified:
  - claim: Live trusted HEAD capture_count is still climbing ~3 per window.
    what_would_verify: Direct read on the VPS trusted store HEAD.
unresolved:
  - Sol ratification of DEC:W2C-M0C-V2-REST-SINGLE-TICKER-DAILY plus the hybrid naming DEC.
next_actions:
  - Sol ratifies or amends. Do not implement M0D in this session.
  - Do not fix close_pass_host_runner.py missing-wanted probe TypeError in a W2C PR.
do_not_redo:
  - Do not switch the sealed v2 source to grouped daily.
  - Do not call the v2 profile an RTH volume bar.
  - Do not edit _expected_registration_spec in place.
danger_areas:
  - Sharing technicals-v1 with REST captures converts v1 abstentions to missed.
---

# M0C addendum — hybrid scope, same source object

Source object unchanged. Versioned name changed so M0D does not mint a false RTH-activity contract.
