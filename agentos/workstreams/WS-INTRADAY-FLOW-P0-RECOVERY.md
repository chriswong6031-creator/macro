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
status: done
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
  - tests/test_opex.py
waves:
  - id: PR-1
    title: Intraday Flow survives missing live data (boot null-safety)
    status: done
    pr: 6014
    next_action: >
      Merged 2026-08-19T22:12:19Z squash d5de4e62779436f1551ce177b7506ffe468e2884.
      Production RTH browser proof closed 2026-08-20T13:32:22Z and rechecked at
      13:34:53Z in a fresh 1280x720 in-app browser tab: 116 named rows, zero loading
      rows, lane counts [0, 0, 0, 0, 0, 116], Spotlight rendered, and zero console
      errors or TypeErrors after polling. The all-stand-aside result is truthful
      degradation from stale live flow, not a repeat of the boot throw.
  - id: PR-2
    title: OPEX calendar must not project future expirations onto the last observation
    status: done
    pr: 6073
    depends_on: [PR-1]
    next_action: >
      Merged 2026-08-20 as b90011f5d37dc3851f2fe17ad7845e6a2fb480a6 before
      the ordered PR-1 production browser receipt was completed; that sequencing deviation
      remains recorded rather than rewritten. Covering engine-render run 32369652484
      concluded green and generated e9e9009c240a7c6337028a2c182ffa3b09be870f.
      Production checkout c3c6534b4b80164203c3c8f07b8dedae75c40eab is a descendant
      and serves phase=mid_cycle, td_to_opex=null, in_opex_week=false,
      is_quad_cycle=false, with the false 0d/quad-witching phrase absent.
  - id: PR-3
    title: Live Theta/M1/R2 options-flow source-clock verdict
    status: done
    depends_on: [PR-1, PR-2]
    next_action: >
      Post-gate read at 2026-08-20T14:19:30Z returned HTTP 200 and schema
      live_flow.meta/v2, but meta.asof remained 2026-08-12T20:09:06.992244Z
      (built_at 2026-08-12T20:09:45.521589Z), age 186.173 hours: verdict DEGRADED.
      No launchd unit was loaded or re-armed. Any repair belongs to the existing
      WS-ADVANCED-DATA-OPTIONS authority lane after its AD-9 gate, not this closed P0.
  - id: PR-4
    title: Restore honest live quote, pulse, and options transport
    status: in_progress
    pr: 6105
    depends_on: [PR-1, PR-2, PR-3]
    next_action: >
      Production incident reopened the user-facing outcome: the board painted but its
      three live inputs were dead or falsely labelled live. Recovery is being shipped
      from a fresh worktree with board-scoped quote coverage, ts-index normalization,
      semantic pulse health, RTH options-source freshness, and exact live receipts.
      The operator's direct 2026-08-20 request to investigate and fix superseded the
      earlier read-only/no-re-arm boundary for this incident. Recovery is limited to
      the existing canonical com.mastermind.liveflow unit; the retired Studio options
      fleet remains disarmed and no second engine or publication plane was created.
next_action: >
  Workstream complete: the board paints in production during RTH, the corrected OPEX
  calendar is on the live checkout, and the independent live-flow plane is explicitly
  DEGRADED. Do not re-arm com.mastermind.liveflow here. Route any later live-flow recovery
  through WS-ADVANCED-DATA-OPTIONS under its existing authority and AD-9 gate.
discoveries:
  - "DSC:INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT"
  - "DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP"
  - "DSC:INTRADAY-FLOW-AGE-HEALTH-CAN-HIDE-EMPTY-BOARD"
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
  - tests/test_opex.py
  - tests/test_intraday_flow_ncp_js.py
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-pr2-out-of-order-reconciliation.md
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-closeout.md
---

## Context

Chairman P0: production Intraday Flow looked fully dead (hero "Reading the tape…",
zero lane counts, "Loading leaders…"). That screen was a frontend boot throw, not
missing BASE_DATA. PR #6014 restored null-safe first render. PR #6073 subsequently
fixed the separate OPEX future-expiry clamp but merged before the ordered PR-1 live
browser receipt. The deviation was preserved in the record, then both production proofs
were closed: 116 names painted without a boot throw during RTH and the normal render lane
put the corrected mid-cycle OPEX state on the live checkout. The final independent source
clock stayed at 2026-08-12, so the product boot is recovered while the live-flow data plane
is explicitly DEGRADED and remains disarmed under the separate options-data authority lane.
