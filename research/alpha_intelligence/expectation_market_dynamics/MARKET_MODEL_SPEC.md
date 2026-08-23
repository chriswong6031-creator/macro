# Market Model Spec

## Objective

Describe the market-response process around expectation change without creating a
new residual, valuation, or trade-authority plane.

## Required components

1. raw price path by lawful horizon windows;
2. broad market contribution where already owned;
3. sector / peer contribution where already owned;
4. issuer residual path from reused residual engines;
5. rerating context where existing valuation inputs are lawful and point-in-time
   honest;
6. options-implied uncertainty / distribution where the current options plane
   supports it.

## Reuse law

- residuals come from existing DRL / residual-alpha owners only;
- options uncertainty comes from existing options owners only;
- no K3E path may recompute these just because doing so is convenient.

## Honest degradations

If one or more components are missing, K3E emits the available surface with an
explicit dominant degradation state. Example lawful states:

- `RAW_ONLY`
- `RAW_PLUS_RESIDUAL`
- `RAW_PLUS_OPTIONS`
- `DEGRADED_NO_RESIDUAL`
- `DEGRADED_NO_OPTIONS`

## Forbidden shortcuts

- no "fair value gap";
- no universal rerating score;
- no use of later event outcomes to define the earlier market state.
