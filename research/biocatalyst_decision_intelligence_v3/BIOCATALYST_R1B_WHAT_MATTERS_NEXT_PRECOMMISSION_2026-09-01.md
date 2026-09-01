# BioCatalyst V3 R1B — What Matters Next Production Vertical Precommission

**Status:** PRE-SHAPED ONLY — not commissioned  
**May become executable only after:** R0 Sol acceptance, R1A entrance/output gates or an explicit architecture-approved substitute, fresh current-owner reconciliation, one new operation/carrier, and current runtime/permission gates  
**Primary product objective:** the first independently useful BioCatalyst Decision Intelligence workflow  
**Authority at R1B:** source facts + deterministic/explainable research priority; calibrated probability/materiality only where an already-accepted owner/method is production-ready, otherwise `NOT_ESTIMABLE`; no trade/Availability/Prophet authority

---

## 1. Observable mission

Ship a real production **What Matters Next** board so an entitled user can open BioCatalyst and immediately discover the biotechnology stocks with meaningful upcoming catalysts, understand what each event is and how its timing was derived, see why it may matter, inspect exact source evidence and revisions, and decide what to research next.

R1B is the first wave that must visibly solve the Chairman's complaint. It is not complete because a schema, API, board shell or four-row fixture exists. It is complete only when useful broad real data reaches the real entitled production browser journey.

---

## 2. Why it matters

This wave converts BioCatalyst from a registry monitor into a daily investment-research product. Every later capability—historical response, calibrated outcome probability, materiality refinement, incorporation analysis, alerts and Prophet integration—becomes an enhancement to the same rows and workflow rather than another disconnected subsystem.

R1B must remain useful even when all sophisticated estimates are unavailable. A truthful board with broad events, canonical stock/asset identity, exact timing-source classes, revisions, evidence and transparent priority is materially more useful than the current workspace and provides the operating surface on which later intelligence can accrue.

---

## 3. Entrance gates

R1B may START only when:

1. R0 has been accepted and exact product/object/owner/contract/authority architecture is frozen.
2. R1A has supplied a production-proven broad event-universe contract, or Sol explicitly approves an alternative source foundation that meets the same product coverage and truth requirements.
3. A lawful Company Intelligence disclosure-event producer/consumer port exists for event families whose forward timing comes from issuer guidance; otherwise those families remain explicitly unsupported.
4. Canonical company/security identity is readable with PIT/current-only semantics.
5. R0 has resolved the asset/drug identity owner or frozen an explicit typed provisional identity path that does not mint a duplicate canonical plane.
6. Current BioCatalyst app/template/API paths and recent PRs have a collision census.
7. #6389 remains separate and does not overlap the new carrier.
8. One new R1B operation and carrier are established; receiver ACK/watcher/START gates clear.

Do not begin by implementing UI against a synthetic contract that has no real producer.

---

## 4. Complete user journey

### 4.1 Landing and decision sentence

The entitled BioCatalyst landing page answers:

> **These are the biotechnology catalysts that deserve attention now, why they are here, what is known, and what remains uncertain.**

The default surface is What Matters Next. Trial Intelligence remains one click away as evidence-level detail.

### 4.2 Board row/card

Minimum R1B row fields:

- canonical ticker/security and company name, or explicit unresolved identity;
- asset/program name/identifier and ownership/economic relationship state, or explicit unresolved/provisional state;
- event family/subtype in plain language;
- scheduled date/window with native precision;
- timing source class:
  - `official_exact`;
  - `issuer_confirmed_exact`;
  - `issuer_guided_window`;
  - `registry_schedule_fact`;
  - `rule_derived_window`;
  - `model_inferred_window` only if separately accepted;
  - `unresolved`;
- days/window to event;
- source and evidence count/quality;
- latest revision/change indicator;
- trial/regulatory/source-native status where applicable;
- issuer materiality availability/band or `NOT_ESTIMABLE`;
- outcome/timing probability availability or `NOT_ESTIMABLE`;
- historical response availability/sample or `NOT_AVAILABLE_IN_R1B`;
- incorporation coverage or `NOT_AVAILABLE_IN_R1B`;
- deterministic research-priority class/order plus concise `why_now`;
- exact coverage/freshness state.

