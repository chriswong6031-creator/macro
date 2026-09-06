# PROPHET FLAGSHIP INTELLIGENCE — DATA, SOURCE & MOAT LEDGER

**Date:** 2026-08-22  
**Status:** architecture/source research; not a procurement authorization  
**Purpose:** map desired flagship intelligence heads to current Mastermind owners, authoritative/public sources, likely licensed gaps, point-in-time requirements, freshness limits, rights risks and the moat created by accumulating lawful history.  
**Parent:** `PROPHET_FLAGSHIP_INTELLIGENCE_EXPANSION_MASTERPLAN_2026-08-22.md`

---

# 0. Source strategy thesis

The flagship data strategy should follow this order:

1. **Reuse canonical Mastermind owner truth already collected.**
2. **Exploit first-party / government / issuer-authoritative sources** where they can support the job honestly.
3. **Build semantic extraction and correction lineage** when the raw source is public but difficult.
4. **License data only when the missing capability is genuinely expensive/impossible to reconstruct lawfully and the incremental value is material.**
5. **Never fill source gaps with prohibited scraping or model invention.**

A source is not “better” merely because it is expensive.

A source is not “good enough” merely because it is free.

The relevant dimensions are:

- authority / evidentiary quality;
- coverage;
- freshness;
- historical PIT reconstructability;
- corrections/revisions;
- identity quality;
- rights;
- cost;
- latency;
- machine accessibility;
- incremental product/alpha value.

---

# 1. Source-class vocabulary

## `FIRST_PARTY_ISSUER`

Issuer filings, IR releases, presentations, earnings calls, company-operated product/segment disclosures.

## `GOVERNMENT_OFFICIAL`

SEC, FINRA, USAspending, ClinicalTrials.gov, FDA and other official public sources.

## `EXCHANGE_OR_MARKET_OFFICIAL`

Exchange/market-operator or official market data feeds where licensed/available.

## `LICENSED_INSTITUTIONAL`

Consensus, detailed financial/KPI estimates, relationship datasets, web/app/consumer data, ownership/borrow or other vendor data subject to contract.

## `PUBLIC_SECONDARY`

Lawfully usable public information outside first-party/official sources. Lower authority unless independently corroborated.

## `MODEL_DERIVED`

Extraction/classification/proposal from source evidence. Never a source substitute.

---

# 2. Current Mastermind-source principle

This ledger is **not** a new ingestion roadmap.

If an owner already collects a source, extend the owner.

Examples from current architecture:

- SEC/fundamental truth → FIF / Fundamental Forensics / Capital Structure owners;
- earnings events → Earnings Intelligence;
- defense procurement → Government Revenue / Defense owner;
- clinical-trial milestones → BioCatalyst owner;
- options → Advanced Options / canonical ThetaData source;
- exact identity → Data OS;
- theme/relationships → GMI;
- historical experience → Market Memory;
- outcome evidence → Eval OS / QLedger.

The flagship program defines **requirements/adapters**, not duplicate collectors.

---

# 3. Segment / product economics — highest-leverage missing substrate

## Desired capabilities

- segment revenue exposure;
- segment profit/operating-income exposure where disclosed;
- product/service participation;
- geographic exposure;
- major-customer concentration;
- segment change/restatement lineage;
- product/segment KPI history.

## Primary authoritative source

**SEC filings / Inline XBRL / financial-statement notes / issuer disclosures.**

SEC's public data library exposes structured financial-statement/note information extracted from XBRL filings, and actual filings carry ASC 280 segment reporting, products/services, geographic and major-customer information where applicable.

Official examples show companies changing segment structures and internal segment metrics over time — exactly why a point-in-time segment layer needs revision/definition lineage rather than one current table.

## Important Mastermind internal constraint

Current FIF archaeology already found that **SEC Company Facts is not a sufficient substitute for dimension-aware filing packages** for core semantic financial work: Company Facts can lose/flatten the dimensional context needed for consolidated/segment interpretation.

Therefore the flagship plan should not say “just query Company Facts for segment revenue.”

## Recommended architecture

```text
exact filing bytes / Inline XBRL / filing package
→ canonical filing/financial owner
→ segment/product occurrence + definition + dimensional evidence
→ PIT segment taxonomy/version
→ GMI economic-exposure projection
→ Prophet thin evidence adapter
```

## Required clocks

- filing acceptance / publication time;
- source period/effective period;
- Mastermind capture time;
- restatement/reorganization known-at;
- segment-definition valid interval.

## Build vs license

