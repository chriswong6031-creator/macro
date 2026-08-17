# Mastermind Biopharma Cycle Intelligence OS
## Federated Clinical, Regulatory, Calendar, Market-Expectation, Historical-Experience, Neural Web, and Prophet Architecture

**Status:** Architecture candidate and program reset; no runtime authority or implementation is granted by this document  
**Date:** 2026-08-16  
**Repository freeze audited:** `mastermindx-market-intelligence/macro` `main` at `810d6ae0b4438072e9c52ae3f6a0520f5221d37b`  
**Existing semantic program key:** `biocatalyst`  
**New execution workstream:** `WS:BIOPHARMA-CYCLE-INTELLIGENCE`  
**Architecture decision:** `DEC:BIOPHARMA-FEDERATED-NOT-MEGA-MERGED`  
**Primary repositories:** `macro`; later bounded consumers in `mastermind-terminal` and `Mastermind`  
**Authority at birth:** evidence, display, research, historical replay, and shadow only  
**Immediate stop condition:** review this architecture freeze and the current-state archaeology handoff; do not begin BCI-1 runtime implementation from this document alone

---

# 0. Executive ruling

## 0.1 Do not pause and mega-merge the specialist programs

BioCatalyst, Market Memory, Defense Procurement, Financial Intelligence Fabric, Earnings Intelligence, Capital Structure, Options, and future specialist lobes must **not** be collapsed into one giant Biopharma or Seasonality project.

They solve different user jobs, have different fact owners, rights, clocks, identity obligations, products, operational cadences, and failure domains. A mega-merge would create one impossible critical path, force unrelated teams into shared files and shared releases, and recreate the failure mode this program is intended to correct: large amounts of infrastructure and documentation without one clear, independently useful capability reaching production.

The architecture is **federated**:

- specialist lobes own their domain truth and domain products;
- shared horizontal systems provide reusable temporal, identity, memory, context, publication, and decision boundaries;
- Biopharma Cycle Intelligence owns only the conversion of biopharma facts into market episodes, expectation state, historical response intelligence, peer read-through, current cycle context, and prospective learning;
- each program advances in bounded vertical waves and integrates through versioned, receipt-bound ports.

## 0.2 Do not leave the programs completely independent either

Independent development without a shared freeze would create:

- duplicate event models;
- duplicate issuer/security identity joins;
- parallel historical episode stores;
- conflicting `known_at` semantics;
- several "market expectation" scores with different meanings;
- multiple Neural Web biopharma dimensions;
- multiple Prophet catalyst features;
- inconsistent correction behavior;
- one lobe silently consuming another lobe's mutable page JSON.

Therefore this masterplan freezes **ownership, ports, authority, and sequencing**, while leaving the specialist programs operationally independent.

## 0.3 The correct company-level structure

The long-term family is:

```text
Mastermind Biopharma Intelligence OS
│
├─ BioCatalyst Truth & Workflow Plane
│    owns clinical/regulatory facts, revisions, source evidence,
│    domain outcomes, search/workbench workflows, coverage and rights
│
└─ Biopharma Cycle Intelligence
     owns market episodes, event-response research, expectation/incorporation,
     analogues, peer read-through, portfolio event exposure,
     Neural Web context and Prophet shadow contribution
```

The existing `biocatalyst` semantic program remains the parent key during this architecture phase. No second source-of-truth program is created merely to obtain a cleaner name. BCI begins as a governed workstream/subprogram and may receive a separate semantic program card only after BCI-0 archaeology proves that the split improves ownership rather than duplicating it.

## 0.4 Market Memory remains a horizontal cognitive fabric

Market Memory Intelligence OS V2 is not absorbed into BCI. It remains the canonical cross-domain historical-experience and analogue system.

BCI supplies:

- biopharma-specific episode packets;
- event-family semantics;
- domain-aware retrieval profiles;
- current-versus-historical comparison fields;
- market and domain outcome labels.

Market Memory supplies:

- `market_memory.as_known_at.v1`;
- exact decision-time context;
- cross-domain episode storage/indexing and retrieval;
- diversity and counterexample search;
- complete path outcomes;
- generic reliability and evidence presentation.

BCI must not build a second general analogue engine while Market Memory is building one. Market Memory must not rebuild BioCatalyst clinical truth or BCI's domain-specific event semantics.

## 0.5 Immediate concurrency ruling

| Program / lane | Ruling now | Reason |
|---|---|---|
| **BCI / current Seasonality implementation** | **Freeze runtime expansion. Proceed with BCI-0 architecture and archaeology only.** | The existing program has multiple substantial but disconnected engines and stale completion accounting. |
| **BioCatalyst P0 recovery** | **Continue P0-C1 and entitled production-browser acceptance.** | This repairs the live truth/workflow plane and does not conflict with BCI. |
| **BioCatalyst post-P0 alpha / asymmetry / Prophet waves** | **Freeze and route into BCI.** | Those responsibilities belong to BCI, Market Memory, Neural Web, and Prophet boundaries rather than the source-truth plane. |
| **Market Memory M0A** | **Continue production proof only. Do not start M0B before the prospective disposition is observed.** | The first-cause repair merged, but the forward opportunity and remaining freshness chain must remain honest. |
| **Financial Intelligence Fabric FIF-1R** | **Continue through review; do not start FIF-2.** | The packet is a shared source for BCI and many other lobes, not part of BCI. |
| **Defense Procurement D0R** | **Continue/close reconnaissance only; D1 remains unauthorized until its own acceptance.** | Defense is an independent specialist lobe that later federates through the same horizontal systems. |
| **Earnings, Capital Structure, Options, Market Structure** | **Continue under their own accepted plans.** | BCI consumes governed packets; it does not own those systems. |

This is a **federated freeze**, not a company-wide stop.

---

# 1. What changed since the earlier Seasonality assessment

The previous recovery analysis remains directionally correct, but several state claims are now obsolete.

## 1.1 Repository movement

Current `main` at this architecture freeze is:

```text
810d6ae0b4438072e9c52ae3f6a0520f5221d37b
```

Material changes include:

1. Market Memory M0A's first causal technical-intake repair merged as PR #5805 / `e1ec8865ac92ccebd11f8208fe2c1e09a85c21e9`.
2. The API deploy path was decoupled from W2C owner-replay attestation in PR #5804 / `021553985cbe6bf950413c7cb10fc302d05a9633`.
3. BioCatalyst P0-B2 production acceptance was recorded in PR #5806 / `6ac162329a84a0c64b8aa913aa256afd85866adc`.
4. BioCatalyst P0-C1 is open as PR #5810 and adds typed client hydration states without changing backend truth, contracts, collectors, Market Memory, or Prophet.
5. FIF-1R remains open as PR #5809 and is explicitly held for re-review; FIF-2 is forbidden.
6. Defense Procurement D0R documentation merged through PR #5814, but D1 remains outside this architecture freeze and must follow its own acceptance ruling.
7. No open Seasonality PR exists at the freeze.

## 1.2 Market Memory status correction

The statement "M0A is ready to start" is obsolete. The exact nested `__case_v1/<UTF-8 hex>.parquet` first-cause repair has merged.

What remains unresolved is not permission to start broad V2:

