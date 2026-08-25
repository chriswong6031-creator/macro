# Cell G — Flagship Value-of-Information Measurement Law

**Issue:** MAS-123  
**Parent:** MAS-116  
**Status:** `SOL_FROZEN_RESEARCH_LAW` — no family promotion, rank mutation, trade authority, or new evaluation store is created by this document.  
**Authored:** 2026-08-22  
**Macro pickup base:** `3049b6f9785e7a08f03d746e0ca909cc425fdbde`  
**Protected Skillpack:** `mastermindx-market-intelligence/Mastermind@e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`, `mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1`.  
**Canonical owners:** Eval OS / QLedger for evidence clocks, legal outcomes and promotion law; Conditional Fusion for cross-family ranking/influence; Prophet V4 for candidate episodes and deterministic Availability; existing outcome/episode ledgers for recorded belief and settlement truth.

> **The governing question is not “did a metric go up?” It is: did this exact family/version make Prophet materially better for a preregistered job, on a lawful forward tape, without buying the improvement by waiting, narrowing coverage, changing the denominator, exploiting dependence, rereading outcomes, or laundering explanation value into alpha?**

---

## 0. Executive ruling

Cell G rejects a universal optimization scalar.

“Prophet got better” is a **claim-specific conjunction**:

1. the experiment was legally observable at its frozen evidence clock and exact version;
2. the population, decision clock, ruler, label, horizon, K, benchmark/control, missingness law, correction view, primary metric, materiality threshold, multiplicity family and look plan were registered before the confirmatory outcome read;
3. the claim-specific primary benefit cleared its preregistered minimum effect after dependence-aware uncertainty and multiplicity control;
4. a flagship-early claim preserved lead time, first-surface actionability and chase/unusable behavior with **zero allowed degradation margin**;
5. path/tail guardrails did not hide a materially worse failure mode;
6. coverage, refusals, effective sample diversity and concentration support the scope of the claim;
7. negative controls/placebos do not expose a plausible selection or analytic artifact;
8. no applicable A1–A12 flagship integrity control is missing;
9. the maximum authority granted matches the experiment actually run; and
10. any rank/predictive authority is granted only through the existing Eval/Fusion promotion path.

A family may improve **discovery**, **ranking**, **risk/path**, or **product/explanation** value. Those are different claims and must not borrow evidence from one another.

---

## 1. Reconciled current-state truth at freeze

### 1.1 Protected prospective races were not opened

- Conditional Fusion W3 is still outcome-blind: the current status surface reported **5 paired sessions accrued, 0 matured H=10 sessions, 20 matured sessions required for the first lawful comparison** at the reconciliation read. No W3 comparative outcomes were opened.
- The W3 `20 matured sessions` floor is a **first-comparison floor**, not a replacement for the broader Eval OS reporting/promotion law.
- QLedger has a live write-once forward evidence clock for `demand_chain` at a 126-trading-day ruler. `stock_desk` and `thematic_desk` did not have corresponding current forward-clock files at reconciliation; a matched-control clock directory was also absent. Cell G does not infer clocks that do not exist.
- The current durable V4 `prophet.candidate_episode/v1` plane is not yet production truth at the target grain. Deterministic entry/actionability semantics exist, but canonical V4 Availability remains only partial/scattered.

### 1.2 Existing measurement substrate to reuse

- `engine/qledger.py` / Eval OS: evidence clocks, family control policy, declared horizons, grading/promotion law.
- `engine/us_prophet_w3.py`: protected maturity/status gate for the current Fusion race.
- `engine/prophet_arena.py`: prospective same-night champion/challenger precedent; explicitly distinguishes selection vs closure grains.
- `scripts/grade_us_board.py` + `engine/grading.py`: next-bar fill, adjusted-price provenance, forward returns, MFE/MDD-style path primitives, board rank metrics, explicit era/coverage semantics.
- `engine/prophet_board_read.py`: explicit `available` / `blocked_data` / `not_applicable` actionability-join semantics; frozen origination status is kept separate from live stance.
- Existing plan ledger remains materially thinner: raw plan return/outcome fields exist, but benchmark/path fields proposed in the 2026-08-12 eval spec are not universally present. Cell G must emit `UNAVAILABLE_FIELD`, not synthesize them.

### 1.3 No-rebuild boundary

Cell G may add **derived read-only reports, metric-contract code, preregistration fields, tests and owner-adopted evaluation projections**. It may not add a new result ledger, scoreboard, promotion registry, evidence clock, ranker, Availability state, episode store or correction store.

---

## 2. Frozen vocabulary

### 2.1 Subject, population and clocks

Every metric registration MUST name:

- `subject_grain`: e.g. `(episode_id)`, `(decision_session, candidate_id)`, `(decision_session ranking list)`, `(operator_id, episode_id)`;
- `reference_population_id`: the population to which its denominator refers;
- `decision_clock`: when the system was allowed to know the inputs and emit the decision;
- `outcome_clock`: when the ruler becomes legally settled;
- `horizon` and units (`trading_sessions`, `calendar_days`, etc.);
- `ruler_id`: entry convention, benchmark/control, path basis and closure law;
- `belief_view`: exact contemporaneous inputs available at decision time;
- `settlement_view`: first canonical settled outcome used by the confirmatory read;
- `corrected_truth_view`: later corrected truth, if any, kept separate.