**Build/extend first-party extraction first.**

A licensed normalized segment dataset may later be valuable for:

- broader global coverage;
- historical normalization;
- product-level granularity;
- faster bootstrap.

But a vendor does not remove the need for internal identity, known-at, corrections and rights-aware adapters.

## Research owner

Cell A + FIF/Data owner.

---

# 4. Earnings expectations / detailed KPI consensus

## Desired capabilities

- consensus level;
- broker/estimate dispersion;
- revision trajectory;
- segment/KPI expectations;
- guidance baseline;
- actual-vs-expectation surprise;
- post-event estimate revision.

## First-party/public baseline

- issuer prior guidance;
- SEC/IR financial disclosures;
- company KPI history;
- management commentary;
- lawful market-implied expected move where options coverage exists.

These can support some expectation states without a vendor.

## Likely licensed gap

Comprehensive **point-in-time broker consensus / detailed KPI estimates / revision histories** are an institutional licensed-data capability. Public benchmarking of Visible Alpha/other institutional systems demonstrates the job, not a free data right.

## Decision law

Do not let the desire for “expectations” auto-create a vendor purchase.

Cell C should quantify:

1. what first-party expectation baselines can already support;
2. which hypotheses truly require analyst-consensus history;
3. what universe/horizon benefits;
4. incremental value vs cost/rights;
5. whether a licensed dataset supports historical PIT snapshots, not only current consensus.

## Rights risk

High. Broker estimates and normalized vendor KPIs should be treated as licensed data with separate display/derived/model rights.

## Owner

Earnings/FIF + Cell C; procurement decision potentially Sol/Chairman if material.

---

# 5. Customer / supplier / economic relationship graph

## Desired capabilities

- customer→supplier;
- supplier→customer;
- competitor/substitute;
- distribution/platform dependency;
- shared input/end market;
- disclosed economic concentration;
- relationship start/end/correction.

## First-party / official sources

- SEC filings: major-customer / concentration disclosures where material;
- issuer releases;
- earnings calls/presentations;
- customer/supplier product announcements;
- government awards/program data where relevant.

## Coverage reality

Mandatory disclosure alone is structurally incomplete. Public relationship-research benchmarks show why broader company disclosures/calls/web evidence are used to supplement quantified mandatory relationships.

## Recommended architecture

Use a **multi-tier relationship evidence model**:

### Tier R0 — quantified authoritative

Direct disclosed revenue/customer concentration, funded contract, disclosed supplier dependency.

### Tier R1 — explicit first-party relationship

Both/one party explicitly identifies the economic relationship but does not quantify share.

### Tier R2 — corroborated public evidence

Multiple lawful sources support the relationship; no fabricated economic percentage.

### Tier R3 — model proposal only

Candidate relationship awaiting evidence validation; never predictive authority.

## Licensed option

A vendor relationship graph can materially accelerate coverage/history, but must still be mapped to canonical identity/known-at/right tiers and should be tested against first-party evidence.

## Owner

GMI / Cell A.

---

# 6. Government procurement / defense / public spending

## Authoritative source

**USAspending.gov** provides official federal award/account data with download/API access. Mastermind already has a dedicated Government Revenue/Defense owner and should extend that existing plane.

## Use cases

- award/change facts;
- agency/program/recipient identity;
- obligations vs ceilings;
- timing/correction;
- program/customer concentration;
- later issuer materiality/read-through.

## Critical semantic law

Award ceiling ≠ funded obligation ≠ issuer revenue ≠ profitability.

The source supports facts. Defense's domain method owns economic interpretation/materiality.

## Freshness

Source/publisher-specific and already governed by Defense's temporal/receipt architecture; do not add a Prophet polling lane.

## Owner

Defense Procurement / Government Revenue; Cell C consumes semantics, A can consume accepted economic relationships.

---

# 7. Clinical trial / biotech milestones

## Authoritative source

**ClinicalTrials.gov official REST API**. Current documentation says study data is refreshed daily Monday-Friday, generally by 9 a.m. ET, and exposes an API data timestamp so consumers can verify completion of the refresh.

## Existing Mastermind owner

BioCatalyst / Catalyst Radar already owns current trial milestone truth and revision semantics.

## Useful flagship facts

- sponsor/submission identity;
- trial phase;
- primary/overall completion dates;
- estimated vs actual status;
- enrollment;
- site/status changes;
- revision/cancellation history;
- known-at/source refresh.

## Not provided by source

- probability of clinical success;
- drug commercial value;
- readout direction;
- issuer materiality;
- approval odds.