- production technicals and the exact prospective opportunity still require complete proof;
- trusted-regime freshness was the next downstream blocker at the M0A closeout;
- the first registered opportunity must become admitted, causal-abstained, or missed exactly as observed;
- no row may be backfilled;
- M0B remains blocked until that disposition is durable.

The checked-in Agent OS workstream still says `awaiting_ci` and should be reconciled by the Market Memory owner, not silently rewritten by BCI.

## 1.3 BioCatalyst status correction

The old Seasonality handoff understated BioCatalyst's current truth plane.

BioCatalyst now has real current-record, bounded record-history, fixed-cohort, private API, correction-aware change-tape, and forward-outcome-clock infrastructure. It is still narrow and incomplete, but it is not "no live source."

The correct remaining statement is:

> The specific BioCatalyst-owned machine projection required by the Seasonality event clock has still not landed.

That distinction matters. BCI should consume the now-real BioCatalyst plane through a narrow producer-owned projection, not treat the whole source program as absent and not scrape the paid user API.

## 1.4 Seasonality status remains materially incomplete

The following earlier findings remain valid:

- `engine/seasonality/event_study.py` has no production builder/caller;
- `engine/seasonality/model.py` and `calibration.py` do not produce operational forecast artifacts;
- `engine/seasonality/prophet_bridge.py` has no production caller;
- `scripts/build_seasonality_event_studies.py` and `scripts/build_seasonality_forecasts.py` remain absent;
- `app/seasonality.py` remains handler/library code and explicitly registers no API route;
- the methodology manifest and program watch are stale or structurally incorrect;
- the public product still exposes mainly the Calendar Clock and a Catalyst shell rather than a genuine multi-clock intelligence workflow.

These are BCI recovery inputs, not reasons to discard the code.

---

# 2. Capability ledger at architecture freeze

This is an architectural ledger, not production acceptance. BCI-0B must re-run every row against current production, exact artifacts, current open PRs, and browser evidence.

| Capability | State | Owner | Disposition |
|---|---|---|---|
| Calendar Clock per-symbol research | `PROVEN_LIVE` at prior audit; re-prove | current Seasonality | Preserve and subordinate to BCI calendar clock |
| Fixed 2,645-window family and selection accounting | `BUILT_NOT_PROVEN` as current production | current Seasonality | Preserve |
| Historical up-share vs calibrated estimate separation | `BUILT_NOT_PROVEN` | current Seasonality | Preserve as constitutional semantic split |
| `biopharma.event.v2` bounded source-time contract | `BUILT_NOT_PROVEN` | current Seasonality contract | Preserve; reconcile with producer rather than version casually |
| BioCatalyst current-record source plane | `PROVEN_LIVE` within narrow cohort/coverage | BioCatalyst | Consume |
| BioCatalyst bounded record history and changes | `PROVEN_LIVE` within declared scope | BioCatalyst | Consume |
| BioCatalyst event projection for BCI | `NOT_BUILT` | BioCatalyst producer | First cross-program data seam |
| Event clock adapter | `DARK_OR_DISCONNECTED` | BCI/current Seasonality | Reconcile after producer contract |
| Event-study engine | `DARK_OR_DISCONNECTED` | BCI/current Seasonality | Commission through a real builder |
| Regime adapter/model/calibration libraries | `DARK_OR_DISCONNECTED` | BCI/current Seasonality | Reuse only after canonical regime ownership freeze |
| Calendar forward ledger | `PARTIAL` | current Seasonality | Preserve; one ledger does not prove multi-clock intelligence |
| BCI event episode ledger | `NOT_BUILT` | BCI | Build prospectively |
| Current Neural Web seasonality state | `PARTIAL` | Neural Web + current Seasonality | Preserve contract shape; populate real clocks |
| Seasonality in Mastermind context | `PARTIAL` | Neural Web | Current calendar annotation only |
| Research browser handlers | `SPEC_ONLY` / library implementation | current Seasonality | Do not call API live |
| Public multi-clock product | `NOT_BUILT` | BCI product + Terminal | Design after real packets |
| Market expectation / incorporation state | `NOT_BUILT` as BCI capability | BCI consuming Options/Market | Build as vector, not opaque score |
| Catalyst collision / contamination engine | `NOT_BUILT` | BCI | Build |
| Financing-to-catalyst context | `PARTIAL` inputs only | BCI consuming FIF/Capital Structure | Build after identity/packet seams |
| Peer read-through memory | `NOT_BUILT` | BCI + Market Memory | Build |
| General historical analogue retrieval | `SPEC_ONLY` / synthetic in Market Memory W4 | Market Memory | BCI must wait for operational service, not clone |
| BCI Context Snapshot dimension | `NOT_BUILT` | Neural Web Context API | Build after packet freeze |
| Portfolio Event Map | `NOT_BUILT` | Mastermind Portfolio consuming BCI | Later bounded consumer |
| Terminal catalyst workspace / alerts | `PARTIAL` across existing pages | Terminal consuming BCI | Later thin client |
| Prophet F4 catalyst expert | `NOT_BUILT` for BCI | Prophet | Shadow only after PIT data |
| Live BCI rank/gate/size authority | `REJECTED_BY_DESIGN` at birth | Prophet / Portfolio owners | Earn only through explicit promotion |

---

# 3. Product thesis and value model

## 3.1 Primary user

The primary user is an active healthcare/biopharma investor or research lead who needs to understand:

- what catalyst or revision changed;
- when it became knowable;
- which security and programs are exposed;
- how important it may be economically;
- what the market already appears to price;
- which historical episodes genuinely resemble the current case;
- what differed in those episodes;
- how the sponsor, peers, options, and portfolio behaved;
- what evidence is missing;
- what would invalidate the current read.

## 3.2 Primary machine job

The machine must convert independently owned evidence into one correction-safe, point-in-time biopharma market episode and use it to:

1. preserve what was knowable before the outcome;
2. retrieve comparable and counter-comparable experience;
3. characterize complete market and domain outcome paths;
4. expose current rhyme, difference, uncertainty, contamination, and expectation;
5. accrue prospective evidence;
6. publish bounded context to Neural Web, Mastermind, Terminal, and Prophet shadow;
7. refuse authority that has not been earned.

## 3.3 North-star question

> **What is happening in this company's clinical, regulatory, financing, and market cycle; what changed; what did the market know and price; what happened in genuinely comparable episodes; what is materially different this time; what could break the analogy; and what have we learned prospectively from prior cases?**

## 3.4 User value

- faster detection of meaningful clinical/regulatory revisions;
- reliable event timing without fake exact dates;
- better preparation for binary and semi-binary catalysts;
- clearer view of realized versus implied event risk;
- identification of event collisions and attribution limits;
- peer read-through and delayed-incorporation research;
- portfolio event concentration and shared-mechanism exposure;
- one cited investigation rather than several disconnected dashboards.

## 3.5 Machine / Neural Web value

- a durable biopharma context dimension;
- point-in-time episodes and outcome paths;
- explicit contradictions and missingness;
- source-owner and correction lineage;
- cross-lobe joins without hidden duplication;
- prospective data for causal/research hypotheses;
- evidence-family contribution analysis for Prophet.

## 3.6 Research and signal value

BCI is not assumed to contain alpha.

It creates the substrate to test high-value questions such as:

