---
key: HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED
claim: >
  Current historical Mastermind routing receipts do not identify the counterfactual
  performance of unchosen workers or models because assignment is deliberately conditioned
  on task context and the estate does not yet log a complete eligible action set with
  nonzero assignment probabilities and demonstrated overlap for the target cohort.
falsifier: >
  Run `rg -n "assignment_probability|propensity|eligible_actions|candidate_set|logging_policy"
  control_plane/model_router.py control_plane/executive_runtime.py
  config/executive_worker_routes.json` at the cited Mastermind revision and inspect an
  Executive export for the proposed cohort. A current owner-native receipt that, before
  assignment, records every eligible alternative, its exact positive assignment probability,
  the chosen action, context available at decision time, and empirical overlap sufficient for
  the stated estimand disproves this claim for that cohort.
so_what: >
  Never rank workers/models or revise routing from raw retrospective success, speed or
  acceptance rates. Treat current history as descriptive or adjusted association only;
  prospective logging, bounded exploration/randomization, overlap diagnostics and explicit
  causal assumptions are required before an off-policy or causal route claim can be admitted.
kind: constraint
verified_at: 2026-08-30
verified_by: >
  Mastermind@5a7046c46046a2ecf597c849aaab914b4f7cd5e1
  control_plane/model_router.py, control_plane/executive_runtime.py and
  config/executive_worker_routes.json; architecture review under
  mastermind-outcome-learning-policy-calibration-20260830-sol-001
scope:
  - mastermind
  - mastermind/control_plane/model_router.py
  - mastermind/control_plane/executive_runtime.py
  - mastermind/config/executive_worker_routes.json
  - organizational-learning
confidence: verified
---

## What is observed today

Current route evidence can preserve task kind, risk, ambiguity, required capabilities, exclusions,
policy version, execution profile, ordered model aliases and reason codes. Executive OS can preserve
the chosen placement, worker, attempt, times, errors, results and review relationships. Those facts
are valuable operating telemetry.

They are not the missing potential outcomes. A harder or more ambiguous job is intentionally more
likely to be routed to a stronger/scarcer lane. Only the selected worker/model is run. Differences in
first-pass acceptance, repair loops, elapsed time or production proof therefore combine at least:

- task and program case mix;
- route/worker effect;
- provider availability and quota;
- handoff quality and architecture maturity;
- reviewer topology and intervention;
- external/admin/CI waiting;
- downstream consequence and luck.

A raw table such as `success_rate by model` cannot separate these components.

## Why estimator names do not close the gap

Inverse-propensity and doubly robust estimators require a defined logging policy and support for the
actions being evaluated. They also rely on declared assumptions about measured confounding,
well-defined interventions, time ordering, missingness and censoring. A fitted propensity model over
deterministic historical assignments is not equivalent to a known assignment probability, and a
reward model cannot identify alternatives that never occur in comparable contexts.

Where hidden confounding remains plausible, a study must report sensitivity or partial-identification
bounds and lower its evidence grade. `DOUBLY_ROBUST` is not itself a causal grade.

## Minimum future route-learning receipt

Before assignment, the owner must record:

1. the complete action set remaining after hard authority/capability exclusions;
2. exact policy and capacity snapshot versions;
3. chosen action and assignment method;
4. assignment probability for every supported action, or a typed reason why no counterfactual
   support exists;
5. context available at decision time, excluding post-outcome information;
6. ex-ante outcome expectations and guardrails;
7. randomization or exploration unit where applicable.

Exploration is permissible only among near-equivalent eligible routes for bounded, reversible,
noncritical work under a separately approved policy. No otherwise-ineligible worker/model becomes
eligible merely to improve statistical support.

## Consequence for current architecture

The first prospective causal consumer should be a lower-risk handoff-quality policy, not worker/model
routing. Routing can follow after the required decision-time logging, overlap and canary machinery are
proven. Until then, route history may guide research priorities but cannot grant worker authority,
change policy or support a leaderboard.