Those require separate Bio/BCI methods/evidence.

## Owner

BioCatalyst/BCI; Cell C adapter research only.

---

# 8. Institutional ownership — SEC Form 13F

## Authoritative source

**SEC Form 13F filings / datasets.**

Official SEC materials state that applicable institutional managers report holdings of Section 13(f) securities; holdings reflect quarter-end positions, and filings are generally due within **45 days after the end of the calendar quarter**.

## Flagship uses

- slow-moving institutional ownership context;
- manager accumulation/distribution research;
- ownership overlap/crowding;
- fund-manager discovery evidence;
- historical external-intelligence lead signals.

## Critical freshness law

13F is **not live institutional flow**.

At any decision clock distinguish:

- holdings period end;
- filing/accepted date;
- amendment date;
- Mastermind captured-at.

A June 30 holding first filed in August is not evidence Mastermind knew on June 30.

## Correction law

13F amendments may restate/add holdings. Preserve original filing and amendment lineage.

## Coverage limitations

- only applicable managers/securities;
- quarterly snapshots;
- filing lag;
- certain confidential-treatment / reporting nuances can exist;
- positions do not reveal full manager thesis or intra-quarter path.

## Owner recommendation

Use/extend an institutional-ownership / smart-money owner if one exists; do not make Prophet a 13F collector.

Cell E/D/A may consume accepted context depending job.

---

# 9. Insider transactions — SEC Forms 3/4/5

## Authoritative source

SEC Section 16 filings.

Official SEC materials state officers/directors/10% holders report most relevant transactions; many Form 4 transactions are due within **two business days**. SEC also publishes flattened insider-transaction datasets, but those bulk datasets update quarterly, so the filing feed itself is the faster source for live evidence.

## Desired features

- open-market purchase/sale vs award/exercise/tax withholding/gift;
- insider role;
- transaction size vs holdings/compensation;
- 10b5-1 indicator/footnotes where available;
- cluster buying/selling;
- correction/amendment.

## Critical law

Do not treat all insider sales as bearish or grants as purchases.

Transaction code/context is essential.

## Freshness

Use actual filing acceptance for live known-at. Bulk quarterly datasets can help historical reconstruction/audit but cannot impersonate live filing clock.

## Owner route

Existing insider/smart-money owner if available; otherwise route through current SEC/fundamental source plane before a new owner is considered.

---

# 10. Short interest — FINRA official position data

## Authoritative source

**FINRA Equity Short Interest.**

Current FINRA documentation states:

- broker-dealers report short positions in exchange-listed and OTC equities;
- reporting is **twice monthly** around mid-month/end-month settlement dates;
- compiled data is published on the **7th business day after the reporting settlement date**;
- data can be revised, with revision flags;
- downloadable/API history is available, subject to FINRA's product terms.

## Flagship use

Short interest is a **slow positioning state**, not an intraday signal.

Useful features may include:

- short interest / float;
- change across official observations;
- days-to-cover with lawful volume denominator;
- long-run percentile;
- interaction with catalyst/fragility/crowding;
- squeeze/path-risk context.

## Important distinction

FINRA explicitly distinguishes short **interest positions** from daily short-sale **volume**. They are not interchangeable.

## Correction/freshness law

Use settlement date, publication/known-at date and revision flag separately.

Never backdate a newly published short-interest number to the settlement date as if the market/Prophet knew it then.

## Owner

Positioning/short-interest owner; Cell E context.

---

# 11. Options / implied expectations / positioning

## Canonical current Mastermind source

**ThetaData** under the Advanced Options owner, per current accepted source ruling.

## Desired flagship uses

- implied move;
- IV term structure;
- skew;
- open interest;
- strike/expiry concentration;
- event positioning;
- dealer/GEX-type mechanics only where methodology is lawful/validated;
- realized-vs-implied path context.

## Current constraint at hardening boundary

Broad-universe current coverage/cadence was still a real blocker in the examined owner record. Covered names demonstrated functional boards, but **missing names must remain NOT_COVERED**, not neutral.

## Critical PIT issues

- OI update timing;
- session/expiry identity;
- chain completeness;
- corrections;
- source store/runner identity;
- no backfilling historical missing chains from a different source and calling them original evidence.

## Owner

Advanced Options; Cell E/B may consume accepted features.

---

# 12. ETF / passive ownership and holdings

## Potential sources

Many fund issuers publish portfolio holdings, but frequency, historical availability, licensing/redistribution terms and identifiers differ substantially by issuer/product.

