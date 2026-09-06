# Prophet Flagship Intelligence Expansion — Hardened Cell Index & Inter-Cell Contract

**Date:** 2026-08-22  
**Parent dispatch:** Linear `MAS-116`  
**Canonical parent research:** `research/prophet_v4/PROPHET_FLAGSHIP_INTELLIGENCE_EXPANSION_FANOUT_2026-08-22.md`  
**Universal execution law:** `research/prophet_v4/flagship_cells/RESEARCH_CELL_EXECUTION_CONSTITUTION_2026-08-22.md`  
**Skillpack used for hardening:** `mastermindx-market-intelligence/Mastermind@90db9baf5bcc5f2221e3c9870c2aa09a95293c99`, protected `master`, Skillpack `1.0.0` / bootstrap major `1`  
**Hardening branch base:** Macro `af7f4af9a86c67885e13dd2bcf80b9932e3c399a`  
**Current-main reconciliation during hardening:** `0e57b06d8e23bf83f4f3f12e755931a283cce0b5`; branch was two commits behind and every hardening change was additive under this directory.  
**Authority:** research/handoff only. No runtime/implementation authority is created by this index.

---

# 0. Why this index exists

Eight flagship research cells can still diverge even if each individual handoff is excellent. The most dangerous divergences are not obvious coding conflicts; they are **semantic ownership conflicts**:

- Theme research invents materiality that should belong to a specialist.
- Catalyst research invents incorporation that should be tested downstream.
- Dislocation research invents exposure rather than consuming GMI.
- Fragility research silently changes deterministic availability.
- Species research creates a second Market Memory.
- D5 evidence translation becomes a second Fusion ranker.
- Evaluation invents a new scoreboard.
- Product design invents fields because a mockup needs them.

This index makes the eight cells a single architecture rather than eight projects.

---

# 1. Controlling packet map

| Cell | Linear | Dedicated handoff | Canonical owner(s) | Core question |
|---|---|---|---|---|
| A | MAS-117 | `CELL_A_THEME_INTELLIGENCE_HANDOFF_2026-08-22.md` | GMI Theme Graph | What theme is changing, who is economically exposed, and how should it propagate? |
| B | MAS-118 | `CELL_B_EVIDENCE_PRICE_GAP_HANDOFF_2026-08-22.md` | Alpha Intelligence / Dislocation; future D5 | Has price responded unusually little/much relative to validated evidence and comparable history? |
| C | MAS-119 | `CELL_C_CATALYST_SURPRISE_MATERIALITY_HANDOFF_2026-08-22.md` | Earnings, Bio/BCI, Defense specialists | What happened vs expectation, how surprising/material is it, under the domain's own law? |
| D | MAS-120 | `CELL_D_STOCK_SPECIES_ANALOGUES_REGIME_HANDOFF_2026-08-22.md` | Stock Identity + Market Memory | What kind of security/episode is this, and which past episodes are actually comparable? |
| E | MAS-121 | `CELL_E_FRAGILITY_POSITIONING_CROWDING_HANDOFF_2026-08-22.md` | Capital Structure, FIF/FF, Options, positioning owners | What can break the thesis/path, and how crowded is the current expression? |
| F | MAS-122 | `CELL_F_EVIDENCE_TRANSLATION_TRAJECTORY_HANDOFF_2026-08-22.md` | Prophet D5 + Conditional Fusion | How do specialist facts become a coherent missing-aware evidence vector without becoming a second ranker? |
| G | MAS-123 | `CELL_G_VALUE_OF_INFORMATION_MEASUREMENT_HANDOFF_2026-08-22.md` | Eval OS + Conditional Fusion + existing outcome ledgers | Did a family make Prophet earlier/better/safer enough to earn authority? |
| H | MAS-124 | `CELL_H_FLAGSHIP_PRODUCT_EXPERIENCE_HANDOFF_2026-08-22.md` | V4 Experience + MP-1 + Design Doctrine | How does the user understand all of this in five seconds without flattening truth? |

The dedicated handoff controls **cell-specific intent** over the shorter Linear description and over the original parent fan-out's abbreviated cell section. A fresh session still rechecks current canonical owner truth before treating any dated state as executable.

---

# 2. Inter-cell architecture

