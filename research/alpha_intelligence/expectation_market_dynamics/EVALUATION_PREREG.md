# EVAL-0 — Frozen Evaluation Preregistration

Status: `FROZEN_BEFORE_ADVANCED_TUNING`

Registration: `K3E-EVAL-0-V1`

Machine record:
`research/alpha_intelligence/expectation_market_dynamics/eval0_preregistration.v1.json`

Schema:
`contracts/research/k3e_expectation_market_dynamics_evaluation_prereg.v1.schema.json`

Canonical JSON SHA-256:
`986ec117e8517b77e8dece565fd9d9dc169e758beb9d1619acc443e061ef87fd`

The digest uses UTF-8 JSON with recursively sorted keys, compact separators, and
`ensure_ascii=false`. The pretty-file SHA-256 is
`664f03b651892c86af0998d993c0a514255414b35e93b240fe2e8c0a4c55c3a7`.
The canonical registration is the JSON record, not this prose rendering.

## What this freeze does

EVAL-0 fixes the competition before any advanced K3E challenger is selected or
tuned. It defines:

- eligible point-in-time observations and clocks;
- population, eras, episodes, dependence, and honest effective N;
- targets and censoring;
- boring baselines;
- challenger and trial budgets;
- metrics, calibration, abstention, and multiple testing;
- motivating-case and current-regime coverage;
- advance, retain, revise, kill, and `UNESTIMABLE_AS_PROGRAM` outcomes.

No advanced challenger result was inspected to create this registration. The
registration contains no model result. It is an immutable research contract
inside the existing Evaluation OS boundary; it is not a second evaluator,
result store, score, ranker, lifecycle, or publication plane.

## Activation and point-in-time boundary

Prospective eligibility begins at the first NYSE session open strictly after an
`origin/main` commit contains the exact canonical registration digest. A later
activation receipt must bind the accepted commit, digest, merge timestamp, and
resolved NYSE session. Rows before that boundary may support declared
retrospective development, validation, and holdout work, but may never be
relabeled prospective.

At any decision cutoff, an input is eligible only when both the owner-native
availability and the K3E/system observation clock are no later than the cutoff.
Source-effective, source-published, provider-observed, and system-observed clocks
remain distinct. A late arrival becomes usable only when observed; its earlier
economic date cannot cure lookahead. Corrections use the version known at the
cutoff and preserve superseded as-known bytes.

Fiscal-period identity stays separate from market-session time. Rolling from one
fiscal period to another is lineage, not an analyst revision. Forward labels
start strictly after the decision cutoff. The maximum registered 63-session
horizon determines a 63-session purge and embargo.

## Population and eras

The primary cohort is point-in-time US primary-listed common equity resolved
through the canonical issuer/security identity owner. Ticker shape is never an
identity rule. ETFs, ETNs, funds, preferreds, warrants, units, and shells without
an operating-issuer mapping are excluded and counted. Lawfully observable
delistings remain; missing delisted coverage is printed. ADRs and non-US names
are separate descriptive cohorts until they meet their own preregistered episode
floor.

The eras are fixed:

| era | interval | use |
|---|---|---|
| Development | 2012-01-03 through 2018-12-31 | fit/features; every attempt counts |
| Validation | 2019-01-02 through 2022-12-30 | select one final challenger per target/horizon |
| Locked retrospective holdout | 2023-01-03 through 2026-08-21 | one final evaluation only |
| Prospective shadow | activation boundary onward | append-only natural-time corroboration; no retuning |

The retrospective holdout is locked by this program; it is not represented as
an unknowable historical tape. If lawful vendor history does not cover the fixed
eras, the result is reduced coverage or `UNESTIMABLE_AS_PROGRAM`, not a
post-hoc date change.

## Episode and effective-N law

The inferential unit is a distinct issuer episode, not observations, rows, days,
or repeated fires. Episode identity binds issuer, metric, horizon or fiscal
period, and episode-start NYSE session. Twenty quiet sessions separate revision
episodes. A pure fiscal rollover does not start one. Overlapping owner-native
events for one issuer collapse to one event cluster for inference.

Uncertainty clusters by issuer, revision episode, and event cluster, with a
date-block sensitivity. Minimum promotion-bearing N is 100 distinct issuer
episodes overall and 25 per claimed subgroup. Row count never substitutes for
episode N.

## Registered targets

| ID | question | horizons | initial promotion status |
|---|---|---:|---|
| T1 | next same-period revision direction | 1/5/21/63 sessions | eligible after SRC-A1 |
| T2 | next same-period revision arrival | 5/21/63 | eligible after SRC-A1 |
| T3 | revision-cluster onset | 10/21 | eligible after SRC-A1 |
| T4 | same-period consensus change | 21/63 | eligible after deterministic surface |
| T5 | same-measure dispersion direction | 21/63 | eligible after deterministic surface |
| T6 | owner-native residual market response | 5/21/63 | reserved; MKT-1 required |
| T7 | expectation/market lead-lag state | 21/63 | reserved; EXP-1/MKT-1/CPL-1 required |
| T8 | next descriptive phase transition | 21/63 | reserved; PHASE-1 required |

