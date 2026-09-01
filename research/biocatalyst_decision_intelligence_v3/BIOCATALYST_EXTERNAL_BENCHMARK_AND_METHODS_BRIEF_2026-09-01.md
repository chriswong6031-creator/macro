# BioCatalyst Decision Intelligence V3 — External Benchmark and Methods Brief

**Status:** R0 research seed; Fable must refresh and deepen before architecture acceptance  
**As of:** 2026-09-01  
**Authority:** external evidence and design implications only. Competitor claims are not source truth, rights grants, predictive validation or implementation authority.  
**Research rule:** learn concrete jobs and interaction patterns, then implement original Mastermind code/design using lawful first-party, official or licensed sources. Do not copy proprietary text, data, assets, brand identity or hidden methods.

---

## 1. Executive findings

1. **The market's minimum discovery bar is hundreds of companies and at least hundreds of upcoming events, not four NCTs.** Current public competitor pages advertise broad searchable catalyst calendars, ticker mapping, PDUFA coverage, change detection, company pipelines and source verification. Their figures are self-reported and must not be treated as audited coverage, but they establish the user expectation that a catalyst product begins with broad discovery.
2. **ClinicalTrials.gov primary-completion dates are not readout announcements.** The official definition is the last participant's final primary-outcome data collection date. ClinicalTrials.gov explicitly distinguishes this from later assessment, analysis or interpretation. Any product that converts that field into an estimated readout window must disclose the derivation and uncertainty rather than relabel the source fact.
3. **Issuer disclosures are the natural primary source for forward readout/PDUFA/AdCom guidance.** SEC EDGAR submissions data is updated throughout the day in real time, with typical submissions processing delays under a second. BioCatalyst should consume a correction-safe Company Intelligence disclosure-event port rather than duplicate SEC/IR ingestion.
4. **Regulatory objects must remain distinct.** FDA advisory committees provide nonbinding recommendations; the final regulatory decision remains with FDA. PDUFA dashboards describe review-goal performance and are not a direct prospective issuer-specific action-date feed. Forward company-specific action dates generally require issuer/regulator disclosure evidence with exact provenance.
5. **Clinical success probabilities vary materially by disease, phase, sponsor, biomarker and time.** Large-scale research rejects a universal biotech success rate. Family-specific or hierarchical models, fold-frozen features, calibration and explicit abstention are required.
6. **Clinical-result announcements can move sponsor stocks, but basic trial descriptors do not fully explain the variation.** A 13,807-trial event study found sponsor type, disease, outcome, phase and target accrual related to abnormal returns, while those characteristics were still insufficient to explain the full dispersion. Materiality, issuer concentration, expectations, financing and incorporation context therefore belong outside the EventFact and outside a one-number catalyst score.
7. **Predictive modeling is technically plausible but retrospective headline metrics are not product authority.** Published ML studies demonstrate signal in clinical, molecular, patent and biological features, but dataset construction, missing-data handling, temporal validation, target definition and calibration determine whether an estimate is usable. BioCatalyst must prove each family prospectively against simple baselines.

---

## 2. Competitive product benchmark

### 2.1 Current public examples

The following are public-page observations captured on 2026-09-01. Counts change continuously and require action-time refresh.

| Product | Publicly visible current claim | Jobs shown publicly | R0 implication |
|---|---:|---|---|
| **Biotech Stock Intel** | 875 upcoming catalysts, 72 PDUFA dates, 1,150 companies tracked | Catalyst calendar, PDUFA calendar, company screener, mover signals, company pages, pipelines, financials, analyst expectations, insider activity, news, source links and update details | A premium catalyst product is expected to unify broad discovery, company/asset context and source verification. Do not assume its “mover signals” are validated or copy its scoring. |
| **BiotechReadouts** | 597 companies, 109 upcoming events on the current public page, 88 disclosed catalyst dates, live change-detection feed | Ticker search, calendar, estimated windows derived from CT.gov, issuer-disclosed dates, trial status/enrollment/outcome changes, weekly update workflow | Change detection and confirmed-vs-estimated timing are minimum useful workflows. Its explicit use of CT.gov primary completion to estimate readout windows reinforces the need to label the derivation honestly. |
| **CatalystAlert** | Public page claims coverage of 1,600+ biotech stocks; 39 PDUFA decisions, 209 Phase 3 readouts and date-confidence labels on the sampled page | Search, catalyst/PDUFA calendars, confidence labels, company pages, watchlist, short interest, “smart money”, analytics and scored predictions | The product bar includes confidence/method labels, watchlists and market context. Its AI timing/prediction claims are competitor assertions, not evidence Mastermind should emulate without validation. |
| **OtimoInvest** | Smaller public pipeline/catalyst experience | Company pages, pipeline, catalyst calendar, daily/weekly analysis, sector/capital context | Even a narrower product frames catalysts through company and capital context rather than a registry record alone. |