```text
                    CANONICAL SOURCE / SPECIALIST OWNERS
                                  |
             +--------------------+--------------------+
             |                    |                    |
             v                    v                    v
       Cell A: Theme        Cell C: Catalyst      Cell E: Risk/
       exposure/state/      fact/expectation/     fragility/crowding
       transmission         surprise/materiality
             |                    |                    |
             +--------------------+--------------------+
                                  |
                                  v
                      Cell F: Evidence Translation
                      missingness / lineage / trajectory
                                  |
               +------------------+------------------+
               |                                     |
               v                                     v
      Cell B: Incorporation                  Cell D: Species/Analogue
      price response vs                      context / historical prior
      validated evidence                             |
               |                                     |
               +------------------+------------------+
                                  |
                                  v
                      Existing Conditional Fusion
                      deterministic baseline first,
                      learned challengers later
                                  |
                                  v
                        Cell G: Eval / VOI
                      promotion / demotion law
                                  |
                                  v
                    bounded earned authority only
                                  |
                                  v
                       Cell H: Product Experience
                  (can research early; final freeze follows
                   stable upstream contracts and owner adoption)
```

This diagram is conceptual, not a required runtime DAG. It defines **semantic dependency**.

---

# 3. Exact ownership seams

## 3.1 A → C

Cell A may estimate **economic/theme exposure** and relationship mechanisms.

Cell C may use exposure as a denominator/context for a domain catalyst, but **does not own theme exposure**.

Example:

- A: “VRT has high verified exposure to data-center power/cooling demand.”
- C: “A customer capex change is materially relevant to VRT because of that exposure.”

C must not create a rival VRT→data-center exposure estimate.

## 3.2 C → B

Cell C owns/eventually federates:

- event fact;
- expectation baseline;
- surprise;
- issuer materiality.

Cell B owns research into **market incorporation relative to that evidence**.

C should not call a catalyst “underpriced.” B should not invent the catalyst's materiality.

## 3.3 A → B

A may provide theme impulse, exposure and transmission paths. B may ask whether the target's price response is small/typical/large relative to those validated relationships.

B must not create its own theme graph or exposure model.

## 3.4 D → B

D provides episode/species/analogue retrieval and empirical priors. B may consume comparable-episode distributions as one incorporation baseline.

B must not create a second analogue store. D must not choose analogues by future success.

## 3.5 E → B

E supplies liquidity/path/crowding context that may explain an apparently delayed/large response. B may use those as confounders/context if validated.

B must not rebuild options/capital/short/fragility sources.

## 3.6 A/C/D/E → F

F does **not** recompute their facts. It standardizes:

- identity joins;
- clocks;
- applicability/missingness;
- trajectory semantics where meaningful;
- evidence lineage/dependence;
- authority/rights/coverage;
- explanation primitives.

Owner-native methods and native units stay available.

## 3.7 F → Fusion

F is not a ranker. Conditional Fusion remains the canonical cross-family ranking/learning arena.

If F produces a field that affects ordering, that influence must be explicitly authorized through existing Fusion/Eval law rather than hidden inside the D5 emitter.

## 3.8 G → all cells

G does not redesign family semantics after seeing outcomes. It tests **frozen versions** from A–F under lawful PIT/prospective evidence.

If a family changes materially after results, it becomes a new version/evidence clock.

## 3.9 H → all cells

H consumes accepted semantic contracts. It may identify UX requirements/gaps but **cannot cause a source or research owner to fabricate a field**.

A product need becomes an owner request, not a client-side heuristic.

---

# 4. Shared vocabulary rulings

These terms must remain distinct across cells.

## `exposure`

How/why a company is connected economically/behaviorally to a theme. Primarily A/GMI.

Not equivalent to event materiality, beta, or stock weight in a theme basket.

## `materiality`

How much an event/fact can matter to an issuer under a defensible domain denominator/context. Primarily C/domain owner.

Not equivalent to evidence confidence or price response.

## `surprise`

Difference between outcome/new information and a prior expectation baseline. C/domain owner.

Requires a defensible prior expectation. Missing baseline ≠ zero surprise.

## `incorporation`

Observed market response relative to a valid reference distribution/control after information becomes tradable. B research.

Not intrinsic fair value.

## `fragility`

Evidence that issuer economics or price path can fail/become adverse. E.

Not automatically a veto.

## `crowding`

Evidence about participation/expensive expression/positioning. E.

Not conviction and not automatically direction.

## `species/fingerprint`

A representation that changes useful conditional behavior/routing/analogue selection. D/Stock Identity.

Not industry taxonomy.

## `analogue`

A PIT-comparable historical episode selected without outcome leakage. D/Market Memory.

Not a cherry-picked historical winner.

## `confluence`

Several distinct evidence roots supporting a candidate, with dependence/lineage preserved. F/Fusion.