- repeated timing-slip patterns conditional on trial and issuer context;
- realized versus options-implied event magnitude;
- asymmetric response to positive versus negative domain outcomes;
- financing pressure as an event-response modifier;
- delayed target/modality/indication peer read-through;
- post-event underreaction or overreaction;
- whether calendar evidence adds anything after catalyst, regime, and expectation state;
- whether any BCI fields add incremental information to Prophet's existing F4 family.

## 3.7 Distribution and commercial value

The same canonical packets support:

- BioCatalyst premium workbench;
- Biopharma Cycle Command Center;
- stock dossiers;
- Mastermind Terminal catalyst overlays;
- saved alerts and watchlists;
- portfolio event maps;
- cited Mastermind AI investigations;
- API/MCP research tools;
- institutional exports;
- public research derivatives with rights-safe aggregate data.

## 3.8 Data moat

The moat is not a seasonal curve or one event score.

It is the accumulated graph of:

- immutable source versions;
- first-known and posted clocks;
- bounded temporal claims;
- issuer/security/program/trial identity;
- corrections and revision sequences;
- decision-time market expectations;
- contamination and collision state;
- complete sponsor and peer outcome paths;
- counterexamples and failure episodes;
- prospective predictions and grades;
- exact model/retrieval/feature versions.

---

# 4. Federated program topology

## 4.1 Ownership matrix

| System | Owns | Does not own | BCI relationship |
|---|---|---|---|
| **BioCatalyst** | ClinicalTrials.gov/regulatory source facts, source revisions, trial/program facts, domain outcomes, coverage, rights, trial workbench | Security market response, options expectations, general analogue retrieval, Prophet rank | Producer of bounded biopharma domain events |
| **Biopharma Cycle Intelligence** | Biopharma market episodes, expectation state, contamination, event response, analogues profile, peer diffusion, current cycle context, BCI prospective learning | Raw clinical collection, generic financial truth, generic options truth, general memory retrieval, portfolio sizing | Central specialist market-intelligence lobe |
| **Market Memory** | Generic as-known-at context, cross-domain episode store/index, retrieval, Rhyme/Difference, counterexamples, path outcomes, reliability presentation | Clinical truth, BCI event semantics, Defense/FIF truth, Prophet decisions | Horizontal experience fabric |
| **Financial Intelligence Fabric** | Filing facts, statements, revisions, financial packets, trace, temporal financial policy | Trial facts, event-response conclusions, BCI ranking | Supplies issuer financial/financing context |
| **Capital Structure** | Issuance, debt, shelf/ATM/convert/warrant and capital structure truth | Clinical or market-response inference | Supplies financing-to-catalyst context |
| **Options Intelligence** | Chain/surface/flow/GEX observations and availability | Clinical event truth, BCI event conclusion | Supplies expectation and incorporation fields |
| **Market Regime / Neural Web** | Canonical market/regime context and context routing | BCI domain truth and rank | Supplies regime clock; consumes BCI context |
| **Defense Procurement** | Procurement/program/company facts and defense-specific alpha research | Biopharma truth | Independent lobe; later shares horizontal primitives |
| **Prophet** | Candidate/rank/plan lifecycle and evidence-family arena | Source facts, BCI retrieval, domain outcomes | Consumes a BCI F4 shadow contribution only |
| **Mastermind Portfolio** | Portfolio decisions, exposure, learning and outcome ledgers | BCI truth or Macro rank | Consumes event exposure/context under its own authority |
| **Mastermind Terminal** | Interactive workspace, chart interaction, saved state and alerts | BCI truth, metric registry, temporal logic | Thin interactive client over governed BCI services |

## 4.2 One source of truth per concept

The architecture follows one canonical owner per concept, not one repository or one mega-program per product.

Examples:

- trial status history → BioCatalyst;
- current options implied move → Options;
- statement cash and debt → FIF / Capital Structure;
- historical experience retrieval → Market Memory;
- biopharma event-response episode semantics → BCI;
- context routing → Neural Web;
- candidate ranking → Prophet;
- user alert state → Terminal.

## 4.3 Shared ports, not shared internal stores

Consumers receive bounded, versioned packets. They do not reach into another program's internal object layout.

A port must carry:

- owner and contract identity;
- source and publication clocks;
- exact temporal cutoff;
- correction lineage;
- identity resolution state;
- rights and distribution class;
- missingness and quarantine reasons;
- authority;
- content hash and receipts.

---

# 5. Shared temporal and identity law

## 5.1 Clock vocabulary

Every relevant record distinguishes, when applicable:

- **effective_at** — when the fact/event took effect in the world;
- **source_time_lower / source_time_upper** — bounded source temporal claim;
- **submitted_at** — when supplied to the source;
- **published_at / posted_at** — when made public by the source;
- **known_at** — earliest eligible public knowledge instant;
- **observed_at** — when Mastermind read it;
- **available_at** — when a particular downstream consumer could use it;
- **recorded_at** — when the current artifact/ledger row was written;
- **superseded_at** — when a correction/revision replaced it;
- **evaluation_cutoff** — latest information allowed into an episode or model;
- **outcome_known_at** — earliest eligible outcome availability.

Unknown clocks remain unknown. A date range never becomes a midpoint. A source update time never automatically becomes event effective time.

## 5.2 Identity vocabulary

Episodes may bind:

- issuer ID;
- security ID and listing interval;
- ticker/exchange history;
- sponsor/legal-entity ID;
- asset/program ID;
- trial NCT ID;
- indication;
- target/mechanism/modality;
- regulatory application/product/jurisdiction;
- partner/ownership relationship interval.

Unresolved identity is a first-class state. A sponsor-name string match does not create an issuer or security join.

## 5.3 Correction law

- source corrections append a new version;
- historical bytes and episode inputs are never rewritten;
- the transaction interval closes on the superseded record;
- prospective episodes keep the exact source versions they originally used;
- later research may request latest-known or corrected views explicitly;
- a current-corrected view must never be presented as what was knowable historically.

## 5.4 Missingness law

Every field distinguishes:

- observed;
- measured negative;
- not applicable;
- not yet available;
- source unavailable;
- rights blocked;
- identity unresolved;
- stale;
- quarantined;
- contradicted;
- unestimable.

Null is not zero and unavailable is not neutral.

---

# 6. BCI canonical objects

The names below are architecture candidates. BCI-0B/0C must first inventory existing contracts and reuse them when they already express the required truth. No new schema version is created merely to make the roadmap look complete.

## 6.1 Domain event input

Preferred existing input:

```text
biopharma.event.v2
```

Owned by the BioCatalyst/biopharma domain plane.

Required semantics:

- exact system clocks separated from bounded source-time objects;
- no single fake temporal value;
- immutable source receipts;
- correction lineage;
- domain event type;
- program/trial/application identity;
- no market-response estimate.

## 6.2 BCI market episode packet

Architecture candidate:

```text
biopharma_cycle.market_episode.v1
```

Represents one point-in-time market research episode.

Core blocks:

- episode identity and family;
- domain event refs;
- issuer/security/program/trial graph refs;
- knowledge cutoff;
- current revision state;
- calendar clock;
- event clock;
- regime clock;
- expectation/incorporation clock;
- financing and financial context refs;
- options/flow context refs;
- contamination/collision classification;
- peer graph snapshot;
- feature availability and provenance;
- prospective registration;
- all-false authority.

