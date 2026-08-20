---
key: INTRADAY-FLOW-P0-RECOVERY
title: Intraday Flow P0 recovery + OPEX clock correction
objective: >
  Restore https://www.mastermind-x.com/intraday_flow.html so a trader always sees the
  static 116-name board or a truthful degraded state, even when live quotes/pulse/flow
  are missing. Then correct engine/opex.py so a truncated price history cannot label
  today as a future monthly/quad expiration. Done = production page paints names during
  RTH with no boot throw; the OPEX glance cannot show 0d-to-expiry / quad on a non-expiry
  day; live Theta/M1/R2 plane has an explicit PROVEN_LIVE | BUILT_NOT_PROVEN | DEGRADED |
  BROKEN verdict without speculative re-arming.
status: active
program: options-intelligence
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - templates/intraday_flow.html.j2
  - site/intraday_flow.html
  - tests/test_intraday_flow_ncp_js.py
  - engine/opex.py
waves:
  - id: PR-1
    title: Intraday Flow survives missing live data (boot null-safety)
    status: done
    pr: 6014
    next_action: >
      Merged 2026-08-19T22:12:19Z squash d5de4e62779436f1551ce177b7506ffe468e2884.
      Production browser proof during RTH is still owed on desktop + narrow: HTML contains
      the fix, but post-merge console/DOM paint was not captured.
  - id: PR-2
    title: OPEX calendar must not project future expirations onto the last observation
    status: done
    pr: 6073
    depends_on: [PR-1]
    next_action: >
      Merged 2026-08-20 as b90011f5d37dc3851f2fe17ad7845e6a2fb480a6 before
      the ordered PR-1 production browser receipt was completed. Do not rewrite history:
      implementation is done, sequencing proof was not. Regenerate through the normal
      builder/render path and prove the production OPEX glance cannot show false 0d/quad
      on a non-expiry day. Do not hand-edit generated site artifacts.
  - id: PR-3
    title: Live Theta/M1/R2 options-flow source-clock verdict
    status: todo
    depends_on: [PR-1]
    next_action: >
      After the outstanding PR-1 browser proof and PR-2 production OPEX proof are both
      closed, re-read meta.asof (not built_at). Last census 2026-08-19T19:25Z was DEGRADED,
      asof 2026-08-12T20:09:06Z, poller disarmed. Do not re-arm launchd. Code change only
      after naming the first failing edge.
next_action: >
  Close the two user-facing production receipts now owed: (1) RTH desktop+narrow browser
  proof that Intraday Flow paints without a boot throw after PR-1, and (2) a normal
  post-#6073 build/render receipt proving the OPEX glance no longer projects a future
  expiry backward onto the last observed session. Only after both receipts are honest
  should PR-3 source-clock adjudication begin. Do not re-arm com.mastermind.liveflow.
discoveries:
  - "DSC:INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT"
  - "DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP"
landmines:
  - >
    PR #6073 landed before the workstream's ordered PR-1 production-browser receipt.
    Treat that as an execution-order deviation, not evidence the proof gate was satisfied.
    Do not compound the deviation by starting PR-3 before both outstanding production
    receipts are closed.
  - >
    WS-ADVANCED-DATA-OPTIONS still forbids loading/re-arming the host-side intraday
    options launchd fleet (15 units, DISARMED BY DEFAULT pending AD-9). Live flow is
    the M1 poller + R2 plane, not Studio launchd.
  - >
    Anonymous live/quotes.json does not cover the 116 Intraday Flow leaders; live/flow_pulse.json
    401s for anonymous visitors. A healthy quotes HTTP 200 can still leave every board
    price as a dash.
do_not_redo:
  - "A new options engine, Theta replacement, second live-flow datastore, or stance-model redesign."
  - "try { render(); } catch {} around the Intraday Flow boot render."
  - "Collapsing L5 unknown (null) into false when flow is missing."
  - "Re-auditing the 2026-08-19 jsdom crash reproduction or the in-memory OPEX Aug-19 fixture."
  - "Treating the frontend boot crash as evidence that Theta is down."
  - "Reverting the already-merged PR-2 solely to recreate the intended sequence; reconcile state and finish the owed proofs instead."
artifacts:
  - templates/intraday_flow.html.j2
  - engine/opex.py
  - tests/test_intraday_flow_ncp_js.py
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-pr2-out-of-order-reconciliation.md
---

## Context

Chairman P0: production Intraday Flow looked fully dead (hero "Reading the tape…",
zero lane counts, "Loading leaders…"). That screen was a frontend boot throw, not
missing BASE_DATA. PR #6014 restored null-safe first render. PR #6073 subsequently
fixed the separate OPEX future-expiry clamp but merged before the ordered PR-1 live
browser receipt. The correct state is therefore two merged implementation fixes with
two still-open production proofs, followed only then by the independent source-clock wave.