## Architecture law

Do not assume there is one free universal “daily ETF holdings API.”

A usable cross-fund product needs:

- source registry by issuer;
- holdings effective date;
- publication time;
- share-class/fund identity;
- historical snapshots;
- corrections;
- rights;
- mapping to canonical securities;
- treatment of cash/derivatives.

## Build-vs-license

A normalized licensed ETF/ownership dataset may be economically preferable to maintaining dozens of heterogeneous issuer adapters. That decision requires an actual coverage/cost study.

## Owner

Positioning/ownership owner, not Prophet.

---

# 13. Attention / narrative / media

## Desired uses

- attention saturation;
- emergence detection;
- novelty;
- investor-awareness proxy;
- possible moderator of incorporation speed.

## Public/first-party inputs

- issuer filing/call mention patterns;
- article/event counts from lawfully licensed/public news sources;
- potentially public search/page-view indicators where terms/API permit.

## Risk

Attention is easy to measure badly:

- source volume changes;
- duplicate syndication;
- bot/social spam;
- publisher mix shifts;
- attention caused by the price move rather than preceding it;
- unavailable historical snapshots.

## Architecture law

Use attention as a separate axis/confound/interaction candidate. “More mentions = bullish” is rejected.

## Likely licensed gap

Reliable historical news/social/web-attention coverage at institutional breadth often requires licensed data.

## Owner

GMI/Narrative/attention owner; A/E/B/G consume where validated.

---

# 14. Consumer / web / app / transaction alternative data

## Potential jobs

- demand inflection;
- product adoption;
- location traffic;
- e-commerce rank;
- web/app usage;
- card/receipt spending;
- hiring/job demand.

## Source reality

These are not one source family.

High-quality historical, normalized, point-in-time datasets are often licensed and can have material rights/privacy restrictions.

Public web scraping should **not** be assumed lawful or durable. A public URL does not automatically grant automated extraction/republication rights.

## Architecture decision rule

Only pursue an alt-data family when:

1. a concrete sector/species hypothesis exists;
2. source rights are clear;
3. historical PIT data exists or forward-only accrual is acceptable;
4. coverage is measurable;
5. an owner is named;
6. incremental value can be evaluated;
7. cost is justified.

Do not build a generic “alt-data lake” to collect everything available.

## Owner

Specialist alt-data lobe per domain; D7 thin adapter after validation.

---

# 15. Price / volume / factor state

## Required jobs

- current quotes/bars;
- technical expert inputs;
- realized volatility;
- market/sector/theme residualization;
- liquidity;
- response measurement;
- entry geometry.

## Architecture law

Price truth already has canonical Mastermind owners. The flagship project should not create a second market-data plane.

For incorporation research, the key requirement is not “more prices” but **correct contemporaneous baselines and frozen transformations**.

Adversarial amendments bind:

- leave target issuer out of theme/peer response baseline;
- no price-derived exposure using the same response window;
- fold-frozen calibration;
- cycle/re-entry guards.

---

# 16. Theme / industry pure-play benchmark members

## Desired job

Construct an independent external impulse for a theme/industry to estimate expected response of diversified issuers.

## Source requirement

Need a PIT-valid theme membership/exposure set with enough independent pure/strong members.

## Critical control

The target economic issuer and its cross-listings/share classes must be excluded from the baseline predicting that target.

If exclusion leaves inadequate member/effective N, return `UNESTIMABLE`.

## Weighting research

Compare preregistered variants:

- equal weight;
- economic/revenue share;
- market cap;
- market share;
- volatility normalized;
- residual return.

Do not choose the weighting after reading the outcome.

## Owner

GMI/Cell A + Cell B/G evaluation.

---

# 17. Analyst / institutional attention

## Potential proxies

- analyst count/coverage;
- estimate-update intensity;
- 13F manager breadth;
- institutional ownership concentration;
- news/research volume;
- options participation;
- ETF ownership.

## Research role

Potential moderator of information-incorporation speed, motivated by academic economic-link literature.

## Critical caution

Most proxies are lagged/selected and correlated with size/liquidity. Cell B/E/G must test whether attention adds anything beyond those controls.

---

# 18. Source-to-intelligence-head matrix

