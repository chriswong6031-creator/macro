# CELL A / MAS-117 — THEME INTELLIGENCE
## ChatGPT-first CEO research → architecture → bounded implementation handoff

**Date:** 2026-08-22  
**Cell:** A / Linear `MAS-117`  
**Parent:** `MAS-116`  
**Canonical production owner:** `WS:GMI-THEME-GRAPH`  
**Prophet integration:** V4 D2/D3/D4 → D5 adapter only after owner acceptance  
**Authoring Skillpack:** `mastermindx-market-intelligence/Mastermind@0f319c79a7b3373a96d4866412c734de12cbf701`, protected `master`, `mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1`  
**Macro current-main observed during launch hardening:** `21f51a1ecfed778a738b048bd7e5efd30b1d9336`  
**Flagship architecture source branch at authoring:** `sol/prophet-flagship-fanout-hardening-20260822` / PR `#6264` — DRAFT research architecture, not production authority  
**Authority at birth:** CEO research/architecture commission. Implementation is permitted only after the receiving Sol re-establishes explicit Chairman intent in the active chat, current owner gates, and a bounded owner-routed vertical. Do not treat this file itself as runtime authority.

---

# 0. Chairman resource instruction — use ChatGPT reasoning aggressively

The Chairman explicitly wants the expensive part of this program to be **thinking-heavy in ChatGPT and coding-light until the design is frozen**.

The receiving Sol should therefore:

- use as many ordinary ChatGPT turns as materially useful;
- use as many available deep/high-effort/Pro research turns as materially useful for difficult archaeology, primary-source research, experiment design, mathematical review and adversarial review;
- keep product thesis, system design, source strategy, contract design, falsification design, wave decomposition and PR review inside ChatGPT whenever possible;
- **not** conserve ChatGPT reasoning by prematurely asking a coding agent to “figure out the architecture”;
- use coding workers when the task becomes execution-heavy: parsers, migrations, reproducible experiments, test harnesses, large code changes, production wiring, browser proof or repeated implementation/review loops;
- give every coding worker a bounded packet with the architecture already frozen.

There is no requirement to finish this cell in one response or one session. A strong Cell A may take many CEO reasoning turns before the first implementation PR is justified.

If a coding-heavy step is required but the architecture is still unresolved, remain in ChatGPT and resolve the architecture first.

---

# 1. Observable mission

Design, validate and, only after lawful owner routing, implement the strongest buildable **Theme Intelligence** system for Mastermind so Prophet and other consumers can answer:

> What economic theme is changing, which companies are genuinely exposed and in what way, how strong/accelerating is the theme now, through what economic mechanisms should the information propagate, and which relationships are trustworthy enough to become evidence rather than decorative graph adjacency?

The result must be useful even if several predictive hypotheses fail. Theme Intelligence should improve company understanding, theme navigation, read-through research and explanation before it earns any ranking authority.

---

# 2. Why this matters to the flagship Prophet thesis

Prophet is being designed as an **Opportunity Inference Engine**, not a technical screener. The desired chain is:

```text
truth
→ evidence change
→ identity
→ economic exposure / relationship
→ expectation / surprise / issuer materiality
→ expected response pressure
→ observed residual price response
→ incorporation state
→ fragility / crowding / priors
→ early technical state
→ deterministic Availability
→ priority
→ prospective learning
```

Cell A owns the economic context that makes the middle of this chain possible. Without it, Prophet can know that a stock is moving but cannot robustly answer whether it is a first-order beneficiary, a second-order supplier, an attention proxy, a cost victim, a customer read-through, or merely co-trading with a theme.

The moat is not “a list of AI stocks.” It is a correction-safe point-in-time history of:

- company ↔ theme economic relationships;
- multiple distinct exposure axes;
- segment/product lineage;
- theme-state trajectories;
- typed transmission mechanisms;
- evidence supporting each relationship;
- what Mastermind believed at each decision clock;
- which mechanisms subsequently proved useful.

---

# 3. 10/10 end-state reference behavior

A mature system should eventually be able to produce a candidate explanation like:

> Data-center power/cooling demand has accelerated across multiple independent evidence roots. The target issuer has a verified high economic exposure through two product groups, moderate strategic optionality, and low current attention share. Customer capex evidence implies a positive `CUSTOMER_CAPEX_TO_SUPPLIER_DEMAND` mechanism. The independent theme basket, excluding the target economic issuer and cross-listings, has rerated materially; the target has not yet moved proportionally. Theme evidence is fresh, membership is observed-era, and source rights permit internal ranking use. Prophet shows the name as high-priority context **only if** its separately owned deterministic Availability remains `ENTRY_OPEN`.

