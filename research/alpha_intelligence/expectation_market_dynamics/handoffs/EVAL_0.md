# EVAL-0 Commission — Model and Evaluation Preregistration

## ROUTE

`analysis` — one preregistration PR, then stop. No model fitting or outcome look.

## Mission

Instantiate the immutable evaluation protocol described in
`../EVALUATION_PREREG.md` before advanced model selection or return-outcome
inspection. Freeze boring baselines, targets, time eras, missingness,
walk-forward design, episode-honest N, multiple-testing and promotion law.

## Required bootstrap

Re-pin current Skillpack, Macro `main`, Eval OS workstream/decisions, current
forward ledgers, MAS-118/MAS-119 and any expectation/evaluation PRs. Read the
current evaluation schemas before deciding where the protocol registration
belongs. Reuse the accepted Eval OS registry/ledger; do not create a K3E grader.

## In scope

- Fix unit/population and distinct-episode law.
- Define exact chronological eras from what current data can honestly support;
  if history is insufficient, freeze maturity rules rather than invent dates.
- Freeze lawful availability/session alignment and embargo/purge rules.
- Declare primary/secondary estimands and horizons.
- Declare price-only, last-observation, simple expectation and owner-residual
  baselines.
- Bound challenger families/hyperparameter search before tuning.
- Freeze metrics, coverage/abstention audit, subgroup/era analysis,
  multiplicity control and allowed final looks.
- Freeze minimum support and promotion thresholds, including baseline parity,
  calibration, stability and red-team requirements.
- Commit a deterministic machine-readable protocol plus human explanation and
  content hash using the existing evaluation owner seam.

## Out of scope

No source collector, model fitting, hyperparameter tuning, outcome inspection,
historical backfill, phase generation, rank, Prophet, Market OS or promotion.

## Acceptance

- Protocol validation and hash reproduction pass.
- The protocol explicitly precedes advanced tuning/outcome inspection.
- Missingness, `UNESTIMABLE`, full-population coverage and adverse/null results
  are first-class.
- Effective N counts episodes, with issuer/episode clustering and panel
  exclusions named.
- Motivating exemplars/current regime coverage is a mandatory conclusion gate.
- One records-only PR lands and leaves every authority field false.

## Stop and return

```text
STATUS
PROTOCOL ID/VERSION/HASH
EXACT BASE/HEAD/PR/MERGE
UNIT/POPULATION
ERAS
ESTIMANDS/HORIZONS
BASELINES/CHALLENGERS
METRICS/MULTIPLICITY
MISSINGNESS/EFFECTIVE-N LAW
PROMOTION THRESHOLDS
VALIDATION
GAPS
DEVIATIONS
```
