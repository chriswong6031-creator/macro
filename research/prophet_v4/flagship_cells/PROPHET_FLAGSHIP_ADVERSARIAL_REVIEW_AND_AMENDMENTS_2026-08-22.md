# PROPHET FLAGSHIP INTELLIGENCE — ADVERSARIAL ARCHITECTURE REVIEW & BINDING AMENDMENTS

**Date:** 2026-08-22  
**Reviewer seat:** Sol fresh-pass adversarial architecture review after integrated masterplan assembly  
**Status:** BINDING RESEARCH-ARCHITECTURE AMENDMENTS to the 2026-08-22 flagship masterplan suite; no runtime authority  
**Applies to:** Integrated Masterplan, Cells A/B/C/F/G, Architecture Freeze, Hypothesis Matrix, Reference Casebook

---

# 0. Review question

Attack the integrated masterplan as if a highly capable future research session wanted to produce the most convincing possible results while technically claiming to follow the spec.

Primary attack classes:

1. circular expected-response construction;
2. look-ahead through priors/calibration;
3. target leakage through theme/peer baskets;
4. materiality inferred from the price response it is later supposed to explain;
5. same-source / same-issuer dependence masquerading as independent evidence;
6. B/F/Fusion ownership blur;
7. fragility/crowding becoming hidden availability/rank authority;
8. mixed units being collapsed into a universal response score;
9. model complexity becoming a goal even when simpler baselines suffice;
10. product copy overstating experimental inference.

Verdict after review: **architecture remains coherent, but five anti-circularity amendments are load-bearing before any Cell A/B response-pressure experiment is accepted.** Additional clarifications close ownership/product risks.

---

# 1. Finding AR-1 — target security can leak into its own theme impulse

**Severity:** BLOCKER for any exposure-weighted response-pressure research.

## Attack

The masterplan gives a conceptual baseline:

```text
ThemePressure(i,t) = Σ_k exposure(i,k,t_known) × residual_theme_impulse(k,t)
```

If `residual_theme_impulse(k,t)` is built from a basket containing security `i`, then the target's observed move partly defines the “expected” move used to classify its own incorporation.

This can mechanically shrink or distort the gap and can become especially circular for concentrated themes where the target is a leader.

Cross-listed securities or multiple share classes of the same economic issuer create the same defect even if the exact ticker is excluded.

## Binding Amendment A1 — leave-target-economic-issuer-out

For any experiment asking whether target `i` has under/over-responded to a theme/peer impulse:

- exclude target security `i` from the impulse estimator;
- exclude all share classes/cross-listings of the same canonical economic issuer;
- exclude mechanically derived duplicates/ETP holdings when the research question requires independent operating-company impulse;
- disclose remaining member N/effective N after exclusion;
- refuse the theme-pressure estimate when exclusion leaves inadequate support.

Preferred label in research code/docs:

`leave_target_issuer_out = true`

This applies to:

- pure-play theme baskets;
- peer baskets;
- sector/industry custom baskets when target is otherwise included;
- relationship-neighbor aggregates where the target can re-enter through a cycle.

## Consequence

A theme that cannot produce an independent impulse after target-issuer exclusion is `UNESTIMABLE` for incorporation research, even if it remains useful for display/context.

---

# 2. Finding AR-2 — historical response prior can leak target episode/future fold

**Severity:** BLOCKER for calibrated response pressure / analogue-informed gap states.

## Attack

`historical_response_prior` is useful, but if it is estimated from:

- the target episode being graded;
- future episodes relative to the decision date;
- a full-sample species/theme calibration later applied backward;
- an analogue set whose membership uses future outcomes;

then the system converts future outcome information into the expected-response model.

## Binding Amendment A2 — fold-frozen prior law

Any historical response prior used to classify an episode at decision time `t0` must be generated from a version/fold whose training/adjudication evidence ends **strictly before the evaluated episode's eligible outcome window** under the registered research protocol.

Required metadata:

```text
prior_version
training_cutoff
feature_cutoff
population_definition_version
calibration_method
n_episodes
n_issuers
n_date_clusters
effective_n
```

Rules:

- target episode excluded;
- future folds excluded;
- if rolling/walk-forward, each prediction preserves its contemporaneous prior version;
- if the prior cannot be reconstructed PIT, the experiment may be descriptive but not confirmatory;
- an updated modern calibration cannot be retroactively written into old candidate features and then treated as what Prophet knew.

---

# 3. Finding AR-3 — trading exposure can become outcome leakage

**Severity:** BLOCKER if a price-derived exposure axis shares the judged response window.

## Attack

The multi-axis architecture intentionally distinguishes economic exposure and trading-beta exposure. However, a careless implementation could estimate “theme trading beta” using returns that overlap the event/response window, then multiply that exposure by theme impulse and compare with the same target return.

That is circular.

## Binding Amendment A3 — pre-event exposure window law

Any **price-derived** exposure/sensitivity used as an input to expected response must be estimated from a window that is:

- wholly prior to the evidence event / evaluated decision clock;
- frozen before observing the target outcome;
- sufficiently separated/embargoed where serial overlap matters;
- versioned separately from economic exposure.

No contemporaneous/post-event target return may update the exposure coefficient before the incorporation label for that same episode is frozen.

If a current rolling trading-beta estimate includes the evaluated response window, it may be displayed as current market context but **cannot** be used in the confirmatory expected-pressure calculation for that episode.

Economic exposure from source-backed business facts does not have this specific price-window issue but still follows known-at/correction law.

---

# 4. Finding AR-4 — issuer materiality can be inferred from the price reaction it is meant to explain

**Severity:** BLOCKER for Cell C→B incorporation studies.

## Attack

A model could define materiality as “events that historically moved this stock more,” then use materiality to generate expected pressure and declare a low current price reaction under-incorporated.

This embeds the target variable in the predictor and can turn price impact history into circular alpha.

## Binding Amendment A4 — materiality ex-price law for incorporation

For a Cell B incorporation experiment, the issuer-materiality feature used in expected pressure must be derived from **non-target-price economic evidence available at t0**, unless a separately preregistered historical-response prior is explicitly isolated as its own statistical feature.

Acceptable materiality inputs may include, where domain-valid:

- revenue/profit/cash-flow scale;
- funded/obligated contract amount vs issuer economics;
- asset/program/customer concentration;
- runway/funding need;
- KPI/segment size;
- guidance/estimate delta;
- domain-specific probability-adjusted economics only from a validated domain method.

The target security's immediate/post-event return is **not** an input to materiality for the same incorporation judgment.

Historical price sensitivity may exist as a separately named empirical prior, never disguised as economic materiality.

---

# 5. Finding AR-5 — mixed units can create a fake universal ResponsePressure score

**Severity:** MAJOR architecture risk.

## Attack

Revenue exposure, earnings surprise, customer capex change, contract materiality and evidence novelty have incompatible units. A future builder could normalize each to a percentile/z-score and sum them, producing an apparently sophisticated universal pressure number with no stable economic interpretation.

## Binding Amendment A5 — family-first calibration law

The initial response-pressure object is a **structured vector / set of component estimates**, not a universal scalar.

Cross-family scalarization is forbidden until:

- each component has a stable owner-native definition;
- coverage/missingness is explicit;
- the component has enough PIT history for family-specific calibration;
- calibration is frozen before confirmatory evaluation;
- dependence between components is measured;
- Conditional Fusion/Eval OS—not D5/Cell B ad hoc code—governs any cross-family weighting authority.

Allowed early output:

```text
expected_response:
  theme_exposure_impulse: <state/value + uncertainty>
  catalyst_surprise_materiality: <state/value + uncertainty>
  transmission_pressure: <state/value + uncertainty>
  empirical_prior: <state/value + uncertainty>
```

Not allowed:

```text
response_pressure_score = 87.4
```

unless a future frozen model/version explicitly earns that interpretation.

---

# 6. Finding AR-6 — B/F/Fusion ownership can blur around `price_incorporation`

**Severity:** MAJOR ownership risk.

## Attack

Cell B researches/calibrates incorporation. Cell F owns D5 evidence grammar. Conditional Fusion owns cross-family rank influence. Without a precise seam, F could start computing a gap or B could start assigning cross-family weights.

## Binding Amendment A6 — compute / transport / influence split