And it must also express negative states honestly:

- high trading beta but weak economic exposure;
- high historical revenue exposure but theme currently dormant;
- strong strategic optionality with no measurable current revenue;
- relationship plausible but source rights block use;
- segment mapping changed after a reorganization;
- theme member historically reconstructed rather than observed;
- transmission mechanism unsupported / generic adjacency only;
- target is a theme leader whose own return must be excluded from the response baseline;
- theme exposure cannot be estimated and remains `UNAVAILABLE` rather than fabricated.

---

# 4. Required cold-start read order

Before conclusions or mutation, the receiving Sol must refresh all current sources. Do not rely on the dated state below.

## 4.1 Current procedure

Load protected `mastermindx-market-intelligence/Mastermind` `docs/sol_skills/INDEX.md` and required skills from one exact current protected-master commit. At minimum use current `COLD_START`, `RECONCILE_STATE`, and `COMMISSION_WAVE` when moving into implementation.

## 4.2 Current Macro truth

Read current `main` SHA and current accepted owner truth:

- `agentos/workstreams/WS-GMI-THEME-GRAPH.md`
- `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md`
- GMI current/recent PRs and any D2/D3/D4 owner handoffs/decisions
- current identity/rights/segment-data owner records

At authoring, GMI remains active and owns `engine/theme_graph/`, `data/theme_graph/` and `config/theme_sources.yml`. Its old `next_action` is operationally stale relative to later GMI work, so use owner records for ownership but newer accepted PR/handoff evidence for current state.

## 4.3 Flagship architecture packet

Read, in this order:

1. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_READ_FIRST_2026-08-22.md`
2. `research/prophet_v4/PROPHET_FLAGSHIP_INTELLIGENCE_EXPANSION_MASTERPLAN_2026-08-22.md`
3. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_ARCHITECTURE_FREEZE_AND_INTEGRATION_GRAPH_2026-08-22.md`
4. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_ADVERSARIAL_REVIEW_AND_AMENDMENTS_2026-08-22.md`
5. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_OPEN_HYPOTHESES_AND_KILL_MATRIX_2026-08-22.md`
6. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_EXTERNAL_METHODS_BENCHMARK_2026-08-22.md`
7. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_DATA_SOURCE_AND_MOAT_LEDGER_2026-08-22.md`
8. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_REFERENCE_CASEBOOK_2026-08-22.md`
9. `research/prophet_v4/flagship_cells/PROPHET_FLAGSHIP_R1_BACKBONE_PREWORK_2026-08-22.md`
10. `research/prophet_v4/flagship_cells/CELL_A_THEME_INTELLIGENCE_HANDOFF_2026-08-22.md`
11. `research/prophet_v4/flagship_cells/RESEARCH_CELL_DELIVERABLE_TEMPLATE_2026-08-22.md`

PR #6264 is a draft at authoring. If it has merged by claim time, read the merged exact SHA. If it has not merged, treat these branch documents as Chairman/Sol research design input, not accepted production source law.

## 4.4 Existing GMI research that must not be rediscovered

Read current versions of:

- `research/theme_graph/W2_EXPOSURE_AXES_PREREG.md`
- `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- current GMI identity/coverage/correction records
- current graph edge/node schema and current `read_nodes`/current-view behavior
- any accepted ThemeState predecessor or W3B/D3 sequencing ruling

---

# 5. Verified current estate at authoring — refresh at claim time

The following are **starting archaeology**, not permanent truth.

## 5.1 GMI ownership

`WS:GMI-THEME-GRAPH` is active. The graph's objective is to answer transmission questions with cited evidence at display tier. GMI owns canonical theme/company relationship truth and the transmission topology; Cell A must not create a second graph.

## 5.2 Exposure W2 already established important laws

Current W2 exposure-axis prereg already names:

- `economic_share`
- `trading_beta`
- `attention_share`

and already established:

- `economic_share` remains an **honest null** because no production-grade per-company segment/theme revenue source exists;
- no LLM-generated economic exposure number is allowed;
- `trading_beta.v0` uses an ex-self equal-weight basket and a causal shift;
- attention sources are sparse/shallow and subject to coverage floors/refusal;
- historical membership before observed graph history is labelled reconstruction era rather than pretended PIT truth.

