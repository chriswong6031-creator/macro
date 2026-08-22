# CELL H — Prophet Flagship Product Experience: Evidence to a 5-Second Decision

**Linear:** MAS-124  
**Parent:** MAS-116  
**Canonical product authority:** Prophet V4 Experience Reference Compositions + MP-1 + current Design Doctrine / product-design system  
**Dependency:** follower of Cells A/F/G and current V4 data contracts; may research now but may not freeze invented semantics  
**Hardening archaeology pin:** branch started from Macro `af7f4af9a86c67885e13dd2bcf80b9932e3c399a`; current default-branch experience compositions must be re-read at claim time  
**Read first:** `RESEARCH_CELL_EXECUTION_CONSTITUTION_2026-08-22.md`  
**Authority:** EXPERIENCE RESEARCH / REFERENCE COMPOSITION ONLY. No UI/template/runtime mutation, no new semantic field, no population/rank/availability change.

---

# 0. Observable mission

Design the flagship Prophet experience so that within roughly **five seconds** the Chairman can answer:

> **Why is this security here now, what changed first, which genuinely independent evidence supports it, what is still missing or contradictory, how much appears already priced, what could break the thesis/path, and am I actually allowed to act at the current price?**

Then, with one deliberate drill-down, the user should be able to inspect:

- source receipts;
- evidence timeline;
- theme/relationship path;
- event/expectation/materiality;
- analogues/counterexamples;
- fragility/crowding;
- exact availability geometry/invalidation;
- corrections/missingness;
- track record and eventual outcome.

The cell's job is to make advanced intelligence **legible without flattening it**.

It is not authorized to invent data semantics because a visual concept needs them.

---

# 1. Current product law — do not clean-room redesign

Current `research/prophet_v4/EXPERIENCE_REFERENCE_COMPOSITIONS.md` freezes a shell of six linked views:

1. **Action Desk** — what can I act on now?
2. **Early Radar** — what is beginning?
3. **All Candidates** — complete searchable/sortable/filterable inventory; nothing invisible.
4. **Themes & Propagation** — theme/microtheme acceleration and read-through.
5. **Track Record** — cohort-honest performance.
6. **Health & Receipts** — operator truth: settlement/source/corrections.

It also freezes availability-first lanes:

- Entry Open Now;
- Approaching Entry;
- Early Radar;
- Wait for Pullback;
- Ran — Don't Chase;
- Invalidated/Expired;
- All Candidates.

Green has one semantic meaning: `availability_state == ENTRY_OPEN`.

Maturity is orthogonal and cannot become the lane key.

The page must announce stale/degraded state before showing cards.

MP-1 is the accepted base for Prophet-board migration/lifecycle presentation and explicitly forbids builder improvisation when the packet and implementation disagree.

**Cell H extends the intelligence experience within these laws; it does not replace them.**

---

# 2. Product thesis — four questions, four separate answers

A flagship card/detail should never force the user to infer these from one score.

## Q1 — Why is it on my desk?

Candidate emergence / priority / what changed.

## Q2 — Why might the thesis be real?

Theme/exposure, catalyst/materiality, fundamentals, independent evidence and analogues.

## Q3 — What could make it wrong or painful?

Contradictions, fragility, crowding, missing evidence, source uncertainty.

## Q4 — Can I act now?

Deterministic availability/entry zone/invalidation/current price state.

A security may answer Q1–Q3 positively and Q4 negatively. The UI must make that coherent rather than look contradictory.

---

# 3. 5-second hierarchy

The cell must research what belongs at three information tiers.

## Glance tier — 5 seconds

Must answer:

- identity;
- availability/action verb;
- what changed now;
- top 1–3 independent evidence reasons;
- key risk/contradiction;
- coverage/confidence warning if material;
- current move/price-incorporation cue;
- freshness.

No raw internals, study names, model jargon or giant score soup.

## Inspection tier — 30–90 seconds

Must answer:

- evidence timeline;
- theme/relationship path;
- catalyst expectedness/materiality;
- price incorporation comparison;
- fragility/crowding components;
- analogue distribution/counterexamples;
- exact availability blockers;
- source/missingness/correction markers.

## Forensic tier — deep research

Receipts, source spans, raw/derived distinction, contracts, historical episode traces, correction history, method details and operator health.

The user should never need forensic tier to understand the basic action state.

---

# 4. Proposed card information anatomy — research target

This must reconcile with current V4 card anatomy rather than supersede it.

## 4.1 Identity

Ticker/company, sector/subsector, meaningful themes, asset/species context only where canonical.

