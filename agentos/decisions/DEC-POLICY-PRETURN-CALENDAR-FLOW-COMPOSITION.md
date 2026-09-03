---
key: POLICY-PRETURN-CALENDAR-FLOW-COMPOSITION
question: "How should Mastermind model recurring OPEX/month-end turns and fast policy jawboning without creating a second calendar or a calendar-driven trade signal?"
answer: >
  Extend the existing Rates & Inflation, Policy-Shock, Options and Rebalance/Liquidity
  owners with one deterministic policy_turn_clock.v1 composer. The composer preserves
  independent event, options-support, Treasury-liquidity, futures-roll, rebalance and
  source-freshness axes; it may summarize support formation, stability, pinning,
  rolloff, catalyst override, month-end dominance, mixed evidence or unknown state.
  Calendar proximity alone carries no direction or capital authority. Official actor
  and Treasury observations accrue as point-in-time keep-FIRST vintages, and the same
  machine artifact serves the Policy Watch user experience and governed machine
  consumers. Yield momentum remains owned by existing RIC F3 PR #6721.
rationale: >
  The Chairman's observed pattern is economically plausible only as a compound inventory,
  liquidity and catalyst clock. Options expiration can remove stabilizing long-gamma/pin
  inventory or remove destabilizing short-gamma inventory; month-end can add Treasury
  settlements, TGA changes, bond-index extension, index/pension rebalancing and closing
  auction flows; quarterly futures rolls apply only in March, June, September and
  December; early-month cash and replacement books are conditional rather than guaranteed;
  and macro releases can dominate every mechanical flow. Existing repository organs
  already own each underlying truth but no current composition answers whether support is
  building, expiring, being replaced or being overwhelmed. A deterministic composer over
  those owners gives the user an anticipatory, falsifiable transition read without
  laundering a decayed turn-of-month anomaly, a dealer-sign assumption or policy narrative
  into a buy/sell signal. One canonical artifact also prevents UI prose and machine context
  from drifting into separate interpretations.
alternatives:
  - option: "Create a universal buy-at-month-start and de-risk-after-OPEX signal."
    why_not: >
      The unconditional turn-of-month anomaly is sample- and era-dependent, modern
      in-repo studies withhold a forward edge, and options expiration can remove either
      stabilizing or destabilizing inventory. A directional calendar rule would be both
      empirically fragile and contrary to the existing no-calendar-sizing authority law.
  - option: "Create a new standalone policy calendar and market-structure database."
    why_not: >
      `engine/event_calendar.py`, Macro Release Intelligence, `engine/opex.py`, the
      ThetaData options plane, Rebalance/Liquidity Transmission and Treasury Watch already
      own these facts. A new database would duplicate event, correction, calendar and
      evidence authority and would inevitably drift from the production owners.
  - option: "Use an LLM to predict when Bessent, Warsh or the administration will intervene."
    why_not: >
      Discretionary private timing and secret coordination are not identifiable from
      public evidence. An LLM may later summarize receipt-grounded interest and rhetoric
      changes, but it cannot invent schedules, infer private locations or originate a
      response probability/state that overrides deterministic evidence.
  - option: "Wait for RIC F3 and every later intelligence layer before shipping anything."
    why_not: >
      The official actor/liquidity clock and monthly support/rolloff composition are
      independently useful without yield-cause decomposition. Building them as W1 creates
      immediate product value while preserving a one-way seam for later RIC and
      cross-asset inputs.
evidence:
  - "Chairman Chris explicitly approved initiation and requested robust monthly/OPEX/futures integration in the active Sol session on 2026-09-03."
  - "Protected procedure was pinned to mastermindx-market-intelligence/Mastermind@793e75639911f21dae9c90a77c3a5dbf4b37cbb0; Skillpack schema/version/bootstrap are compatible."
  - "Macro issue #6787 is the sole canonical W1 implementation carrier and records WAITING_CAPACITY / needs_placement, receiver NONE, START NONE, effect NONE."
  - "Macro PR #6721 is the existing RIC F3 yield-momentum carrier at observed head 0d7ff3db29cd95c5296a8fd5d33d3b0494ce6647 and remains open/draft/unmerged/release-blocked."
  - "Macro PR #6658 remains open/draft and owns the colliding .github/ci/legacy-jobs.yml path; the RIC F3 worker was continued in PARK on Slack carrier C0BSBM78V1N/1788266777.058699."
  - "DEC:RIC-CANONICAL-COMPOSITION-BOUNDARIES assigns scheduled events, release truth, OPEX, options, transmission, policy, risk and learning to existing owners and denies calendar rank/gate/size/trade authority."
  - "engine/event_calendar.py, engine/opex.py, engine/opex_risk.py, engine/options_surface.py, engine/rebalance_calendar.py, engine/rebalance_pulse.py and engine/treasury_watch.py provide the canonical W1 inputs."
  - "research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md and reports/artifacts/options_opex_vanna_charm_summary.md reject a robust unconditional post-OPEX direction while preserving measured concentration/vanna/volatility context."
  - "reports/d2-rates-calendar-flows-phase0.md finds measurable month-end Treasury duration extension while generic auction and pension-rebalance hypotheses fail, requiring asset- and mechanism-specific treatment."
  - "research/REBALANCE_LIQUIDITY_TRANSMISSION_MASTERPLAN_BY_FABLE.md explicitly keeps turn-of-month direction dead and treats rebalance observations as display/context rather than bottom calls."
