# BioCatalyst Decision Intelligence V3 — External Benchmark and Methods Brief

**Status:** R0 research seed; Fable must refresh and deepen before architecture acceptance\
**As of:** 2026-09-01\
**Authority:** external evidence and design implications only. Competitor claims are not source truth, rights grants, predictive validation or implementation authority.\
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

---

## 12. September 6 external-evidence refresh

**Observation date:** 2026-09-06. **Scope:** public-source research and method implications, not R0 acceptance or source activation. This dated addendum updates the external evidence in sections 1-6 and 10; it preserves the September 1 observations as history. The owner/interface, priority-rule and experience decisions still open in section 9 are explicitly dispositioned below, not silently marked complete.

Source input: exact PR head `828141acc915293def802556697c1d895a682142`, protected Mastermind `cd297f1079bf5a44b520697a096096000f64efdd`. The whole-R0 review is recorded in GitHub review `5125937773`: the four repaired files remain sound and R1A architecture is sufficiently concrete, while R1B architecture choices remain. This research refresh does not apply the separately withheld authority-amendment batch, change its refusal boundary, or recover the stopped principal.

### 12.1 Public product observations, not audited coverage

The numbers below are the pages returned during this refresh. They are not independently counted records, synchronized live snapshots, licensed datasets or promises that every page shares one generation. No competitor records, proprietary text, assets, algorithms or brand treatment are incorporated into Mastermind source.