Not count of bullish fields.

## `confidence`

Evidence/measurement quality/coverage/uncertainty under a defined basis.

Not a universal blended conviction score.

## `availability`

Deterministic current actionability/entry geometry. Prophet Availability owner.

No intelligence cell may redefine it.

---

# 5. Shared clock law

Cross-cell joining is illegal unless the session can state which clock it is joining.

Conceptual common clocks:

- economic/source event time;
- source/lawfully available time;
- Mastermind captured time;
- computation/belief time;
- correction/supersession time;
- first tradable market time/session;
- candidate episode first/latest event;
- evaluation horizon start/end.

Domain-native clocks remain canonical. The common vocabulary exists to prevent accidental collapse, not to rename every owner field.

A feature known at `T+1` cannot appear on a `T0` candidate vector because the underlying event occurred at `T0`.

---

# 6. Shared missingness law

All cells must preserve the difference among at least:

- not applicable;
- not covered;
- source unavailable;
- stale;
- rights blocked;
- identity unresolved;
- insufficient history;
- unestimable;
- accruing / not yet mature;
- measured neutral/zero.

No downstream cell may coerce upstream typed absence into numeric zero because its model/schema prefers numbers.

---

# 7. Shared authority ladder

A useful default conceptual ladder is:

```text
SOURCE FACT / OBSERVATION
        ↓
CONTEXT / DISPLAY
        ↓
FROZEN RESEARCH FEATURE
        ↓
PIT REPLAY / EXPLORATORY SUPPORT
        ↓
FORWARD SHADOW / PROSPECTIVE ACCRUAL
        ↓
EARNED PRIORITY/RANK AUTHORITY
        ↓
(trade/entry/size authority remains separate)
```

Each canonical owner may use different actual enums/steps. Do not mint a parallel status system; map to the owner.

No cell gains rank authority because the handoff describes a compelling feature.

---

# 8. Shared method law

## Deterministic

Facts/transforms whose answer follows from source/contract: identity mapping, denominator calculation, current availability, source freshness, fixed ratios, typed edge lookup.

## Statistical

Estimated relationships/distributions: beta, lag, analogue prior, expected response, conditional routing, learned ranker. Must expose N/coverage and evaluation.

## Model-generated

Semantic extraction/classification/summarization/proposal. Must carry source evidence and starts without predictive authority.

Downstream interfaces must not erase `method_kind`.

---

# 9. Cross-cell failure scenarios

Every final cell artifact should test whether it survives at least these program-wide scenarios.

## Scenario 1 — Theme hot, issuer not economically exposed

A sees high theme impulse but weak/unknown economic exposure. C/B/F/H must not call this high-confluence merely because ticker appears in a basket.

## Scenario 2 — Strong catalyst, no expectation baseline

C has an event fact/materiality but surprise is unestimable. B can still measure response descriptively, but cannot call it underreaction relative to a nonexistent surprise model.

## Scenario 3 — Strong evidence, source-derived duplication

Five F fields trace to one earnings release. Fusion/H shows one evidence root with several observations, not five confirmations.

## Scenario 4 — Strong evidence, price already ran

B says response large vs history; Availability says `RAN / DON'T CHASE`. H must present strong thesis / unavailable opportunity coherently.

## Scenario 5 — Strong opportunity, high financing fragility

E says high structural risk. Availability may still be open. No hidden risk score silently closes it; user sees asymmetry/risk.

## Scenario 6 — No options coverage

E reports crowding `NOT_COVERED`. F/H must not show “low crowding.”

## Scenario 7 — Six analogues

D reports raw cases + `UNESTIMABLE`; B/G/H cannot manufacture stable probability/percentile.

## Scenario 8 — New microtheme proposed

A's emergent theme is probationary/model-proposed. F preserves authority; it cannot become measured canonical theme evidence until ratified.

## Scenario 9 — Later correction

Upstream owner corrects fact. F appends/supersedes according to owner law; B/G replay uses what was knowable at the historical time; H shows correction.

## Scenario 10 — Evaluation says no lift

G finds a fascinating family has no incremental early/path value. It remains context-only or is rejected; H may still show it if useful, but Fusion rank does not gain it.

---

# 10. Recommended parallel research order

Because research is read-only/additive, several cells can run concurrently, but dependency awareness matters.

## First parallel wave

**A / F / G / B**

- A defines the world/theme relationship side.
- F defines how evidence is translated without duplicate ranker.
- G defines the acceptance law before results tempt us.
- B deepens the core dislocation/incorporation thesis while current P0 remains protected.