No row may imply a probability exists merely because a source date exists.

### 4.3 Board summary

The board discloses:

- as-of/generation;
- declared universe;
- covered issuers/assets/events;
- upcoming counts by horizon/family;
- unresolved identity and unsupported-family counts;
- source freshness/partial/outage state;
- how priority is derived;
- the authority ceiling: research triage, not a trade signal.

### 4.4 Filters

R1B must freeze and implement the highest-value filters without building an analyst-terminal maze. Minimum candidate set:

- 7/30/90/180/365-day horizon;
- catalyst family;
- ticker/company/asset/indication search;
- clinical phase/regulatory stage;
- timing source class;
- new/revised/date-moved;
- identity resolved/unresolved;
- materiality available/not estimable;
- watchlist/portfolio relationship if an existing safe read seam is ready;
- source/coverage state.

### 4.5 Row investigation

Expanding/selecting a row shows:

- complete EventFact;
- exact source links/evidence pointers;
- date/status revision lineage;
- company/asset/security/economic relationship and validity;
- timing assessment/source-class explanation;
- materiality/probability objects or explicit absence and required evidence;
- current trial/regulatory dossier link;
- related events for the same asset/company;
- unresolved/conflicting evidence;
- correction and as-known-at history.

### 4.6 Action

At least one existing downstream action must be useful in R1B:

- open Trial Intelligence evidence;
- open Stock Dossier/Terminal company research;
- follow via the existing canonical watch/alert seam if safe;
- copy/export a structured research question.

R0 must choose the exact first action based on current owner readiness. Do not create another watchlist store.

---

## 5. Candidate read model / contract

R0 must freeze exact naming and reuse. Candidate semantic shape:

```text
biocatalyst_what_matters_next.v1
```

Top-level:

- contract/schema version;
- generation and source health;
- as-of and coverage clocks;
- declared universe/denominator;
- authority block;
- priority-method/version;
- rows;
- pagination/cursor;
- typed state/reason.

Row:

- `event_fact_ref` and public-safe evidence projection;
- issuer/security/asset relationship;
- event family/subtype;
- timing object and source class;
- source-native status;
- revision summary;
- materiality/probability/history/incorporation availability objects;
- research-priority object;
- coverage/missingness;
- safe product links.

Do not copy the candidate contract if an accepted existing event/read-model contract can be cleanly extended or composed. R0's reuse matrix decides.

---

## 6. Research Priority V1

R1B requires useful ordering without pretending to be a predictive trade rank.

### 6.1 Allowed deterministic inputs

Candidate V1 factors:

- current/upcoming/occurred status;
- distance to event window;
- source/timing quality;
- event-family importance class frozen by architecture, not model vibes;
- issuer materiality availability and deterministic owner-derived band where accepted;
- recent date/status/source revision;
- evidence completeness/conflict;
- identity/asset-resolution quality;
- user watchlist/portfolio relationship through a private safe read seam;
- unresolved research burden.

### 6.2 Required output

Each row carries:

- ordinal priority bucket or stable order;
- component reasons;
- missing components;
- `why_now`;
- rule/version;
- authority `research_priority_only`;
- explicit `does_not_originates_trade_or_availability` semantics.

### 6.3 Prohibited behavior

- no black-box LLM ranking;
- no outcome probability inferred from event family alone;
- no missing=zero;
- no hidden penalty that suppresses unresolved rows entirely;
- no ranking based on current BPC export-time price/IV/OI as historical evidence;
- no direct Prophet candidate admission, ordering or sizing;
- no user portfolio mutation.

R6 may later evaluate and promote a statistical priority model. R1B V1 must be explainable and useful on day one.

---

## 7. Probability and materiality behavior in R1B

R1B must not be blocked on R3, but it must reserve the correct object boundary.

For each row:

- accepted production-ready family estimate exists → show calibrated value, interval, method/version, sample/effective N and as-of;
- only descriptive base rate exists → show clearly as descriptive historical context, not personalized probability;
- evidence insufficient/model unaccepted → `NOT_ESTIMABLE` with reason;
- materiality owner facts incomplete → decomposed available facts plus `NOT_ESTIMABLE` for the unsupported aggregate;
- no silent placeholder zero, low, neutral or 50%.