## 6.3 Market outcome path

Architecture candidate:

```text
biopharma_cycle.market_outcome_path.v1
```

Contains append-only labels after they become knowable:

- event occurrence/disposition;
- domain outcome refs owned by BioCatalyst;
- market close-to-close and intraday paths;
- benchmark and peer-relative paths;
- MAE/MFE and gap state;
- realized volatility and liquidity;
- realized versus implied move;
- peer read-through paths;
- post-event financing or narrative follow-ons;
- attribution/contamination quality;
- censoring and ungradable reasons;
- correction lineage.

## 6.4 Current BCI context packet

Architecture candidate:

```text
biopharma_cycle.context.v1
```

Compact current packet for Neural Web, dossiers, Mastermind AI, Portfolio, and Terminal.

It answers:

- what changed;
- what is approaching;
- timing bounds;
- source confidence/coverage;
- market expectation;
- historical response context;
- rhyme and differences;
- top contradiction;
- event collision;
- next research action;
- freshness and authority.

## 6.5 Market Memory retrieval profile

Architecture candidate:

```text
biopharma_cycle.memory_profile.v1
```

Declares:

- eligible episode families;
- required and optional planes;
- matching components;
- weights or non-parametric stages;
- missingness behavior;
- diversity/cluster rules;
- counterexample requirements;
- contamination filters;
- eligible outcomes;
- index/retrieval version.

BCI owns the profile semantics. Market Memory owns the generic operational retriever and index.

## 6.6 Prophet contribution

Architecture candidate:

```text
biopharma_cycle.prophet_contribution.v1
```

At birth:

- shadow only;
- no candidate addition;
- no rank/score/gate/size/geometry authority;
- exact F4 evidence-family membership;
- contribution and missingness trace;
- overlap group;
- feature/episode/version refs;
- expiry and freshness;
- prospective grade linkage.

---

# 7. Four-clock intelligence architecture

## 7.1 Calendar clock

Preserve the current Calendar Clock but narrow its claim:

- repeated calendar/trading-session structure;
- selection-adjusted historical evidence;
- current window phase;
- stability and regime sensitivity;
- explicit current-vintage/universe limitations;
- forward calendar ledger.

It is context, not a calibrated forecast by default.

Domain-conditioned calendar research may include:

- FDA/AdCom/PDUFA calendar clustering;
- conference periods;
- fiscal/reporting cycles;
- trial-duration cohorts;
- year-end enrollment/reporting patterns;
- financing windows;
- event-duration and post-event drift cohorts.

## 7.2 Catalyst/event clock

Consumes BioCatalyst domain events and revisions.

It describes:

- event family;
- timing bounds and precision;
- revision velocity;
- status and domain outcome state;
- event importance/materiality dimensions;
- related programs and peers;
- source and identity quality;
- next eligible observation.

It does not invent clinical outcome probabilities.

## 7.3 Regime clock

BCI must consume canonical regime/context planes rather than maintain a competing market-regime system.

BCI may derive a biopharma-relevant projection such as:

- broad market risk state;
- XBI/IBB and healthcare tape;
- rates/liquidity;
- small-cap/speculative appetite;
- issuer financing environment;
- event volatility regime;
- peer dispersion.

Derived values must retain the canonical source refs and remain BCI context, not a second regime authority.

## 7.4 Expectation/incorporation clock

This becomes the fourth first-class clock.

It asks how much event uncertainty or information appears reflected in the market:

- pre-event absolute and residual run-up;
- options-implied move;
- IV rank and term structure;
- skew and liquidity;
- volume/attention;
- short-interest/borrow state;
- peer and target/modality moves;
- news/publication diffusion;
- post-event absorption and drift.

It is a vector with independent dimensions, not one opaque "priced-in score."

---

# 8. High-value BCI intelligence modules

## 8.1 Catalyst Revision Intelligence

Primary job:

> Explain exactly how a catalyst or trial has evolved, rather than merely listing an event date.

Dimensions include:

- timing changes;
- enrollment target/type changes;
- site additions/removals;
- status transitions;
- endpoint text changes;
- sponsor/responsible-party changes;
- phase/design changes;
- geography changes;
- results posting;
- record-update/publication sequence.

Rules:

- no revision is automatically bullish or bearish;
- repeated or unusual revision patterns become research features;
- each difference has exact before/after values and source versions;
- BCI measures subsequent market behavior only after the event was knowable.

## 8.2 Trial Execution State

Do not publish a fake 0–100 trial health score.

Publish typed dimensions:

- schedule stability;
- enrollment evolution;
- site-network evolution;
- protocol-change burden;
- status-transition state;
- endpoint stability;
- data recency;
- evidence coverage;
- contradiction state.

Any later model consumes versioned fields with explicit missingness.

## 8.3 Catalyst Collision and Attribution

Detect overlapping events such as:

- earnings;
- financing/SEC filing;
- another program readout;
- FDA/regulatory event;
- conference release;
- competitor event;
- macro release;
- index/rebalance/OPEX;
- major sector shock.

Outputs:

- clean / partial / contaminated / unassignable attribution class;
- exact collision refs and windows;
- event-study admissibility;
- historical analogue filter;
- user-facing warning.

A statistical nuisance becomes a useful product capability.

## 8.4 Financing-to-Catalyst Context

Consume FIF and Capital Structure packets.

Questions:

- does estimated runway intersect the catalyst window;
- what financing facilities or securities exist;
- what issuer financing actions recently changed;
- what is observed versus inferred;
- how have comparable event/financing combinations behaved.

Never convert "needs capital" into an automatic bearish call.

## 8.5 Market Expectation and Realized-vs-Implied Intelligence

For eligible catalysts:

- current options implied move and liquidity;
- historical realized event-magnitude distribution;
- directional and absolute-return distributions separately;
- pre-event run-up;
- event premium relative to comparable episodes;
- realized-vs-implied outcome after maturity.

The product can say that present pricing differs from historical experience without recommending a trade.

## 8.6 Peer Read-Through Memory

Relationships include:

- same target/mechanism;
- same modality;
- same indication/endpoint;
- direct competitor;
- partner/licensor;
- supplier/platform dependency;
- shared narrative/theme.

For every eligible event, preserve:

- sponsor reaction;
- peer reactions;
- time-to-incorporation;
- residualized response;
- direction and magnitude heterogeneity;
- whether the relationship was knowable at the time.

The system retrieves delayed or missing read-through hypotheses; it does not assume every peer moves in the same direction.

## 8.7 Event Analogue and Counter-Analogue Intelligence

Retrieval must provide:

- closest comparable episodes;
- diverse episode clusters;
- failed analogues;
- opposite-outcome counterexamples;
- key similarities;
- key differences;
- complete path distributions;
- effective independent N;
- event-family and era compatibility;
- contamination quality.

No universal similarity score is required. A component vector is preferable.

## 8.8 Post-Event Absorption and Drift

Separate:

- event occurrence/outcome;
- first market reaction;
- subsequent revisions and narrative;
- post-event price drift;
- financing/follow-on events;
- peer diffusion.

This is a promising research family but receives no authority without prospective evidence.

---

# 9. Product and experience architecture

## 9.1 Product surfaces

