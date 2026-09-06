# CELL C — Catalyst Surprise, Materiality & Incorporation Federation

**Linear:** MAS-119  
**Parent:** MAS-116  
**Canonical domain owners:** Earnings Intelligence, BioCatalyst / future BCI federation, Defense Procurement, and any later specialist catalyst owner  
**Possible future consumer:** Prophet D5 evidence adapters + Conditional Fusion only after owner-specific validation  
**Hardening archaeology pin:** Macro `af7f4af9a86c67885e13dd2bcf80b9932e3c399a`  
**Read first:** `RESEARCH_CELL_EXECUTION_CONSTITUTION_2026-08-22.md`  
**Authority:** RESEARCH / FEDERATED CONTRACT DESIGN ONLY. No catalyst score, no active owner runtime change, no E3/Bio/Defense continuation, no Prophet rank/gate authority.

---

# 0. Observable mission

Design a common **semantic envelope** that lets specialist systems express four fundamentally different things without losing their domain-specific truth:

1. **What happened or is scheduled?**
2. **What did the market/company/consensus reasonably expect immediately beforehand?**
3. **How economically or strategically material is the change to this issuer?**
4. **How much appears already incorporated into price/expectations?**

The federation exists so Prophet can eventually compare evidence **conceptually** across domains without pretending a defense award, earnings revision, trial milestone and regulatory decision share one scoring formula.

The 10/10 output is a typed contract and research method where each domain can say:

> “This is a verified event fact; expectation is measurable/unmeasurable; surprise is X under the domain's own ruler; materiality is Y under a defensible issuer denominator; incorporation is separate and may be unknown; source clocks and corrections are explicit.”

No generic catalyst engine is created.

---

# 1. Why this matters to the flagship product

A calendar/event detector is not intelligence.

A future Prophet should be able to distinguish:

- an event that merely occurred;
- an event the market already knew was scheduled;
- an outcome that deviated from expectation;
- an outcome that is large but immaterial to a giant issuer;
- an outcome that is small in dollars but transformative to a small issuer;
- a positive outcome already fully priced;
- a scheduled date whose outcome is entirely unknown;
- a high-impact event whose evidence quality or identity is uncertain.

The moat comes from historical, point-in-time **expectation → surprise → materiality → market-response** sequences by domain and issuer type—not from event counts.

---

# 2. Current owner boundaries — binding facts

## 2.1 Earnings E3 is an intelligence compiler, not a scorer

`WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER` explicitly owns a model-propose / deterministic-admission workflow extending canonical `event_workspace.v1`. It forbids earnings_qual as event truth, a second Q&A store, and arbitrary beat/miss semantics. At the current open E3-A PR, the gold has only seven AAPL exchanges and explicitly refuses to invent a numeric usefulness threshold.

**Cell C may study future expectation/surprise semantics, but may not use E3-A to infer predictive materiality or reopen the compiler freeze.**

## 2.2 BioCatalyst Trial Milestone Radar is schedule truth

The current Sol-ratification PR states that ClinicalTrials.gov supplies sponsor-submitted primary/overall completion dates, often estimated. The product must say **Trial Milestones**, not topline readouts. No outcome, approval probability, materiality, score, rank or Prophet authority is granted.

**A scheduled trial milestone is not a positive or negative catalyst.** Cell C must preserve this distinction even if users colloquially call it a catalyst.

Future Biopharma Cycle Intelligence may own expectation, historical response and peer read-through above BioCatalyst; this cell must route that capability to the canonical owner rather than placing it inside Trial Milestone Radar.

## 2.3 Defense already has temporal/source/financial foundations

`WS:DEFENSE-PROCUREMENT-V3` has completed D1–D4, including identity, temporal Change Tape, dual clocks and a company-financial-truth bridge. D5R ontology/representability research is separately active/gated; D5 implementation remains unauthorized at the hardening pin.

**Cell C must consume Defense's owner semantics and propose future adapter requirements; it may not start or redesign Defense D5.**

---

# 3. Chairman intent — what “catalyst intelligence” means

The user-facing question is not:

> “What events are coming?”