- **Cell B / accepted incorporation owner** computes or defines the frozen incorporation evidence state under its own research contract.
- **Cell F / D5** transports the owner-produced state, clocks, coverage, baseline disagreement, evidence references and authority metadata into Prophet. It does not recompute the statistical gap from raw prices/evidence.
- **Conditional Fusion** decides whether/with what authority that evidence affects cross-family ordering after promotion law.
- **Prophet Availability** remains uninvolved.

If no canonical owner for a surviving incorporation method exists after research, Sol must explicitly route it before implementation. D5 does not become owner by default.

---

# 7. Finding AR-7 — fragility/crowding can become a hidden veto through E1 heuristics

**Severity:** MAJOR product/control risk.

## Attack

Even if Cell E does not alter `ENTRY_OPEN`, an E1 deterministic priority rule could bury high-fragility names below visibility, effectively creating a hidden availability veto.

## Binding Amendment A7 — visibility and lane-honesty law

Within the complete All Candidates surface:

- an `ENTRY_OPEN` candidate remains in the `ENTRY_OPEN` lane regardless of fragility/crowding;
- priority may order within the lane only under earned/frozen authority;
- if risk evidence causes severe deprioritization, the UI must expose the reason rather than silently disappearing the candidate;
- featured/top-K shelves must disclose that they are bounded projections of a complete lane, never the complete candidate population;
- no risk feature may remove a candidate from All Candidates except through a separately owned validity/identity/data-integrity rule.

A future strategy may choose “do not take this risk,” but that is not the same as erasing the opportunity state.

---

# 8. Finding AR-8 — product wording can promote an experiment by copy

**Severity:** MAJOR epistemic UX risk.

## Attack

Even with `authority=false` in data, copy such as “underpriced” or “should be +20%” can make an experimental incorporation read functionally authoritative to the user.

## Binding Amendment A8 — copy authority parity

Product language must reflect the actual authority tier.

Examples:

### Experimental

> “Price response appears light versus the research baseline; incorporation analysis is experimental.”

### Promoted contextual/rank evidence

> “Price response remains below the calibrated range for comparable evidence states.”

### Forbidden without separately earned forecast authority

> “The stock is 25% undervalued.”

> “Fair value is $X.”

> “The market is wrong.”

The UI cannot upgrade a statistical research state into a forecast through phrasing.

---

# 9. Finding AR-9 — relationship cycles can reintroduce the target indirectly

**Severity:** MAJOR for graph propagation studies.

## Attack

Even with direct target exclusion, graph aggregates can contain cycles:

```text
A shock → B → C → A
```

or an ETF/holding/company chain that routes target-return information back into the expected-pressure feature.

## Binding Amendment A9 — path-provenance / cycle guard

For confirmatory transmission-pressure research:

- every aggregate contribution must preserve source/path provenance;
- reject or separately classify paths that re-enter the target economic issuer before the prediction endpoint;
- cap propagation depth according to a preregistered mechanism, not observed performance;
- distinguish direct evidence transmission from contemporaneous price-network propagation;
- include cycle/degree concentration diagnostics.

A temporal graph model later inherits the same law; graph depth does not waive leakage controls.

---

# 10. Finding AR-10 — “independent roots” can still be economically dependent

**Severity:** MODERATE/MAJOR depending use.

## Attack

Two separately published sources can be causally dependent. Example: an analyst revision and a news article both react to the same company guidance. Different URLs are not independent information roots in the economic sense.

## Binding Amendment A10 — two-level dependence model

Preserve at least two concepts:

1. **source/evidence root identity** — same originating artifact/event lineage;
2. **economic dependence group** — distinct roots that plausibly reflect the same underlying information shock.

The product may state source-root counts, but Fusion/evaluation must avoid assuming source-root uniqueness equals statistical independence.

Cell F/G should research the minimum practical dependence grouping; where uncertain, use conservative grouping/uncertainty rather than inflated confirmation.

---

# 11. Finding AR-11 — missingness can itself encode universe selection

**Severity:** MAJOR model-evaluation risk.

## Attack

A model can learn that “options covered,” “analyst consensus available,” or “segment economics available” proxies for size/liquidity/quality. Apparent feature value may come from coverage selection rather than the evidence value itself.

## Binding Amendment A11 — coverage-selection audit

Every predictive/priority experiment involving sparse families must report:

- covered vs uncovered cohort composition;
- baseline outcomes for both cohorts;
- size/liquidity/sector/species differences;
- feature increment **within the covered cohort**;
- whether adding a coverage indicator alone explains the apparent lift;
- production behavior for uncovered names.

A sparse family does not earn broad authority from cross-sectional performance dominated by who happens to be covered.

---

# 12. Finding AR-12 — correction-safe backtests need contemporaneous feature reconstruction, not corrected final truth

**Severity:** BLOCKER for historical validation of corrected sources.

## Attack

The masterplan preserves correction lineage, but a builder could train/evaluate on the final corrected historical dataset while calling it PIT because source timestamps exist.

## Binding Amendment A12 — dual historical views

Where corrections/restatements matter, distinguish:

- **contemporaneous-belief view** — what Mastermind could lawfully have known at each decision clock;
- **final-corrected truth view** — later corrected economic truth used for audit/labeling where appropriate.

Predictive features use contemporaneous-belief view.

Final-corrected truth may be used for specific outcome/quality audits only when the experiment states why it is legitimate.

Never silently replace historical feature values with later corrections.

---

# 13. Findings that survived without amendment

The adversarial pass found no architecture change required for:

## Availability separation

The masterplan consistently keeps Availability deterministic and independent from intelligence. Amendment A7 strengthens visibility but does not change this law.

## Specialist ownership

No system-level document requires Prophet to own Earnings/Bio/Defense/Capital/Options truth.

## Market Memory / Stock Identity

The architecture preserves their distinct ownership and anti-outcome-audition/prospective constraints.

## Model ladder

E1 deterministic baseline before E3/E4/E5 remains correct; E5 temporal graph is explicitly optional.

## Hypothesis failure

The kill matrix allows features to fail while retaining independent descriptive/product jobs. No architecture rewrite is required if individual alpha hypotheses fail.

## Healthy abstention

Reference cases explicitly include no-action, unestimable, missing-data and conflicting-evidence states.

---

# 14. Required propagation into future cell research

## Cell A must incorporate

A1, A3, A9, A10, A12.

## Cell B must incorporate

A1-A6, A8-A12.

## Cell C must incorporate

A4, A10, A12.

## Cell D must incorporate

A2, A10-A12 for analogue/calibration work.

## Cell E must incorporate

A7, A11, A12.

## Cell F must incorporate

A5-A6, A8, A10-A12.

## Cell G must test/enforce

all amendments that affect evaluation, especially A1-A5 and A9-A12.

## Cell H must incorporate

A7-A8 and the distinction between source-root vs economic dependence.

---

# 15. Updated research acceptance checklist

No Cell A/B incorporation/transmission result can receive PASS unless the return answers:

1. Was the target economic issuer excluded from its own pressure baseline?
2. Were cross-listings/share classes removed?
3. Were priors fold-frozen before the evaluated outcome?
4. Were price-derived sensitivities estimated strictly pre-event?
5. Was issuer materiality independent of the target response being explained?
6. Were mixed component units kept separate until lawful calibration?
7. Were graph cycles/path re-entry checked?
8. Were source-root and economic dependence distinguished?
9. Was coverage-selection bias measured?
10. Were contemporaneous-belief features reconstructed under correction lineage?

A missing answer is a HOLD, not a minor documentation gap.

---

# 16. No automatic rewrite of older documents

These amendments are intentionally a separate, explicit review artifact rather than silently rewriting all earlier masterplan prose.

Reason:

- preserves the history of what the architecture said before adversarial review;
- makes the discovered defect classes visible to future researchers;
- prevents an apparently seamless spec from hiding why certain controls exist.

`PROPHET_FLAGSHIP_READ_FIRST_2026-08-22.md` and Linear MAS-116 should point future sessions to this review after the integrated masterplan and before executing cell-specific research.

---

## Final adversarial verdict

**PASS WITH BINDING AMENDMENTS A1-A12.**

The flagship architecture remains coherent and appropriately modular.

The most dangerous failure mode was confirmed to be **circularity/leakage inside an apparently economically sensible response-pressure construction**, not the high-level product thesis.

With A1-A12 binding, future sessions have far less room to create a self-fulfilling “under-incorporation” signal or inflate evidence independence while believing they followed the masterplan.