| Intelligence head | Preferred first sources | Likely licensed gap | Freshness class | Key owner |
|---|---|---|---|---|
| economic exposure | SEC filings/iXBRL/issuer segment disclosures | normalized global segment/product history | quarterly/event-driven | FIF/Data → GMI |
| ThemeState | price/evidence/estimate/capex/procurement owners | broad attention/consensus if needed | daily/event | GMI |
| transmission | filings/calls/releases/official contract evidence | broad PIT relationship graph | event/slow | GMI |
| expectation/surprise | issuer guidance + owner facts + options expected move | detailed broker/KPI consensus/revisions | event/daily | domain owner |
| institutional ownership | SEC 13F | faster/normalized ownership/flows | quarterly + filing lag | ownership owner |
| insider activity | SEC Forms 3/4/5 | normalized enrichment | near-event filing | SEC/smart-money owner |
| short interest | FINRA | borrow/rate/realtime lending | twice monthly | positioning owner |
| options crowding | ThetaData | none if existing entitlement suffices; coverage topology first | daily/intraday | Advanced Options |
| defense procurement | USAspending + official agency sources | optional commercial enrichment | source-specific | Defense |
| trial milestones | ClinicalTrials.gov | commercial biotech intelligence/consensus | weekday daily refresh | BioCatalyst |
| accounting/forensics | SEC filing packages | normalized specialist accounting data | filing-driven | FIF/FF |
| attention | lawful news/filing/call evidence | institutional news/social/web datasets | intraday/daily | narrative/attention owner |
| alt consumer/web | source/domain specific | often substantial | source-specific | specialist lobe |
| analogue prior | internal historical accepted evidence/outcomes | none conceptually; source families themselves may be licensed | historical PIT | Market Memory |
| observed incorporation | canonical price/factor/peer/theme planes | optional licensed factor data | daily/intraday | B + market owner |

---

# 19. Freshness classes — do not compare unlike clocks

## `INTRADAY`

Examples: price, some options/news/event feeds.

## `DAILY`

Examples: daily bars, some source refreshes, ClinicalTrials.gov weekday refresh, daily issuer/file updates.

## `EVENT_DRIVEN`

Examples: SEC filings, earnings releases, company announcements, government awards.

## `BIMONTHLY`

FINRA short interest.

## `QUARTERLY_WITH_PUBLICATION_LAG`

13F; many financial segment facts.

## `SLOW_STRUCTURAL`

Relationship/segment/ownership facts whose economics persist but whose updates are sparse.

A slow source can be extremely valuable; it simply cannot pretend to be a live signal.

---

# 20. Point-in-time source requirements

For every source family ask:

1. What is the source's economic/effective date?
2. When did the source publish it?
3. When could Mastermind lawfully access it?
4. When did Mastermind actually capture it?
5. Is the source revised later?
6. Can the historical versions be reconstructed exactly?
7. Does a later bulk dataset overwrite the old state?
8. Does the vendor expose point-in-time snapshots or only today's corrected value?
9. Are identifiers stable across time?
10. Does licensing permit historical storage/model use/display?

A current API endpoint is not a historical backtest source unless version history exists.

---

# 21. Build-vs-license decision matrix

## Prefer build/first-party when

- source is authoritative and machine-accessible;
- semantic extraction is the main challenge;
- corrections/known-at are core to the moat;
- the data can unlock many Mastermind products;
- vendor mapping would still require substantial internal reconciliation.

**Likely example:** SEC segment/product truth.

## Prefer license when

- data depends on proprietary contributor networks or broker estimates;
- historical PIT normalization is prohibitively expensive to reconstruct;
- rights/compliance are clearer under a contract;
- broad coverage materially changes the research/product;
- the vendor cost is small relative to expected intelligence value.

**Likely example candidate:** detailed broker/KPI consensus, if Cell C proves incremental need.

## Prefer defer/reject when

- source rights are unclear;
- only current snapshot exists for a historical hypothesis;
- coverage is tiny/nonrandom;
- source is unstable or disappears frequently;
- the feature duplicates existing evidence;
- no clear user/machine decision improves.

---

# 22. Data moat priority ranking

Not all data collection creates the same moat.

## Moat Tier 1 — accumulate as early as lawful/useful

- candidate episodes and evidence known-at history;
- exact corrections/revisions;
- accepted theme membership/exposure versions;
- relationship validity history;
- specialist evidence envelopes;
- current source coverage/null states;
- user actions on candidates;
- outcomes tied to the exact frozen feature version.

Why: history cannot be reconstructed perfectly later.

## Moat Tier 2 — valuable reusable structured truth

- segment/product financial history;
- expectation/revision histories;
- procurement/program histories;
- capital-structure state;
- options/positioning histories;
- analyst/ownership histories.

## Moat Tier 3 — generic commodity data

