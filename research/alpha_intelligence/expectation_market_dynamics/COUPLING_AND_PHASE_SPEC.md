# K3E-0 Coupling, Assimilation and Phase Specification

## 1. The object is a vector, not a label

Expectation/market coupling is a temporal relationship between a typed
expectation surface and typed market-response legs. The internal object is:

```text
ExpectationMarketDynamics
  expectation_ref
  market_response_ref
  clock_alignment
  expectation_axes
  response_axes
  coupling_axes
  unresolved_conflicts
  failed_or_unavailable_gates
  next_observables
  estimability
  method/version
  authority
```

It never owns the referenced source facts. It cannot be reduced to one
`gap_score`, belief score, opportunity score or fair value.

## 2. Coupling axes

At minimum, research keeps the following independently visible:

| Axis | Question | Example measures |
|---|---|---|
| Expectation direction | Are near/far-horizon source expectations rising, falling, disagreeing or rolling? | robust slopes, change points, horizon shape |
| Expectation breadth | Is change supported across the reported population? | analyst denominator, range/dispersion, contributor support where licensed |
| Response magnitude | How large is each owner-native response leg? | raw/relative/residual curves |
| Response timing | When does a detectable response occur? | first lawful window, lag curve, time-to-threshold with fixed rule |
| Response persistence | Does the response persist, reverse or remain unresolved? | fixed future horizons, survival description |
| Cross-channel agreement | Do price, volume, options and attention agree? | decomposed signs/states; never fused score |
| Residual conflict | Does raw response differ from peer/factor residual? | explicit dual read |
| Information quality | Are clocks, population, identity, rights and correction sound? | degradation vector |

## 3. Descriptive phase projection

A product may eventually render a compact phase only as a lossy projection of
the complete vector. Candidate vocabulary is descriptive, non-ordinal and
method-versioned:

- `PRE_RESPONSE`: expectation movement observed; response windows not mature.
- `PARTIAL_ASSIMILATION`: some response legs moved while material expectation
  or channel disagreement remains.
- `BROAD_ASSIMILATION`: preregistered observable legs broadly moved with the
  expectation change; no claim of full information efficiency.
- `CONTESTED`: expectation sources or market channels materially disagree.
- `REVERSING_OR_REPRICING`: later expectation/response observations reverse the
  earlier path; no automatic mean-reversion thesis.
- `STALE_OR_EXHAUSTED`: no current change and response windows matured under a
  fixed rule; not a sell signal.
- `UNESTIMABLE`: required support is insufficient.

These are not five mutually exhaustive market regimes; several internal axes
can coexist. The projection prints its method, mature windows, denominator,
dominant degradation and the strongest unresolved fact.

## 4. Temporal and dynamic estimands

EVAL-0 must choose estimands before fitting. Candidate estimands include:

- probability a preregistered response leg crosses a fixed materiality band by
  horizon, conditional on observable expectation change;
- time to first mature, directionally consistent response;
- persistence/reversal of the response curve at fixed horizons;
- incremental information of expectation dynamics beyond price-only and
  last-observation baselines; and
- calibration of declared `UNESTIMABLE` versus observed support failures.

These are associational unless a separate identification design earns causal
language. Outcome windows are immutable after preregistration.

## 5. Conflicts are data

The object must lead with a dual read when raw price, residual, options or
expectation components disagree. It prints:

```text
WHAT IS OBSERVED
WHAT IS INFERRED
WHAT THE MARKET APPEARS TO REFLECT
STRONGEST UNRESOLVED FACT
FAILED / UNAVAILABLE GATES
NEXT OBSERVABLE
ENTRY AVAILABILITY
```

The language above is inherited from the authenticated Market Ontology K3
rider. It does not grant K3E entry-timing authority; `ENTRY AVAILABILITY` is a
descriptive prerequisite receipt only.