affects:
  - "WS:RATES-INFLATION-COMMAND"
  - "Policy Transmission & Pre-Turn Command"
  - "Rebalance & Liquidity Transmission"
  - "Policy-Shock Regime"
  - "engine/event_calendar.py"
  - "engine/opex.py"
  - "engine/opex_risk.py"
  - "engine/options_surface.py"
  - "engine/rebalance_calendar.py"
  - "engine/rebalance_pulse.py"
  - "engine/treasury_watch.py"
  - "site/policy_turn_clock.json"
  - "site/policy_watch.html"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-09-03
---

# Binding ruling

## One canonical composition

`policy_turn_clock.v1` is a deterministic composition and projection. It does not own the underlying scheduled event, release, OPEX, options, futures-price, rebalance, TGA, yield, market-state, forecast or trade facts. It carries exact owner references, availability clocks, assumptions, corrections and gaps.

The glance state preserves this closed vocabulary:

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

The state is not a score and cannot be consumed as a position instruction. `VOLATILITY_WINDOW_OPEN` requires independent realized confirmation from an existing owner; the expiration date alone can reach at most a support-rolloff watch. A calendar-eligible month-end without an observed non-quiet Rebalance Pulse cannot become dominant.

## Monthly mechanism ruling

The current product must communicate these distinctions:

1. Into OPEX, measured long-gamma, pin, front-cycle concentration and vanna/volatility conditions can stabilize price. The date does not establish the sign of dealer inventory.
2. Expiration can remove stabilizing support or remove destabilizing short-gamma exposure. “Post-OPEX” therefore means a conditional inventory transition, not an automatic correction.
3. Replacement-book evidence must be observed from comparable current and prior option-surface rows. Missing evidence is `unknown`, not `absent`.
4. Month-end may combine equity/index rebalancing, bond-index extension, Treasury operations/settlements, TGA movement and closing-auction liquidity. Those mechanisms can point in different asset directions.
5. Major equity-index and Treasury futures rolls are quarterly. Ordinary months are `not_applicable`; a scheduled window is not active without source-owned volume/open-interest progress.
6. High-impact releases and policy events can override mechanical support. The product must show catalyst dominance and the exact collision instead of retaining a stale seasonal label.
7. Early-month support must be evidenced through current liquidity, replacement inventory, breadth, volatility-control or other accepted owners. It is not inferred merely because the date changed.

## Actor and policy ruling

Current actor location is shown only during a bounded official event window. After the window, the product retains `last_verified_location` and reports current location unknown. A source conflict is visible and unresolved rather than silently selected.

Actor interests, tools and constraints can later support a receipt-grounded response-window graph. They cannot prove private coordination or a precise discretionary action time. Retrieved statements and model summaries remain context, not authority.

## Authority ceiling

The W1 contract always publishes:

```json
{"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
```

No calendar, official-event, OPEX, futures-roll, rebalancing, TGA or model-generated field may bypass existing Prophet/portfolio promotion and authority law. A future request to wire any state into ranking, entry, risk or size is a new Sol/Chairman decision after point-in-time replay and forward promotion evidence.

## Execution sequence

1. Land the records-only architecture/spec/plan carrier after exact-head validation and independent review.
2. Canonical capacity placement binds one eligible CTO Sol receiver to issue #6787.
3. The worker posts pickup and separate START receipts after a fresh path/collision census.
4. W1 returns one immutable source-to-artifact-to-browser/machine PR for Sol review.
5. Source breadth, yield/cross-asset decomposition, actor reaction functions and calibrated posture remain separate later waves.