### 2.2 Two different “first surfaces”

Cell G freezes two timestamps because collapsing them launders discovery into ranking:

- **`T_eligible(v, e)`** — earliest decision session on which version `v`, under its frozen admission/retrieval law, could lawfully include episode `e` in its candidate population using only information then known.
- **`T_surface(v, e, K)`** — earliest decision session on which `e` was actually presented in the registered review surface/top-K/lane after admission and ranking.

If the experiment cannot reconstruct these from prospective logs or a valid point-in-time replay, the corresponding metric is `UNAVAILABLE_FIELD`. It is never approximated from a later plan date.

### 2.3 Registered relevance, never a universal “winner”

There is **no single global winner label**. Different jobs have different rulers (e.g. H10 excess-rank, 21-session rotational liftoff, 126-session positional path).

Each confirmatory experiment MUST preregister:

- `positive_label_id` for binary precision/recall/capture metrics, if used;
- `relevance_grade_id` and exact integer gain mapping for NDCG, if used;
- `continuous_outcome_id` for rank-IC/path metrics;
- horizon and benchmark/control;
- the minimum effect worth promoting.

A label chosen after seeing which one makes the challenger look best is exploratory and starts a fresh confirmatory clock/version if it is pursued.

---

## 3. The metric contract — required fields

Every metric is executable only when its registration names all of the following:

`metric_id` · `version` · question · subject grain · statistic/numerator · denominator · decision clock · outcome clock · horizon/ruler · reference population · benchmark/control · eligibility · missing/refusal behavior · correction behavior · tie behavior · direction of improvement · uncertainty method · multiplicity family · look plan · descriptive-vs-confirmatory class · authority ceiling.

A report MUST emit one of these terminal measurement states rather than silently dropping a metric:

- `MEASURED`
- `NOT_MATURE`
- `PROTECTED_OUTCOME`
- `UNAVAILABLE_FIELD`
- `UNESTIMABLE`
- `NOT_APPLICABLE`
- `DESCRIPTIVE_ONLY`
- `HOLD_INTEGRITY`

These are **report states, not a new lifecycle/control plane**.

---

## 4. Early Actionable Winner Capture metric family

EAWC is a vector. No weighted composite is authorized.

### 4.1 Earliness

#### `eligibility_lead_sessions`

- **Grain:** episode.
- **Population:** registered positive/reference episodes for which both champion and challenger have observed `T_eligible` before censoring.
- **Value:** `session_index(T_eligible_champion) - session_index(T_eligible_challenger)`; positive means challenger earlier.
- **Denominator:** number of paired episodes with both timestamps.
- **Missing:** never impute a huge lead for a one-sided capture. Report the four capture cells separately: `both`, `challenger_only`, `champion_only`, `neither`.
- **Correction:** decision-time membership is immutable; later data corrections attach separately.
- **Class:** confirmatory only if preregistered; otherwise descriptive.

#### `surface_lead_sessions@K`

Same law, using `T_surface(...,K)`. It measures user-visible lead, not retrieval lead.

#### `early_actionable_capture_recall`

- **Grain:** episode.
- **Numerator:** registered positive episodes whose first registered surface occurred and was canonically actionable at that first surface.
- **Denominator:** **all registered positive episodes in the independent reference population**, including missed, uncovered and refused positives.
- **Clock:** first surface state frozen at the decision clock; outcome label only after maturity.
- **Missing:** no surface or missing actionability contributes zero to the numerator and remains in the denominator.
- **Class:** eligible as a discovery primary endpoint when preregistered.

This is the closest single member of the EAWC family to the Chairman’s phrase “capture winners early enough to act,” but it is not allowed to hide the rest of the vector.

### 4.2 Deterministic actionability at first surface

#### `actionable_at_first_surface_rate`

- **Grain:** first surfaced episode.
- **Numerator:** applicable first surfaces whose **canonical owner-stamped** Availability/actionability state is in the preregistered actionable-now set.
- **Denominator:** every applicable first surface, **including blocked/missing actionability**.
- **Missing:** missing/blocked is “not proven actionable” for the headline rate; an observed-only rate may be shown only as descriptive support.
- **Owner law:** Cell G does not invent or recompute historical Availability. Until V4 unifies the contract, adapters may use only the exact actionability state frozen in the source artifact and must name that source/version.
- **Class:** flagship lead/actionability guardrail.

For the current `entry_signal` vocabulary, a report MAY define a source-specific adapter with `buy_now` and `partial` as actionable-now, but it must say `source_contract=entry_signal`, not pretend this is the final V4 universal Availability enum.

### 4.3 Chase / opportunity consumption

A future-outcome fraction such as “percent of eventual MFE already consumed” is useful but **descriptive only**. It may not define live actionability or promotion.