It is:

> **“What changed relative to what was expected, how much does it matter to this company, what evidence supports that judgment, and is the market response commensurate?”**

The cell therefore must preserve five separate objects:

1. event/schedule fact;
2. expectation baseline;
3. realized outcome / surprise;
4. issuer materiality;
5. incorporation/market response.

Some domains cannot populate all five. That is acceptable.

A missing expectation baseline does **not** become “neutral surprise.” A scheduled milestone with no result does **not** become positive. A large dollar award does **not** become highly material without issuer context.

---

# 4. Candidate common envelope — research target, not frozen schema

The cell must reconcile existing contracts and propose the smallest common semantics. Candidate fields/questions:

```text
catalyst_event_id / canonical owner event id
owner_family / owner_contract_version
subject_company_epoch / security if market-specific
event_kind
event_state (scheduled / occurred / revised / cancelled / outcome-known etc.)
source_event_time
source_available_at
captured_at
corrected_at / supersedes
source_evidence_refs
fact_state
expectation_state
expectation_basis
expectation_known_at
surprise_state
surprise_magnitude_native
surprise_estimability
materiality_state
materiality_basis / denominator
materiality_estimability
incorporation_state / reference
coverage_state
confidence_basis
rights_tier
authority_tier
method_kind
null_reason
```

Do not force a domain to emit fake numeric magnitude merely to satisfy a common schema.

---

# 5. Common axis 1 — Event / schedule fact

The common layer should answer only what the source supports.

Examples:

### Earnings

- earnings release published;
- guidance metric changed;
- Q&A exchange accepted from source transcript;
- conference time / source availability exact.

### Biopharma

- trial primary-completion estimate moved;
- trial status changed;
- regulatory filing/decision exists when a lawful prospective source supports it;
- result/readout only when actual result source exists.

### Defense

- award/modification/appropriation/program milestone posted;
- amount/recipient/agency/program relationship;
- first-known versus effective/action dates.

Required distinction:

`SCHEDULED` ≠ `OUTCOME_KNOWN` ≠ `EXPECTED_POSITIVE`.

---

# 6. Common axis 2 — Expectation baseline

Expectation is the hardest and most domain-specific object. The cell must define **valid expectation sources**, their clocks and abstention law.

Potential classes:

## Direct explicit expectation

- consensus estimate;
- management guidance range;
- contract/program milestone already announced;
- published trial timeline;
- options implied move (market expectation of magnitude, not direction);
- officially disclosed procurement ceiling/backlog baseline.

## Inferred expectation

- sell-side revision consensus;
- historical issuer behavior;
- event probabilities;
- narrative/whisper expectation.

Inferred expectations require much higher evidence burden and usually remain context-only until validated.

## No defensible expectation

Output `UNESTIMABLE` / `NO_BASELINE`, not zero surprise.

The research must specify for each domain:

- expectation source hierarchy;
- PIT availability;
- revisions;
- coverage;
- rights;
- denominator/scale;
- whether model extraction is acceptable;
- falsifiers.

---

# 7. Common axis 3 — Surprise

Surprise exists only relative to a prior expectation.

Possible domain-native representations:

### Earnings

- actual minus consensus, standardized appropriately;
- guidance midpoint/range change vs previous/consensus;
- new management qualitative answer vs pre-event expectation, likely model-generated/context-only until calibrated.

### Biopharma

- milestone date moved earlier/later vs prior schedule;
- outcome result versus preregistered/market expectation **only when actual outcome and defensible expectation exist**;
- trial enrollment/status change versus prior record.

### Defense

- award/modification amount versus previously known ceiling/backlog/expected timing;
- new program transition/appropriation versus known baseline;
- recipient share/contract scope surprise when evidence supports it.

The common contract should preserve native units plus a possible family-relative percentile, not force all surprises onto 0–100.

---

# 8. Common axis 4 — Issuer materiality

Materiality answers:

> **If this event is true, how much can it matter to the issuer's economics, strategic position or risk?**

It does not answer whether the market will react.

The cell must research domain-specific denominator hierarchies.

## Defense examples