The product copy must distinguish:

- source certainty;
- timing confidence;
- outcome probability;
- issuer materiality;
- historical response;
- research priority.

---

## 8. Identity and relationship behavior

R1B cannot simply map sponsor string to ticker and call it complete.

Required states:

- canonical issuer/security/asset relationship valid for current/upcoming event;
- subsidiary/parent relationship;
- co-development/license/royalty/regional rights;
- multiple economically exposed issuers;
- ticker/security alias/listing change;
- sponsor matched but canonical company identity not joined;
- asset lexical/provisional identity;
- ambiguous/unresolved relationship;
- current-only mapping not valid historically.

For R1B upcoming events, current relationship may be lawful when explicitly labelled current and when no historical claim is made. The system must not reuse it to backdate R2 historical events.

No local CIK/security map and no model self-admission.

---

## 9. Source and timing behavior

### 9.1 Registry schedule facts

ClinicalTrials.gov primary/study completion:

- remain registry schedule facts;
- may help derive or prioritize research windows;
- are never called topline readout dates;
- retain estimated/actual/date-type and native precision;
- display revisions and source status.

### 9.2 Issuer-guided events

Issuer IR/SEC/disclosure evidence may support:

- topline readout guidance;
- PDUFA/AdCom disclosures;
- filing/submission timing;
- conference/publication plans;
- corporate/partnership/financing events.

BioCatalyst consumes a bounded correction-safe Company Intelligence event/evidence port. It does not scrape SEC/IR independently.

### 9.3 Rule-derived windows

A rule-derived window must carry:

- input EventFacts;
- deterministic rule/version;
- lower/upper bound and precision;
- validation/coverage;
- prohibited claims;
- source and rule correction behavior;
- label `rule_derived`, never company-confirmed.

### 9.4 Conflicts

Conflicting issuer, registry and regulator timing does not select the most convenient date. The UI shows the conflict, current source hierarchy and unresolved state. An accepted deterministic precedence rule may select a display anchor while preserving all evidence.

---

## 10. Failure states

R1B must exercise:

- populated broad board;
- valid empty horizon/family;
- partial source coverage;
- source stale/outage;
- integrity block;
- locked entitlement;
- unresolved issuer/security;
- unresolved/provisional asset;
- multiple exposed issuers;
- conflicting dates;
- date moved/revised;
- unsupported family;
- timing not estimable;
- probability not estimable;
- materiality not estimable;
- history/incorporation unavailable;
- source-native terminated/withdrawn/suspended;
- duplicate event collision;
- generation/pagination pointer change;
- correction arriving during page session;
- downstream Stock Dossier/alert action unavailable;
- privacy/licensed evidence withheld;
- API timeout or 5xx with last-known-good behavior.

Front-facing copy must be plain language, bilingual and not expose internal slugs/private locators.

---

## 11. Exact scope and non-goals

R0 must define paths and owners. The R1B PR should remain one complete vertical and may touch only the source/read-model/API/UI/test/deploy/Agent OS surfaces necessary for the production journey.

Explicitly out of R1B unless already accepted and directly consumable:

- broad historical outcome reconstruction;
- new event-study/model/calibration engines;
- complex probability models;
- a universal materiality score;
- options/positioning incorporation engine;
- Prophet/Fusion/Availability changes;
- ranking promotion;
- portfolio mutation;
- new alert/watchlist storage;
- continuous BPC reconstruction;
- #6389 modification;
- generic Company Intelligence, Identity, Capital Structure, Market Memory or Options redesign;
- new universal event store.

R1B may add stable contract slots and honest unavailable states for later R2–R4 objects without implementing those systems.

---

## 12. Ordered implementation sequence

