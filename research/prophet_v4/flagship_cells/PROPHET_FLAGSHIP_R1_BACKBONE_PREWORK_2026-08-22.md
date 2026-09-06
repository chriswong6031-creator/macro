# PROPHET FLAGSHIP INTELLIGENCE — R1 BACKBONE PREWORK

**Date:** 2026-08-22  
**Cells:** A / MAS-117, F / MAS-122, G / MAS-123, B / MAS-118  
**Status:** SOL PREWORK — candidate contracts/experiments for future cell sessions to attack, refine, narrow or reject; **not cell completion and not implementation authority**  
**Required companion:** `PROPHET_FLAGSHIP_ADVERSARIAL_REVIEW_AND_AMENDMENTS_2026-08-22.md`

---

# 0. Purpose

The R1 research cells form the intellectual backbone:

```text
A — what is the company economically exposed to and how should information propagate?
F — how does owner evidence enter Prophet without becoming a second ranker/warehouse?
G — how do we prove a family made Prophet earlier/better rather than merely more complicated?
B — given lawful evidence, how do we test whether price has incorporated it?
```

This document pre-fills the **most likely strong starting design** from current estate archaeology and the integrated flagship research.

Future cells should not repeat broad first-principles debate unless new evidence invalidates the candidate design.

Every section is labeled:

- `PRELIMINARY_RULING` — Sol-preferred starting architecture, not implementation authorization;
- `OPEN_TEST` — empirical question;
- `REJECTED_STARTING_SHAPE` — do not waste research time without new evidence;
- `CELL_MUST_RETURN` — exact unresolved output required from the future cell.

---

# 1. Current estate facts that materially constrain R1

## 1.1 Existing US Context Vector is already a PIT full-universe history

Current `engine/us_context_vector.py` / `research/CONTEXT_VECTOR_SCHEMA_CONTRACT.md` establish:

- full analyzed US universe, including ineligible names;
- keep-first on `(stamp_date, ticker, board_definition)`;
- schema-union append;
- monthly physical parts behind a single reader;
- no retroactive backfill;
- null = unmeasured, never false;
- source-owned columns read off existing producers;
- zero authority at birth;
- no forward-return join / no score origination;
- existing identity/board, rank/shadow, theme, event, flow, regime, risk and Context Snapshot columns;
- tier separation (`curated` vs `scan`);
- coverage is uneven and intentionally disclosed.

**Consequence:** D5 does not need to rebuild the historical nightly feature/admission log.

## 1.2 D5 contract is already ruled ready before all families are measurable

`D1_D5_READINESS_RULING.md` freezes:

- D5 contract can exist after D1;
- Theme family remains `ACCRUING` with `theme_state_not_built` until canonical D3;
- no ticker-string joins;
- rights fields mandatory;
- sparse scan-tier coverage must be honest;
- predecessor/owner surfaces cannot be silently promoted to measured ThemeState.

## 1.3 GMI W2 already tested the “three exposure axes” premise honestly

`W2_EXPOSURE_AXES_PREREG.md` already defines:

- `economic_share`;
- `trading_beta`;
- `attention_share`.

Important findings/constraints:

- `economic_share` is honest null because no production per-company segment/theme revenue source exists;
- current W2 explicitly rejects LLM-generated exposure numbers;
- `trading_beta.v0` uses an **ex-self equal-weight basket** and causal shift — an important anti-circularity precedent;
- attention sources are market-specific, shallow/sparse in places, and coverage floors/refusals are built into the prereg;
- current/history theme membership before observation era is reconstruction-labelled rather than pretended PIT truth.

## 1.4 Current Fusion already owns cross-family influence

Conditional Fusion already has:

- canonical current US C1 role;
- family registry / typed evidence;
- dependence/anti-double-count concerns;
- prospective paired challenger race;
- forward outcome gate.

**Consequence:** R1-F should define translation/lineage, not weighting.

## 1.5 Current Eval OS already owns forward evidence and rulers

Eval OS / QLedger already own:

- horizon units/rulers;
- prospectivity;
- evidence clocks;
- benchmark/matched-control policy;
- promotion legality.

**Consequence:** R1-G should define flagship metric/experiment semantics over canonical outcomes rather than build a new result store.

## 1.6 Current Dislocation P0 is blinded and protected

Cell B prework may define a future general incorporation architecture, but cannot tune the active Cross-Issuer Dislocation P0 taxonomy/manifest/arms from outcomes.

---

