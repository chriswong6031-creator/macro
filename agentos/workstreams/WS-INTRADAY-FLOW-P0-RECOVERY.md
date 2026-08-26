---
key: INTRADAY-FLOW-P0-RECOVERY
title: Intraday Flow P0 recovery + OPEX clock correction
objective: >
  Restore https://www.mastermind-x.com/intraday_flow.html so a trader always sees the
  static 116-name board or a truthful degraded state, even when live quotes/pulse/flow
  are missing; correct engine/opex.py so truncated price history cannot label today as
  a future monthly/quad expiration; and ensure any `live` upgrade is backed by current,
  semantically usable board-scoped quotes, pulse, and the canonical M1/R2 options-flow
  plane. Done = boot and OPEX truth are production-proven, PR-4's live transport passes
  a genuine current-session production dossier, and no second options engine or
  speculative fleet re-arm was used to manufacture health.
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
  - scripts/build_intraday_flow.py
  - scripts/build_intraday_flow_quotes.py
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
      errors or TypeErrors after polling. The all-stand-aside result was truthful
      degradation from stale live flow, not a repeat of the boot throw. Do not reopen
      this wave unless a direct regression reproduces.
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
      and served phase=mid_cycle, td_to_opex=null, in_opex_week=false,
      is_quad_cycle=false, with the false 0d/quad-witching phrase absent. Do not reopen
      this wave without direct OPEX regression evidence.
  - id: PR-3
    title: Live Theta/M1/R2 options-flow source-clock verdict
    status: done
    depends_on: [PR-1, PR-2]
    next_action: >
      The 2026-08-20T14:19:30Z read returned HTTP 200 and schema live_flow.meta/v2,
      but meta.asof remained 2026-08-12T20:09:06.992244Z (age 186.173 hours):
      verdict DEGRADED. That finding triggered no Studio-fleet re-arm. A later direct
      operator incident authorized PR-4 to repair the existing canonical M1 plane and
      bounded projections; it did not erase this source-clock receipt or settle AD-9.
  - id: PR-4
    title: Restore honest live quote, pulse, and options transport
    status: in_progress
    pr: 6105
    depends_on: [PR-1, PR-2, PR-3]
    next_action: >
      Implementation merged 2026-08-20 as 364b85973517f459dba937145a040dce93862907.
      #6105 filters the existing VPS full quote snapshot into board-scoped
      live/intraday_quotes.json; normalizes Polygon DatetimeIndex(name=ts) for current-
      session pulse bars; refuses mode=no_data or severe undercoverage as healthy;
      adds semantic /api/status and dead-man checks; and makes browser live labels depend
      on source freshness + coverage. It recovered the existing com.mastermind.liveflow
      M1 lane through the runbook without creating a second engine or loading the retired
      Studio fleet. Keep this wave BUILT_NOT_PROVEN until one genuine current-session
      production receipt proves all three source planes, semantic health, and the served
      desktop+narrow browser journey. On PASS, land a separate records closeout.
decisions:
  - "DEC:INTRADAY-FLOW-PR4-MERGED-PRODUCTION-ACCEPTANCE-OWED"
discoveries:
  - "DSC:INTRADAY-FLOW-RTH-NULL-QUOTE-BOOT"
  - "DSC:OPEX-FUTURE-MONTH-LAST-OBS-CLAMP"
  - "DSC:INTRADAY-FLOW-AGE-HEALTH-CAN-HIDE-EMPTY-BOARD"
next_action: >
  PR-4/#6105 is merged but BUILT_NOT_PROVEN. Execute exactly one genuine current-
  session production dossier: prove board-scoped quote coverage + source freshness;
  current-session pulse mode/coverage; the reviewed com.mastermind.liveflow M1/R2 plane
  advancing naturally; /api/status and dead-man semantic health; and the actual served
  board at desktop+narrow with live labels only when every required gate passes. Stop at
  the first causal failure and repair it narrowly. Keep the retired Studio fleet
  disarmed and AD-9 separate. Only a later records closeout may return this workstream to
  done.
landmines:
  - >
    PR #6073 landed before the workstream's ordered PR-1 production-browser receipt.
    The deviation is historical and reconciled; do not rewrite it or use it to reopen
    accepted boot/OPEX work.
  - >
    A 116-name static render proves product fallback, not live transport. A quote HTTP
    200, young file mtime, deployment timestamp or generated_at over stale source bytes
    cannot grant a live label.
  - >
    Quote, pulse and options-flow health are independent. One healthy plane may not
    launder a stale/empty/under-covered sibling. Missing is null/unavailable, never zero.
  - >
    The canonical live-flow producer is com.mastermind.liveflow M1 + R2. The retired
    host-side Studio options fleet (15 units) remains disarmed pending AD-9; PR-4's direct
    incident authority did not settle long-term fleet ownership.
  - >
    M1 recovery used a clone-beside swap and prior-WAL quarantine. Do not silently attach
    quarantined state, delete evidence, or treat the old checkout as a fallback.
  - >
    Old split-deploy payloads may omit additive semantic-health fields. The browser and
    dead-man must fail toward static/degraded, not infer health from file age or HTTP.
do_not_redo:
  - "A new options engine, Theta replacement, second live-flow datastore, poller, or stance-model redesign."
  - "try { render(); } catch {} around the Intraday Flow boot render."
  - "Collapsing L5 unknown (null) into false when flow is missing."
  - "Re-auditing the 2026-08-19 jsdom crash reproduction or the in-memory OPEX Aug-19 fixture without regression evidence."
  - "Treating the frontend boot crash as evidence that Theta/M1 is down."
  - "Reverting PR-2 solely to recreate the intended sequence."
  - "Manufacturing a notable flow event or replaying later knowledge as current-session proof."
  - "Calling #6105 merge, fixture 116/116, HTTP 200, or green CI production acceptance."
artifacts:
  - templates/intraday_flow.html.j2
  - scripts/build_intraday_flow.py
  - scripts/build_intraday_flow_quotes.py
  - engine/opex.py
  - tests/test_opex.py
  - tests/test_intraday_flow_ncp_js.py
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-pr2-out-of-order-reconciliation.md
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-closeout.md
  - agentos/handoffs/INTRADAY-FLOW-P0-RECOVERY-2026-08-20-pr4-merge-reconciliation.md
  - agentos/decisions/DEC-INTRADAY-FLOW-PR4-MERGED-PRODUCTION-ACCEPTANCE-OWED.md
---

## Context

The first closeout was honest for its original scope: PR #6014 restored null-safe first
render, PR #6073 fixed the OPEX observation-history clamp, and PR-3 classified the stale
live-flow plane DEGRADED without speculative re-arming. A later production incident
proved that the broader user-facing live outcome remained broken even while the board
painted. Public quotes covered only 3/116 leaders, pulse could look age-fresh while
`mode=no_data`, a ts-named Polygon index produced no current bars, and M1 remained on an
old deploy tree.

PR #6105 is now the bounded repair on main. It preserves the existing engine/store,
introduces source-semantic health, and adds the board-specific quote projection the
actual page needs. That is meaningful implementation capability, but the live product is
not complete until a natural current-session production cycle and real browser prove the
three planes together. The workstream is therefore active with PR-4 in_progress.