- award value vs trailing revenue;
- funded value vs backlog;
- expected annualized revenue, not headline ceiling, where estimable;
- program duration and margin assumptions;
- sole-source/strategic role;
- option/ceiling uncertainty.

A $1B IDIQ ceiling is not necessarily $1B issuer revenue.

## Earnings examples

- revenue/EPS/gross-margin/guidance change relative to company base and prior expectations;
- segment contribution;
- durability / recurring vs one-off.

## Biopharma examples

- asset contribution to company valuation/pipeline concentration;
- phase/stage and addressable market only under lawful, defensible assumptions;
- cash runway/financing dependency may belong to Capital Structure, not BioCatalyst truth;
- probability-of-success estimates require independent validation and cannot be silently model-invented.

Materiality may be categorical or interval-valued when exact economics are not estimable.

---

# 9. Common axis 5 — Incorporation

Incorporation is deliberately separated from source/domain truth and links conceptually to Cell B.

A domain owner may emit the event/surprise/materiality packet; a future downstream research layer can ask whether price response is small/typical/large relative to history.

The common catalyst contract should provide enough identity/time/materiality information for Cell B without embedding a universal market-response score.

No domain lobe should call an event “underpriced” merely because it knows its own fact.

---

# 10. Model-generated evidence law

Models may help extract:

- Q&A topics;
- guidance wording changes;
- semantic expectation language;
- program/mission relationships;
- trial/protocol narrative.

But model output must preserve:

- exact source spans/IDs;
- model/version/prompt or controlled method identity where policy requires;
- deterministic validation/admission;
- unsupported/refused states;
- zero predictive authority by default.

Do not let an LLM generate:

- “materiality = 82”;
- probability of approval/trial success;
- management credibility score;
- beat/miss when canonical owner forbids it;
- expected contract revenue without source-backed assumptions.

---

# 11. Correction / temporal law

The cell must design shared semantics that tolerate:

- trial date revision/cancellation;
- earnings transcript correction;
- revised guidance;
- contract modification/deobligation;
- award effective date earlier than discovery date;
- restated company financials;
- source corrections;
- expectation revisions before event outcome.

Preserve both:

- what the world/economic event date was;
- when Mastermind/the market could first know each belief.

Never project a later correction backward into a previous evaluation tape.

---

# 12. Required cross-domain reference compositions

The research must show at least these states.

## Composition 1 — Defense award, high headline / low economic materiality

Large ceiling; low funded amount; multi-year duration; issuer already has similar backlog. Event fact strong, surprise moderate/unknown, materiality low/moderate. No “huge catalyst” language.

## Composition 2 — Defense modification, small dollars / high strategic materiality

Small near-term amount but confirms entry into a major program/mission with future optionality. Economic direct value low; strategic materiality context high but predictive authority limited.

## Composition 3 — Earnings result, measurable surprise

Actual/guide versus frozen consensus; segment contribution known; materiality high; Q&A model evidence source-backed. Separate market incorporation.

## Composition 4 — Earnings qualitative shift, no stable numeric baseline

Management language changes materially, but no validated expectation measure. Fact/semantic delta context-only; surprise `UNESTIMABLE`.

## Composition 5 — Biopharma scheduled milestone

Primary completion estimate within 180 days. Event is scheduled, not outcome-known; surprise/materiality not yet populated. Product must not imply imminent topline result.

## Composition 6 — Biopharma schedule revision

Milestone slips materially versus prior sponsor-submitted estimate. Surprise exists relative to prior schedule; clinical outcome remains unknown.

## Composition 7 — Conflicting catalyst evidence

Positive earnings guidance but simultaneous financing/dilution risk or contract deobligation. Preserve separate axes/owners; do not average into one catalyst score.

## Composition 8 — Insufficient expectation data

Strong event fact but no defensible expectation/materiality denominator; Catalyst intelligence remains useful context while downstream rank authority stays absent.

---

# 13. Owner-specific research matrix

The final artifact must produce a matrix for at least Earnings, Defense and Biopharma:

```text
axis | current owner contract | current capability state | source | PIT clock |
coverage | model role | valid nulls | authority | missing work | future adapter
```

The goal is to find **shared semantics**, not shared implementation.

If two owners use the same word differently (e.g. “event date”, “materiality”, “confidence”), record a same-name/different-meaning collision and recommend explicit translation.

---

# 14. Buildability / estimability questions

For every domain/axis classify:

- source exists now?
- PIT history exists?
- expectation history sufficient?
- denominator available?
- rights clear?
- identity stable?
- model needed?
- sample size adequate for validation?
- useful context before predictive proof?
- active owner wave collision?

Likely outcome: event facts are broadly buildable; expectation/materiality are much more domain-conditional; incorporation is downstream; universal predictive catalyst score should remain rejected.

---

# 15. Evaluation / falsification

Each owner-specific future method must eventually answer:

- Does expectedness/surprise improve outcome prediction vs raw event presence?
- Does issuer-normalized materiality improve vs headline dollar/value magnitude?
- Does the construct work prospectively and remain early?
- Does it add beyond existing Earnings/Defense/Bio context?
- Does it survive issuer/event/date clustering?
- Is the effect carried by one event type?
- Does model-derived semantic evidence add independent value beyond deterministic facts?

Negative controls:

- scheduled events with no outcome;
- immaterial but newsworthy events;
- old/repeated awards;
- consensus-exact earnings;
- date-only/late-discovered events;
- placebo semantic features;
- structural risk events with opposite expected behavior.

---

# 16. Proposed future implementation waves — NOT authorized

### C-W1 — Cross-domain semantic census / collision ledger

Research only. Reconcile owner contracts and freeze common envelope terms without runtime change.

### C-W2 — One owner-approved expectation/surprise adapter

Choose the most mature domain after current owner gates; preserve owner computation and emit common translation fields to a research consumer.

### C-W3 — One issuer-materiality vertical

Use defensible domain denominator and correction/PIT law; context-only until evaluated.

### C-W4 — Multi-domain federation projection

Three domains can be viewed under the same semantic questions while retaining method/authority differences. No universal score.

### C-W5 — D5/Fusion research adapter

After Cell F/G contracts mature, expose versioned fields for prospective evaluation. Availability remains separate.

---

# 17. Explicit non-goals / do-not-redo

- Do not create a universal catalyst score.
- Do not reopen Earnings E3 architecture or infer a usefulness threshold from N=7.
- Do not call Trial Milestones topline/readout dates.
- Do not infer PDUFA coverage without lawful prospective source.
- Do not start Defense D5 implementation.
- Do not make contract ceiling equal expected revenue.
- Do not default missing expectation to neutral surprise.
- Do not let model extraction become materiality/probability authority.
- Do not create another event workspace/store.
- Do not copy specialist data into a new catalyst warehouse for convenience.
- Do not let a domain event directly change `ENTRY_OPEN`.

---

# 18. Fresh-Sol misconstruction checklist

Prove all are false:

1. I turned the common envelope into a common scoring algorithm.
2. I treated schedule as outcome.
3. I treated event existence as surprise.
4. I treated headline size as issuer materiality.
5. I made `NO_EXPECTATION_DATA` equal zero surprise.
6. I absorbed an active Earnings/Bio/Defense wave.
7. I generated probabilities/materiality from an LLM without evidence.
8. I created another event store.
9. I fused contradictory evidence into one hidden number.
10. I gave catalyst evidence immediate Prophet rank/entry authority.

---

# 19. Required final deliverable / stop condition

Return a durable federation architecture containing:

- current owner/capability ledger;
- same-name/different-meaning collision ledger;
- common event/expectation/surprise/materiality/incorporation envelope candidate;
- owner-specific method tables for Earnings/Defense/Biopharma;
- clocks/null/correction/model law;
- eight reference compositions;
- buildability/estimability matrix;
- validation/falsifier plan;
- 3–5 owner-routed future wave packets;
- explicit CEO decisions/unresolveds.

**STOP before modifying Earnings E3, BioCatalyst, BCI, Defense D5, any event store, Prophet D5/Fusion rank or availability.**
