---
key: INTRADAY-FLOW-P0-RECOVERY
title: Intraday Flow P0 recovery + OPEX clock correction
objective: >
  Restore https://www.mastermind-x.com/intraday_flow.html so a trader always sees the
  static 116-name board or a truthful degraded state, even when live quotes/pulse/flow
  are missing. Then correct engine/opex.py so a truncated price history cannot label
  today as a future monthly/quad expiration. Done = production page paints names during
  RTH with no boot throw; Aug. 19 cannot show 0d-to-expiry / quad when expiry is Aug. 21;
  live Theta/M1/R2 plane has an explicit PROVEN_LIVE | BUILT_NOT_PROVEN | DEGRADED | BROKEN
  verdict without speculative re-arming.
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
      Next session must still prove the live page in a browser during RTH (desktop +
      narrow) — HTML contains the fix; console/DOM paint was not captured post-merge.
  - id: PR-2
    title: OPEX calendar must not project future expirations onto the last observation
    status: todo
    depends_on: [PR-1]
    next_action: >
      Freeze tests/test_opex.py cases A–E then fix engine/opex.py expiration_days/tag/snapshot.
      Do not hand-edit site/vol/regime.json or site/flowtracker/base.json.
  - id: PR-3
    title: Live Theta/M1/R2 options-flow source-clock verdict
    status: todo
    depends_on: [PR-1]
    next_action: >
      Re-read meta.asof (not built_at). Last census 2026-08-19T19:25Z was DEGRADED,
      asof 2026-08-12T20:09:06Z, poller disarmed. Do not re-arm launchd. Code change
      only after naming the first failing edge.
next_action: >
  Browser-prove production Intraday Flow during RTH, then open a fresh origin/main
  worktree for PR-2 (engine/opex.py + tests/test_opex.py). Do not re-arm com.mastermind.liveflow.
discoveries:
  - "DSC:INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT"
  - "DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP"
landmines:
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
artifacts:
  - templates/intraday_flow.html.j2
  - engine/opex.py
  - tests/test_intraday_flow_ncp_js.py
---

## Context

Chairman P0: production Intraday Flow looked fully dead (hero "Reading the tape…",
zero lane counts, "Loading leaders…"). That screen is a **frontend boot throw**,
not missing `BASE_DATA`. PR #6014 restored null-safe first render. OPEX date
corruption and the stale live-flow plane are separate remaining waves.