Confirmatory chase law consumes the canonical decision-time Availability/geometry only:

- `chased_or_closed_at_first_surface_rate`: first surfaces whose owner-stamped state says the opportunity is already chased/closed/late under the preregistered actionability contract;
- `unusable_or_unknown_at_first_surface_rate`: chased/closed **plus blocked/missing actionability**, over all applicable first surfaces.

If the Availability owner exposes a canonical signed chase-margin field, Cell G may report it; Cell G must not derive a second chase formula.

### 4.4 Eventual move consumed — diagnostic

`eventual_move_consumed_fraction` may compare move-to-first-surface with a registered future MFE/path endpoint. It is `DESCRIPTIVE_ONLY` because the denominator is an ex-post path maximum and can behave badly when eventual MFE is small. It can explain a late precision gain; it cannot rescue or originate an actionability gate.

---

## 5. Ranking metrics

Ranking experiments require the **same candidate population at the decision session**. If the family changes retrieval, run the discovery experiment first; do not intersect the two lists and call it a paired rank test.

### 5.1 `NDCG@K`

For decision session `t`, with preregistered non-negative integer relevance grades `rel_r`:

`DCG@K = sum_{r=1..min(K,n)} (2^rel_r - 1) / log2(r + 1)`

`NDCG@K = DCG@K / IDCG@K`.

- **Grain:** decision-session ranking list.
- **Population:** same eligible candidate set for both arms.
- **Denominator:** ideal DCG from the exact same candidate set/grade mapping.
- **No-positive session:** if `IDCG=0`, NDCG is `NOT_APPLICABLE`, never silently set to 0 or 1. The rate/count of no-positive sessions is reported separately.
- **Aggregation:** unweighted session-level mean/median and paired session deltas; never pooled-row NDCG.
- **Class:** confirmatory only when K, gain mapping and ruler are frozen before outcomes.

NDCG is appropriate precisely because graded relevance can reward putting more valuable opportunities earlier; the gain map is therefore part of the hypothesis, not a formatting choice.

### 5.2 `precision@K_presented`

- Numerator: registered positive items among the first `min(K,n_presented)`.
- Denominator: number actually presented up to K.
- Always reported with `fill@K = n_presented / K`; a sparse list may not inflate precision while hiding that it presented almost nothing.

### 5.3 `positive_yield@K_capacity`

- Numerator: positives in top K.
- Denominator: K.
- Measures quality **and** slot fill; secondary to precision but useful when review capacity is fixed.

### 5.4 `recall@K`

- Numerator: positive items in top K.
- Denominator: **all positive items in the fixed eligible reference population for that session**.
- If retrieval changed, this is not a legal rank-only denominator.

### 5.5 `rank_ic`

- Spearman correlation, per decision session, between frozen score/rank and preregistered continuous outcome.
- Session is unestimable when score or outcome has no variation or the registered minimum per-session count is not met.
- Aggregate as a session-level series with dependence-aware inference.

### 5.6 Rank stability / burden

Turnover, top-K churn and underfill are descriptive product/ranking diagnostics unless explicitly preregistered as guardrails.

---

## 6. Path and risk metrics

Cell G reuses the canonical grader/ledger definition actually present. It does not rename incompatible path bases into one pooled “MAE.” Every report row MUST print `path_basis` and ruler.

### 6.1 `MFE_H`

Maximum favorable excursion within the exact registered strictly-forward window after the registered fill. On the current shared grader, the window is `(fill, fill+H]` and fill is next bar. If another ledger uses another convention, the rows are not pooled.

### 6.2 `MAE_H` / adverse excursion

Use the canonical source’s exact adverse excursion definition. Current US board history includes close-path and benchmark/basis nuances; a report must name them. If only `fwd_mdd_H` exists, report it under its native semantics instead of upgrading it to intraday MAE.

### 6.3 `R_H`

Where entry and initial invalidation/stop are both frozen at decision time:

`R_H = direction_signed_realized_PnL_H / abs(entry_price - invalidation_price)`.

If initial risk is zero, absent or recomputed later, `R_H=UNAVAILABLE_FIELD`. Do not infer a stop after the outcome.

### 6.4 `time_to_payoff_xR`

- **Grain:** entered episode.
- **Value:** first strictly-forward session at which direction-signed path reaches the preregistered `xR` threshold (e.g. `+0.5R` or `+1R`).
- **Non-hit:** right-censored at H, never dropped.
- **Summary:** hit-by-H rate plus Kaplan–Meier median/quantiles when estimable. If the median is not reached by H, print `NOT_REACHED_BY_H`.

### 6.5 `time_underwater_fraction_H`

Number of strictly-forward sessions with direction-signed cumulative return below zero divided by H for fully matured entered episodes. Missing path => unavailable; no partial-window denominator shrinkage.

### 6.6 `invalidation_rate`

Invalidated/stopped episodes divided by all entered matured applicable episodes under the exact registered closure law.

### 6.7 `false_bounce_rate`