- undifferentiated news text;
- current price bars available everywhere;
- current static sector labels;
- generic sentiment.

Commodity data becomes moat only through correction-safe, decision-linked history and useful intelligence.

---

# 23. Historical bootstrap versus forward-only accrual

## Bootstrap when

- official/first-party historical versions are available with reliable timestamps;
- source identity/corrections can be reconstructed;
- universe/identity history is known;
- no outcome-driven selection is required.

## Forward-only when

- historical source versions are unavailable;
- current snapshot cannot reveal what was known then;
- rights prohibit historical use;
- model/extractor did not exist and cannot be replayed without future context;
- source timing is ambiguous.

A smaller forward evidence clock is better than a large fake backtest.

---

# 24. Data-source negative controls

For any new source family test:

- coverage indicator alone;
- stale version vs current version;
- shuffled values within coverage cohort;
- same-size/liquidity cohort without feature;
- source removed / missing behavior;
- correction-heavy subset;
- identity-conflict subset;
- one-source-root vs multi-independent-root cohorts;
- current-snapshot historical replay failure.

This distinguishes information value from source-selection value.

---

# 25. Procurement decision docket candidates

These are **not current purchase recommendations**.

Potential future Sol/Chairman decisions only after cell research:

1. detailed broker/KPI consensus history;
2. broad normalized segment/product economics;
3. broad PIT customer/supplier/competitor graph;
4. normalized institutional/ETF/borrow ownership data;
5. sector-specific alternative data for high-value species;
6. institutional news/attention history.

For any proposal return:

- current capability gap;
- hypothesis unlocked;
- first-party alternative;
- cost;
- coverage;
- historical depth/PIT quality;
- rights for internal/model/display/export;
- vendor lock-in;
- expected product/VOI improvement;
- stop/cancel condition.

---

# 26. What this ledger changes for the first research cells

## Cell A

Do not begin with “which theme vendor should we buy?”

Begin with:

- canonical segment/product truth architecture;
- first-party extraction viability;
- economic-exposure estimability;
- relationship evidence tiers;
- specific licensed gaps after census.

## Cell B

Do not assume advanced factor/vendor data is required.

Start with lawful simple baselines and prove whether more complex residualization changes conclusions.

## Cell C

Explicitly split:

- first-party expectation baselines that can be built now;
- hypotheses that need licensed detailed consensus;
- domains where expectations are structurally unobservable.

## Cell D

Do not build analogue memory from present-day vendor snapshots. Every feature used for matching needs a historical known-at story.

## Cell E

Treat FINRA short interest, SEC 13F, options and attention as different freshness/coverage classes. Never merge them into “current positioning” without clock disclosure.

## Cell F

D5 must transport source/rights/freshness/coverage metadata so the product/model can distinguish these classes.

## Cell G

Every VOI study must condition on source coverage and source clock.

## Cell H

Product copy must make slow/stale/missing/rights-blocked evidence legible rather than presenting all evidence as live.

---

# 27. Source truth is not alpha truth

An authoritative official source can still have zero predictive value.

A noisy licensed source can sometimes have predictive value.

The source ledger answers:

> **Can we know this fact lawfully and point-in-time?**

The hypothesis/evaluation system separately asks:

> **Does knowing it improve Prophet?**

Do not merge those questions.

---

# 28. First recommended source verticals for research

These are research candidates, not implementation commissions.

## DS-1 — one diversified issuer segment truth

Exact filing package → segment definitions/revenues → changes/restatements → GMI exposure candidate.

## DS-2 — one official slow-positioning family

FINRA short interest or SEC 13F → exact effective/published/captured clocks → positioning context → no rank authority.

## DS-3 — one domain expectation baseline without vendor

Prior guidance / first-party KPI / option-implied move where valid → expectation/surprise envelope → compare with licensed-data need.

## DS-4 — one typed first-party economic relationship

SEC/IR/call evidence → GMI relationship with valid interval/confidence → transmission research.

The point is to prove the contracts before scaling source count.

---

## Closing source strategy

The strongest long-term data moat is not “we bought every dataset.”

It is:

> **Mastermind knows exactly what evidence existed, what it meant economically, which issuer/theme/relationship it belonged to, when it became knowable, how it was corrected, whether price incorporated it, what Prophet did, and what happened next.**

Public/first-party data can supply a surprising amount of the truth layer.

Licensed data should be used selectively where it creates a genuine expectation/coverage/history advantage.

The unique asset is the integrated, point-in-time **decision history** built on top of all of it.