# 2. R1-A Theme Intelligence — candidate starting architecture

## PRELIMINARY_RULING A-P1 — exposure is an axis registry, not one percentage

Start with the following conceptual registry:

```text
company_theme_exposure.vNext
  identity
    issuer_id
    security_id?              # only for security-specific axes
    theme_id
  axis_id
  value
  unit
  numerator_definition
  denominator_definition
  applicability
  coverage_state
  evidence_quality
  source_refs[]
  source_effective_at
  known_at
  captured_at
  valid_from
  valid_to
  correction_of?
  rights_tier
  authority_tier
```

Candidate axes:

### Company/issuer-grain economic axes

- `revenue_share`
- `profit_share` where disclosed/estimable
- `capex_share` where meaningful
- `customer_dependency`
- `supplier_dependency`
- `input_cost_dependency`
- `policy_funding_dependency`
- `geographic_dependency`
- `strategic_optionality`
- `management_attention`

### Security/market-grain axes

- `trading_beta`
- `attention_share`
- optional future positioning sensitivity

**Do not combine company-grain economic exposure and security-grain trading sensitivity into one scalar.**

## REJECTED_STARTING_SHAPE A-R1

```text
theme_exposure = 0.73
```

with no named axis/denominator/evidence.

## PRELIMINARY_RULING A-P2 — first economic-share vertical should be one diversified issuer, one theme, one filing package

The first Cell A research target should not be broad-universe extraction.

It should prove the ontology/clock/correction problem on one real diversified issuer with a nontrivial segment structure:

```text
exact filing package
→ segment definition occurrence(s)
→ segment revenue/profit/product facts
→ known-at/revision lineage
→ theme mapping evidence
→ one economic exposure axis
→ historical change across at least one segment-definition/revision boundary if available
```

The research must answer:

- What is the canonical segment identity across filings?
- What happens when the issuer reorganizes segments?
- Can product/service detail map to a theme without forcing the entire segment into it?
- Can overlapping themes exceed 100% in summed “exposure” because themes are non-exclusive? If yes, how is that explained?
- How are intersegment/elimination amounts treated?
- Does current FIF/filing infrastructure expose enough dimensions, or is a new **owner-owned** semantic layer required?

## PRELIMINARY_RULING A-P3 — ThemeState should separate evidence impulse from return impulse

Candidate ThemeState vector:

```text
theme_state
  identity/theme version
  source session / decision clock
  membership basis/version

  market:
    member_breadth
    residual_return_impulse
    dispersion
    leadership_concentration
    volatility_state

  evidence:
    event_breadth
    evidence_acceleration
    estimate_revision_breadth
    capex/procurement_impulse
    narrative_attention_acceleration

  propagation:
    first_impulse_at
    propagation_depth
    downstream_breadth
    lag_state

  quality:
    membership_quality
    source_coverage
    freshness
    era
```

### OPEN_TEST A-T1

Which fields are actually estimable, nonredundant and PIT-safe now?

### REJECTED_STARTING_SHAPE A-R2

One `theme_score` that mixes membership, returns, narrative and price momentum without explainable family separation.

## PRELIMINARY_RULING A-P4 — transmission must be mechanism-conditioned

Candidate mechanism registry:

```text
CUSTOMER_CAPEX_TO_SUPPLIER_DEMAND
SUPPLIER_DISRUPTION_TO_CUSTOMER_CAPACITY
COMPETITOR_CAPACITY_TO_PRICING
SUBSTITUTE_PRODUCT_TO_SHARE_SHIFT
SHARED_INPUT_COST
SHARED_END_MARKET_DEMAND
POLICY_FUNDING_CHAIN
DISTRIBUTION_PLATFORM_DEPENDENCY
GEOGRAPHIC_DEMAND
FINANCING_RATE_SENSITIVITY
PEER_EXPECTATION_READTHROUGH
```

Each mechanism requires:

- source node type;
- destination node type;
- relationship evidence;
- expected sign if defensible;
- economic axis;
- valid interval;
- shock definition;
- target-issuer leave-out baseline where price aggregates are used;
- negative controls;
- minimum support;
- refusal state.

## PRELIMINARY_RULING A-P5 — first response baseline should be simple before graph ML

Candidate first Theme/Transmission research baseline:

```text
IndependentThemeImpulse(k,t)
  = robust aggregate of pure/strong members
    excluding target economic issuer and cross-listings
    using preregistered residual-return or evidence-impulse method

ExposureWeightedThemePressure(i,t)
  = Σ_k economic_exposure(i,k,t_known) × IndependentThemeImpulse(k,t)
```