Prefer an existing canonical field. Where Outcome Spine’s `post_cushion_breach` is available, it is the legal false-bounce proxy: an episode first obtained the registered cushion and subsequently breached the registered failure boundary. A new family may not invent a retrospective “felt like a false bounce” label.

### 6.8 `tail_loss_ES10`

Expected shortfall over the worst 10% of the registered signed return/R distribution.

- `tail_n = ceil(0.10 * n_matured)`.
- `UNESTIMABLE` when `tail_n < 10` (thus normally `n_matured < 100`).
- The 10th percentile may be shown descriptively below that floor, but not as a promotion-bearing tail estimate.

---

## 7. Coverage, refusals and selection bias

### 7.1 Coverage denominator

`coverage = covered_applicable / all_applicable`.

`NOT_APPLICABLE` is excluded. Every other reason an applicable subject could not be evaluated stays in the denominator: source unavailable, stale, rights blocked, identity unresolved, gauge null, parse error, missing family evidence, or explicit refusal.

Reports MUST break those causes out. “No signal” and “could not look” are never the same state.

### 7.2 Broad versus specialist claims

Mastermind already carries a 70% cohort-coverage precedent in the shared grading taxonomy. Cell G adopts that as the **default broad-coverage floor**:

- `coverage >= 70%`: potentially eligible for a broad-population claim, subject to all other gates;
- `<70%`: the family is **not disqualified**, but its claim is specialist/covered-cohort only unless a newer canonical owner law preregisters another coverage contract before outcomes.

A sparse family may be extremely valuable. Sparse coverage may not be converted into a universal score by dropping uncovered rows.

### 7.3 Mandatory sparse-coverage selection audit

For any family below full coverage, report:

1. covered vs uncovered population composition;
2. outcome/base-rate difference between covered and uncovered using the champion/reference outcome only;
3. a `coverage_indicator_only` negative-control model/arm; and
4. the family’s incremental effect **within the covered cohort**.

If coverage alone satisfies the promotion endpoint or the within-covered increment fails, attribution to family content is `HOLD_INTEGRITY`/`MIXED`, not a family win.

---

## 8. Effective N and concentration law

### 8.1 No magic scalar

Cell G forbids reporting one “effective N” as if it repaired every dependence problem.

Every report prints a vector:

- raw rows;
- unique subject episodes;
- unique decision sessions;
- unique economic issuers;
- unique themes/species/regimes when the claim generalizes across them;
- concentration-effective counts;
- top-1/top-5 shares; and
- the actual cluster/block/HAC inference method.

### 8.2 Concentration-effective count

For a grouping dimension `G` with group shares `p_g = n_g / n`:

`N_eff(G) = 1 / sum_g p_g^2`.

Interpretation: the number of equally represented groups that would have the same concentration. It is a **scope/concentration diagnostic**, not a number to plug into a binomial or t distribution.

### 8.3 Default promotion estimability floors

These are governance floors, not claims that asymptotic theory becomes perfect at the boundary. A stricter existing preregistration always wins.

For a cross-issuer predictive/ranking promotion claim:

- at least **50 matured subject episodes** at the declared ruler (house Eval OS reporting floor);
- `N_eff(decision_date) >= 20`;
- `N_eff(economic_issuer) >= 20`.

For a claim that says it generalizes across themes or species:

- `N_eff(theme) >= 5` for a cross-theme claim;
- `N_eff(species) >= 5` for a cross-species claim.

If the domain is inherently single-issuer/single-theme, the dimension is `NOT_APPLICABLE` and the authority claim is explicitly narrowed to that scope rather than failed.

A dimension with more than 50% of the observations in one group is always surfaced as `DOMINATED`; a broad generalization cannot pass while dominated even if another count looks large.

**W3 reconciliation:** its frozen `20 matured H10 sessions` permits the first lawful W3 comparison. It does not override the 50-matured-subject promotion/reporting floor or the claim-specific concentration law above.

---

## 9. Dependence-aware statistical method

### 9.1 Ranking/session metrics

Compute one ranking metric per decision session, then compare champion/challenger as paired session deltas.

For regularly spaced daily observations with an H-session overlapping outcome, the default is HAC/Newey–West with lag `H-1` **when the owning preregistration already uses that convention** (W3 H10 lag 9 is the current precedent). Otherwise use a preregistered moving-block bootstrap with block length at least the dependence horizon. Do not stack multiple uncertainty corrections merely to manufacture a desired interval.

### 9.2 Episode/discovery/path metrics

Use date-clustered resampling/inference because many fires on one market day share shocks. If issuers repeat materially across dates, use two-way date × economic-issuer clustering or a bootstrap that preserves both dependence axes. Fewer than 20 effective clusters on an applicable axis is `UNESTIMABLE` for a confirmatory broad claim.

Raw-row Wilson/binomial intervals remain descriptive only when clustering is material.

### 9.3 Lead-time medians/rates

Use cluster/block bootstrap intervals on the paired lead/actionability statistics. Do not t-test raw per-name lead observations as independent rows.

### 9.4 Censored payoff time

Do not calculate average time-to-payoff only among winners. Non-hitters are censored and remain in the risk set.