### 2.2 What is worth reproducing independently

R0 should preserve these concrete jobs:

- search by ticker, company, asset/drug and indication;
- broad upcoming calendar with 7/30/90/180/365-day horizons;
- confirmed versus estimated/inferred timing;
- source and change history on every event;
- company and pipeline context;
- event-family filters;
- PDUFA/regulatory views;
- watchlist and revision alerts;
- company-level research drill-down;
- current market/financial context;
- transparent methodology and confidence/coverage disclosures.

### 2.3 What not to infer from competitor pages

Do not assume:

- self-reported counts are audited or deduplicated;
- every listed “readout” is issuer-confirmed;
- a confidence label is calibrated;
- a mover or AI score predicts forward returns;
- source links prove point-in-time capture or correction safety;
- public availability grants bulk redistribution or model-training rights;
- a product's taxonomy is semantically correct merely because it is popular.

The competitor benchmark sets the **discovery and workflow floor**, not the truth, statistical or authority standard.

---

## 3. Official source semantics

### 3.1 ClinicalTrials.gov

Official sources:

- API and update schedule: https://clinicaltrials.gov/data-api/api
- Protocol data-element definitions: https://clinicaltrials.gov/policy/protocol-definitions
- FAQ clarifying Primary Completion Date: https://clinicaltrials.gov/policy/faq
- Study data structure: https://clinicaltrials.gov/data-api/about-api/study-data-structure

Load-bearing semantics:

- **Primary Completion Date** is the date of final data collection for the primary outcome, whether the study completed normally or was terminated.
- **Study Completion Date** is the final data collection date for primary/secondary outcomes and adverse events.
- The date of later assessment, central review, analysis or interpretation is not the Primary Completion Date.
- Date fields may be partial and may be `ESTIMATED` or `ACTUAL`.
- ClinicalTrials.gov states data is generally refreshed on weekdays and recommends checking `/api/v2/version.dataTimestamp` to confirm the refresh.

Product consequence:

```text
registry completion date = EventFact / schedule evidence
not
readout announcement date = separate issuer/disclosure fact or methoded TimingAssessment
```

A rule-derived readout window must carry its inputs, interval, method/version, calibration and source class. It cannot be labelled confirmed.

### 3.2 SEC EDGAR and issuer disclosures

Official source:

- EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

Load-bearing semantics:

- submissions JSON is updated throughout the day as filings are disseminated;
- typical submissions processing delay is under a second, though it may be longer at peaks;
- submissions data includes filing history and company metadata, while XBRL APIs expose structured financial facts;
- bulk archives are republished nightly;
- automated access must follow SEC developer/privacy/security policy.

Architecture consequence:

- Company Intelligence should own issuer disclosure ingestion, evidence spans, corrections and event extraction.
- BioCatalyst consumes bounded event/evidence objects for readout guidance, PDUFA/AdCom disclosures, filings, financing, partnerships and other company-reported catalysts.
- Filing publication time, source statement effective period and Mastermind observation time remain distinct.
- The first filing found today cannot be backdated as the event's historical known time.

### 3.3 FDA PDUFA and advisory committees

Official sources:

- PDUFA performance dashboards: https://www.fda.gov/about-fda/fda-track-agency-wide-program-performance/fda-track-prescription-drug-user-fee-act-pdufa-performance
- Advisory committee explanation: https://www.fda.gov/consumers/consumer-updates/advisory-committees-give-fda-critical-advice-and-public-voice
- Human Drug Advisory Committees: https://www.fda.gov/advisory-committees/committees-and-meeting-materials/human-drug-advisory-committees

Load-bearing semantics:

- PDUFA dashboards report review-goal performance; they do not by themselves enumerate every prospective issuer-specific action date.
- Advisory committees provide expert advice and nonbinding recommendations. FDA retains the final decision.
- Meeting announcements/materials and final FDA actions are different event objects with different clocks and terminality.

Product consequence:

- `AdCom meeting scheduled`, `AdCom vote/recommendation`, `PDUFA target disclosed`, and `FDA action` must be separate EventFacts.
- An AdCom recommendation may influence an OutcomeProbabilityAssessment but is not the regulatory outcome.
- Prospective PDUFA dates need exact disclosure provenance and revision handling; Drugs@FDA retrospective records cannot manufacture a pending action date.

---

## 4. Clinical success-rate evidence

### 4.1 Wong, Siah and Lo — large-scale success-rate estimation

Source:

- PubMed: https://pubmed.ncbi.nlm.nih.gov/29394327/
- DOI: https://doi.org/10.1093/biostatistics/kxx069
- Corrigendum DOI: https://doi.org/10.1093/biostatistics/kxy072

The study used 406,038 clinical-trial entries covering more than 21,143 compounds from 2000 through October 2015. It estimated success rates and durations across disease, phase, sponsor type, biomarker use, lead indication and time. Results differed from commonly cited aggregate rates; biomarker-selected trials showed higher success probabilities in the study.

R0 implications:

- no universal probability across all biotech catalysts;
- phase, disease, sponsor and biomarker features may matter, but must be available at prediction time;
- time-varying base rates require temporal validation and model/version freezing;
- trial-entry duplication and compound/indication linkage are central data-engineering issues;
- published population base rates are priors/baselines, not issuer-specific probabilities.

### 4.2 BIO/Informa/QLS 2011–2020 report

Source:

- https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020

The report analyzes clinical development success rates across indications, modalities, regulatory factors and predictive factors. The public page describes it as a dataset intended to inform R&D and investment risk profiles.

R0 implications:

- modality and indication stratification should be tested as family/hierarchical priors;
- commercial/curated datasets may improve breadth but carry rights and reproducibility constraints;
- any proprietary denominator or taxonomy must be licensed and preserved as such, not silently fused with official-source truth;
- independent official-source reconstruction remains strategically valuable.

---

## 5. Market-response evidence

### 5.1 Singh et al. 2022 — 13,807 clinical outcomes

Sources:

- PubMed: https://pubmed.ncbi.nlm.nih.gov/36054103/
- Full article / DOI: https://doi.org/10.1371/journal.pone.0272851

The study analyzed stock reactions around result announcements for 13,807 trials from 2000–2020 across 379 publicly traded U.S. companies. Sponsor class, disease, outcome, phase and target accrual related to abnormal returns, but those features did not explain the full variation.

R0/R2 implications:

- historical response distributions are a legitimate product object;
- issuer archetype and concentration matter materially;
- outcome and phase alone are insufficient for a useful expected-return score;
- use distributions, tails and counterexamples rather than one mean return;
- event-date identification and confounding-event control are first-class;
- the study design supports short event windows for attribution but does not resolve longer incorporation paths;
- sponsor company identity and economic exposure must be correct before market linking.

### 5.2 Hwang 2013 — asymmetry and persistence

Sources:

- PubMed: https://pubmed.ncbi.nlm.nih.gov/23951273/
- DOI: https://doi.org/10.1371/journal.pone.0071966

In a small sample of 24 compounds, positive and negative trial announcements were associated with economically meaningful abnormal returns; negative-event underperformance was larger and persisted longer in the reported windows.

R0/R2 implications:

- upside and downside response should be modeled separately rather than assumed symmetric;
- small samples cannot support universal probability or return claims;
- event families, issuer size/concentration and outcome polarity need stratification;
- historical response is descriptive until prospective validation demonstrates research utility.

### 5.3 Pre-announcement incorporation

Source:

- Company Stock Prices Before and After Public Announcements Related to Oncology Drugs: https://doi.org/10.1093/jnci/djr338

The study found differing pre-announcement stock trends for companies later reporting positive versus negative trial results in its sample, while also raising legal and ethical implications.

R0/R4 implications:

- market incorporation may begin before the public result date;
- pre-event price behavior is context, not proof of information leakage or outcome;
- incorporation analysis needs clean public-known clocks, control for broad/sector factors and explicit alternative explanations;
- do not use future outcome labels to select the pre-event window or analogue set.

---

## 6. Predictive modeling evidence and cautions

### 6.1 Statistical imputation and approval prediction

Source:

- Lo, Siah and Wong, *Machine Learning With Statistical Imputation for Predicting Drug Approvals*: https://doi.org/10.1162/99608f92.5c5f0525

The authors used more than 140 clinical/drug-development features across disease groups and reported retrospective AUCs for later-stage approval prediction. The work emphasizes missing-data handling rather than complete-case deletion.

Implications:

- missingness is informative and coverage-dependent; it must not be silently zero-filled;
- imputation method/version belongs in the prediction receipt;
- random record-level splits are inadequate when issuer, asset and time leakage are possible;
- AUC alone is insufficient for user-facing probability; calibration and decision utility are required.

### 6.2 Open-source multimodal approval models

Sources:

- DrugApp: https://pubmed.ncbi.nlm.nih.gov/36444655/
- Bioactivity/target integration model: https://doi.org/10.1111/cbdd.14092
- ChemAP: https://pubmed.ncbi.nlm.nih.gov/39362916/

These studies demonstrate that molecular, physicochemical, trial, patent, target and biological features can contain predictive signal. They also use different targets, populations and validation schemes.

Implications:

- external model performance is evidence that research is possible, not that a model transports to public-market event prediction;
- approval prediction, phase transition, trial outcome and stock reaction are different targets;
- public-market usability requires issuer/asset/event identity, contemporaneous features, timing, economic materiality and market expectations beyond drug science;
- every model family needs a boring baseline and prospective evaluation on Mastermind's actual coverage.

---

## 7. Architecture consequences for R0

### 7.1 Separate the objects

The evidence supports the V3 separation:

```text
EventFact
→ TimingAssessment
→ ExpectationBaseline
→ OutcomeProbabilityAssessment
→ IssuerMaterialityAssessment
→ HistoricalResponseDistribution
→ IncorporationEvidence
→ ResearchPriority
```

No source or paper justifies collapsing these into one universal Catalyst Score.

### 7.2 Separate timing from outcome

A registry completion date may help define a timing window. It provides no direct evidence that the endpoint will succeed and no guarantee that results will be announced then.

### 7.3 Separate clinical probability from stock response

Even a well-calibrated clinical outcome probability does not answer stock upside/downside. Market response also depends on issuer exposure, prior expectations, financing, competition, alternatives, valuation, positioning, liquidity and information already reflected.

### 7.4 Start with discovery and evidence

Competitor products demonstrate that broad coverage, ticker mapping, source links, change detection and search are table stakes. R1B should ship those jobs before waiting for a fully mature prediction stack.

### 7.5 Calibrate or abstain

Every probability family needs a declared outcome and denominator, time-forward validation, calibration and effective N. Unsupported rows display `NOT_ESTIMABLE` rather than 50%, low or neutral.

### 7.6 Build the prospective ledger before promotion

Retrospective papers and backtests cannot confer Prophet/trade authority. Every Mastermind estimate/rank must be frozen with its model, features and as-known-at state before the outcome, then graded later under Eval/Fusion law.

---

## 8. Minimum product benchmark for R1B

R0 should freeze quantitative acceptance thresholds after current source/owner archaeology, but the first useful production board should at minimum demonstrate:

- a materially broad company/event universe, not a four-NCT canary;
- searchable ticker/company/asset/indication identity;
- 7/30/90/180/365-day horizon views;
- source-confirmed versus issuer-guided versus registry/rule-derived timing;
- date/status/evidence change detection;
- exact source and correction lineage;
- issuer/asset relationship or explicit unresolved state;
- deterministic explainable research priority;
- a company/trial/evidence drill-down;
- one useful follow/watch/research action;
- explicit coverage, freshness and unsupported-family counts;
- `NOT_ESTIMABLE` for unavailable probability/materiality/history/incorporation;
- EN/ZH, desktop/mobile and entitlement/privacy safety.

Competitor counts should **not** become a vanity target. Mastermind should optimize for verified investable coverage and decision usefulness, while showing the denominator and unresolved population.

---

## 9. R0 research questions still requiring current estate work

Fable must answer, with current repository/production evidence:

1. Which existing Company Intelligence event/evidence contracts can carry issuer readout/PDUFA/AdCom guidance without a duplicate producer?
2. What is the canonical owner for asset/drug identity, aliases and economic relationships?
3. Which current market-data path can support point-in-time event studies without retroactive adjustment leakage?
4. Can the existing Seasonality event-study and calibration modules be lawfully wired, or have owner/contracts moved?
5. Which #6389 families/rows are useful despite unresolved identity, and what is the cost of completing the existing carrier?
6. Which broad CT.gov discovery query/universe can be defended as useful, bounded and measurable?
7. What event families have enough official-source history and effective N for an initial probability model?
8. Which materiality dimensions are available now from FIF/Company Intelligence/Capital Structure?
9. What deterministic Research Priority V1 maximizes user usefulness without hidden trade authority?
10. What prospective records and evaluation target are needed before any statistical ranking is allowed?

---

## 10. Source register

### Official / primary

- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- ClinicalTrials.gov protocol definitions: https://clinicaltrials.gov/policy/protocol-definitions
- ClinicalTrials.gov FAQ: https://clinicaltrials.gov/policy/faq
- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- FDA PDUFA performance dashboards: https://www.fda.gov/about-fda/fda-track-agency-wide-program-performance/fda-track-prescription-drug-user-fee-act-pdufa-performance
- FDA advisory committee explanation: https://www.fda.gov/consumers/consumer-updates/advisory-committees-give-fda-critical-advice-and-public-voice

### Research

- Wong CH, Siah KW, Lo AW. Estimation of clinical trial success rates and related parameters. DOI: https://doi.org/10.1093/biostatistics/kxx069
- Wong CH, Siah KW, Lo AW. Corrigendum. DOI: https://doi.org/10.1093/biostatistics/kxy072
- Singh M, Rocafort R, Cai C, Siah KW, Lo AW. The reaction of sponsor stock prices to clinical trial outcomes. DOI: https://doi.org/10.1371/journal.pone.0272851
- Hwang TJ. Stock market returns and clinical trial results of investigational compounds. DOI: https://doi.org/10.1371/journal.pone.0071966
- Lo AW, Siah KW, Wong CH. Machine Learning With Statistical Imputation for Predicting Drug Approvals. DOI: https://doi.org/10.1162/99608f92.5c5f0525
- BIO/Informa/QLS Clinical Development Success Rates 2011–2020: https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020

### Competitive public pages

- Biotech Stock Intel: https://www.biotechstockintel.com/
- BiotechReadouts: https://www.biotechreadouts.com/
- CatalystAlert: https://catalystalert.io/pdufa
- OtimoInvest: https://otimoinvest.com/

---

## 11. R0 acceptance implication

This brief is not the final competitive or methods study. R0 is not complete until Fable:

- refreshes the current competitor/source facts at its return date;
- distinguishes first-party semantics from competitor transformations;
- maps every proposed method to Mastermind's actual data rights and clocks;
- defines exact family targets, denominators, validation and abstention;
- uses external precedent to strengthen the product and falsifiers rather than to claim alpha;
- carries the findings into the final R1A/R1B handoffs and no-rebuild matrix.