They may complete research even if implementation gates are closed.

## Second parallel wave

**C / D / E**

Each depends heavily on active specialist owners/current source proof. Their output should feed F/G rather than auto-start builds.

## Experience follower

**H** can research compositions in parallel but final contract freeze follows stable upstream semantics and current V4/MP-1 design authority.

This is a recommendation, not a runtime queue.

---

# 11. Fresh-session launch packet

When assigning a cell to a new Sol CEO chat, Chairman can send only:

> Take responsibility for **MAS-XXX** as Sol CEO research owner. Fetch MAS-116, the child issue, `PROPHET_FLAGSHIP_CELL_HARDENING_INDEX_2026-08-22.md`, `RESEARCH_CELL_EXECUTION_CONSTITUTION_2026-08-22.md`, and the child’s dedicated handoff. Reconcile current default-branch SHA, canonical owner Agent OS records and open/recent PRs. Comment `SOL RESEARCH SESSION CLAIMED` with the reconciliation before moving the child In Progress. You are research/architecture-only; do not mutate an owner plane without a separate current authorization. Deliver the full hardened output contract and owner-routed continuation.

The child dedicated handoff contains the cell-specific research problem. The constitution contains universal operating law. This index contains cross-cell boundaries. The fresh session should not need this originating chat.

---

# 12. Return-to-Sol integration protocol

When a cell finishes, Sol should not immediately authorize its proposed waves.

Review in this order:

1. Did it preserve Chairman intent?
2. Did it remeasure current owner/production truth?
3. Did it reuse rather than duplicate canonical planes?
4. Did it respect sibling-cell ownership seams in this index?
5. Did it classify buildability/estimability honestly?
6. Are clocks/nulls/corrections/rights explicit?
7. Did it attempt to falsify itself and compare boring baselines?
8. Are proposed waves independently useful verticals?
9. Does Cell G's evaluation framework know how this family could earn authority?
10. Does final product composition preserve availability and uncertainty?

Only then should an accepted wave be written into the canonical owner workstream/Agent OS handoff and separately commissioned.

---

# 13. Program-level rejection conditions

Sol should reject a cell result—even if technically sophisticated—if it:

- creates a second owner/control plane;
- shrinks the product thesis to what is easiest to code;
- claims precision unsupported by source/denominator/N;
- uses hindsight/current snapshot in historical research;
- hides missingness;
- turns LLM interpretation into authority without validation;
- creates a monolithic score;
- bypasses deterministic availability;
- optimizes only future return while sacrificing early actionability;
- calls a spec/PR/CI completion “live” without production proof;
- lets UI composition redefine upstream semantics.

---

# 14. End-state integration example

A final high-priority candidate might eventually read internally like:

```text
Episode
  early technical emergence: TRUE
  deterministic availability: ENTRY_OPEN

Theme / exposure [A]
  data-center power/cooling impulse: accelerating
  economic exposure: verified / high
  customer-capex transmission: 2 independent customer roots

Catalyst [C]
  issuer guidance: improved
  expectation baseline: measured
  materiality: moderate-high

Incorporation [B]
  residual response since evidence: +3.1%
  comparable-response percentile: low
  state: RESPONSE_SMALL_VS_HISTORY

Species / analogues [D]
  behavioral neighborhood: supported
  analogues: 41
  prior: favorable MFE, moderate early MAE

Risk [E]
  structural fragility: low
  crowding: low-moderate
  options coverage: current

Translation [F]
  independent evidence roots: 4
  derived observations: 11
  coverage: high
  model-generated observations: source-backed / context-only where unpromoted

Evaluation [G]
  each promoted family/version earned its current authority prospectively

Experience [H]
  first viewport: “ENTRY OPEN — customer capex + issuer guidance strengthened; price response remains modest; four independent evidence roots; low structural fragility.”
```

And an equally valid outcome is:

```text
Strong thesis
Evidence well covered
Price response already extreme
Crowding high
Availability = RAN / DON'T CHASE
```

The second state is not a system contradiction. It is one of the main reasons the architecture keeps truth, intelligence and actionability separate.

---

# 15. Stop condition

This index is complete when:

- all eight dedicated handoffs exist;
- every cell has an explicit owner seam and no-rebuild law;
- shared vocabulary/clock/null/authority/method laws are non-contradictory;
- cross-cell failure scenarios are covered;
- Linear children point at their dedicated packets;
- the hardening PR is reviewed against current `main` before merge.

The index itself authorizes **no implementation wave**.