---

## 10. Multiplicity, search tax and repeated looks

### 10.1 One primary endpoint per promotion experiment

A registration names exactly one promotion-bearing primary endpoint, one horizon/ruler, one K where relevant, one materiality threshold and the required guardrails. Secondary metrics remain visible but cannot be auditioned into the primary result after the read.

### 10.2 Multiple families / hypotheses

When several promotion-bearing hypotheses are tested in the same research family/round, use **Holm family-wise error control** by default. Exploratory family discovery may use Benjamini–Hochberg FDR for triage, but an FDR-selected finding receives **no authority** until it earns a fresh preregistered prospective confirmatory test.

Every tested/abandoned variant counts toward the search family. Renaming a feature or suppressing a failed chart does not erase a look.

### 10.3 Model search/data snooping

If the same historical tape was used to invent/select the model, replay support is evidence for research architecture, not prospective promotion. Specification search is explicitly taxed: the selected version begins a fresh forward evidence clock. Data-snooping-adjusted methods may help assess historical plausibility, but they do not substitute for live-forward authority.

### 10.4 Repeated looks

Every confirmatory registration chooses one before the first outcome read:

1. **`fixed_look` (default):** one adjudicative read after the frozen maturity/estimability floor. Status/maturity counters may be read before then; outcome comparisons may not.
2. **`sequential_safe`:** a preregistered alpha-spending / anytime-valid confidence-sequence or e-process design whose boundary is fixed before outcomes.

If a fixed-look result is inconclusive, repeatedly checking until significance is forbidden. Continue only under a preregistered later-look plan or treat subsequent reads as exploratory and start a fresh confirmatory cohort for authority.

---

## 11. Calibration law

Calibration applies only to a head that emits an actual probability or predictive distribution with a defined event/horizon.

For a binary probability head, preregister and report:

- Brier score and Brier skill versus the registered base-rate forecast;
- logarithmic score where probabilities are clipped only by a preregistered numerical-safety epsilon;
- calibration intercept/slope when estimable;
- reliability diagram/bin counts as descriptive diagnostics.

Strictly proper scoring rules are used because they reward honest probabilistic forecasts. A rank score, sentiment score, evidence score or arbitrary “confidence” number is **not** called calibrated until it has earned this contract.

---

## 12. LOFO, plus-family and placebo law

### 12.1 Operational LOFO (default)

`ChampionMinusFamily(F)` runs the exact champion version on the same decision-time tape with family F removed according to the champion’s **already-defined missing-family semantics**. Remaining weights/thresholds are not retuned after seeing outcomes.

This estimates operational marginal dependence on F.

### 12.2 Refit LOFO is a different experiment

If the intended question is “how good would the system become after retraining without F?”, that is a new refit model/version. Training folds are frozen without future/target episodes; the new model starts its own forward clock. Do not call a refit comparison the same LOFO experiment.

### 12.3 Plus-family shadow

`ChampionPlusFamilyShadow(F)` is prospective and zero-authority. It must use the same frozen decision-time world/ruler. If F changes retrieval, classify it as discovery plus downstream rank — not a pure paired rank test.

### 12.4 Negative controls / placebos

At minimum, a scored family declares an appropriate negative control:

- **within-tape shuffled-family placebo:** shuffle family values/identity mapping within the decision session and relevant coverage stratum while preserving marginal distribution and missingness;
- **coverage-indicator-only placebo:** tests whether “where the family exists” explains the apparent value;
- **retrieval-volume-matched placebo:** for discovery families, random/matched additions of the same count from the lawful reference universe rather than pretending added coverage is alpha.

A negative control that itself clears the claimed promotion endpoint is `HOLD_INTEGRITY` until the bias mechanism is understood. A null negative control does **not** prove causality; it is a falsifier, not positive evidence.

---

## 13. Four separate experiment templates

## 13.1 Discovery value

**Question:** Does F find useful episodes the champion would otherwise miss, early enough to act?

- **Reference population:** independently defined all-candidate/opportunity universe at each decision session. If unavailable, use `champion ∪ challenger` only and label the result `OBSERVED_UNION_DISCOVERY`; no absolute-recall claim.
- **Arms:** Champion; Champion+F shadow; retrieval-volume/coverage matched placebo.
- **Primary candidate endpoint:** preregistered `early_actionable_capture_recall` or another explicit discovery endpoint.
- **Mandatory companions:** total candidate burden, positive precision/yield, challenger-only/champion-only/neither capture, eligibility/surface lead, first-surface actionability, chase/unusable rate, coverage/refusals.
- **Forbidden:** intersecting the two retrieved sets, computing NDCG only there, and calling it discovery value.

## 13.2 Ranking value

**Question:** Holding the candidate population fixed, does F put the better opportunities nearer the top?