## 4.2 Availability — dominant action state

- current price;
- entry zone / distance;
- availability state;
- exact blocker if not open;
- invalidation;
- risk geometry.

Availability remains visually/semantically dominant because it answers the action question.

## 4.3 Why now / emergence

One concise plain-language statement:

> “Customer capex acceleration + first technical turn; supplier peer group is already repricing.”

Must be generated from receipts/approved explanation primitives, not a freeform hallucinated summary.

## 4.4 Evidence confluence

Show **independent evidence groups**, not raw signal count.

Possible presentation:

- Theme / transmission: strong / measured;
- Catalyst/materiality: moderate / measured;
- Fundamentals: supportive / current;
- Incorporation: response small vs history;
- Analogues: favorable but high MAE;

Dependent evidence from one source should visually group under one root.

## 4.5 Risk / contradiction

One or two most decision-relevant items:

- active ATM / runway;
- crowded options expression;
- conflicting earnings evidence;
- source coverage missing;
- high path MAE.

Do not show ten tiny warning chips with equal weight.

## 4.6 Timing / incorporation

- first evidence/episode time;
- move since first event;
- whether response looks small/typical/large vs valid reference when available;
- maturity separate from availability.

## 4.7 Coverage / freshness

A sparse candidate should visibly read as sparse rather than lower-quality by invisible default.

---

# 5. “Why now” explanation law

The most important sentence on the card must answer **change**, not static quality.

Bad:

> “High-quality company with strong AI exposure and good fundamentals.”

Better:

> “Two hyperscalers raised 2027 data-center capex this week; VRT's verified cooling/power exposure is high, peers have rerated and VRT's residual move remains modest. Early turn fired today.”

Required components when available:

- newly changed evidence;
- relationship to issuer;
- timing/first-known;
- price response relative to context;
- candidate emergence;
- current availability.

The explanation must degrade gracefully:

> “Early technical turn; theme corroboration is still accruing.”

not fabricate missing context.

---

# 6. Evidence independence UX

The user must understand when five facts are really one source.

Potential design patterns to research:

- grouped evidence roots;
- “2 independent sources / 5 observations” language;
- expandable source tree;
- receipt icons/links;
- separate observed fact vs model interpretation styling.

Never show a confluence count without lineage semantics.

Example:

```text
2 independent evidence roots
├─ Earnings event
│  ├─ guidance raise
│  ├─ Q&A demand topic
│  └─ semantic acceleration
└─ Customer capex event
   ├─ MSFT capex raise
   └─ META capex raise
```

The three earnings derivatives are one root family, not three votes.

---

# 7. Price incorporation UX

Cell B may eventually supply an incorporation state. Cell H must design the product to avoid “fair value” implications.

Safe early wording examples:

- “Response small vs comparable episodes”;
- “Response typical”;
- “Already moved more than comparable episodes”;
- “Not enough comparable history.”

Do not show:

- “20% undervalued” from a response gap;
- pseudo-price targets;
- “mispriced” as certainty when the method only measures unusual response.

The UI should connect incorporation to current move since evidence and availability:

> Thesis strong · response already large · **WAIT PULLBACK**

---

# 8. Fragility / crowding UX

Risk must not overwrite opportunity.

Recommended conceptual display:

```text
Opportunity thesis       STRONG
Structural fragility     HIGH — active ATM + 8mo runway
Crowding                 UNKNOWN — options source not current
Availability             ENTRY OPEN
```

This allows a sophisticated user to choose whether the asymmetry is worth it.

Do not collapse into:

> “Overall score 62 / Neutral.”

Missing risk evidence must show as unknown, not reassuring green.

---

# 9. Analogue / historical prior UX

When Cell D/Market Memory supports it, display:

- comparable episode count;
- central MFE/MAE/time-to-payoff ranges;
- nearest success;
- nearest failure/counterexample;
- match quality / missing dimensions;
- reconstructed vs prospective history.

A “75% win probability” is not the default presentation.

For small N:

> “6 comparable episodes — too few for a stable rate. See cases.”

Counterexamples must be one click away, not buried.

---

# 10. Theme & Propagation experience

The existing shell already reserves this view. Cell H must design the intelligence composition, not a new graph.

Key questions:

- Which themes/microthemes are accelerating?
- Is acceleration broad or concentrated?
- Which companies have verified exposure and by which axis?
- What relationship path explains expected propagation?
- Who has already moved?
- Who appears to lag?
- Which links are economic vs only trading/attention?
- What evidence is rights-blocked/internal only?

Potential visual units:

- ranked theme impulse list;
- propagation chain/path;
- exposure-axis panel;
- “moved vs exposure” scatter only if semantics are robust;
- lagging beneficiary table;
- source/evidence timeline.

Do not build a decorative force-directed graph whose edges cannot answer the research question.

---

# 11. Early Radar experience

Early Radar should celebrate **uncertainty honestly**, not make early candidates look like finished convictions.

Each item should answer:

- what first changed;
- which expert/event created the episode;
- what is provisional;
- what evidence is missing/accruing;
- what would advance maturity;
- whether entry is already open/approaching/waiting;
- what would invalidate/remove it.

The product should make “watch because this is early” feel deliberate, not inferior.

---

# 12. Action Desk experience

Primary ordering is availability/actionability, then priority—not raw intelligence score.

Within `ENTRY_OPEN`, user should be able to distinguish:

- highest opportunity priority;
- strongest evidence coverage;
- high-risk/high-asymmetry situations;
- newest changes;
- portfolio/watchlist relevance.

Filters/sorts must not silently redefine the server authority.

A candidate not featured remains accessible in All Candidates.

---

# 13. All Candidates experience

This is the anti-selection-bias surface.

Requirements inherited from V4:

- complete row count;
- search/sort;
- filters;
- saved views;
- lossless server rows;
- virtualized large-count rendering;
- rights-bounded exports.

Cell H should add research-oriented filtering only if underlying contracts exist, e.g.:

- evidence coverage;
- theme;
- catalyst state;
- incorporation state;
- fragility;
- crowding;
- analogue support;
- freshness;
- species.

Do not invent client-side derived “overall conviction.”

---

# 14. Dossier / drawer question order

Current V4 order is binding and should be enriched, not rearranged casually:

1. why it entered the candidate plane;
2. why trade is available/blocked;
3. what happened since first event;
4. which themes/peers are moving;
5. what intelligence is measured;
6. **what is missing**;
7. what would invalidate;
8. similar episodes;
9. prior Chairman action/history if canonical product supports it.

Cell H must define where new Cell A–G information fits without turning the drawer into a data dump.

Potential nested sections:

- Evidence timeline;
- Theme & relationships;
- Catalyst/materiality;
- Price response;
- Risks/crowding;
- Analogues;
- Receipts.

---

# 15. Failure / degraded states — mandatory reference designs

A flagship product is only premium if broken/partial states are as coherent as success.

Design at least:

## Stale board

Full-page/board header warns before cards; timestamps and which sources are stale; avoid serving old conclusions as current.

## Partial family coverage

Candidate remains visible; missing families named; priority/explanation reflects uncertainty without treating null as negative.

## Source unavailable

Show last-known state only if contract permits, clearly labeled; otherwise unavailable.

## Correction pending/applied

Correction banner and changed evidence; historical receipt accessible.

## Identity conflict

Refuse misleading company/theme/catalyst composition; explain identity under review.

## Rights-locked/internal-only evidence

Do not leak protected raw/derived content; show permitted status/capability message.

## Unestimable analogue/incorporation

Show cases/context or “not enough history,” never fake percentile.

## No candidates / empty lane

Explain why empty; don't hide section or look broken.

## Loading

Use skeleton/shimmer under MP-1 law; em dash retains published-absence meaning, not loading.

## Authentication/entitlement lock

Real server-side gating, not a DOM overlay with full paid data in source.

---

# 16. Bilingual / plain-language law

All user-facing flagship states must work in EN/ZH.

Do not translate internal enum slugs literally. Provide plain investment/research language.

Avoid front-facing:

- `falsifier` / `refuted`;
- raw experiment IDs;
- `n=` without explanation;
- internal model/state names;
- “validated” when evidence is merely observed;
- blended confidence numbers.

Technical detail belongs in hover/detail/receipts.

---

# 17. Mobile / responsive priority law

At 390px, the user still needs the 5-second answer.

Priority order:

1. identity + availability action;
2. why now;
3. top evidence / top risk;
4. price/incorporation cue;
5. freshness/coverage;
6. expandable detail.

Do not simply stack every desktop panel into a 20-screen scroll.

The final reference architecture must cover at least:

- 1440 desktop;
- laptop;
- tablet;
- 390 mobile;
- EN/ZH;
- light/dark under current design doctrine.

Actual implementation later requires browser proof, not mockup-only acceptance.

---

# 18. Interaction / alert design

Current V4 alerts are transition-driven. Cell H should research new intelligence transitions without creating notification spam.

Potential useful alerts after canonical semantics exist:

- new independent evidence root;
- material theme/transmission change;
- incorporation state changes meaningfully;
- fragility/crowding worsens;
- analogue prior changes because episode state changes;
- source becomes stale/degraded;
- `ENTRY_OPEN`/re-entry/invalidation transitions.

Do not alert on every raw source refresh or model re-run.

---

# 19. Required real-data-style reference compositions

At minimum eight full compositions:

1. **Flagship ideal:** theme acceleration + verified exposure + independent catalyst + small response + early turn + ENTRY_OPEN + low fragility.
2. **Strong thesis, bad entry:** all evidence strong, response already large, `RAN / DON'T CHASE`.
3. **Early sparse:** technical/emergence only, theme/catalyst accruing, explicit watch conditions.
4. **High asymmetry/high fragility:** strong opportunity with active financing risk.
5. **High crowding:** thesis strong, options/attention expensive; entry still open but risk clear.
6. **Contradictory evidence:** theme positive, earnings/fundamentals negative; no hidden average.
7. **Unestimable:** not enough analogue/incorporation history; still useful source facts.
8. **Degraded/stale:** board/source problem visibly outranks card content.

Each composition must include desktop + mobile information hierarchy and explain why each field belongs at glance/inspection/forensic tier.

---

# 20. 5-second acceptance test

For each reference composition, show it to a fresh reviewer with only the first viewport and ask them to answer:

1. What is the action state?
2. Why is it interesting now?
3. What is the strongest independent evidence?
4. What is the biggest risk/missing piece?
5. Has the move already run?

If the answers require opening raw receipts or interpreting internal enums, the first viewport fails.

This is a product comprehension test, not alpha validation.

---

# 21. Proposed future implementation waves — NOT authorized

### H-W1 — Intelligence composition contract / wireframe reference

Docs/reference only. Map current V4/MP-1 primitives to Cell A–G semantics and explicit degraded states.

### H-W2 — One existing-contract card enhancement

Only fields already canonical; real data; desktop/mobile/EN/ZH; no new semantics.

### H-W3 — Evidence timeline / receipt drill-down

Source-backed, grouped by independence lineage; no freeform unsupported AI prose.

### H-W4 — Theme/Propagation and analogue composition

Only after Cells A/D contracts/owners are stable; one real end-to-end reference.

### H-W5 — Full flagship acceptance

Six-view coherence, real auth/production data, performance/accessibility/browser proof, telemetry hooks. Separate from predictive acceptance.

---

# 22. Explicit non-goals / do-not-redo

- Do not redesign the six-view V4 shell from scratch.
- Do not replace MP-1 lifecycle law.
- Do not make lifecycle/maturity the availability lane.
- Do not use green for anything except `ENTRY_OPEN` under current law.
- Do not invent fields because a mockup wants them.
- Do not create an overall conviction/risk score.
- Do not hide missing evidence.
- Do not bury counterexamples.
- Do not let client-side filters create hidden authority.
- Do not port reference-only interaction code when production primitive exists.
- Do not use mockups as production proof.
- Do not expose paid/private body behind client-only DOM lock.
- Do not call response gap “undervalued” unless separately supported.
- Do not let intelligence visually override a closed/chased availability state.

---

# 23. Fresh-Sol misconstruction checklist

Prove all false:

1. I treated this as a greenfield redesign.
2. I invented data semantics for visual convenience.
3. I used one score to simplify the page.
4. I made strong thesis look actionable when availability is closed.
5. I represented missing as low/neutral.
6. I counted dependent evidence as multiple votes.
7. I hid failed analogues/counterevidence.
8. I made early uncertainty look like product failure.
9. I designed only the happy desktop state.
10. I changed server population/rank/gates from the UI lane.

---

# 24. Required final deliverable / stop condition

Return a durable experience architecture containing:

- current V4/MP-1 product authority/reuse ledger;
- 5-second information hierarchy;
- card anatomy mapping to canonical fields;
- “why now” explanation contract;
- evidence-independence presentation;
- incorporation / fragility / crowding / analogue UX laws;
- Themes & Propagation composition;
- Early Radar / Action Desk / All Candidates / dossier integration;
- explicit stale/partial/correction/identity/rights/unestimable/loading/auth states;
- eight full real-data-style compositions;
- desktop/mobile/EN/ZH hierarchy;
- 5-second comprehension test;
- 3–5 follower implementation waves;
- CEO decisions/unresolveds.

**STOP before editing templates/site/scripts/runtime, changing population/rank/availability, or freezing UI around data contracts that current canonical owners have not accepted.**