1. Fresh current producer/owner/path/collision census.
2. Freeze one real data composition covering useful upcoming events and the hardest identity/timing states.
3. Implement/reuse the event + identity + timing read model from real producers.
4. Implement deterministic Research Priority V1 before pagination.
5. Add bounded entitled API with typed health/coverage/failure states and private/no-store semantics where required.
6. Replace/augment the BioCatalyst landing hierarchy so What Matters Next is primary and Trial Intelligence is drill-down.
7. Add evidence/lineage/relationship inspector and at least one downstream research action.
8. Add EN/ZH and desktop/mobile behavior.
9. Add discriminating contract/unit/integration/hydration/geometry/security tests; ensure CI runs them.
10. Production-shaped local/browser proof over real data.
11. Open DRAFT/HOLD PR and STOP for Sol/Fable exact-head review before merge.
12. After release, merge/deploy through current law and run real entitled production acceptance.
13. Update Agent OS/Linear and return terminal result for Sol acceptance.

Do not build UI first and retrofit source/identity semantics afterward.

---

## 13. Acceptance tests

### 13.1 Data/contract

- broad real event universe, not fixture-only/four-NCT-only;
- stable source-native event identity and deterministic dedupe;
- exact timing source class and precision;
- registry completion never labelled readout;
- issuer-guided event linked to Company Intelligence evidence;
- canonical identity join and unresolved/multi-issuer cases;
- current-only relation cannot backdate historical claim;
- conflicts/revisions preserved;
- priority ordering before pagination, stable cursors and no duplicates;
- missing probability/materiality/history/incorporation returns typed state;
- recursive forbidden-key/private-locator checks;
- authority booleans pin no trade/Availability/Prophet behavior.

### 13.2 UI/browser

- populated default board with useful breadth;
- nonzero 7/30/90/180-day cuts where current real data supports them;
- filters/search and priority explanations;
- row evidence/lineage/relationship drill-down;
- all required failure states;
- EN/ZH;
- desktop and mobile breakpoints;
- no clipping/overflow/collision;
- zero page-origin console errors;
- accessible keyboard/focus/status behavior;
- no internal slugs/private paths/licensed raw text.

### 13.3 Production

- exact deployed commit/asset/generation identities;
- `/api/me`/entitlement and signed-out denial;
- API timings inside current edge budget;
- no unexplained 4xx/5xx/524;
- current broad generation/coverage;
- evidence links resolve;
- source stale/outage/integrity behavior tested without corrupting last-known-good;
- exact cache/version stamps and natural deployment path;
- real user can complete discovery → investigation → research action.

### 13.4 Product claim

R1B may claim:

`PROVEN_LIVE — What Matters Next broad catalyst discovery and research-priority workflow`

with exact source/family/coverage scope.

It may not claim calibrated alpha, complete biotech universe, outcome prediction coverage, historical-response completion, incorporation/mispricing, Prophet integration or trade authority.

---

## 14. Stop condition

The builder stops for review when one independently useful production-shaped vertical is complete. It does not absorb R2/R3 because slots are empty.

After production acceptance, Fable/Sol decides the next dependency based on the actual board:

- largest user-value gap;
- source/identity coverage;
- event-family demand;
- historical data readiness;
- calibration feasibility;
- instrumentation.

R2 is not automatic merely because it is next in the masterplan.

---

## 15. Required return

```text
STATUS
OPERATION / PR / EXACT HEAD / BASE / DEPLOYED COMMIT
USER CAPABILITY DELIVERED
REAL UNIVERSE / EVENT / ISSUER / IDENTITY / HORIZON COUNTS
SOURCE + TIMING CLASS COVERAGE
RESEARCH PRIORITY METHOD + EXPLANATIONS
PROBABILITY / MATERIALITY / HISTORY / INCORPORATION AVAILABILITY
CONTRACT / API / UI / FAILURE-STATE PROOF
EN/ZH / DESKTOP / MOBILE BROWSER EVIDENCE
ENTITLEMENT / PRIVACY / LICENSE SAFETY
CI / FENCES / DEPLOY / PRODUCTION RECEIPTS
GAPS / DEVIATIONS / NON-CLAIMS
#6389 NON-EFFECT PROOF
LEARNING INSTRUMENTATION START STATE
EXACT NEXT ACTION
```

No independent next wave begins until explicit Sol/Fable continuation and a new operation/carrier.
