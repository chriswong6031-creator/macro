---
key: POLICY-PRETURN-CALENDAR-FLOW-COMPOSITION
question: >
  How should Mastermind model recurring OPEX/month-end turns, official policy events,
  Treasury liquidity and futures mechanics without creating a second market owner,
  an unexecutable test plan, a stale cross-lane publisher or a calendar-driven trade signal?
answer: >
  Build one deterministic policy_turn_clock.v1 composition over existing event, release,
  OPEX, options, broad-flow, rebalance, Treasury/TGA, volatility, market-state and futures
  owners. Hourly is the sole official-event/current-artifact writer; the existing nightly
  regional-desk lane runs the same builder in ledger-only mode. Preserve event venue apart
  from explicitly supported physical actor presence, preserve Treasury operation mechanism,
  purpose and separate amount fields, make silent source revisions correction-safe, and
  expose method/input/source identity. Standard VX settlement is monthly and separate from
  weekly fronts and quarterly equity/Treasury rolls. Calendar proximity and every W1 state
  remain context-only with can_rank/can_gate/can_size/can_trade=false.
rationale: >
  The Chairman's observed sequence is plausible only as a compound inventory, liquidity,
  flow and catalyst clock. Expiration can remove stabilizing long-gamma inventory or
  destabilizing short-gamma inventory; replacement may rebuild or fail; month-end may
  combine broad ETF flow, observed rebalancing, asset-specific bond-index extension and
  Treasury cash movement; standard VIX futures settle monthly while major equity-index and
  Treasury futures roll quarterly; macro events can dominate every mechanical clock.
  Existing repository organs already own each underlying truth, but the previous W1 draft
  omitted explicit inputs needed by its own states, lacked a real nightly receipt advancer,
  allowed wall-clock-only hourly byte churn, conflated buyback mechanism with purpose,
  treated event venue as physical presence, could drop silent source corrections, and
  forbade the CI manifest required to execute its new suites. The repaired architecture
  closes those defects by composing current owners through an explicit pure interface,
  one current publisher, one nightly receipt path, semantic no-op/no-regress behavior and
  canonical executable test ownership. This creates useful anticipatory context without
  laundering calendar folklore, source ambiguity or model narrative into capital authority.
alternatives:
  - option: "Create a universal buy-at-month-start and de-risk-after-OPEX signal."
    why_not: >
      The unconditional effect is era-dependent; options expiration can remove either
      stabilizing or destabilizing inventory; current in-repo evidence withholds a robust
      universal post-OPEX direction. A calendar trade would be empirically fragile and
      violate existing authority law.
  - option: "Create a standalone policy calendar, futures database and transition score."
    why_not: >
      Event Calendar, Macro Release Intelligence, OPEX, ThetaData options, Rebalance Pulse,
      ETF flows, Treasury Watch, Cboe VX and current market-state/volatility owners already
      hold the facts. New stores or a weighted score would fork truth, correction clocks and
      authority.
  - option: "Run collection, current publication and prospective evidence from both hourly and nightly lanes."
    why_not: >
      Two writers with independent concurrency/rebase behavior can regress a newer evidence
      cutoff and create duplicate receipts. Hourly single-writer plus nightly ledger-only is
      the smallest composition over existing workflows.
  - option: "Use an LLM to infer private actor location, coordination or intervention timing."
    why_not: >
      Private timing and physical presence are not identifiable from public calendars or
      aligned interests. Model text may later narrate grounded receipts but cannot create
      source facts or W1 state.
  - option: "Keep the prior plan and let implementation discover the missing interfaces and CI/runtime owners."
    why_not: >
      Independent exact-head review proved the plan could not produce several promised
      states, could never advance its prospective ledger, and could leave tests dark.
      Delegating those architecture decisions to a bounded worker would recreate the
      ambiguity W1 is supposed to remove.
evidence:
  - "Chairman Chris explicitly approved initiation and instructed Sol to continue at full throttle in the active session on 2026-09-03."
  - "Protected procedure was re-pinned to mastermindx-market-intelligence/Mastermind@c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6; Skillpack v1.0.1 remains bootstrap-major-1 compatible."
  - "Macro PR #6788 exact-head review child policy-preturn-pr6788-9bc18-full-review-20260903-sol-002 returned merits REQUEST_CHANGES at Slack 1788427555.357049; Sol accepted and terminally stopped the child at 1788427931.007269."
  - "The review proved six blocking defects: no real nightly invocation, quiet-hour byte churn, Treasury taxonomy/amount collapse, venue/presence and silent-revision defects, incomplete pure-composer inputs, and non-reproducible market/method identity."
  - "Current W1 design and plan are replaced on the same PR branch with explicit hourly single-writer, nightly ledger-only, semantic no-op/no-regress, corrected evidence schema, pure input closure and method identity."
  - "Current open-PR census found multiple .github/ci/legacy-jobs.yml candidates beyond PR #6721; W1 therefore requires a fresh all-owner START-time collision census rather than a single-owner assumption."
  - "collectors/cboe_vix_futures.py and its existing stores distinguish nearest weekly-or-monthly front from standard monthly M1-M6; W1 consumes those owners and suppresses rank-roll false changes."
  - "engine/etf_flows.py documents the SPY/QQQ/IWM/RSP/DIA broad-flow proxy as forward-accruing, T+1 and display-only; W1 preserves that lag and limitation."
  - "reports/artifacts/options_surface_coverage.md proves canonical options coverage for 20 roots, mostly 2017 onward; issue #6794 separately freezes historical versus prospective study cohorts."
  - "reports/d2-rates-calendar-flows-phase0.md finds asset-specific TLT/IEF month-end extension while generic auction/pension variants fail, requiring separate duration context rather than a generic equity flow claim."