- **Population:** exact same eligible candidate tape per session.
- **Arms:** Champion; Champion−F operational LOFO and/or Champion+F shadow; within-tape shuffled placebo.
- **Primary:** one preregistered ranking endpoint (`NDCG@K` or rank-IC).
- **Mandatory companions:** precision@K, recall@K, fill@K, lead/surface timing when ranking across repeated sessions, coverage/refusals, concentration/effective N.
- **Forbidden:** allowing the challenger to introduce/drop candidates without reclassifying the study as discovery + ranking.

## 13.3 Risk/path value

**Question:** Holding the intended opportunity/entry basis fixed, does F improve the path or reduce failure/tail risk?

- **Population:** paired entered episodes with the same entry clock/risk ruler for a pure risk experiment.
- **Primary:** one preregistered path/risk endpoint (e.g. invalidation rate, MAE/R guard, tail loss, time-to-payoff).
- **Mandatory companions:** MFE, adverse excursion, realized R when available, false-bounce/post-cushion breach, time underwater, lead/actionability if the risk rule delays action.
- **If F changes selection/rank:** that effect is not a pure risk comparison; run the selection/ranking estimand separately.
- **Authority:** risk evidence does not grant trade sizing/gating authority by itself.

## 13.4 Explanation / product value

**Question:** Does presenting F make the operator faster, better grounded or more consistent without claiming market alpha?

- **Design:** same evidence/world, randomized or counterbalanced presentation where practical.
- **Grain:** operator × episode/review task.
- **Candidate primaries:** active review time per applicable episode; controlled evidence-comprehension accuracy; decision-completion within SLA; correction/provenance recognition.
- **Mandatory:** explanation grounding/receipt coverage and correction visibility.
- **Forbidden:** using realized returns as the primary endpoint and calling explanation prose alpha.
- **Maximum authority:** display/product experience unless a separate predictive/ranking experiment later earns more.

---

## 14. Lead-time preservation — flagship hard law

The early flagship lane has **zero tolerated degradation margin** by default:

- `delta_lead`: positive means challenger earlier;
- `delta_actionable`: positive means more first surfaces are actionable;
- `delta_unusable`: positive means more first surfaces are chased/closed/unknown (worse).

Using preregistered one-sided 95% dependence-aware intervals:

### `LEAD_PASS`

- lower bound(`delta_lead`) >= 0;
- lower bound(`delta_actionable`) >= 0; and
- upper bound(`delta_unusable`) <= 0.

### `LEAD_FAIL`

Any of:

- upper bound(`delta_lead`) < 0;
- upper bound(`delta_actionable`) < 0; or
- lower bound(`delta_unusable`) > 0.

### `LEAD_MIXED`

Anything else: point estimates may look favorable, but the no-degradation claim is unresolved.

**Flagship classification:**

- primary benefit passes + `LEAD_PASS` + safety/coverage/integrity pass => eligible to become a flagship improvement candidate;
- primary benefit passes + `LEAD_FAIL` => **FAIL for the flagship-early claim**;
- primary benefit passes + `LEAD_MIXED` => **MIXED / keep accruing**, no flagship promotion;
- primary benefit fails => no flagship improvement regardless of timing.

A family that becomes more precise by waiting can still be useful only as a **separately preregistered conservative-confirmation lane**. That lane must exist before outcome inspection. It cannot be invented after a late precision win as a rescue story.

---

## 15. Correction and vintage law

Cell G separates three views:

1. **belief view** — exact decision-time evidence/version; never rewritten;
2. **settlement view** — first canonical legal outcome at the registered ruler; frozen once used for the confirmatory read;
3. **corrected-truth view** — later corrections/revisions, shown as a reconciliation diagnostic and attached to the original result.

A correction discovered **before** the first legal settlement/read follows the canonical outcome owner’s correction policy. After the confirmatory read, it may not silently rewrite the evidence record. If the correction is material enough to invalidate the result, the result becomes `HOLD_INTEGRITY`/invalidated with a visible receipt; it is not replaced by a nicer restatement.

Historical model features must use the contemporaneous-belief view, not today’s final corrected history, unless the experiment is explicitly a descriptive final-truth study.

---

## 16. Promotion and authority ladder

Cell G reports evidence; existing owners mutate authority.

A research report may describe these semantic rungs, mapped onto existing Eval/Fusion lifecycle rather than stored in a new registry:

1. `DISPLAY_CONTEXT` — truthful context, zero predictive/rank authority;
2. `REPLAY_SUPPORTED` — historical/PIT research support, still zero rank authority;
3. `FORWARD_ACCRUING` — preregistered live-forward evidence accumulating;
4. `FORWARD_SHADOW_ADJUDICABLE` — maturity/estimability floors reached and lawful read completed;
5. `PROMOTED_FOR_RANK` — **only** if existing Eval/Fusion owner grants bounded influence after the full gate;
6. trade/entry sizing/execution authority — separate downstream gauntlet, not granted here.

### 16.1 Rank-promotion evidence gate

Before Cell G may recommend rank promotion, all applicable conditions must pass:

- live-forward exact version at registered clock;
- primary endpoint clears its preregistered minimum material effect after multiplicity control;
- `LEAD_PASS` for flagship-early claims;
- preregistered path/tail noninferiority/safety guardrails;
- coverage/effective-N/scope estimability;
- required benchmark or matched-control policy satisfied;
- sparse-coverage selection audit passes where applicable;
- negative controls do not trigger a bias hold;
- calibration passes if the authority claim is probabilistic;
- every applicable A1–A12 integrity amendment is satisfied;
- no protected/missing/late-read violation;
- owner adoption through the existing Eval/Fusion path.

No Cell G report auto-promotes anything.

### 16.2 Materiality threshold law

Every confirmatory primary registers `minimum_effect_of_interest` **before outcomes**. Statistical nonzero without material value is not a promotion win. Cell G intentionally does not choose one universal delta across discovery, ranking, path and product metrics.

---

## 17. Revalidation and demotion

Promotion is revocable.

### 17.1 Immediate authority suspension / fresh clock triggers

Without waiting for a performance sample:

- leakage/timestamp/correction integrity failure;
- material family/model version change;
- source/rights/identity contract change that invalidates the original evidence basis;
- required coverage/control disappears;
- outcome ruler/label/horizon changes.

A material new version starts a new forward evidence clock. It does not inherit the old version’s result by semantic similarity.

### 17.2 Performance revalidation

Use the **same original endpoints, lead law and materiality margins** on new non-overlapping forward evidence. Do not weaken a threshold because a promoted family later misses it.

Two legal monitoring modes:

- preregistered fixed revalidation blocks at least as large/diverse as the original promotion block; or
- a preregistered anytime-valid sequential monitor.

For fixed blocks, one failed block is an `AT_RISK` review signal; **two consecutive non-overlapping blocks that materially violate the original promotion/lead contract trigger a demotion recommendation**. A preregistered catastrophic tail/integrity tripwire may suspend sooner. Existing owner lifecycle performs the actual demotion.

---

## 18. A1–A12 controls as Cell G acceptance checks

A report is `HOLD_INTEGRITY` if an applicable control is absent:

1. leave-target-economic-issuer-out baselines, including cross-list/share-class identity;
2. fold-frozen priors, no target/future episodes;
3. strictly pre-event price-derived sensitivities;
4. target-price-independent materiality;
5. family-first calibration, no unearned universal response scalar;
6. compute/transport/influence ownership separation;
7. fragility/crowding not a hidden removal veto;
8. product copy cannot upgrade evidence authority;
9. graph path/cycle re-entry guards;
10. source-root identity separated from economic-information dependence;
11. sparse coverage-selection audit;
12. contemporaneous-belief history separated from final-corrected truth.

---

## 19. First bounded implementation contract

The preferred first vertical is a **read-only derived VOI report**, not a new evaluation store.

### 19.1 Observable mission

Given existing lawful Eval/Fusion/Prophet measurement surfaces, emit one report that answers:

- what can legally be measured now;
- what is protected/not mature;
- which frozen Cell G metrics are supported by current fields;
- coverage/refusal/effective-N/concentration;
- lead/actionability/path tradeoffs where the source actually contains them; and
- why no family promotion follows from the report.

### 19.2 Required safety behavior

- W3 adapter reads its **status/maturity surface first**. If the gate says outcome-blind/not mature, it MUST NOT open an outcome-bearing race file.
- QLedger family adapter checks a real evidence-clock registration and declared ruler before any confirmatory family result.
- Missing first-surface/actionability/path fields emit `UNAVAILABLE_FIELD`.
- Existing US board outcome truth may support lawful historical/descriptive rank/path rows, but the report labels historical/replay versus live-forward authority explicitly.
- No writer, no new ledger, no threshold mutation, no rank consumer.
- Tests use synthetic fixtures to execute formulas and protected-gate behavior without peeking at immature real outcomes.

### 19.3 Minimum report sections

1. authority/evidence-clock status;
2. population/ruler/era;
3. metric support matrix (`MEASURED` vs refusal states);
4. discovery metrics if a lawful reference population exists;
5. rank metrics;
6. actionability/lead metrics;
7. path/risk metrics;
8. coverage/refusals;
9. effective-N/concentration vector;
10. inference/multiplicity/look metadata;
11. integrity/placebo status;
12. explicit `promotion_authority=false`.

---

## 20. Capability ledger after research freeze

| Capability | State after Cell G research freeze |
|---|---|
| EAWC metric family | **FROZEN_RESEARCH_LAW** |
| exact first-eligibility vs first-presentation semantics | **FROZEN_RESEARCH_LAW** |
| deterministic first-surface actionability/chase law | **FROZEN_RESEARCH_LAW**, consumes owner-stamped Availability only |
| NDCG/P/R/rank metric denominators | **FROZEN_RESEARCH_LAW** |
| MFE/adverse/R/time/tail metric law | **FROZEN_RESEARCH_LAW**, source basis must be explicit |
| coverage/refusal/sparse-selection law | **FROZEN_RESEARCH_LAW** |
| effective-N/concentration policy | **FROZEN_RESEARCH_LAW** |
| multiplicity/repeated-look policy | **FROZEN_RESEARCH_LAW** |
| lead-time PASS/MIXED/FAIL policy | **FROZEN_RESEARCH_LAW** |
| discovery/rank/risk/product experiment templates | **FROZEN_RESEARCH_LAW** |
| promotion/demotion recommendation law | **FROZEN_RESEARCH_LAW**, mutation remains Eval/Fusion-owned |
| full canonical V4 first-surface/Availability history | **NOT_BUILT / PARTIAL owner substrate** |
| current W3 comparative result | **PROTECTED_OUTCOME / NOT_MATURE** at reconciliation |
| flagship read-only VOI report implementation | **NOT_BUILT** at this research-freeze commit |
| any family predictive/rank promotion | **NOT AUTHORIZED** |