Do not repeat this research as if it were unknown.

## 5.3 Identity correction work is real and load-bearing

Prophet/GMI D2 work has already expanded identity coverage and created correction lineage for reused symbols/entity-kind conflicts. Cell A must use canonical Data OS/GMI identity and current-node/edge semantics. Never join economic history on naked ticker strings.

## 5.4 ThemeState/transmission remains the high-value missing layer

The estate has structural membership and older dynamic thematic predecessors, but the flagship architecture still requires one canonical, owner-adopted ThemeState and typed transmission semantics. Do not promote an older Neural Web output merely because it resembles the desired shape.

---

# 6. Preliminary architecture to attack, refine or reject

These are starting designs from the R1 backbone prework, not conclusions.

## A-P1 — exposure is an axis registry, never one theme percentage

Candidate conceptual contract:

```text
company_theme_exposure.vNext
  issuer_id
  security_id?               # only for security-specific axes
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

Candidate issuer/company economic axes:

- `revenue_share`
- `profit_share`
- `capex_share`
- `customer_dependency`
- `supplier_dependency`
- `input_cost_dependency`
- `policy_funding_dependency`
- `geographic_dependency`
- `strategic_optionality`
- `management_attention`

Candidate security/market axes:

- `trading_beta`
- `attention_share`
- future positioning sensitivity only if a lawful owner/source exists.

**Rejected starting shape:** `theme_exposure = 0.73` with no named axis, denominator, clock or evidence.

## A-P2 — first economic-share work should be one difficult issuer vertical, not a universe scrape

Choose one diversified issuer + one economically meaningful theme + one exact filing package and trace:

```text
filing package
→ segment/product identities
→ revenue/profit/product facts
→ known-at/revision lineage
→ theme mapping evidence
→ one economic exposure axis
→ at least one historical segment-definition/revision boundary if possible
```

The cell must answer segment reorganization, restatement, intersegment elimination, overlapping themes, product-vs-segment mapping, subsidiary/venture handling and correction semantics before proposing broad ingestion.

## A-P3 — ThemeState separates economic/evidence impulse from return impulse

Candidate heads:

```text
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
  capex_procurement_impulse
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

Cell A must decide which are actually estimable, nonredundant and PIT-safe now.

## A-P4 — transmission is mechanism-conditioned

Starting mechanism registry:

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

A valid transmission candidate needs source node, destination, economic mechanism, relationship evidence, valid interval, direction if defensible, exposure axis, shock definition, negative controls, minimum support and refusal behavior.

Generic graph adjacency is not transmission alpha.

## A-P5 — first predictive baseline is simple and leave-target-issuer-out

```text
IndependentThemeImpulse(k,t)
  = robust aggregate of strong/pure members
    excluding the target economic issuer and all cross-listings/share classes

ExposureWeightedThemePressure(i,t)
  = Σ_k economic_exposure(i,k,t_known) × IndependentThemeImpulse(k,t)
```

Compare against simple baselines:

- market/sector momentum;
- equal-weight theme membership;
- target lagged momentum;
- exposure-weighted impulse;
- volatility-normalized variant.

No GNN before the deterministic baseline is honestly evaluated.

---

# 7. Binding adversarial law for Cell A

The A1–A12 flagship adversarial amendments apply wherever relevant. Especially:

- leave the **economic issuer**, not merely ticker, out of any theme/peer price baseline;
- all price-derived exposure/sensitivity estimates use strictly pre-event windows;
- historical priors/calibration are fold-frozen and future episodes excluded;
- current/final-corrected graph membership cannot impersonate historical known-at membership;
- graph paths cannot re-enter the target through cycles and create self-confirmation;
- source-root identity and economic-information dependence are separate;
- sparse coverage must be audited for selection bias;
- rights tier and missingness are first-class, not metadata footnotes.

A research return that omits applicable controls is `HOLD`, not PASS.

---

# 8. Research program — ChatGPT should own these phases

## Phase A0 — claim and current-state reconciliation

In the active Chairman chat:

1. record current protected Skillpack SHA;
2. record current Macro `main` SHA;
3. fetch MAS-117 + MAS-116;
4. read current GMI owner WS/DEC/handoffs/open PRs;
5. read #6264 state and merged/not-merged status;
6. write a disagreement/collision ledger;
7. comment `SOL RESEARCH SESSION CLAIMED` and move MAS-117 to In Progress only after the above.