Then compare to simple baselines:

- market/sector momentum;
- equal-weight theme membership;
- target's own lagged momentum;
- exposure-weighted impulse;
- volatility-normalized variant.

No graph neural network belongs in the first test.

## CELL A MUST RETURN

1. exact economic-exposure golden-issuer/source choice and why;
2. segment identity/correction design;
3. accepted/rejected exposure axes;
4. accepted ThemeState fields vs predecessors to adopt/supersede;
5. mechanism registry with at least one highest-value first mechanism;
6. exact PIT/negative-control design for exposure-weighted impulse;
7. current data gaps/rights gaps;
8. 3–5 owner-routed verticals, not implementation started.

---

# 3. R1-F Evidence Translation — candidate D5 design

## PRELIMINARY_RULING F-P1 — preserve Context Vector as a PIT research/history store

Current Context Vector has legitimate jobs that D5 should not replace:

- nightly full-universe feature/admission history;
- keep-first research tape;
- historical schema union;
- zero-authority feature capture;
- curated + scan population context;
- experiment substrate.

**Candidate ruling:** `REUSE_AS_PIT_HISTORY_SUBSTRATE`, not `SUPERSEDE`.

Cell F must verify whether any current consumer/owner change since this prework invalidates that ruling.

## PRELIMINARY_RULING F-P2 — D5 is a typed decision-time evidence envelope

D5's useful grain is not “another flattened 150-column universe table.”

Candidate conceptual hierarchy:

```text
prophet.intelligence_vector/v1
  episode_id
  security_id
  issuer_id
  decision_session
  generated_at
  coverage_summary
  families[]
```

Each family:

```text
family_id
family_version
owner
method_class               # deterministic | statistical | model_generated
authority_tier
applicability
status                     # measured / accruing / not_covered / ...
null_reason?
coverage
freshness
confidence_state
known_at
source_effective_at?
captured_at
corrected_at?
rights_tier
evidence_roots[]
economic_dependence_groups[]
features{}
explanation_facts[]
```

The outer envelope **does not require all families to share one numeric scale**.

## PRELIMINARY_RULING F-P3 — separate `feature` from `head`

An owner family can expose several facts/features. A Prophet “head” is a semantic projection, e.g.:

```text
emergence
evidence_trajectory
theme_state
economic_exposure
transmission
expectation_surprise
issuer_materiality
price_incorporation
empirical_prior
structural_fragility
path_fragility
crowding_attention
confidence
```

Candidate rule:

- **family** preserves source/owner lineage;
- **head** is a product/research semantic grouping;
- **Fusion member** is an explicitly registered rank feature with its own authority/version.

Those three are not synonyms.

## PRELIMINARY_RULING F-P4 — D5 should store references, not duplicate source truth

Example:

```text
family_id: earnings_surprise
owner: earnings_intelligence
features:
  surprise_state: POSITIVE
  issuer_materiality_state: HIGH
source_refs:
  - earnings_event_id...
  - financial_packet_id...
```

D5 should not copy the full transcript/filing packet or originate the underlying actual/consensus arithmetic if the owner already owns it.

## PRELIMINARY_RULING F-P5 — evidence independence needs two layers

Candidate minimum lineage:

```text
evidence_root_id
root_event_id
source_object_id
economic_dependence_group
feature_derivation_id
```

Why:

- same transcript → several derived features = same root;
- analyst revision article + broker estimate change may be distinct source objects but same economic-information shock;
- customer capex announcement may generate news + theme evidence + supplier read-through; roots/dependence must survive across families.

## PRELIMINARY_RULING F-P6 — status vocabulary should be semantically richer than plain null

Candidate common status vocabulary, mapped to existing V4 law:

```text
MEASURED
MEASURED_NEUTRAL
ACCRUING
NOT_APPLICABLE
NOT_COVERED
SOURCE_UNAVAILABLE
STALE
RIGHTS_BLOCKED
IDENTITY_UNRESOLVED
INSUFFICIENT_HISTORY
UNESTIMABLE
CONFLICTED
CORRECTION_PENDING
```

Cell F must reconcile exact names against current D5/V4 contract rather than invent incompatible duplicates.

## PRELIMINARY_RULING F-P7 — no “confidence number” unless calibration exists

Prefer typed quality fields first:

```text
source_quality
identity_quality
coverage_quality
history_quality
model_calibration_state
```

