# W5 preregistration — descriptive method evaluation and threshold calibration

`child: macro-flow-observatory-v2-w5-method-calibration-20260902-fable-001`
`preregistered_by: Fable principal (program macro-flow-observatory-v2-program-20260902-sol-001)`
`frozen BEFORE any evaluation run — the harness may not start until this file is committed`
`authority: context_only — no future-return optimization anywhere in this program`

## 1. Question

Which relative-flow normalization method and which state thresholds best serve the
DESCRIPTIVE objective for the Flow Observatory: stable, interpretable, outlier-resistant
context states with an honest neutral band — evaluated on point-in-time history, never
on forward returns.

## 2. Candidates (frozen definitions)

All candidates consume the same causal per-entity flow series (the 主力 demeaned-rate
plane and the southbound aggregate) and emit a per-session standardized value v_t.

- **M0 (incumbent benchmark, #3561)**: slope_z of cumulative flow over the window with
  trailing-mean causal demeaning (126d names/themes, 252d aggregate) and 0.25×
  expanding-std volatility floor. Never removed; the benchmark whatever wins.
- **M1 winsorized**: M0 with the demeaned inputs winsorized at their causal rolling
  2.5th/97.5th percentiles (window 126) before the slope_z.
- **M2 median/MAD**: v_t = (x_t − rolling_median_126) / (1.4826 × rolling_MAD_126),
  with the same 0.25× expanding floor applied to the MAD scale.
- **M3 causal percentile**: v_t = 2×(rolling_percentile_rank_126(x_t) − 0.5) mapped to
  a σ-like scale via the normal quantile function (probit), floored identically.

## 3. Metrics (frozen; all computed per lens: themes n=22, names n≈1500, southbound)

Over all available PIT history (the flow_hist grid ~260 sessions; southbound 2014→):

1. **State distribution**: share of sessions each of the five velocity states is
   emitted (per entity, pooled). Degeneracy alarm: any verdict >80% or unreachable.
2. **One-day flip rate**: P(state_t ≠ state_{t−1}) pooled; and per-entity median.
3. **Persistence**: median run-length of non-neutral states.
4. **Outlier sensitivity**: max |Δv_t| caused by injecting a single ±5σ spike into an
   otherwise median series (constructed fixture, per method).
5. **Quiet-series behavior**: v_t distribution on a 60-session near-zero-variance
   fixture (degenerate-extreme alarm: any |v| > 1.5).
6. **Coverage sensitivity**: |Δv_t| when 20% of members are randomly dropped
   (themes lens, 100 draws, median absolute shift).
7. **Revision sensitivity**: |Δv_t| when the last 3 sessions' inputs are perturbed by
   the historical revision magnitude distribution (use actual desk revisions if ≥5
   exist in the ledger, else ±10% of series std).
8. **Concordance**: rank correlation of theme orderings between each candidate and M0
   (interpretability anchor — a method that reorders everything needs a reason).

## 4. Threshold calibration (frozen procedure)

For the winning method (and M0 if it wins): sweep the velocity threshold τ ∈ {0.3,
0.4, 0.5, 0.6, 0.75, 1.0} and breadth tilt cutoff β ∈ {15, 20, 25, 30} (percentage
points). Selection objective (lexicographic):
1. neutral-band share of sessions in [25%, 60%] (honest neutral mass);
2. minimize one-day flip rate;
3. subject to: both non-neutral verdicts reachable ≥5% of sessions each.
Ties break toward the incumbent (τ=0.5, β=25).

## 5. Decision rule (frozen)

Adopt a challenger over M0 ONLY if it (a) improves outlier sensitivity (metric 4) or
quiet-series behavior (metric 5) by ≥30%, AND (b) does not worsen flip rate (metric 2)
by >10% relative, AND (c) keeps concordance (metric 8) ≥ 0.8, AND (d) triggers no
degeneracy alarm. Otherwise M0 stays and only thresholds may change (per §4).
The final selection is adjudicated by the Fable principal against this rule — the
harness reports, it does not decide. A held-out check: the last 60 sessions are
excluded from the threshold sweep and reported separately (drift check only).

## 6. Non-goals

No forward-return metrics, no IC, no predictive claims, no promotion. Validation
metadata stays context_only with zero forecast weights. Any exploratory
forward-return curiosity is OUT of this wave entirely.