affects:
  - "WS:RATES-INFLATION-COMMAND"
  - "Policy Transmission & Pre-Turn Command"
  - "policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001"
  - "policy_turn_clock.v1"
  - "collectors/policy_event_clock.py"
  - "engine/futures_roll_calendar.py"
  - "engine/policy_turn_clock.py"
  - "scripts/build_policy_turn_clock.py"
  - ".github/workflows/whitehouse-sentinel.yml"
  - "scripts/ci/daily_engine_regional_desk_builders.sh"
  - ".github/ci/legacy-jobs.yml"
  - "site/policy_turn_clock.json"
  - "site/policy_watch.html"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-09-03
---

# Binding ruling

## One canonical composition

`policy_turn_clock.v1` is a pure deterministic composition and projection. It does not own underlying event, release, options, OPEX, flow, Treasury, market-state, futures or portfolio truth. Every axis carries owner, as-of/available-at, freshness, assumption, correction and null evidence.

The closed glance vocabulary is:

```text
SUPPORT_BUILDING
SUPPORT_STABLE
PINNED
SUPPORT_ROLLOFF_IMMINENT
VOLATILITY_WINDOW_OPEN
MONTH_END_REBALANCE_DOMINANT
CATALYST_DOMINANT
MIXED
UNKNOWN
```

No state is a score or position instruction.

## Evidence ruling

Official evidence preserves stable event identity, explicit/fallback revision identity, canonical semantic digest and keep-FIRST receipts. A reused revision token with changed semantic content is a visible collision. Formatting-only page changes do not create vintages.

Event location, attendance mode and actor physical presence are distinct. Current physical location requires explicit official live-presence support; scheduled, virtual, prerecorded, ambiguous, cancelled and ended appearances leave it unknown.

Treasury operation mechanism and purpose are distinct. A cash-management or liquidity-support case remains `operation_kind=buyback` with an explicit purpose. Maximum, offered, submitted and accepted amounts remain separate nullable fields.

## Monthly mechanism ruling

1. OPEX proximity never establishes dealer sign or direction.
2. Stabilizing and destabilizing expiration configurations remain opposite cases.
3. Replacement evidence requires comparable canonical observations; missing is unknown.
4. `SUPPORT_BUILDING` requires at least two independent applicable support mechanisms, not option replacement alone.
5. Month-end scheduled eligibility, pressure estimate and observed mechanical pulse are distinct; dominance requires observed pulse.
6. Bond-index extension is an asset-specific duration context, not a current equity flow claim.
7. Standard VX settlement is monthly; weekly fronts and quarterly equity/Treasury rolls remain separate.
8. `VOLATILITY_WINDOW_OPEN` requires fresh independent market/volatility/breadth/credit confirmation.
9. High-impact official catalysts may override mechanical windows without gaining capital authority.

## Runtime ruling

Hourly White House Sentinel is the sole official-event and current `site/policy_turn_clock.json` writer. Healthy semantic no-op reruns remain byte-stable. Older cutoffs cannot overwrite newer artifacts.

The existing nightly regional-desk owner invokes `scripts.build_policy_turn_clock --mode ledger-only` immediately before Policy Watch. It does not collect evidence or publish current JSON/UI. It may append one keep-FIRST receipt only through `engine.ledger_lane.nightly_advance_enabled()`.

`config/dag.yml` mirrors real execution; it is not an executor.

## CI ruling

Every new suite must be executed by one canonical logical job in `.github/ci/legacy-jobs.yml` and triggered through `.github/workflows/ci.yml`. W1 waits until all current owners of the shared manifest path are released. It may not bypass the hold with another workflow, job, planner or unrun-test exemption.

## Authority ceiling

Every W1 artifact remains:

```json
{"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
```

A later request for ranking, gating, sizing or trading is a new Chairman/Sol decision after issue #6794 evidence and the existing promotion gauntlet.