# CELL B — Evidence–Price Gap / Information Incorporation Research

**Linear:** MAS-118  
**Parent:** MAS-116  
**Canonical upstream owner:** `WS:ALPHA-INTELLIGENCE-INTEGRATION` / `research/dislocation_intelligence/`  
**Possible future consumer:** Prophet V4 D5 evidence adapter + Conditional Fusion, only after owner validation/promotion  
**Hardening archaeology pin:** Macro `af7f4af9a86c67885e13dd2bcf80b9932e3c399a`  
**Read first:** `RESEARCH_CELL_EXECUTION_CONSTITUTION_2026-08-22.md`  
**Authority:** RESEARCH / THEORY / FUTURE CONTRACT ONLY. Zero current P0 event-taxonomy change, price join, feature tuning, live score, Prophet integration or trade authority.

---

# 0. Observable mission

Harden the Chairman's core dislocation thesis into a scientifically defensible future capability:

> **When the company's information/evidence state changes, can Mastermind estimate whether the security's market-price state has responded less, roughly as much, or more than comparable history and context would imply—without pretending to know an exact intrinsic fair value?**

The deliverable is a rigorous definition of **information incorporation state**, its estimands, clocks, baselines, leakage defenses, failure states and future adapter path.

This cell does **not** test or modify the currently preregistered Cross-Issuer Dislocation P0. It works downstream and orthogonally so that P0 remains genuinely blinded.

---

# 1. Original Chairman intent

The key insight is:

> **The company's information state and its current market-price state temporarily disagree. That disagreement may be where alpha lives.**

This does NOT mean Mastermind must produce an exact “true value.” The Chairman explicitly recognizes that valuation can depend on regime, narrative, confidence, growth duration, rates, theme participation and investor expectations.

Therefore the desired system should answer a narrower and more tractable question:

> **Given what changed and what has historically happened after comparable changes, does the observed price response look unusually small, normal or unusually large?**

That can be useful even when a DCF-style fair value is unknowable.

The moat is the accumulated point-in-time history of **evidence change → expected response distribution → realized response path → later resolution**, conditional on event family, issuer/species, theme and context where estimable.

---

# 2. Current Dislocation P0 is a protected scientific experiment

`research/dislocation_intelligence/DISLOCATION_CROSS_ISSUER_P0_PREREG_2026-08-20.md` freezes a specific experiment around adverse temporary-event evidence + relative confirmation.

Its laws include:

- **Extractor is price/outcome blind.**
- Canonical manifest/source hashes/trials freeze before price join.
- Runner cannot change event fields.
- Endeavour/EXK/EDR and design-used issuers are excluded from proof.
- Mining is held as external validation until non-mining adjudication.
- Event families/controls are frozen.
- Exact fill clocks and donor/counterfactual rules are frozen.
- H0/H1/H2/H3/H4 arms are frozen.
- Sole primary claim is H4–H1 40-session policy return after costs.
- Falsifiers can kill the construction.
- P0 has zero Prophet/score/rank/gate authority.

**Cell B MUST NOT:**

- read P0 outcomes if current law says they remain blind;
- propose post-outcome P0 taxonomy changes;
- tune arms/horizons/controls;
- use the EXK thesis to redefine P0;
- fold the future Evidence–Price Gap into the P0 test.

If P0 later fails, Cell B may still research a broader incorporation framework—but cannot claim P0 validated it.

---

# 3. What Evidence–Price Gap is NOT

The fresh session must not misconstrue the idea as:

### Exact fair value

Do not output “stock is 37% undervalued” unless a separate validated valuation owner supports that claim. Information incorporation is relative/empirical, not omniscient intrinsic value.

### Raw price change after news

A -5% move after bad news may be an underreaction, overreaction or normal depending on market/sector/theme/issuer/event magnitude.

### Sentiment minus return

LLM sentiment is not an evidence magnitude ruler and must not create rank authority.

### “Good news but stock down = buy”

Price may correctly reject apparently positive evidence because the evidence is expected, immaterial, low quality or offset by other information.

### Generic residual z-score

A statistical residual is an observation. It does not automatically mean mispricing.

### P0 rebranded

P0 tests a specific temporary-event + confirmation policy. The future framework should be able to consume many validated evidence families without rewriting them.

---

# 4. Conceptual decomposition the research must preserve

The cell should treat incorporation as at least four independent objects.

## 4.1 Evidence change

What new information became knowable?