| First-party page | Returned observation | Job to preserve independently |
|---|---|---|
| [Biotech Stock Intel](https://www.biotechstockintel.com/) | 862 upcoming catalysts, 69 PDUFA dates, 1,157 companies; different from the retained September 1 counts. | Search, calendar/regulatory views, company/pipeline context and source/update drill-down. |
| [BiotechReadouts](https://www.biotechreadouts.com/) | Home page displays 597 companies, 109 upcoming events and 88 disclosed dates. Its relative countdown includes an August date despite this September observation. | Separate disclosed timing from registry-derived estimates; expose changes and actual observation dates. |
| [CatalystAlert PDUFA](https://catalystalert.io/pdufa) | Returned six-month counters show 36 PDUFA, 202 Phase 3, zero AdCom and 20 NDA/BLA events; the site advertises 1,600+ stocks. | Filter event families and timing confidence, then continue to company/watch research. |
| [OtimoInvest](https://otimoinvest.com/) | Calendar/pipeline view reports an update at September 4, 06:01 UTC and mixes day- and month-precision schedules. | Company/pipeline context, visible update time and preservation of native timing precision. |

Interpretation: broad discovery is the workflow floor, not a license to manufacture breadth. A stock count, trial count, upcoming-event count and issuer-event exposure count describe different populations. Relative countdowns and cross-page counts are unsafe evidence of freshness without the actual generation, filter and as-of identity. No diagnosis of a competitor's internal implementation follows from these observations.

### 12.2 Methodology pages change the benchmark

[Biotech Stock Intel's methodology](https://www.biotechstockintel.com/methodology) and [data standards](https://www.biotechstockintel.com/data-standards), each dated August 29, describe selective rather than exhaustive coverage, automated normalization without universal pre-publication human review, distinct timestamps and broad-window display rules. Its methodology separates options quote quality from directional interpretation. Source links therefore cannot be treated as a universal accuracy, completeness or predictive-performance guarantee.

[BiotechReadouts' methodology](https://www.biotechreadouts.com/methodology) explicitly separates quoted company guidance from as-filed registry estimates and says it uses no predictive timing model. That page reports 187 estimated and 13 confirmed entries, unlike the home counters, and describes a 450-trial cap with six companies occupying 156 slots. Its curated sponsor aliases exclude unmatched names. These are useful limits to disclose, not methods to copy: Mastermind must distinguish tracked companies from covered trials and retain unresolved identities rather than silently counting them as covered. Treat its claimed earliest timing interpretation as a competitor transformation, not an official guarantee about interim or topline announcements.

[CatalystAlert's track record](https://catalystalert.io/track-record) is a useful warning against headline accuracy: the returned page reports 74.7% direction accuracy across 257 predictions, while its always-neutral baseline is 87.5%. Its displayed confusion matrix gives 192/257 correct and 225/257 neutral outcomes, reproducing that negative baseline gap. Dilution predictions are listed separately with zero graded outcomes; historical backtest claims are not those live grades. The same returned page includes a weekly accuracy row dated October 12, 2026 despite a September 6 update stamp. This is an unresolved internal chronology inconsistency, not evidence of fraud or an explanation of its cause.

Mastermind acceptance consequence: evaluate the frozen target against a matched simple baseline; expose confusion/class balance, calibration and effective sample rather than only accuracy/AUC. A future-dated grade is rejected relative to the evaluation cutoff. Scheduled future events remain valid schedules; future realized outcomes do not become valid grades. Do not select a model because a competitor advertises a positive-looking percentage.

### 12.3 Official source and clock refresh

| Primary evidence read | Observation and bounded use |
|---|---|
| [ClinicalTrials.gov API guidance](https://clinicaltrials.gov/data-about-studies/learn-about-api) | The official indexed guidance describes weekday refresh and checking `/api/v2/version` / `dataTimestamp`. The direct page renderer returned a shell in this tool; this refresh does not claim a full current OpenAPI inspection or a transaction-isolation guarantee. Matching version observations alone do not establish an atomic population/materialization snapshot. |
| [ClinicalTrials.gov glossary in an official study record](https://clinicaltrials.gov/study/NCT02568553) | Primary completion concerns final primary-outcome data collection, with estimated versus actual source status. It is not the public release of analyzed results. No source date is turned into a clinical outcome or topline announcement. |
| [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Submissions history/metadata and XBRL financial APIs are distinct; submissions update as disseminated and bulk archives update nightly. Typical processing latency is not Mastermind's observation clock. The Bio consumer still needs the Company Intelligence-owned event extraction/receipt interface, not another SEC collector. |
| [FDA advisory committee explanation](https://www.fda.gov/consumers/consumer-updates/advisory-committees-give-fda-critical-advice-and-public-voice) | Advice is nonbinding and FDA retains the decision. A meeting schedule, a vote/recommendation and final agency action stay separate objects. |
| [FDA PDUFA performance dashboards](https://www.fda.gov/about-fda/fda-track-agency-wide-program-performance/fda-track-prescription-drug-user-fee-act-pdufa-performance-dashboards) | Page updated June 16, 2026; it reports review-goal performance, including preliminary fiscal-year results. It is not a comprehensive prospective company-specific action-date calendar. |

The API refresh convention is an operational expectation, not a fixed UTC-offset rule across daylight-saving changes. Source publication, retrieval, first Mastermind knowledge, scheduled window and final occurrence retain their own meaning and native precision. This refresh grants no source rights, production collection or alternate historical-soak verdict. The separate readiness census ended `NOT_RECOMPUTED` because its detailed inventory was not admitted, not because this research proved evidence absent from production.

### 12.4 Research methods, rights and target transport

[Singh et al. (2022)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0272851) studies 13,807 trial announcements in 2000-2020 and shows meaningful but heterogeneous sponsor-price reactions; basic descriptors do not explain the full dispersion. Crucially, its data-availability statement identifies proprietary Informa trial/development data and subscription CRSP prices. Open access to the article does **not** license those underlying datasets for Mastermind redistribution or model training. R2 may implement original event-study methods over independently lawful data, preserving sponsor identity, occurrence evidence, confounders, adjustment vintage and a documented eligible population. No research-paper row is treated as Mastermind's historical known-at record.

[Lo, Siah and Wong's statistical-imputation study](https://hdsr.mitpress.mit.edu/pub/ct67j043/release/10) and its [data supplement](https://hdsr.mitpress.mit.edu/pub/4tx7h11w/release/1) use development features and vendor trial/drug-indication joins to predict later approval at defined phase-completion boundaries. That target is not the same as predicting an unannounced trial endpoint or stock direction. A known phase result can be eligible for subsequent approval prediction while leaking the answer to a pre-result endpoint model. Any reuse therefore requires an explicitly different target/eligibility/as-known-at receipt, fold-local missingness handling and forward calibration, not transfer of a headline retrospective AUC.

The Wong success-rate article/corrigendum pair in section 4 remains historical bibliography. Full corrected numerical tables were not retrievable in this refresh, so no corrected aggregate success rate is restated or harmonized from memory. No published aggregate rate, competitor score or ungraded forward prediction is promoted into an issuer-specific probability.

### 12.5 Disposition of the ten section 9 questions

This is an evidence/decision ledger for this brief, not a second workstream or execution authority. `OPEN_R0` is deliberately not an answer. A later-wave disposition removes only an inappropriate demand that R2-R7 already be implemented before R1B; it does not waive that wave's method, owner, rights or proof requirements. Repository anchors below refer to the reviewed `828141acc915293def802556697c1d895a682142` package unless another date is stated.

| Q | Disposition / accountable owner | Evidence or decision still required; discriminating check |
|---|---|---|
| 1 — Company disclosure event interface | `OPEN_R0`; Company Intelligence interface owner with Bio consumer. | R1B section 9.2 correctly calls the proposed port `SPEC_ONLY`. SEC API documentation explains transport/data, not that internal port. Freeze the exact versioned producer/consumer seam; an absent port must withhold issuer-guided families rather than substitute fiscal context or a local SEC scraper. |
| 2 — Asset/drug/economic identity | `OPEN_R0`; Sol integration with the existing canonical identity owner. | Masterplan identity section and R1B section 8 require separate identities/relationships but do not bind the final interface. No sponsor alias list is an economic ownership record. Review wholly-owned, licensed, multi-issuer, corrected and unresolved cases before admitting joins. |
| 3 — PIT price/event studies | `DEFERRED_R2`, non-load-bearing for deterministic R1B; canonical market-data owner plus event-study consumer. | The retained August 16 Seasonality handoff section 3 warns that current-vintage adjusted prices do not prove historical vintages. It is historical evidence, not a fresh production census. Before R2, bind actual current bars/actions/vintage provenance and reject retrospective as-of claims when unavailable. R1B history stays `NOT_ESTIMABLE` meanwhile. |
| 4 — Existing Seasonality modules | `DEFERRED_R2_R3`; existing Seasonality/event-study owners. | `research/BIOPHARMA_SEASONALITY_INTELLIGENCE_HANDOFF_2026-08-16.md` names `engine/seasonality/event_study.py`, `model.py`, `calibration.py` and absent callers at that date. Preserve these as reuse leads, not today's execution proof or permission to start another builder now. Later integration must prove actual producer, consumer and output, not just module existence. |
| 5 — Finite historical snapshot | `DEFERRED_R2`; independent #6389 source owner. | The V3 commission section 14 preserves the held carrier and unresolved identity population. No fresh #6389 release is proved by this refresh. Consume only accepted rights/identity/occurrence-qualified rows; do not turn its historical licensing into continuous acquisition authority or an R1B dependency. |
| 6 — Broad CT.gov population | Architecture principle answered by repaired R1A sections 6.4/6.4.1 and whole-R0 review; source-owner execution bounds remain an R1A gate. | FULL/INCREMENTAL/PERIODIC_REPAIR, unchanged-record retention, overlap accounting and all-required-parts publication reuse the existing discovery/coverage owners. The population cannot be a recent-update-only denominator. R1A must freeze its actual admitted query/budget/coverage before collection; no whole-registry claim follows from this document. |
| 7 — First probability family | `DEFERRED_R3`, non-load-bearing for the R1B discovery workflow; model/evaluation owners. | This refresh establishes no actual family-level effective N. Publish no supported clinical probability until an eligible PIT cohort, target, censoring, baseline, temporal/group split and calibration/abstention rule are preregistered and evaluated. A paper's licensed cohort or retrospective AUC is not that proof. |
| 8 — Materiality inputs | `DEFERRED_R3`; FIF/Company Intelligence facts and Capital Structure projections, already named in the delegated commission section 6. | R1B may display accepted sourced context but does not synthesize an unsupported materiality estimate. Each future dimension needs its owner contract, units/currency, publication/observation clock and missingness. A missing financial input must not imply immateriality. No new financial engine is commissioned here. |
| 9 — Research Priority V1 | `OPEN_R0`; Sol product/intelligence decision, then bounded implementation. | R1B section 6.1.1 is still explicitly proposed. The new benchmark shows why headline accuracy is not an acceptance target. Freeze lane precedence, horizons, null/revision behavior and deterministic tie-breaks with counterexamples; keep `research_priority_only` and no trade/Availability/sizing effect. |
| 10 — Prospective evaluation | Architecture separation answered by masterplan/R1B and external-method cautions; operational proof `DEFERRED_R6` under existing Eval/Fusion owners. | Freeze prediction/priority method, eligible population, features, evidence revision and as-known-at before outcome; retain abstentions and censored rows. Grade only matured, evidenced outcomes against matched simple baselines. A future-dated grade, ungraded prediction count or rewritten old forecast cannot establish performance. Reuse the existing evaluation owner, not a new ledger plane. |

Questions 1, 2 and 9 remain genuine R0 decisions. The experience freeze and Agent OS reconciliation are additional whole-review findings outside this external brief. Marking them open is not a substitute for resolving them, and the corresponding withheld write boundaries remain intact. Conversely, completed R1 production, historical forecasts and prospective grades are not prerequisites for calling the architecture sufficiently specified.

### 12.6 Evidence-to-acceptance mapping

| Evidence limitation | Required discriminating future proof |
|---|---|
| Different page counts, caps and unresolved names | One generation/query-bound coverage receipt separates companies, trials, source events, issuer exposures, exclusions and unresolveds; pagination never silently mixes generations. |
| High raw accuracy below a majority-class baseline | Same eligible sample/cutoff for method and baseline, per-class errors and calibration; no promotion from accuracy alone. |
| Future date presented as an outcome grade | Schedule fields may be future; knowledge and realized-outcome grading clocks must satisfy their own cutoff rules. |
| Licensed research cohort beneath an open article | Data-rights receipt and independent cohort provenance before ingestion/training/distribution, with no implied license from the article. |
| Approval prediction transported to pre-result trial prediction | Freeze the actual target and prediction time; reject already-known outcome features for the target being forecast. |
| Historical reuse leads mistaken for running code | Fresh owner/caller/output evidence at the later wave; preserve typed unavailable outputs until then. |

This refresh supplies current external evidence and explicit research-question dispositions. It does not certify a final accepted R0, change the historical soak, choose an asset owner, invent the priority rule, modify application code, or demonstrate production/browser success. The next source step remains closure of the exact open R0 decisions followed by independent actual-head review and current integration checks, not another unbounded competitor study.

## 13. September 6 accepted-decision references after the research refresh

This section records subsequent internal architecture acceptance, not another external data refresh. The September 1 observations and section 12's earlier September 6 research vintage remain unchanged. Their three `OPEN_R0` entries describe the state before the decisions below; they are no longer instructions to choose those interfaces or policy again. No competitor count, source timestamp, study result, data right or historical-soak verdict is changed here.

| Question | Current architectural disposition | Exact answer and acceptance evidence | Implementation boundary |
|---|---|---|---|
| Q1 — Company disclosure event interface | Architecture choice resolved | `BIOCATALYST_R1B_OWNER_INTERFACE_FREEZE_2026-09-06.md` sections 1/2/5/6/8.1 chooses the Company Intelligence-owned non-fiscal `company_catalyst_event.v1` projection, its existing event/document/validator owners, and the Bio read/inspector consumers. Independent INTERFACE_PASS at a335729cc689adaad3a228511ba4967a4dece239 is adjudicated in PR6712 review 5126573589. | The port remains planned, not built. Absent disclosure input produces explicit unsupported-family coverage, not fiscal-context substitution, a second SEC/IR collector or a full multi-family product claim. |
| Q2 — Asset/drug/economic identity | Architecture choice resolved | The same accepted freeze sections 3/4 names the existing Data OS current issuer reader and a pure Bio domain projection with source-scoped therapeutic occurrence references. It separates sponsor evidence, admitted economic claims, issuer, security and global asset equivalence. Review 5126573589 closes whole-R0 findings 2/3 at architecture level. | No running global asset registry or real company ownership claim follows. Missing/conflicted relationships remain explicit; current-only joins cannot backdate an event study. Commit 1774fde6a9d06067406bdc9c0f9c0bdcc0ec9648 clarifies ambiguous issuer output to the existing RP unresolved input and preserves one public missing-input code. |
| Q9 — Research Priority V1 | Policy semantics accepted | `BIOCATALYST_R1B_WHAT_MATTERS_NEXT_PRECOMMISSION_2026-09-01.md` section 16 and `BIOCATALYST_RP_V1_ACCEPTANCE_CASES_2026-09-06.json` fix time-and-evidence triage, inclusive horizons, exclusive lanes, full-set ordering and generation/query/day-bound pagination. PR6712 review 5126025473 accepts the policy at 75a994307998dd8d25ff45dc53193d5c4dc5267c. | This is a deterministic research workflow, not a running classifier or statistical forecast. Probability, return, materiality, sentiment and private portfolio context do not rank V1. Real composer/handler/browser conformance remains R1B work. |

Questions 3/4/5/7/8 retain their explicit later-wave dispositions in section 12.5; the price-vintage, licensing, target, effective-sample, calibration and actual owner/caller evidence must be established before their R2–R3 capabilities or model claims. They are not prerequisites that the first deterministic board already possess those later capabilities. Question 6 remains answered at architectural level by R1A's full/incremental/repair population and accounting requirements; its actual admitted source scope, budget and prospective activation are source-owner execution gates, not an inferred historical pass. Question 10 retains the existing Eval/Fusion prospective-proof boundary, not a new ledger or immediate forecast promotion.

The ten research questions now have either an explicit accepted architectural answer or the previously bounded later-wave owner/evidence condition. This does not independently accept every external observation in section 12: their returned-page, chronology, retrieval and underlying-data-rights limitations remain visible, and review of the research refresh itself is still distinct from the RP/interface reviews. The pending whole-R0 requirements include actual experience reference evidence, canonical workstream reconciliation, final review and current integration checks. No spec is called shipped, no previously refused write is revived, and #6389 remains independent of the R1B milestone.