---

## 21. Adversarial self-review / attacks this law must survive

A valid implementation must kill each of these attacks:

1. Challenger reports better precision by returning 8 names instead of 80. **Killed by coverage + fill + full-denominator recall/actionability.**
2. Challenger adds new names, then compares rank only on the intersection. **Killed by discovery/ranking separation.**
3. 500 rows from four dates are called n=500. **Killed by date concentration-effective count + cluster inference.**
4. A dominant issuer/theme creates apparent generality. **Killed by effective counts + scope narrowing.**
5. Analyst tries H5/H10/H21 and publishes the best. **Killed by one primary horizon + search/multiplicity law.**
6. Analyst checks every night until p<0.05. **Killed by fixed-look default / sequential-safe alternative.**
7. Feature coverage itself selects winners. **Killed by coverage-indicator placebo + within-covered increment.**
8. Later corrected history makes old evidence look prescient. **Killed by belief/settlement/corrected-view separation.**
9. Precision rises because the signal arrives after the chase boundary. **Flagship `LEAD_FAIL`; conservative lane only if preregistered separately.**
10. Explanation copy gets high user ratings and is called alpha. **Killed by product experiment authority ceiling.**
11. Probability-like confidence is shown without calibration. **Killed by proper-score calibration law.**
12. Negative control is null, so team declares causality proven. **Killed: placebo is falsifier, not positive evidence.**
13. LOFO retrains every remaining parameter and is called “remove one family.” **Killed by operational vs refit LOFO split.**
14. Missing actionability rows are dropped and actionable rate jumps. **Killed by applicable-denominator rule.**
15. A protected prospective file is opened only to decide whether it is mature. **Killed by metadata/status-first gate; outcome-bearing file is never opened pre-gate.**

---

## 22. External method anchors

The architecture uses external methods as methodological support, not as authority over Mastermind’s own preregistered contract:

- Järvelin & Kekäläinen (2002), *Cumulated gain-based evaluation of IR techniques*, ACM TOIS 20(4), DOI `10.1145/582415.582418` — graded relevance and discounted/normalized rank evaluation.
- White (2000), *A Reality Check for Data Snooping*, Econometrica 68(5), DOI `10.1111/1468-0262.00152` — specification search/data reuse can manufacture apparent winners.
- Harvey, Liu & Zhu (2016), *… and the Cross-Section of Expected Returns*, Review of Financial Studies 29(1); NBER w20592 — financial factor research needs explicit multiple-testing discipline.
- Holm (1979), *A Simple Sequentially Rejective Multiple Test Procedure*, Scandinavian Journal of Statistics 6 — strong family-wise multiplicity control without requiring a single Bonferroni step.
- Benjamini & Hochberg (1995), *Controlling the False Discovery Rate* — suitable for exploratory triage, not Cell G authority by itself.
- Cameron, Gelbach & Miller (2011), *Robust Inference with Multi-Way Clustering*, JBES 29(2) — dependence can exist on multiple nonnested clustering axes.
- Lipsitch, Tchetgen Tchetgen & Cohen (2010), *Negative Controls: A Tool for Detecting Confounding and Bias in Observational Studies*, Epidemiology 21(3) — negative controls detect classes of bias but do not by themselves identify the source/magnitude.
- Gneiting & Raftery (2007), *Strictly Proper Scoring Rules, Prediction, and Estimation*, JASA — proper scoring for honest probability/distribution forecasts.
- Lan & DeMets (1983), *Discrete Sequential Boundaries for Clinical Trials*, Biometrika 70(3), and modern confidence-sequence literature — repeated looks need a design that remains valid under sequential monitoring.

---

## 23. Exact continuation

**Primary next action:** implement the bounded read-only Cell G VOI report against the existing owner surfaces, beginning with status/evidence-clock gates and synthetic formula tests. The implementation must prove it does **not open W3 outcome-bearing files while W3 is immature** and must emit explicit unavailable states for current missing flagship fields.

**Owner gate:** implementation remains zero-authority and must be reviewed as an Eval/Fusion-compatible derived measurement projection. It may not redefine any formula, denominator, label, horizon, K, minimum effect, evidence clock or promotion gate after observing real outputs.

**Independent work that may continue in parallel:** Cells A/F/B can refine their own family contracts. If any material family representation changes, its Cell G experiment registration must bind the new exact version and a fresh lawful evidence clock before authority evidence accrues.