Examples:

- earnings revision;
- guidance change;
- customer capex change;
- procurement award;
- temporary disruption/recovery;
- clinical milestone/outcome;
- capital-structure change;
- commodity/input shock;
- theme propagation evidence.

Owned by source/specialist systems.

## 4.2 Expected economic/material effect

How important should this information be to the company economically or probabilistically?

This is domain-specific and may be unestimable. Cell C owns cross-domain catalyst semantics; Cell A owns theme/transmission exposure. Cell B consumes those outputs later rather than inventing its own materiality facts.

## 4.3 Expected market response distribution

Historically, after comparable knowable evidence, how did this security class or matched cohort tend to respond over a declared horizon?

This is a statistical distribution, not fair value.

## 4.4 Realized incorporation path

How much has the target security actually moved relative to the appropriate market/sector/theme/control since the evidence became tradable?

The gap between 4.3 and 4.4 is a candidate **incorporation observation**, subject to uncertainty and confounds.

---

# 5. Target estimands — the cell must compare alternatives

Do not commit to one equation prematurely. Research at least these formulations.

## 5.1 Residual response percentile

Within a validated event/evidence family, compare target residual return to historical matched distribution.

Example output:

> “At T+2, target residual response is in the 18th percentile of comparable positive-surprise episodes.”

This says response is unusually small, not that price is wrong.

## 5.2 Expected-pressure vs realized-response gap

Conceptual form:

```text
expected_response_pressure
  = issuer_specific_surprise/materiality
  + theme impulse × defensible exposure
  + relationship propagation terms

incorporation_gap
  = expected_response_pressure distribution
    versus realized residual response
```

The research must attempt to KILL this formulation if simpler family-specific methods work better.

## 5.3 Matched episode difference

Retrieve historically similar episodes and compare current response path to analogue median/distribution. This may be more interpretable than one global model.

## 5.4 Synthetic-control abnormal response

For discrete issuer events, use a pre-event donor/synthetic control to estimate abnormal response. P0 already uses matched-k/sc-NNLS in one construction; do not automatically reuse them for every family.

## 5.5 Cross-sectional peer propagation gap

When a theme/catalyst affects several related companies, measure whether one security lags the response of economically linked peers after controlling common factors.

This requires Cell A's relationship/exposure truth to avoid “peer” by sector label alone.

---

# 6. Baseline hierarchy / residualization research

The cell must define when each baseline is appropriate and how to prevent target leakage.

Candidate hierarchy:

1. broad market benchmark;
2. sector/industry residual;
3. canonical theme factor/basket where PIT membership and rights are valid;
4. matched peer cohort;
5. synthetic control;
6. issuer-specific expected beta model;
7. mechanism-specific related-company control.

Questions to resolve:

- When does subtracting a theme basket remove the very propagation signal being studied?
- How do we exclude the target from a theme factor to avoid mechanical circularity?
- How do we handle thin/small-cap stocks with unstable beta?
- How do we avoid choosing the baseline that makes the gap look largest?
- What is the prespecified fallback order when preferred control is unavailable?
- How do corporate actions, delistings and ticker reuse affect controls?

Estimator disagreement should be printed and treated as uncertainty, not silently averaged.

---

# 7. Evidence magnitude / comparability problem

Cross-family evidence cannot be added in raw units.

A $500M defense award, a 300bp guidance raise, a clinical trial milestone and an AI capex read-through do not share a natural scale.

The research must compare architectures:

### Family-native percentile

Normalize evidence magnitude relative to historical observations of the same family/species.

### Economic materiality ratio

Normalize to issuer revenue, EBITDA/backlog/cash/market cap where the domain owner can defend the denominator.

### Surprise vs expectation

Use pre-event expectation baseline where one exists.

### Categorical state

When N is weak, classify only `LOW/MEDIUM/HIGH_MATERIALITY` or `UNESTIMABLE` rather than fake precision.

### Hierarchical model

Potential later method to pool related families while retaining family-level effects.

Hard rule: **no universal LLM-generated 0–100 evidence strength.**

---

# 8. Clock / event-time architecture

This cell is highly sensitive to time leakage.

The research must define at minimum:

- source occurrence time;
- first public/lawfully available time;
- Mastermind captured time;
- first tradable market instant/session;
- baseline price instant;
- response horizon clocks;
- confirmation time if later evidence changes state;
- correction/retraction time.

Rules:

- after-close vs pre-open matters;
- date-only source may be unusable for fine inference;
- no nearest-date substitution;
- no forward fill across unavailable price sessions;
- a later filing correction cannot change the original event's historical features;
- a relationship/theme membership must be valid as known then;
- event and price clocks must use the security's actual exchange calendar.

The P0 fill law is a useful precedent but is not automatically universal.

---

# 9. Underreaction vs “market correctly ignored it”

This is the hardest conceptual problem and must be treated explicitly.

A small price response can mean:

- true underreaction;
- evidence was expected;
- evidence is economically immaterial;
- evidence quality is poor;
- another negative fact offset it;
- the security is illiquid and price discovery is delayed;
- theme/market moved oppositely;
- market believes management claim is unreliable;
- evidence affects distant optionality but not near-term cash flow;
- prior price already anticipated it.

Therefore a future incorporation state needs **confidence and counterevidence**, not merely gap magnitude.

Cell B should define the minimum set of explanatory fields required before using words such as `UNDERINCORPORATED`.

A conservative first product may use:

- `RESPONSE_SMALL_VS_HISTORY`;
- `RESPONSE_TYPICAL`;
- `RESPONSE_LARGE_VS_HISTORY`;
- `UNESTIMABLE`;

with “underreaction” reserved for later promoted inference.

---

# 10. Multi-evidence attribution / overlapping events

Real markets rarely present one isolated fact.

Design rules for:

- earnings + guidance + product launch same day;
- macro shock overlapping issuer news;
- several customer read-throughs across days;
- mitigation/update after initial adverse event;
- theme impulse and company-specific evidence arriving together;
- capital raise following a positive catalyst.

Potential approaches:

- event bundles / episode identity;
- attribution windows with explicit collision flags;
- refuse clean causal attribution but retain descriptive aggregate state;
- sequential Bayesian/hazard-style updates later;
- event-family priority rules only if preregistered and economically justified.

Never force one event label when the evidence is genuinely entangled.

---

# 11. Liquidity / microstructure / reflexivity

A delayed response can come from trading mechanics rather than mispricing.

Research whether incorporation assessment needs:

- median dollar volume;
- spread/liquidity;
- halt status;
- gap/open mechanics;
- short/borrow constraints;
- options-implied move / volatility state;
- small-float/high-short reflexivity;
- market-hours vs overnight response.

Cell E owns broad positioning/crowding evidence. Cell B should specify adapter needs, not recreate those systems.

---

# 12. Complete user / machine journey

## 12.1 New evidence is validated upstream

Example: two large customers raise data-center capex; GMI says a supplier has verified economic exposure; Earnings shows no contradictory issuer update.

## 12.2 Expected-response reference is selected

System uses the frozen family/species/control hierarchy. If too few comparable episodes exist, output is `UNESTIMABLE`.

## 12.3 Actual response is measured

Residualized response since first tradable evidence time is computed with exact market clock.

## 12.4 System reports incorporation state

Example:

> “Evidence strength/materiality is high relative to this family; linked peers rerated 8–14%; this security's residual response is +2.3%, in the 14th percentile of matched historical responses. Coverage is moderate; supplier dependency is verified, revenue-share mapping is incomplete. State: RESPONSE_SMALL_VS_HISTORY, research-priority candidate.”

This is very different from “fair value +20%.”

## 12.5 Prophet consumes later only after promotion

Cell G/Eval/Fusion determines whether incorporation state adds prospective value. It may become a D5 head. It never controls deterministic entry availability.

---

# 13. Required reference compositions

The research must produce at least:

1. **Strong evidence / small response / good controls** — candidate underincorporation hypothesis.
2. **Strong evidence / huge response** — thesis valid but likely already incorporated.
3. **Positive headline / low materiality** — small response is normal, not dislocation.
4. **Strong evidence / contradictory evidence** — refuse clean gap conclusion.
5. **Illiquid security / delayed prints** — response measurement uncertain.
6. **Theme-wide rally / target lags** — test whether lag survives theme residualization.
7. **No historical analogues** — `UNESTIMABLE`, not neutral.
8. **Overreaction possibility** — response far exceeds historical distribution; potential wait/mean-reversion research, not automatically short.

---

# 14. Falsification / threat model

Mandatory threats:

- event taxonomy defined after seeing price;
- evidence magnitude tuned to outcomes;
- baseline chosen post hoc;
- current theme membership used historically;
- target included in its own control/theme factor;
- delisted losers missing;
- survivorship bias;
- price timestamp earlier than source availability;
- overlapping market shock mistaken for event response;
- high-return family carried by one issuer/date/theme;
- estimator disagreement hidden;
- small N represented as confidence;
- only large liquid winners have complete data;
- LLM materiality correlated with hindsight because source spans include later updates.

Required negative controls/placebos:

- no-event matched dates;
- structural-impairment controls for temporary-event constructs;
- random/permuted event dates where economically meaningful;
- unrelated same-sector companies;
- future relationship/member leakage test;
- stale evidence control;
- generic breakout control.

---

# 15. Relationship to current P0

The final research must explicitly describe three possible worlds:

### P0 passes

Its validated temporary-event/confirmation construct becomes one strong evidence family that can inform the broader framework. Do not generalize its effect to all catalysts.

### P0 is mixed

Preserve useful event attribution/context findings; only surviving families/arms may inform future research.

### P0 fails

Kill that tested entry construction as preregistered. The broader incorporation research can continue with other independent evidence families, but cannot cite P0 as support.

This prevents sunk-cost logic.

---

# 16. Buildability / estimability ledger

The cell must classify candidate capabilities:

- family-specific residual response percentile;
- family-specific expected response model;
- cross-family materiality normalization;
- theme propagation incorporation;
- matched analogue incorporation;
- overreaction state;
- multi-event attribution;
- intraday incorporation;
- species-conditioned response;
- regime-conditioned response;
- learned global incorporation model.

Likely result should be **progressive**: simple family-specific deterministic/statistical observations first; global learned model last, if ever.

---

# 17. Proposed future implementation waves — NOT authorized

### B-W1 — Incorporation estimand & baseline research freeze

Docs/replay design only. No current P0 change.

### B-W2 — One validated evidence-family historical/PIT incorporation lens

Use an owner-approved family with adequate PIT history. Produce descriptive response percentile + uncertainty, zero Prophet rank authority.

### B-W3 — Prospective incorporation shadow

Freeze family/version/baseline; accrue response observations on future events and compare against historical expectations.

### B-W4 — Cross-family adapter contract

Only after Cell F D5 grammar exists. One `incorporation` head with family-specific provenance and `UNESTIMABLE` behavior.

### B-W5 — Fusion/Eval promotion study

Cell G/Conditional Fusion evaluates incremental early/actionable value. No direct trade authority.

---

# 18. Explicit non-goals / do-not-redo

- Do not modify or outcome-contaminate Dislocation P0.
- Do not use EXK/EDR design examples in P0 proof.
- Do not produce intrinsic fair value from this cell.
- Do not make sentiment a materiality score.
- Do not select favorable residual baseline after outcomes.
- Do not fuse matched-k/sc-NNLS disagreement into one prettier number.
- Do not create a universal event store.
- Do not create another ranker or score.
- Do not use future theme relationships/memberships in historical tests.
- Do not infer “underreaction” from small raw return alone.
- Do not default no analogue to zero gap.
- Do not let incorporation intelligence bypass `ENTRY_OPEN` availability.

---

# 19. Fresh-Sol misconstruction checklist

Prove all are false:

1. I treated the project as fair-value modeling.
2. I retuned P0 after seeing outcomes.
3. I used positive-news sentiment minus price return.
4. I assumed small response means mispricing.
5. I invented one cross-family evidence-strength scale.
6. I picked whichever control made the thesis work.
7. I ignored overlapping events.
8. I used current taxonomy/relationships historically.
9. I forced a conclusion when N/controls were insufficient.
10. I gave the resulting head immediate Prophet rank authority.

---

# 20. Required final deliverable / stop condition

Return a durable incorporation research architecture containing:

- exact current P0 non-interference proof;
- Chairman-intent reconstruction;
- target-estimand comparison;
- baseline/residualization hierarchy;
- evidence magnitude/materiality options;
- clock/fill/correction law;
- overlapping-event attribution law;
- underreaction-vs-correct-ignore framework;
- liquidity/microstructure requirements;
- eight reference compositions;
- leakage/falsifier/negative-control matrix;
- buildability/estimability ledger;
- P0-pass/mixed/fail continuation branches;
- 3–5 owner-routed future wave packets;
- CEO decisions/unresolveds.

**STOP before price-joining or retuning the protected current P0, implementing a live incorporation score, changing Prophet/Fusion/Availability, or reading outcomes forbidden by current source law.**