If later product needs one confidence tier, derive a transparent tier from these with explicit missingness; do not expose `confidence = 82` by aesthetic preference.

## REJECTED_STARTING_SHAPE F-R1

A giant flat `prophet_intelligence_features.parquet` that becomes a second source warehouse and implicit ranker.

## CELL F MUST RETURN

1. field-by-field current Context Vector `REUSE / EXTEND / SUPERSEDE / REJECT` ruling;
2. candidate D5 JSON/schema example for at least 5 real/reference families;
3. exact status/null vocabulary reconciliation;
4. evidence-root/economic-dependence contract;
5. correction/revision semantics;
6. episode/security/issuer grain rules;
7. D5↔Fusion exact seam;
8. D5↔Context Vector write/read relationship;
9. smallest future D5 contract-only vertical.

---

# 4. R1-G Value of Information — candidate measurement architecture

## PRELIMINARY_RULING G-P1 — EAWC should remain a metric family, not one optimization scalar initially

The flagship mission has several simultaneous dimensions. Start with a dashboard/registered metric dictionary rather than one composite.

### A. Earliness

**First Eligible Surface**

Earliest decision session at which the frozen system could have surfaced the episode under its registered candidate rules.

**Lead Time vs Champion**

```text
lead_sessions = champion_first_surface - challenger_first_surface
```

Positive = challenger earlier.

Must compare the same episode/population under the same decision clock.

### B. Actionability

**Actionable at First Surface**

Was deterministic Availability `ENTRY_OPEN` at the candidate's first eligible surface?

**Opportunity Consumption at First Surface**

Use a preregistered, availability/geometry-derived measure rather than future-picked “stock had already moved 10%.” Candidate forms:

- distance from first evidence price relative to frozen entry-zone/chase geometry;
- ATR-normalized move since first evidence;
- fraction of eventual MFE already consumed, **descriptive only** because eventual MFE is future knowledge and cannot define live status.

Cell G must choose which belongs in confirmatory vs descriptive metrics.

### C. Ranking

- NDCG@K;
- precision@K;
- recall@K;
- rank of later positive-path episodes at first eligible surface;
- rank stability / churn.

### D. Path quality

- MFE;
- MAE;
- R;
- time to +0.5R / +1R where defined;
- time underwater;
- invalidation;
- false-bounce;
- tail loss.

### E. Coverage

- eligible population;
- covered population;
- covered-vs-uncovered cohort characteristics;
- effective N;
- refusal counts.

### F. Product value

- operator review volume;
- watch/pass/reject/action rates;
- explanation drill-down;
- later correction rate;
- user override/rejection reasons.

## PRELIMINARY_RULING G-P2 — define “winner” only from a registered outcome rule; prefer continuous metrics in core reports

Do not let “winner” be hand-curated after results.

Candidate use:

- core reports remain continuous (R/MFE/MAE/path);
- thresholded winner classes are registered per experiment/horizon;
- sensitivity across reasonable thresholds is disclosed.

## PRELIMINARY_RULING G-P3 — same-tape paired experiments are default

For family `f`:

```text
Champion(t)                 # frozen current system
ChampionMinusF(t)           # same decision tape, f withheld
ChampionPlusF_Shadow(t)     # if f is not in champion
ShuffledF_Placebo(t)        # within lawful structure
```

Compare on the **same candidate episodes / same clocks / same availability state** where the experiment design allows.

If f changes candidate retrieval/population, report that as a separate retrieval effect rather than pretending a paired rank-only experiment.

## PRELIMINARY_RULING G-P4 — separate four ways a family can add value

1. **Discovery value** — surfaces a candidate that champion missed/was later on.
2. **Ranking value** — orders an already-shared candidate better.
3. **Risk/path value** — improves tail/MAE/trap understanding.
4. **Explanation/product value** — improves human decision quality without rank alpha.

A family can PASS one and FAIL another.

## PRELIMINARY_RULING G-P5 — lead-time preservation is a hard review axis

A challenger that improves top-K precision but surfaces candidates materially later cannot be called a flagship improvement without explicit tradeoff/alternate-lane ruling.

Candidate report:

```text
ΔNDCG
Δprecision@K
Δmedian_lead_sessions
Δactionable_at_first_surface
ΔMFE
ΔMAE
Δopportunity_loss
```

No promotion recommendation without displaying all relevant tradeoffs.

## PRELIMINARY_RULING G-P6 — effective N / concentration is mandatory