### BioCatalyst Workbench

Remains the source-grounded domain product:

- Trial Screen;
- Peer Matrix;
- Milestones;
- Change Tape;
- First-seen Tape;
- trial/program dossier;
- source evidence.

### Biopharma Cycle Command Center

Evolves the current `stock_seasonality` operating shell rather than launching another shallow page by default.

Proposed modes:

1. **Cycle Overview**
2. **Catalyst Timeline**
3. **Revision Intelligence**
4. **Market Expectations**
5. **Historical Episodes**
6. **Peer Read-Through**
7. **Calibration & Evidence**

The exact route and shell are frozen only after BCI-0C real-data reference compositions. A new page is permitted only if the existing shell cannot support the complete primary journey without confusing the Calendar Clock and domain workbench.

### Terminal

Owns:

- chart event markers;
- saved investigations;
- watchlists;
- alerts;
- custom peer sets;
- portfolio event calendar;
- interactive comparison;
- workspace persistence.

### Stock dossiers and Mastermind AI

Consume compact BCI packets and evidence links. They never scrape HTML pages.

### Mastermind Portfolio

Consumes:

- event exposure;
- timing concentration;
- related-mechanism concentration;
- context and contradictions;
- prospective learning fields.

It does not gain hidden sizing authority.

## 9.2 Ten-second user contract

Every primary current-event view must answer above the fold:

1. **What changed or is approaching?**
2. **When is it knowable and how precise is timing?**
3. **Which issuer/security/programs are exposed?**
4. **How much is the market already pricing?**
5. **What happened in comparable episodes?**
6. **How independent and clean is the evidence?**
7. **What is materially different now?**
8. **What collision or financing risk matters?**
9. **What would update or invalidate the read?**
10. **Where are the exact receipts?**

## 9.3 Golden user journeys

### Journey A — Morning change review

```text
Open What Changed
→ filter to holdings/watchlist
→ inspect a trial/regulatory revision
→ see exact before/after and known-at clock
→ see market/peer reaction
→ open evidence
→ save investigation or alert
```

### Journey B — Upcoming catalyst

```text
Open issuer
→ see bounded catalyst timeline
→ inspect current expectation state
→ compare realized-vs-implied historical episodes
→ inspect collisions and financing
→ read rhyme/difference
→ open peer map
```

### Journey C — Post-event investigation

```text
Open event
→ see domain outcome and source
→ see sponsor/peer response path
→ inspect attribution quality
→ compare historical episodes and counterexamples
→ record follow-up hypothesis
```

### Journey D — Portfolio event risk

```text
Open portfolio event map
→ identify clustered event weeks
→ inspect shared target/modality exposure
→ see which holdings have unresolved timing
→ open company evidence
```

## 9.4 Required product states

Design and prove:

- loading;
- locked;
- nonempty;
- valid empty;
- stale;
- degraded;
- source outage;
- integrity block;
- identity unresolved;
- rights blocked;
- partial coverage;
- timing conflict;
- correction pending;
- historical view;
- recovery.

No raw exception or schema name becomes the primary user copy.

---

# 10. Market Memory integration

## 10.1 The boundary

BCI emits immutable domain-aware episode packets. Market Memory indexes and retrieves them.

BCI must not:

- create a general episode database parallel to Market Memory;
- create a generic vector search service;
- create a cross-domain Rhyme/Difference engine;
- duplicate Market Memory reliability/calibration presentation;
- mutate Market Memory prospective ledgers;
- claim general retrieval is live while Market Memory W4 remains synthetic.

Market Memory must not:

- infer trial/program semantics;
- create BioCatalyst corrections;
- infer sponsor-to-security identity;
- invent clinical/regulatory outcomes;
- define BCI event families without BCI ownership.

## 10.2 Forward compatibility while Market Memory is blocked

BCI cannot wait indefinitely for the complete Market Memory V2 product.

Therefore the vertical boundary is:

1. BCI builds and prospectively appends its own **domain market episode packet** and outcome sidecar.
2. The packet contract includes everything a generic Market Memory adapter needs.
3. BCI's first product may read its own bounded episode store for exact event history and simple deterministic cohorts.
4. BCI does not build a general learned/hybrid retriever.
5. When Market Memory operational retrieval is ready, it ingests the same packet bytes and becomes the canonical analogue/counterexample service.
6. Any temporary BCI cohort reader is retired or retained only as a deterministic baseline.

## 10.3 Retrieval profiles

BCI provides profile-specific comparison rules such as:

- event family;
- issuer dependency/archetype;
- phase;
- indication/target/modality;
- timing precision;
- trial execution state;
- pre-event run-up;
- options expectation;
- financing state;
- regime;
- contamination class;
- era.

Market Memory owns index generation, retrieval execution, diversity, negative controls, and generic packet rendering.

---

# 11. Other lobe integration and the role of Seasonality

## 11.1 Seasonality is a shared method family, not the owner of every domain

There are two distinct concepts:

1. **generic calendar/statistical primitives** — repeated calendar windows, circular-shift nulls, event-window alignment, selection correction;
2. **domain clocks** — biopharma catalysts, procurement budgets/recompetes, filing/earnings cycles, option expiry, policy releases.

Domain clocks remain owned by their specialist lobes.

BCI is the biopharma-conditioned implementation. Defense may later consume the same generic calendar primitives for budget/recompete cohorts, and FIF may use them for filing/fiscal cycles, but neither becomes part of BCI.

## 11.2 Do not create a new Temporal Intelligence Fabric yet

A generic cross-domain temporal commons should be extracted only when:

- BCI and at least one second independent lobe use the same primitive;
- the reused behavior is measured rather than merely similar in prose;
- extraction reduces duplicate code without moving domain ownership;
- the contract is reviewed by both producers and consumers.

Until then:

- preserve current generic Seasonality primitives;
- use narrow adapters;
- record duplication candidates;
- do not refactor all event systems into a new framework.

## 11.3 Defense Procurement

Defense continues as an independent specialist program.

Potential later shared seams:

- Market Memory episodes and analogues;
- known-at/effective-at/correction grammar;
- market expectation/incorporation vector;
- event collision;
- FIF financial packets;
- Neural Web context;
- Prophet shadow contribution;
- generic calendar research primitives.

It must not be merged into BCI or wait on BCI's domain work.

## 11.4 Financial Intelligence Fabric

FIF continues as the canonical financial source.

BCI later consumes bounded packet fields for:

- cash/runway;
- debt and liquidity;
- financing facilities/events;
- operating and cash-conversion state;
- filing changes;
- source traces.

BCI never recreates financial statements, metric mappings, restatement logic, or SEC source archives.

## 11.5 Future lobes

Every future lobe uses the same federated pattern:

```text
domain facts and workflow
→ governed context/episode packet
→ Market Memory historical experience
→ Neural Web context and contradiction
→ Prophet shadow contribution
→ evidence-gated authority, if ever earned
```

This is a repeatable architecture, not one central project owning every domain.

---

# 12. Neural Web, context, and authority architecture

## 12.1 BCI Context Snapshot dimension

BCI should eventually add one bounded dimension to the existing point-in-time context API:

```text
context_snapshot(ticker, date)["biopharma"]
```

It contains:

- current/nearest event summaries;
- revision state;
- timing precision;
- expectation/incorporation vector;
- contamination;
- top historical context;
- coverage/freshness;
- authority.

Historical requests must resolve against episodes and sources knowable by the requested cutoff. Current snapshots cannot leak backward.

## 12.2 Neural Web current state

BCI publishes a compact current lobe state with:

- all four clocks;
- contradictions;
- missingness;
- expiry;
- evidence refs;
- prospective learning state;
- all-false action authority.

It may explain and flag research attention. It may not originate, rank, gate, size, rewrite geometry, or raise confidence at birth.

## 12.3 Critical authority repair before richer contradictions

The current Portfolio Neural Web reader has a typed decision ladder whose default is capable of candidate sourcing and subtract-only shrink, and it can derive shrink from `graph_conflicts` counts after its own gates.

BCI will generate many legitimate context-only contradictions. If those edges are added to a generic count, BCI could indirectly alter portfolio behavior despite carrying all-false authority.

Before BCI publishes decision-visible contradiction edges, the cross-repository contract must require:

- `authority_class`;
- `decision_eligible`;
- exact eligible action;
- promotion receipt;
- source-lobe identity;
- evidence version;
- expiry.

Portfolio decision code may count only contradictions explicitly promoted for that exact action. Context-only contradictions remain available to product, prompts, and learning but cannot alter behavior through aggregation.

This is BCI-0B and may require a separate cross-repository PR. It is not bundled into episode construction.

## 12.4 Cortex and language models

Allowed:

- summarize structured BCI packets;
- cite event/source evidence;
- explain rhyme/difference;
- identify missing evidence;
- propose research hypotheses through governed research systems;
- abstain.

Forbidden:

- originate event facts;
- invent probabilities;
- infer sponsor/security identity;
- create scores or trade actions;
- change rank/size/gate from prose;
- treat a historical association as causality.

---

# 13. Prophet integration

## 13.1 Existing landing zone

Prophet US now uses evidence-family fusion and already has an F4 Catalyst/Event family.

BCI should enter only through that governed family structure, not through:

- a new global catalyst score;
- number-of-confirming-events;
- a bonus added to the board;
- a new candidate population;
- calendar-gated risk;
- a fused conviction composite.

## 13.2 Why simple C1 voting may be insufficient

Many BCI fields are not monotonically bullish or bearish:

- event proximity;
- protocol revision;
- high event importance;
- options premium;
- financing proximity;
- peer response;
- timing uncertainty.

They may become informative only conditional on:

- setup species;
- issuer archetype;
- event family;
- regime;
- horizon;
- expectation state.

BCI should first log them in the PIT Context Vector and episode ledger. Later Prophet arena rungs may test conditional contribution.

## 13.3 Promotion ladder

```text
context/display
→ prospective feature accrual
→ research baseline
→ shadow F4 contribution
→ chronological OOS and untouched holdouts
→ calibration and overlap analysis
→ bounded authority proposal
→ CEO/operator adjudication
→ explicit registry/contract amendment
→ continuous demotion and expiry
```

At no point may a BCI context packet alter live Prophet merely because its code merged.

## 13.4 Standing laws

BCI and Prophet work must preserve:

- `DNR:KILL-LLM-ORIGINATION`;
- `DNR:KILL-OFFHORIZON-VERDICTS`;
- `DNR:KILL-CALENDAR-GATED-RISK`;
- `DNR:KILL-CAUSAL-DAG-ALPHA`;
- `DNR:KILL-PROPHET-POP-MERGE`;
- the amended conditional-fusion boundaries around `DNR:KILL-FUSED-COMPOSITE`;
- `DNR:LAW-TIME-CLUSTERED-CI`;
- `DNR:LAW-ERA-SPLIT`.

---

# 14. Research and statistical architecture

## 14.1 Separate target families

Never collapse:

1. event timing;
2. clinical/regulatory/domain outcome;
3. absolute market move;
4. directional market move;
5. residual sponsor response;
6. peer read-through;
7. post-event drift;
8. financing or operational follow-on.

Each has its own owner, ruler, censoring and evaluation.

## 14.2 Event-study requirements

For eligible event families:

- explicit event-time and availability alignment;
- source-time uncertainty perturbations;
- abnormal return and complete path outcomes;
- event-induced variance treatment;
- time and issuer clustering;
- contamination filters;
- matched controls and placebo dates;
- era splits;
- costs/liquidity where a trade-like claim is studied;
- selection accounting across event families/windows;
- negative and counter-analogue cohorts.

## 14.3 Independence and effective N

Do not count overlapping windows or several events from one issuer/date cluster as independent observations.

Report:

- raw event count;
- issuer count;
- date cluster count;
- mechanism/target cluster count;
- effective N;
- leave-one-cluster-out sensitivity.

## 14.4 Baselines

At minimum compare:

- unconditional event-family base rate;
- same issuer archetype;
- same phase/event family;
- same regime;
- same pre-event run-up;
- same options expectation bucket;
- simple nearest-date/calendar control;
- random/placebo dates;
- existing Prophet baseline where relevant.

## 14.5 Calibration

A probability or interval product requires:

- chronological training/evaluation separation;
- exact frozen versions;
- Brier/log score for probabilities;
- CRPS/interval coverage for distributions;
- reliability curves;
- abstention;
- subgroup/era drift;
- prospective renewal;
- comparison with simple baselines.

A historical up-share or event-average is not a calibrated forecast.

## 14.6 Research Factory integration

BCI may emit candidate hypotheses into the canonical research/governance systems.

It must not create a separate hypothesis queue or promotion system.

---

# 15. Operational architecture

## 15.1 Two-speed system

### Slow research plane

Runs off the product path:

- calendar resampling;
- historical event studies;
- episode/outcome compilation;
- retrieval index builds;
- analogue research;
- model fitting;
- calibration;
- holdouts;
- comprehensive reports.

### Fast current-state plane

Runs after relevant source updates and before consumers:

```text
latest stable calendar evidence
+ fresh BioCatalyst events/revisions
+ canonical regime
+ options/market expectation
+ FIF/Capital Structure context
→ current BCI context packet
→ Neural Web / dossiers / Terminal / Prophet shadow
```

The fast plane must not invoke heavy research fitting.

## 15.2 Freshness clocks

Track separately:

- source content freshness;
- source publication freshness;
- ingestion freshness;
- episode projection freshness;
- market expectation freshness;
- product publication freshness;
- transport/client freshness;
- forward-ledger freshness.

A stale source cannot be laundered by a recent render time.

## 15.3 Failure behavior

- preserve last good with explicit degraded state where lawful;
- fail closed on integrity/identity/temporal mismatch;
- never turn missing into no-event;
- never delete prior episodes because the current source is unavailable;
- isolate experimental owner failure from unrelated API deployment;
- health and program watch consume canonical DAG/registry state rather than grepping one implementation file;
- alerts name the failed seam and downstream impact.

## 15.4 Rights and distribution

Every source family declares:

- acquisition rights;
- retention;
- derived-model use;
- redistribution;
- user/API projection;
- attribution;
- internal-only fields;
- expiry/review.

BCI consumes only fields permitted for its use and publication.

## 15.5 Fitness sensors

BCI requires sensors for:

- event-source liveness;
- correction latency;
- reviewed issuer/security join coverage;
- episode append heartbeat;
- registered vs graded episodes;
- contamination share;
- expectation-data coverage;
- clean attribution share;
- analogue effective N;
- calibration/coverage when eligible;
- context freshness;
- Neural Web packet coverage;
- Prophet shadow coverage and incremental value;
- zero unauthorized authority paths.

A green job with zero new eligible episodes must be distinguishable from an unwired writer.

---

# 16. Architecture freeze and no-rebuild boundaries

## 16.1 Preserve

- current Calendar Clock and its selection-accounting work;
- `biopharma.event.v2` temporal semantics;
- historical-up-share versus calibrated-estimate separation;
- BioCatalyst current/history/correction source plane;
- BioCatalyst outcome-family clocks and domain truth;
- Market Memory `market_memory.as_known_at.v1`;
- Context Snapshot explicit absent semantics;
- US Context Vector forward-only accrual;
- current Neural Web state authority ceiling;
- Prophet evidence-family fusion and conditional-authority arena;
- Terminal user-state ownership;
- FIF and Capital Structure financial truth;
- existing event-study/model/calibration modules as candidate implementation, not commissioned capability.

## 16.2 Quarantine as built but disconnected

Until operationally commissioned:

- `engine/seasonality/event_study.py`;
- `engine/seasonality/model.py`;
- `engine/seasonality/calibration.py`;
- `engine/seasonality/prophet_bridge.py`;
- `app/seasonality.py` handler surface;
- synthetic Market Memory W4/W5/W6/W7 kernels;
- any fixture-only BCI/seasonality forecast.

Quarantine means preserve tests and contracts while refusing live/product claims.

## 16.3 Supersede

The new plan supersedes these aspects of earlier documents:

- any claim that BioCatalyst has no live source plane;
- any claim that the Seasonality research browser is a commissioned API;
- the post-P0 BioCatalyst roadmap that assigns general market-response, analogue, asymmetry, Neural Web, or Prophet ownership to the source-truth plane;
- any direction to continue broad Seasonality W8 feature expansion;
- any roadmap that makes Market Memory a BCI subcomponent;
- any design that merges Defense/FIF into BCI.

Earlier documents remain authoritative for their verified history, formulas, tests, and clean-room research unless explicitly contradicted here.

## 16.4 Do not build

Without a new ruling:

- a second BioCatalyst collector or trial truth store;
- a second company/security identity system;
- a second general Market Memory episode/retrieval service;
- a parallel financial packet/metric system;
- a new generic regime engine inside BCI;
- another user-state/alerts database;
- a new generic temporal fabric based only on perceived similarity;
- a BCI composite opportunity score with hidden weights;
- a BCI candidate population or live Prophet bonus;
- request-time network research/fitting;
- an LLM-based event or identity classifier with money-path authority.

---

# 17. Program waves

Every wave is one independently reviewable capability. No operator receives a broad "continue the masterplan" prompt.

## BCI-0A — Architecture and federation freeze

**Mission:** freeze the product thesis, ownership, program boundaries, concurrency ruling, no-rebuild rules, and provisional wave sequence.

**Deliverables:**

- this masterplan;
- Agent OS decision;
- workstream;
- current-state handoff.

**Non-goals:** no engine, schema, route, workflow, UI, registry or authority change.

**Acceptance:** CEO/Chairman review explicitly accepts or amends the federation ruling.

## BCI-0B — Current-state archaeology and supersession ledger

**Mission:** re-audit all current BCI/Seasonality code, artifacts, production, open PRs, BioCatalyst ports, Market Memory seams, Neural Web/Portfolio authority, and product states.

**Deliverables:**

- exact capability ledger using the required maturity vocabulary;
- producer → builder → artifact → workflow → consumer → health map;
- contract inventory and reuse decision;
- superseded-document matrix;
- current product browser evidence;
- exact BCI-0C and BCI-1 handoffs.

**Non-goals:** no runtime code or schemas.

**Acceptance:** no built-but-inert capability counted as live; every blocker has an owner and exact next action.

## BCI-0C — Experience architecture and contract freeze

**Mission:** design the complete real-data product reference states and freeze the smallest episode/context contracts required for BCI-1.

**Deliverables:**

- 1440/820/390 real-data reference compositions;
- golden user journeys and failure states;
- golden episode set;
- exact contract reuse/new-schema adjudication;
- ownership and rights matrix;
- BCI-1 implementation handoff.

**Non-goals:** no production implementation.

**Acceptance:** one BCI-1 vertical slice can be implemented without reinterpreting intent.

## BCI-0D — Cross-repository contradiction authority hardening

**Mission:** prevent context-only BCI contradictions from influencing Portfolio or any decision system through generic conflict counts.

**Scope:** separate Macro/Mastermind contract and consumer PRs as necessary.

**Non-goals:** no BCI market intelligence, no new decision authority.

**Acceptance:** typed action eligibility and promotion receipt are enforced; context-only edge mutations cannot change decisions.

## BCI-1 — Prospective market episode packet

**User/machine capability:** one real biopharma event can be frozen with exact decision-time market context and later receive append-only outcomes.

**Scope:**

- reuse `biopharma.event.v2`;
- define/reuse minimal market-episode packet;
- one prospective episode writer;
- one real event family;
- one real consumer/inspection artifact;
- health heartbeat;
- no model.

**Production proof:** real BioCatalyst input through real BCI packet and visible/operator-readable receipt.

## BCI-2 — BioCatalyst machine projection

**Capability:** a producer-owned immutable machine projection delivers real clinical/regulatory events and revisions to BCI.

**Owner:** BioCatalyst writes; BCI reads.

**Non-goals:** no new collector, no scraping user API, no ranking.

**Proof:** exact producer bytes, pointer/receipt, one current and one historical revision event.

## BCI-3 — Commissioned event-study vertical

**Capability:** `event_study.py` runs on a registered real event family and publishes a versioned, contamination-aware research artifact.

**Scope:** implement `scripts/build_seasonality_event_studies.py` or adjudicated renamed equivalent; one downstream product/research consumer; health and receipts.

**Non-goals:** no model/forecast/Prophet.

## BCI-4 — Current BCI context and morning change feed

**Capability:** Neural Web and dossiers receive current four-clock biopharma context, and users can see "What Changed."

**Scope:**

- Context Snapshot `biopharma` dimension;
- compact BCI current state;
- source/coverage/freshness;
- morning change feed;
- no decision authority.

## BCI-5 — First complete product vertical

**Capability:** an entitled user completes one full catalyst investigation in the product.

**Scope:**

- Cycle Overview;
- Catalyst Timeline;
- Revision Intelligence;
- evidence drawer;
- one issuer/event family;
- responsive, EN/ZH, all typed states;
- Terminal decision on user-state seam.

**Proof:** production browser at 1440/820/390 with real data.

## BCI-6 — Expectations, collisions, and financial context

**Capability:** users can compare current market pricing with historical event magnitude and understand financing/event collisions.

**Consumes:** Options, FIF, Capital Structure, market/attention.

**Non-goals:** no opaque score or trade recommendation.

## BCI-7 — Market Memory analogues and peer read-through

**Capability:** retrieve diverse comparable and counter-comparable biopharma episodes with complete sponsor/peer outcome paths.

**Dependency:** operational Market Memory packet/index/retrieval contract.

