# Expectation <-> Market Dynamics / Price <-> Expectations

Date: 2026-08-23
Status: K3E-0 architecture freeze
Authority at this stage: research / records / context only
Canonical owner: WS:ALPHA-INTELLIGENCE-INTEGRATION wave K3

## Outcome

Build one institutional-grade descriptive intelligence plane that can reconstruct
point-in-time expectation trajectories, reconstruct market-response trajectories,
measure how those processes interact through time, and surface honest phase
states without claiming fair value, ranking authority, trade authority, or
guaranteed alpha.

The cold-reader test for this freeze is simple:

- a fresh operator can start `SRC-A1`, `VEND-0`, or `EVAL-0` without deciding
  ownership, storage, clock semantics, or product authority;
- no owner-native truth plane is duplicated;
- `UNESTIMABLE` remains a first-class successful result.

## Frozen architecture

```text
OWNER-NATIVE TRUTH
  expectation observations (revisions owner lane)
  event facts (Earnings / Bio / Defense owners)
  financial facts and revisions (FIF owners)
  price / corporate actions / residuals (existing price and DRL owners)
  options-implied uncertainty (existing options owners)
  identity / issuer-security mapping (existing identity owners)
      |
      v
DERIVED K3E READ-MODEL
  expectation surface
  market-response surface
  coupling / lag / disagreement / phase
      |
      v
DESCRIPTIVE PROJECTIONS
  Security / Terminal / research consumers
```

K3E is a derived read-model semantics lane. It is not:

- a new truth store;
- a new event system;
- a new identity plane;
- a new residual engine;
- a new ranker or score plane;
- a new publication or lifecycle plane.

## Binding laws

1. `DEC:MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE` remains binding.
2. MAS-119 owns cross-domain `ExpectationBaseline` federation.
3. MAS-118 owns family-specific incorporation science.
4. K3E remains descriptive-first. Predictive authority requires preregistration,
   model comparison, and explicit later promotion.
5. Historical expectation state must be point-in-time honest. Current consensus
   backfilled into historical dates is forbidden.
6. `UNESTIMABLE`, `UNAVAILABLE`, `STALE`, `LOW_COVERAGE`, and
   `RIGHTS_BLOCKED` are lawful outputs, not errors to hide.
7. Any aggregate must expose denominator, dominant degradation, and the clocks
   of the owner-native observations it consumed.

## Capability target

For any covered security and cutoff, the system should eventually answer:

1. What observable expectations were:
   EPS / revenue / margin / KPI expectations by horizon, coverage, freshness,
   dispersion, revision breadth, and change-point state.
2. What the market did:
   raw return path, residual response where lawful, rerating context, and
   options-implied uncertainty where lawful.
3. How the two processes interacted:
   lead / lag, synchronization, divergence, stalling, disagreement evolution,
   and whether the question is estimable at all.
4. What visible descriptive state is most honest:
   market leading, expectations leading, synchronized rerating, expectations
   continue / market stalls, market extends / expectations stale, opposing sign,
   high disagreement, transitioning, or unestimable.

## Descriptive phase law

K3E phases are descriptive summaries over emitted sub-components. They do not:

- imply fair value;
- imply target price or sizing;
- imply that one state is automatically tradable;
- collapse all evidence into one hidden scalar.

Every emitted state must preserve:

- what is directly observed;
- what is inferred from owner-native observations;
- what the market appears to reflect;
- strongest unresolved fact;
- failed / unavailable gates;
- next observable.

## Wave order

K3E-0 is records only. No runtime, model, or product mutation is authorized here.

After K3E-0 is merged and no new blocker appears:

1. `SRC-A1` - raw prospective expectation observation accrual in the existing
   revisions owner lane.
2. `VEND-0` - institutional estimates vendor bake-off.
3. `EVAL-0` - preregistered evaluation protocol before advanced tuning.

Later waves depend on those three:

- `EXP-1` expectation surface from lawful accrual;
- `MKT-1` market-response read-model over reused residual / options planes;
- coupling / phase implementation only after both sides are real and the
  preregistration exists.

## Explicit non-goals

This freeze does not:

- implement any runtime lane;
- start model tuning;
- modify current revisions collectors;
- build a vendor adapter;
- create a universal expectation schema;
- start MAS-118 or MAS-119 on their behalf;
- alter Prophet, Radar, Market OS, or Security State authority.