Every result should publish:

- rows;
- unique episodes;
- unique issuers;
- unique decision-date clusters;
- effective N / dependence grouping where applicable;
- top issuer/theme/species/date contribution;
- era splits;
- coverage cohort.

## PRELIMINARY_RULING G-P7 — promotion scorecard should be claim-specific

Candidate Sol scorecard fields:

```text
feature_version
claim_scope
population
prospective_clock_start
matured_n
coverage
primary_metric_result
lead_time_result
path_result
placebo_result
concentration_result
calibration_result
failure_states
verdict
maximum_authority
```

No single “VOI = 0.83” is needed.

## CELL G MUST RETURN

1. exact EAWC metric dictionary with formulas/denominators;
2. winner/positive-path label law and sensitivity policy;
3. discovery-vs-ranking-vs-risk-vs-product experiment taxonomy;
4. same-tape LOFO/placebo design compatible with current Eval/Fusion stores;
5. effective-N/concentration method;
6. lead-time preservation gate candidate;
7. promotion/demotion scorecard and authority ceiling mapping;
8. smallest report/read-model vertical using existing Eval/Fusion truth.

---

# 5. R1-B Evidence–Price Gap — candidate incorporation architecture

## PRELIMINARY_RULING B-P1 — incorporation is family-first before universal

Start with **one evidence family whose magnitude/materiality is estimable**, rather than a universal all-evidence gap.

Potential first research families after current owner gates:

- exposure-weighted theme impulse;
- earnings surprise/materiality;
- defense procurement materiality;
- a surviving Dislocation temporary-event family.

Cell B should choose based on data maturity, not product excitement.

## PRELIMINARY_RULING B-P2 — expected response and observed response are separate objects

Conceptual structure:

```text
ExpectedResponseEvidence
  family
  version
  decision_clock
  economic_magnitude
  exposure/materiality
  historical_prior_version
  expected_direction?          # nullable
  expected_response_state / distribution
  uncertainty

ObservedResponse
  target issuer/security
  window
  raw_return
  market_excess
  sector_excess
  theme_excess?
  factor_residual?
  matched_peer_residual?
  synthetic_control_residual?
  baseline_agreement
```

Then:

```text
IncorporationAssessment
  family
  horizon
  expected_response_reference
  observed_response_reference
  calibrated_state
  baseline_agreement
  confidence/estimability
  authority
```

## PRELIMINARY_RULING B-P3 — first calibration should be historical percentile/state, not a valuation target

Candidate family-specific calibration:

Within each walk-forward training fold and lawful population:

1. compute ex-ante evidence magnitude/materiality;
2. compute lawful response baseline(s);
3. learn empirical distribution of observed response conditional on evidence bucket/continuous model;
4. for new episode, compare current observed response to that pre-frozen distribution;
5. output a state, e.g. `LOW_RELATIVE_RESPONSE`, `IN_RANGE`, `HIGH_RELATIVE_RESPONSE`, `UNESTIMABLE`, with baseline agreement.

Only later, if calibration is strong, map to user vocabulary such as experimental `UNDER_INCORPORATED`.

This avoids pretending that `expected response = +12.4%` is known when the empirical distribution is wide.

## PRELIMINARY_RULING B-P4 — baseline ladder is a robustness test, not a menu to optimize

Candidate ordered baseline stack:

1. raw return;
2. market excess;
3. sector/industry excess;
4. independent theme excess;
5. simple public/owned factor residual;
6. matched peer basket;
7. synthetic control where preregistered and supported.

The experiment should freeze:

- primary baseline;
- secondary robustness baselines;
- disagreement rule.

If primary and plausible secondary baselines reverse the conclusion, output `CONFLICTED_BASELINES`.

## PRELIMINARY_RULING B-P5 — “correct ignore” is a mandatory negative class

A low price response can mean:

- market underreacted;
- event is economically immaterial;
- evidence is already expected;
- exposure is weak;
- evidence is low quality;
- a positive and negative root offset;
- liquidity delays the print;
- baseline is wrong.

Therefore a candidate gap state requires upstream evidence quality, expectation/materiality and exposure checks where applicable.

## PRELIMINARY_RULING B-P6 — first-time and evolving-episode states differ

At t0, only t0-knowable evidence may classify the initial response.

As new first-party evidence arrives, the **episode state may update prospectively**.

Do not use future confirmation to relabel the original t0 assessment as if it had been known then.

Candidate storage concept:

```text
incorporation_observation
  episode_id
  decision_session
  evidence_snapshot_version
  baseline_version
  state
```

append-only across the episode.

## PRELIMINARY_RULING B-P7 — Dislocation P0 remains a separate live experiment

Cell B may use P0's eventual adjudication as evidence. It may not retrofit the current P0 test into the universal incorporation architecture before the blind experiment closes.

## PRELIMINARY_RULING B-P8 — all A1-A12 amendments are binding

Especially:

- target issuer excluded from its own theme/peer response baseline;
- future folds excluded from response prior;
- price-derived exposures use strictly pre-event data;
- materiality not defined by target response;
- mixed evidence families not scalarized ad hoc;
- graph cycles/re-entry rejected;
- sparse coverage audited;
- contemporaneous-belief features used for historical decisions.

## OPEN_TEST B-T1 — simple expected-response state vs continuous regression

Compare at least:

- bucketed empirical response bands;
- regularized monotonic/linear response model where applicable;
- no-gap baseline.

Prefer the simpler method if it gives comparable calibration/robustness.

## OPEN_TEST B-T2 — does gap state add beyond momentum?

This is mandatory. If `low response + strong evidence` merely picks low-momentum/mean-reversion states already captured by existing timing features, the gap may be redundant.

## CELL B MUST RETURN

1. first candidate evidence family and why it is estimable;
2. exact response object and decision clocks;
3. frozen primary/secondary baseline hierarchy;
4. calibration method and fold law;
5. `correct ignore` negative-control taxonomy;
6. baseline disagreement semantics;
7. incremental test vs momentum/technical state/evidence-only;
8. product authority language for experimental vs promoted incorporation states;
9. owner route for any surviving method;
10. no modification of current blinded P0.

---

# 6. Cross-R1 seam — proposed shared research contracts

These are candidate interfaces for the cells to refine together, not production schemas.

## A → F

```text
ThemeEvidenceEnvelope
  exposure_axes[]
  theme_state
  transmission_evidence[]
  source/known_at/correction/rights
  authority
```

## C/A → B

```text
ExpectedResponseInput
  family
  evidence_magnitude
  issuer_materiality
  exposure/transmission
  expectation/surprise
  uncertainty
  decision_clock
```

Not every family populates every field.

## B → F

```text
IncorporationEvidence
  owner
  family_version
  state
  horizon
  primary_baseline
  baseline_agreement
  history_support
  known_at
  authority
```

F transports; it does not recompute.

## F → Fusion

Registered family/member projection with explicit version/authority/dependence.

## F/Fusion → G

Frozen feature/version + exact decision tape + outcomes.

## G → Sol

Claim-specific promotion/demotion scorecard.

---

# 7. Recommended R1 research order inside the parallel wave

The four cells may run in parallel, but their returns should be integrated in this order:

1. **F translation contract** — because it defines the common evidence language but can remain null-aware.
2. **G measurement contract** — because every later claim needs a common evaluation language.
3. **A theme/exposure architecture** — feeds the first large contextual family.
4. **B incorporation architecture** — consumes accepted/estimable evidence semantics.

This is an **integration order**, not a requirement to block research starts.

If B needs a field A has not accepted, B writes the dependency as `UNAVAILABLE / INPUT_CONTRACT_PENDING`; it does not invent it.

---

# 8. What R1 should make unnecessary later

After R1 returns, later implementation sessions should not have to debate:

- whether Context Vector is replaced wholesale;
- whether D5 is a flattened feature warehouse;
- whether exposure is one scalar;
- whether ThemeState mixes every signal into one score;
- whether rank weighting belongs in D5;
- whether EAWC is “accuracy”;
- whether later-but-more-precise automatically means better;
- whether incorporation can choose whichever baseline looks favorable;
- whether low response automatically means underreaction;
- whether historical priors can use final/full-sample calibration;
- whether evidence families can be summed before calibration;
- whether a failed feature must be kept because it was in the vision.

Those starting shapes are now either explicitly rejected or made testable.

---

## Closing prework ruling

The R1 backbone should aim for a **small number of clean contracts and falsifiable baselines**, not a giant intelligence model.

If R1 succeeds, the later build path should look boring in the best possible way:

```text
owner truth
→ typed D5 evidence envelope
→ deterministic explainable E1 priority
→ canonical Eval/VOI evidence
→ only then learned challengers
```

The novelty belongs in the quality of the economic intelligence and evidence history, not in creating another opaque control plane.