T1 treats unchanged scheduled snapshots as `FLAT`; collection failures and 429s
are not `FLAT`. T2 and T3 preserve right-censoring. Snapshot-level and
contributor-level clusters never pool. T4 stays on owner-native metric, units,
currency, and basis; percentage transforms cannot divide through negative or
near-zero EPS. T5 never substitutes high-low range for standard deviation. T6
reuses DRL/residual-alpha output or degrades to `RAW_ONLY`; K3E never recomputes
a residual. T7/T8 remain non-promotion targets until their dependency contracts
exist.

## Boring baselines

Nine baselines are registered before challengers:

1. no change;
2. latest cutoff-eligible consensus;
3. deterministic trailing-30-day revision summary;
4. deterministic trailing-90-day revision summary;
5. fresh median with stale observations still counted;
6. the later frozen REV-1 deterministic wave;
7. development-only historical base rate;
8. market/sector-only components for coupling questions;
9. revisions-only components for coupling questions.

The comparison baseline for a target is the strongest eligible baseline, not
the easiest one to beat. Baselines consume zero challenger trials; changing a
baseline after seeing outcomes requires a new registration version.

## Challenger and multiple-testing budget

The entire EVAL-0 v1 family has at most 64 trials:

| challenger family | maximum trials |
|---|---:|
| regularized linear/logistic or discrete-time hazard | 12 |
| gradient-boosted trees | 16 |
| Bayesian change-point | 10 |
| latent state-space | 10 |
| point-process cascade | 8 |
| sequence model | 8 |

A trial identity includes model family, target, horizon, feature set,
preprocessing, hyperparameters, and seed policy. Failed jobs, discarded feature
sets, ablations, and manual threshold changes count. Analyst-skill weighting is
not registered in v1 because no accepted contributor-level rights/training
contract exists.

All promotion-bearing challenger/target/horizon comparisons share FDR family
`k3e_expectation_market_dynamics_v1`. Benjamini-Yekutieli at `q=0.10` applies
across the full family because target/horizon losses are dependent. A subgroup
cannot rescue a failed overall result; unregistered comparisons are exploratory
and count toward any later budget if reused.

## Metrics and uncertainty

- Classification: multiclass log loss first, Brier score second.
- Arrival/onset survival: IPCW integrated Brier score with censoring preserved.
- Continuous targets: MAE and pinball loss, stratified by owner-native metric,
  units, currency, and the positive/negative/near-zero EPS regime.
- Calibration: reliability curve, ECE, intercept, and slope.
- Abstention: risk-coverage curve plus error and denominator by abstention reason.
- Uncertainty: issuer-episode clustered 95% bootstrap interval with date-block
  sensitivity.

Ranking metrics may be reported only as descriptive diagnostics. EVAL-0 grants
no ranking authority.

## Coverage gate

At least 60% of eligible observations and 60% of named motivating cases must be
answered without hiding abstentions. Every conclusion leads with the current
regime, named motivating cases, missing/delisted panel members, rights losses,
and episode N.

The frozen motivating cases are:

- AAPL current live event path;
- MRNA post-June-2026 revision episode;
- NVDA 2023 as a PIT-availability negative control;
- GOOG/GOOGL dual-class issuer/security identity.

No expected directional winner is assigned to them. The hostile set covers thin
coverage, negative/near-zero EPS, fiscal roll, provider 429, market-versus-sector
baseline conflict, no-options coverage, and correction/supersession.

## Decision law

`ADVANCE_RESEARCH_ONLY` requires all of the following:

- exact digest was frozen on `origin/main` before eligible observations;
- the strongest baseline is beaten on primary loss in validation and locked
  holdout;
- relative primary-loss improvement is at least 5% in both eras;
- the issuer-episode clustered 95% interval excludes zero;
- BY-FDR `q <= 0.10` across the whole family;
- overall and subgroup episode floors pass;
- coverage/current-regime/casebook gates pass without hiding abstentions;
- calibration and abstention do not materially regress;
- independent review finds no surviving leakage, rights, identity, correction,
  denominator, or use-case blocker.

Retrospective passage is research-only until a naturally accrued prospective
shadow corroborates it and a new explicit promotion decision is made. EVAL-0
itself can never grant product, Prophet, fair-value, rank, gate, size, or trade
authority.

Retain the boring baseline, revise under a new preregistration, or kill the
specific construction when the holdout does not improve, cluster/date-block
sensitivity removes the edge, leakage is required, coverage selection explains
the result, the trial budget is exceeded, or motivating/current cases are
systematically refused while easy historical cases drive the win.

Return `UNESTIMABLE_AS_PROGRAM`, `RIGHTS_BLOCKED`, or
`INSUFFICIENT_EPISODE_N` when lawful PIT data, identity/clocks, episode N,
coverage, or reproducible rights cannot support the question. These are correct
first-class results.

## Null, adverse, and amendment law

Every registered target, attempted trial, abstention reason, failure, null,
adverse subgroup, and rights exclusion is reported. Missing is never zero;
rights-blocked is never imputed; censored is never negative. No winner may be
selected by suppressing failed configurations.

This v1 record is immutable once accepted. Any change requires a new version,
new digest, explicit reason and diff, explicit supersession, and a new forward
boundary. Outcomes already seen remain attached to the old registration and
cannot be relabeled under the amendment.

## Validation receipt

Validate the schema and instance with Draft 2020-12 plus a format checker. The
accepted command must print:

```text
errors 0
summary K3E-EVAL-0-V1 8 9 64
```

EVAL-0 stops at this freeze. It does not train, tune, grade outcomes, register a
QLedger claim, build a product surface, or start the next wave.