**Fallback:** deterministic BCI cohort baseline only; no second general retriever.

## BCI-8 — Forecast and calibration commissioning

**Capability:** operational forecast builder registers predictions, appends outcomes, and publishes calibration/eligibility.

**Scope:** implement `scripts/build_seasonality_forecasts.py` or adjudicated equivalent over frozen episodes.

**Rule:** `calibrated_estimate` remains null whenever eligibility or prospective evidence is insufficient.

## BCI-9 — Prophet F4 shadow expert

**Capability:** Prophet can ablate a BCI contribution against the canonical ranker without changing live rank or population.

**Scope:** exact feature definitions, PIT joins, coverage/variance, overlap, contribution trace, prospective grades.

## BCI-10 — Portfolio event map and thesis memory

**Capability:** Portfolio users can see clustered catalyst exposure, shared mechanism risk, evidence changes, and historical event analogues without hidden size changes.

## BCI-11 — Earned authority adjudication

**Capability:** prepare a bounded promotion proposal only if the preregistered evidence gates are satisfied.

**Default outcome:** no promotion is an acceptable and useful result.

---

# 18. Integration checkpoints for other programs

Other programs do not wait for every BCI wave. They expose ports when their own accepted work naturally reaches them.

## 18.1 BioCatalyst checkpoints

- finish P0 typed hydration and entitled proof;
- freeze the producer projection with BCI-0C;
- continue source/coverage/domain workflow waves;
- route market-response and Prophet work to BCI.

## 18.2 Market Memory checkpoints

- close M0A prospective disposition;
- complete M0B archaeology under its own plan;
- freeze V2 episode packet/adapter interface;
- ingest BCI episodes when operational indexing is ready;
- do not make BCI wait for later learned retrieval.

## 18.3 FIF checkpoints

- accept FIF-1R packet;
- BCI-0C maps exact financial fields/receipts;
- BCI consumes only after a real packet/service exists;
- BCI does not block FIF's filing product.

## 18.4 Defense checkpoints

- close D0R acceptance and handoffs;
- proceed under its own authorization;
- later register its event packet and Market Memory profile;
- share only proven generic primitives.

## 18.5 Future-lobe checkpoint template

A lobe may federate when it can provide:

1. owner-approved event/context packet;
2. identity and temporal semantics;
3. correction behavior;
4. rights/coverage;
5. outcome owner;
6. all-false initial authority;
7. health and production proof.

---

# 19. Validation and hardening

## H0 — Current-state truth

- current repository and production census;
- capability ledger;
- open PR/worktree collisions;
- exact route/product states.

## H1 — Temporal and correction integrity

- future-information sentinels;
- partial dates/ranges;
- posted versus submitted;
- source corrections;
- exact historical replay;
- no nearest/latest fallback.

## H2 — Identity integrity

- sponsor/company/security/program/trial golden cases;
- mergers, ticker changes, partnerships;
- ambiguous and unresolved cases;
- mutation tests.

## H3 — Episode integrity

- immutable packet identity;
- source/context cutoffs;
- no label leakage;
- prospective append;
- duplicate and rerun behavior;
- missed opportunity behavior.

## H4 — Statistical integrity

- event alignment;
- time clustering;
- era split;
- contamination;
- placebos;
- effective N;
- multiplicity;
- outcome reproducibility.

## H5 — Retrieval integrity

- baseline;
- component scores;
- diversity;
- counterexamples;
- negative controls;
- index generation;
- human adjudication.

## H6 — Product utility

- ten-second contract;
- real golden journeys;
- typed states;
- responsive/browser/accessibility;
- source trace;
- user comprehension.

## H7 — Neural Web and authority

- no context-to-action leakage;
- typed contradiction eligibility;
- exact authority propagation;
- prompt/prose cannot escalate;
- stale context cannot loosen behavior.

## H8 — Prophet

- PIT frame;
- family accounting;
- null/abstention;
- overlap;
- untouched evaluation;
- no population change;
- no live authority without signed promotion.

## H9 — Operations

- source/build/projection/publication/transport clocks;
- no stale-green;
- single writers;
- recovery/rollback;
- bounded cost;
- no private evidence leakage;
- content heartbeat.

---

# 20. Completion standard

BCI is not complete because:

- a temporal schema exists;
- a page has a Catalyst tab;
- an event-study module has tests;
- a model returns a number;
- a Neural Web JSON exists;
- Prophet accepts a context field.

It is complete when an authorized user can:

1. find a current or changed biopharma catalyst;
2. understand exact timing precision and evidence;
3. trace issuer/security/program/trial identity;
4. inspect revisions and collisions;
5. compare current market expectation with historical episodes;
6. inspect diverse analogues and counterexamples;
7. understand sponsor and peer outcome paths;
8. see clear missingness, freshness and attribution quality;
9. save/monitor the investigation through canonical user-state services;
10. receive the same bounded packet in dossiers, Terminal, Neural Web and Mastermind AI;
11. have the exact decision-time episode recorded for prospective evaluation;
12. reproduce every quantitative claim from receipts;
13. prove no unauthorized rank, gate, size, geometry or trade path;
14. measure whether the product improves research speed, discovery, retention or decisions.

The company-level program is successful even if no BCI feature ever earns Prophet authority. Truth, product, memory, portfolio exposure, and research learning are independently valuable.

---

# 21. Immediate next action

Do **not** start BCI-1.

The next session executes BCI-0B only:

- fetch current `origin/main`;
- inspect current open PRs and worktrees;
- re-audit current production and all BCI/Seasonality modules;
- reconcile this architecture with BioCatalyst P0, Market Memory M0A, FIF-1R, Defense D0R, Neural Web, Prophet and Portfolio;
- produce the exact capability ledger, contract reuse matrix, supersession ledger and BCI-0C/BCI-1 handoffs;
- stop without runtime code.

---

# 22. Primary-source and internal research register

## Internal sources

- `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_HANDOFF_2026-08-16.md`
- `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md`
- `research/biocatalyst_recovery_v2/README.md` and Parts 01–08
- `research/MARKET_MEMORY_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`
- `research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md`
- `research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V3_FINANCIAL_ALPHA_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`
- `research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md`
- `research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md`
- `research/DO_NOT_REBUILD.md`
- `engine/seasonality/`
- `engine/biocatalyst/`
- `engine/neuralweb/market_memory.py`
- `engine/neuralweb/context_api.py`
- `engine/us_context_vector.py`
- `engine/theme_clinical.py`
- `config/mastermind_programs.yml`
- current PRs #5809 and #5810
- current merges #5804, #5805, #5806 and #5814

## Official/public scientific references guiding the architecture

- ClinicalTrials.gov API and study-data structure documentation, including posted/submitted clock semantics and record history;
- SEC EDGAR acceptance-time and filing-availability documentation;
- FDA Drugs@FDA data-file documentation;
- FDA advisory committee role and meeting-material documentation;
- peer-reviewed studies on clinical-trial announcement market response, protocol amendments, and FDA advisory-vote alignment;
- published event-study, calibration, clustered-inference, and multiple-testing methods;
- public data-mesh/domain-ownership architecture literature used only for the federation concept.

These sources support user jobs and methodological constraints. They are not copied product schemas or proprietary output corpora.
