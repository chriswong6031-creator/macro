# K3E-0 Market Response Model Specification

## 1. Model target

The market side describes how owner-native market observations evolve around a
lawfully timed expectation observation. It does not infer a single true market
belief and does not replace the existing residual-alpha, DRL, options, event or
Market OS planes.

```text
MarketResponseView
  subject/security refs
  anchor expectation observation ref
  lawful availability session
  raw return refs
  peer/factor/residual refs
  volume/liquidity refs
  options refs (optional)
  attention/positioning refs (optional)
  horizons[]
  degradation
  estimability
  authority
```

The view references exact owner versions. It may cache a reproducible derived
research artifact only if an accepted consumer proves a need; it does not mint
a price or residual truth store.

## 2. Alignment law

1. Map the expectation observation to the first market session at which it was
   lawfully observable under the preregistered availability rule.
2. When only collection date is known, do not pretend pre-open, intraday or
   after-close knowledge. Use the conservative next-session rule defined by
   EVAL-0.
3. Preserve holidays, half-days, halts and listing boundaries from the canonical
   calendar/market owners.
4. Record the anchor security/share class and all peer/factor membership as
   known at the anchor clock where the owner supports it.
5. Do not select the event window after viewing the result.

## 3. Response vector

For each preregistered horizon, keep independent legs:

```text
raw_return
market_relative_return
peer_relative_return
factor_or_DRL_residual
realized_volatility
volume_or_turnover_surprise
liquidity_response
gap_and_intraday_path (only when source clocks permit)
options_distribution_change (optional)
attention_or_positioning_change (optional)
```

Each leg carries input refs, method/version, included/excluded denominator,
coverage and estimability. Raw return is not silently substituted when a
residual leg is unavailable. Peer basis and membership are explicit, including
the peer-basis retune condition inherited from
`DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER`.

## 4. Dynamic-response candidates

Research may compare, in order:

- fixed windows and cumulative response curves;
- distributed-lag/local-projection baselines;
- robust state-space response with time-varying noise;
- survival/time-to-assimilation descriptions; and
- family-specific response models accepted by MAS-118.

No method is universal by default. Horizon, family and coverage determine
estimability. Change-point or impulse-response language remains descriptive
unless causal identification is separately established; K3E must not revive
`DNR:KILL-CAUSAL-DAG-ALPHA` or a killed mean-reversion classifier by renaming it.

## 5. Missingness and adverse results

- No options prerequisites → options leg `UNESTIMABLE`, not zero.
- No lawful same-day clock → intraday/gap legs `UNESTIMABLE`.
- Thin peer set or unknown membership → peer leg `UNESTIMABLE`.
- No owner residual → residual leg `UNESTIMABLE`; raw return stays separately
  observable.
- Halt, corporate action or identity ambiguity → affected horizons are
  excluded with reason; no silent winsorization.
- A null, reversed or unstable market response is retained and evaluated.

## 6. Authority

The response vector may contextualize an expectation change. It does not
originate a candidate, predict return, rank securities, set entry timing, size
positions, train Prophet or claim that price is wrong.