Do not modify GMI/runtime merely because the issue is claimed.

## Phase A1 — estate archaeology

Trace real current producer→store→consumer paths for:

- graph nodes and edges;
- identity/current-view/correction behavior;
- theme source ingestion;
- curated/local/probation mappings;
- exposure axes/probes;
- older ThemeState-shaped predecessors;
- Prophet/context consumers;
- rights/coverage registry.

Produce a capability ledger with `PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, `BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`.

## Phase A2 — primary/external research

Use deep research turns liberally. Focus on the actual unresolved methods:

- segment/product revenue extraction and longitudinal segment identity;
- product-to-theme mapping methods;
- revenue/profit/capex exposure methodologies;
- supply-chain/customer-supplier relationship evidence;
- event/relationship diffusion and lead-lag research;
- emergent theme discovery/probation;
- temporal graph correction/validity methods;
- source licensing/redistribution/model-training rights where material.

Do not spend time re-proving generic facts already summarized in the shared external benchmark unless the cell needs deeper primary-source detail.

## Phase A3 — golden vertical design

Pick the hardest useful **one-issuer / one-theme / one-filing-history** exposure vertical. Freeze:

- identity grain;
- segment identity rule;
- source package(s);
- exact clocks;
- correction/restatement behavior;
- mapping evidence;
- target axis;
- null/refusal states;
- user/machine consumer.

Prefer a real difficult issuer over an artificially clean example.

## Phase A4 — ThemeState design

Reconcile every proposed ThemeState field against current owners and existing predecessors. For each field classify:

`ADOPT_AS_IS / ADAPTER_ONLY / EXTEND_OWNER / VERSION_AND_SUPERSEDE / REJECT / UNESTIMABLE_NOW`.

Specify expected frequency, point-in-time clock, denominator, missingness, correction and rights.

## Phase A5 — transmission experiment design

Choose the **highest-value first mechanism**, not ten at once. Freeze:

- source event/shock;
- relationship source;
- target population;
- timing clock;
- primary outcome/read-through endpoint;
- market/sector/theme controls;
- target-issuer leave-out rule;
- negative/placebo relationships;
- minimum N/effective N;
- falsifier;
- authority ceiling.

## Phase A6 — emergent theme discovery

Research how a candidate microtheme should move through:

```text
proposal
→ evidence bundle
→ duplicate/parent-theme check
→ human/owner ratification
→ probation
→ observed evidence accumulation
→ accepted/rejected/superseded
```

LLMs may propose/organize evidence but do not autonomously mint canonical themes or economic percentages.

## Phase A7 — adversarial review

Run an independent review turn against:

- circular price baselines;
- survivorship/current-snapshot leakage;
- theme overlap semantics;
- segment reorganization;
- false causal edges;
- source rights;
- selection bias;
- “strategic exposure” becoming an excuse for non-estimable numbers;
- overlap with GMI/transmission owner paths.

Revise before implementation.

---

# 9. What Cell A must return before coding is justified

The CEO research return must include:

1. exact golden issuer/theme/source choice and why it is difficult/useful;
2. segment/product identity + correction law;
3. exposure-axis registry: accepted / rejected / unavailable axes;
4. exact source/rights/build-vs-license requirements;
5. ThemeState field ledger with reuse/supersession rulings;
6. one first transmission mechanism and frozen experiment;
7. emergent-theme proposal/ratification/probation workflow;
8. exact A→F evidence interface candidate;
9. capability ledger;
10. falsifiers / negative controls / estimability limits;
11. three to five **owner-routed future verticals** in dependency order;
12. explicit `ADOPT / EXTEND / DEFER / REJECT` rulings for every major starting idea.

If the best answer is “economic exposure is not yet estimable broadly,” return that honestly and narrow the build.

---

# 10. Transition from ChatGPT research to implementation

The Chairman authorizes the session to continue end-to-end **if current owner gates permit**. Do not automatically stop after the research return.

Implementation may begin only when all are true:

- active Chairman message still authorizes the session to own the cell / next bounded wave;
- current GMI/V4 owner state has been refreshed;
- no open sibling PR owns the same paths;
- the capability is narrowed to one observable vertical;
- identity/time/null/correction/rights semantics are frozen;
- tests/failure states are specified;
- the wave does not rebuild a canonical owner;
- required research falsifiers are not unresolved blockers.

At that point Sol may either:

### Option 1 — implement itself

Use when the vertical is small enough and keeping context in ChatGPT produces better coherence. Still obey one useful capability per PR and require real tests/proof.

### Option 2 — commission a coding worker

Use when parser/runtime/test volume is large. Send the worker only the bounded vertical, exact paths/contracts/tests and non-goals. The worker does **not** decide product thesis, owner boundaries or whether the hypothesis deserves authority.

Suggested first build, **only if Cell A research accepts it**:

> One diversified issuer × one theme × one filing-history segment/product truth vertical through the canonical owner, with correction lineage and one real read-only consumer. No universe rollout, no rank authority.

A second possible first build, if segment truth is blocked but ThemeState is ready, is one owner-adopted ThemeState vertical with a real consumer and explicit `ACCRUING/UNAVAILABLE` families.

---

# 11. Coding-worker packet requirements

Every coding handoff must contain:

- one observable mission;
- why it matters;
- exact current base SHA and recent owner PRs;
- exact paths/repos;
- canonical owner and document precedence;
- explicit non-goals;
- complete producer→contract→consumer journey;
- identity/time/null/correction/rights behavior;
- deterministic/statistical/model-generated distinctions;
- failure states;
- ordered implementation sequence;
- unit/integration/mutation tests;
- real production or machine-consumer proof owed;
- stop condition;
- exact return packet.

Do not hand a worker “build Theme Intelligence.”

---

# 12. Acceptance and proof law

Architecture acceptance is not predictive acceptance.

For a build wave:

- fixture/unit proof can establish implementation correctness;
- real owner-source → canonical contract → real consumer proof establishes the vertical is live;
- PIT-safe retrospective work can support a research claim;
- forward/preregistered evidence through existing Eval/Fusion law is required before ranking authority;
- production/UI proof is required for user-facing claims.

A segment parser landing successfully does **not** prove exposure predicts returns.

A transmission graph rendering successfully does **not** prove lead-lag alpha.

---

# 13. Stop conditions

Stop and return to Sol/Chairman rather than absorbing more scope if:

- a new canonical owner is genuinely required;
- current GMI owner law conflicts materially with the flagship architecture;
- a paid/vendor source commitment is strategically material;
- source rights are unresolved and would determine architecture;
- the proposed exposure cannot be estimated without inventing numbers;
- the first mechanism fails its negative controls;
- the only way to make the result work is current-snapshot historical membership or target self-inclusion;
- implementation would touch an active sibling owner's paths;
- a desired predictor fails but the temptation is to rescue it by post-outcome retuning.

Failure of a predictive hypothesis is a valid successful Cell A outcome.

---

# 14. Required continuation packet

At any handoff or session boundary, write a durable return containing:

```text
Cell: A / MAS-117
Skillpack SHA:
Macro main SHA at claim:
Macro main SHA at return:
Current GMI owner state:
PR/branch identities inspected:
Capability ledger:
Golden vertical chosen:
Exposure axes accepted/rejected:
ThemeState decisions:
Transmission mechanism / experiment:
Emergent-theme ruling:
Source/rights gaps:
A1-A12 compliance:
What is empirically supported:
What remains hypothesis:
Implementation waves authorized/built/proven:
Exact PRs/SHAs/CI/proof if any:
Do-not-redo:
Exact next action:
```

Use Agent OS/current owner records when cross-session organizational truth changed. Keep Linear as a projection, not the research corpus.

---

# 15. Copy-paste launch instruction for the Chairman

A fresh ChatGPT Sol session can be launched with:

> **Take full responsibility for MAS-117 / Cell A Theme Intelligence. I authorize you to use as many ChatGPT turns and deep/high-effort Pro research turns as useful. Keep the research, architecture, experiment design, adjudication and review in ChatGPT as long as that is the highest-quality/lowest-external-token path. Read the attached ChatGPT-first execution handoff and all required current canonical sources. You are authorized to carry the cell end-to-end; after you freeze a bounded owner-compatible implementation wave and re-check current gates, you may either implement that bounded wave yourself or commission coding workers. Do not delegate product/system thinking to coding agents, do not create duplicate canonical systems, and do not grant predictive/rank authority without the existing prospective gauntlet.**

That active Chairman instruction supplies the fresh-session intent. The receiving Sol must still obey current owner/runtime/permission gates before modification.
