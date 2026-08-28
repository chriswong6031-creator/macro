# Preserved archaeology from the superseded 2026-08-17 China masterplan draft

**Provenance:** verbatim section extracts from
`research/CHINA_INTELLIGENCE_INSTITUTIONAL_ALPHA_MASTERPLAN_2026-08-17.md`
(PR #5822 draft, branch `research/china-intelligence-alpha-masterplan-2026-08-17`,
never merged). The draft's ARCHITECTURE is superseded by
`research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md`
(`DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`): its two-axis
"intelligence quality × Prophet timing" frame, single collapsed
`china_intelligence_state.v2` object, 8-shelf naming, and 15-wave roadmap
(old §0, §16, §17, §20, §27, §28) are NOT preserved. What follows is the
repo archaeology and China-specific source detail that remains correct and
load-bearing under the four-model architecture. Claims are as-of 2026-08-17;
re-verify live-state claims before acting on them.

**Reading map (old-draft section → canonical home):**
- §2 estate archaeology → masterplan §1 (current-state truth)
- §3 frozen no-rebuild + PIT/null semantics → masterplan §15 + failure states §9.3
- §4 capability ledger, §5 US-parity map → family design inputs (§6)
- §6 data acquisition detail (exact Tushare tables) → masterplan §8.1
- §11 vertical lobes, §12 physical industry state → Track S design input
- §13 vendor map, §14 priority matrix, §23 procurement → masterplan §8
- §15 feature grammar → family feature design (§6)
- §19 experience detail + failure-state taxonomy → masterplan §9
- §24 not-yet spends → masterplan §8.5 + §15 boundaries
- §25 asymmetry patterns → masterplan §7 motifs
- §26 research evidence anchors → source registry for RIGHTS-0 / Track R

---

## [Old §2–§6] Estate archaeology, frozen laws, capability ledger, US-parity, acquisition detail (old L87–390)

## 2. What actually exists today — correction to the superficial picture

China is **not** a mostly-macro greenfield. The live estate is materially richer.

### Existing live/implemented planes

`engine/china_altdata.py` and `engine/china_extras.py` already include or parse substantial stock-level evidence:

- analyst consensus;
- earnings calendar;
- own-history valuation;
- margin financing / positioning;
- 千股千评 attention and institutional/main-force cost fields;
- attention velocity;
- 龙虎榜 activity, institutional seats and institutional net flows;
- block trades;
- TuShare money flow;
- broker monthly gold picks;
- chip/winner-rate data (`cyq_perf`);
- earnings guidance/preannouncements;
- limit-up pool / seal quality;
- buybacks;
- pledges.

`engine/china_special_situations.py` separately fuses unlocks, preannouncements, inquiry letters, ST state/history, goodwill, buybacks, pledge stress, block anomalies and earnings-calendar context. It is context-only.

`engine/china_intel_hub.py` currently fuses five surfaces per ticker: news, alt data, radar/sector membership, stock-board membership and special situations. It also performs off-desk discovery such as Dragon Tiger first-seat, margin velocity, southbound delta and emerging concepts. Its raw opportunity score is not a lawful Prophet input because it includes board-derived/circular information.

### Existing Prophet seam

`cn_prophet_v4` is already the canonical **Intelligence-ranked Prophet** seam. The design is “Rank by interestingness. Gate by entry.” Within existing v3 lifecycle lanes it orders by `intel_interest_score`, then the unchanged Prophet score, then ticker; v3 fillability, freshness, liquidity, extension and admission logic remain intact.

`engine/china_board_rank.py` is the sole board authority. `engine/china_intel_interest.py` exists specifically to re-derive a board-independent Intelligence interest value. Recent work also made Intelligence ordering coverage-atomic: a partial intelligence board must fall back rather than silently mix covered and uncovered names.

This is the correct seam to preserve.

### What the current score already taught us

The current China alt-data experiments are a warning against intuitive “smart money” labels:

- raw positive Dragon Tiger activity was negatively associated with forward excess returns in one current study;
- raw positive block premium was also negative;
- deep-discount blocks were materially different and showed positive forward behavior in the studied sample;
- institutional-seat Dragon Tiger activity was directionally better but weak/statistically inconclusive in the existing sample.

Therefore the new architecture must **model event/actor context**, not award positive points because a feed sounds sophisticated.

### Current product gap

The public China Intelligence experience remains primarily a five-surface, context-only command deck with a materially narrower command universe than the underlying alt-data engine can cover. The live alt-data page still exposes a small set of core feeds while the backend has more evidence.

The next product step is therefore not “another page.” It is a **full-universe company intelligence dossier and evidence projection** that explains every family, source, timestamp, freshness state, contradiction and authority level.

---

## 3. Frozen architecture / no-rebuild boundaries

The following systems are canonical and should be extended, not replaced.

### 3.1 Listing identity

Use the existing DataOS canonical listing identity (`CN-XSHG-*`, `CN-XSHE-*`, etc.). A ticker string is never identity. Parent/subsidiary/corporate entities should resolve to canonical listing IDs through the existing identity contract.

### 3.2 Point-in-time clocks

Use the existing DataOS temporal contract and fail closed. `known_at` must be derived from actual publication/first-seen/ingestion evidence; do not back-stamp a current snapshot into history.

Classify every dataset before use:

- append-only event with reliable publication/known time;
- event/session history without explicit known_at;
- revisable historical series;
- snapshot-only data requiring prospective first-seen accrual;
- model-generated intelligence with source lineage.

### 3.3 Null semantics

Keep the existing explicit missing-reason model. Zero is data; absence is not zero. Distinguish no event, no coverage, vendor failure, not yet accrued, stale, rights-suppressed and unresolved identity.

### 3.4 Dataset contracts

Register every new source in the canonical DataOS registry with:

- owner;
- primary key;
- listing/entity identity semantics;
- event/published/known/ingested timestamps;
- correction policy;
- expected freshness;
- coverage definition;
- rights/licensing class;
- producer and consumers;
- source-health contract.

### 3.5 Entity/theme/supply-chain graph

Extend the existing **Global Market Intelligence (GMI)** bitemporal graph. Do **not** create a second China company/theme/supply-chain graph. Add China-specific nodes/edges/evidence such as `VISITED_BY`, `HELD_BY`, `AWARDED_TO`, `SUPPLIES`, `BUYS_FROM`, `APPROVED_FOR`, `PROJECT_OF`, `MANAGED_BY`, `ACTED_BY` as appropriate, preserving evidence spans and bitemporal validity.

### 3.6 Prophet authority

Do not alter the canonical China Board scorer. New intelligence can enter Prophet only through the established board-independent interest seam **after** it earns authority. No direct feed may silently modify Prophet score, lane, admission, sizing or gate state.

### 3.7 Terminal kills

Do not rebuild killed China deterministic conjunctions or revive lower bars from the prior CN limit-alpha program. The precursor candidate family was exhausted and explicitly not promoted. New work must introduce **new independent information carriers**, not stack the same tape/theme/limit mechanics harder.

---

## 4. Capability ledger — current state versus target

| Capability | Current state | Decision |
|---|---|---|
| DataOS China identity/time/null/contracts | `PROVEN_LIVE` | Freeze and extend |
| GMI entity/theme graph spine | `PROVEN_LIVE` substrate | Extend; never give direct trade authority |
| China alt-data collection/product | `PROVEN_LIVE` | Keep; separate descriptive feeds from validated families |
| China alt-data current convergence formula | `PARTIAL` | Treat weights as context until family-level incremental validation |
| China Special Situations | `PROVEN_LIVE` context | Keep context-only; deepen event bodies/ontology |
| China Flow Velocity | `PROVEN_LIVE` context | Preserve as independent flow desk |
| Narrative Radar | `PROVEN_LIVE` theme/price context | Preserve; do not confuse theme ignition with company quality |
| China Mechanics | `PROVEN_LIVE` market/timing context | Preserve; no quality authority |
| Prophet v4 Intelligence ordering seam | `PROVEN_LIVE` operational | `BUILT_NOT_PROVEN` predictive authority; continue shadow outcomes |
| Investor Q&A raw accrual | `BUILT_NOT_PROVEN` | Upgrade semantics; preserve receipts |
| Sell-side revision accrual | `BUILT_NOT_PROVEN` | Deepen expectation-delta model |
| Holder-count accrual | `BUILT_NOT_PROVEN` | Validate dispersion/crowding use |
| Guidance/preannouncement tape | `BUILT_NOT_PROVEN` | High-quality fundamental event family candidate |
| Broker-gold/margin/block/buyback prospective tapes | `BUILT_NOT_PROVEN` | Continue accrual; no authority by intuition |
| Full-universe stock dossier | `PARTIAL` | Build as canonical user/machine projection |
| Full announcement event ontology | `NOT_BUILT` at required breadth | Build from one corpus, many event families |
| Institutional research/site visits | `NOT_BUILT` | **P0** |
| Public-fund portfolio ownership | `NOT_BUILT` | **P0** |
| Top-holder / shareholder-management delta graph | `NOT_BUILT` | **P0** |
| Named hot-money actor history | `NOT_BUILT` | **P0/P1**, descriptive first |
| Government/public-resource demand graph | `NOT_BUILT` | **P1**, high expected value |
| SOE procurement graph | `NOT_BUILT` | **P1**, sector-specialized |
| Capacity/project approval graph | `NOT_BUILT` | **P1** |
| Biopharma commercialization lobe | `NOT_BUILT` | **P1** |
| EV/auto regulatory/product lobe | `NOT_BUILT` | **P1** |
| Grid/energy procurement/project lobe | `NOT_BUILT` | **P1** |
| AI/software/game regulatory lobe | `NOT_BUILT` | **P1** |
| Semiconductor/advanced-manufacturing lobe | `NOT_BUILT` | **P1/P2** |
| Physical commodity/customs state | `PARTIAL` macro-level / disconnected | **P2** company mapping |
| Corporate entity resolver | `NOT_BUILT` as production-grade PRC resolver | Buy/bake-off; do not hand-maintain |
| Rights-safe online sales/app/jobs/patents | `NOT_BUILT` as canonical family | **P2** vendor bake-off |
| Daily directional per-stock Northbound accumulation | `REJECTED_BY_DESIGN` | Current public disclosure no longer supports it |
| Unlicensed social-platform scraping as core signal | `REJECTED_BY_DESIGN` | Rights/ToS/identity noise too high |
| Exact-limit/auction/minute disconnected planes | `DARK_OR_DISCONNECTED` | Do not widen this program into rebuilding them |
| Naive existing-factor conjunction stacking | `REJECTED_BY_DESIGN` | Terminal kill unless Chairman explicitly reopens |

---

## 5. US parity: copy the job, not the dataset

The mature US side provides several useful jobs that China should reproduce with China-native sources.

| US intelligence job | US mechanism | China-native translation |
|---|---|---|
| Detect informed/committed insiders | Form 4 / insider transactions | shareholder/director/executive increases/decreases, buybacks, pledges, unlocks, control changes |
| Track institutional conviction | 13F, fund ownership | public-fund portfolios, top float holders, strategic/state fund changes, visiting-institution follow-through |
| Detect unusual political/public demand | Congress/government activity | state policy + central/local procurement + SOE tender/award/contract |
| Detect corporate catalysts | 8-K, filings, M&A, FDA/trial | full CN announcements + exchange inquiries + CDE/NMPA/NHSA + MIIT/NPPA/CAC + project approvals |
| Detect expectation changes | earnings calls, analyst revisions | brokerage reports/revisions + guidance + Q&A response semantics + institutional-visit content |
| Detect market actor concentration | options/flows/activists | LHB named actors/institutional seats + blocks + margin + fund changes |
| Build cross-source convergence | event families + provenance | independent China evidence families with PIT receipts |
| Time an idea separately | technical/entry engines | Prophet remains independent timing/admission authority |

China can exceed US parity because its **policy, project-approval, SOE-procurement and product-admission clocks** can reveal operational change before normal financial reporting.

---

## 6. Data acquisition strategy

### Principle

Buy/activate data when a rights-safe normalized feed is cheap relative to engineering/identity debt. Build when the source is an official public corpus with stable semantics and the differentiation is in our entity linking/event modeling rather than access itself.

### 6.1 Activate/buy immediately — horizontal P0

#### A. Institutional research/site visits (`stk_surv` or equivalent)

**Why:** this is one of the strongest China-native candidates. Peer-reviewed China research finds abnormally frequent corporate/site visits contain information about future returns and fundamentals; effects are stronger in information-poor/manufacturing firms and for group/mutual-fund visits. This is unusually aligned with the Intelligence-quality thesis.

**Raw fields to preserve:** company/listing, visit date, publication date, institution name/type, visitors, mode/location, receiving executives, topic/content when available, source document.

**Derived features:**

- abnormal visit frequency vs company baseline;
- unique-institution breadth;
- high-quality institutional breadth;
- first-time visitor count;
- repeat-visitor persistence;
- group vs solo visit;
- visit acceleration 7/30/90d;
- visit→research-report follow-through;
- visit→fund-holding follow-through;
- topic novelty/materiality;
- management-seniority exposure;
- information scarcity interaction;
- post-visit price absorption/crowding.

**Authority:** descriptive immediately; shadow family after PIT history/reconstruction review; no positive score because “institution visited.”

#### B. Public-fund portfolio holdings (`fund_portfolio` or licensed equivalent)

Build a China 13F-like ownership plane, but with correct disclosure lags and paired-report handling.

Features:

- new position / exit / increase / decrease;
- active weight vs fund's own history;
- number of independent funds adding;
- manager/fund style consistency;
- concentration and crowding;
- ownership broadening/narrowing;
- first appearance among top holdings;
- quarter-over-quarter manager consensus;
- visiting institutions that subsequently add exposure;
- sector-normalized ownership change.

Do not fabricate exits when a comparison filing is missing/pending.

#### C. Shareholder/management alignment (`stk_holdertrade`, top holders, float holders)

Features:

- executive/director/major-holder net accumulation;
- transaction size vs float/market cap/ownership;
- price paid vs current;
- repeat purchase/sale streak;
- controller vs employee vs passive holder distinction;
- top-holder turnover;
- strategic/state-linked holder appearance;
- alignment composite with buyback/pledge/unlock context.

#### D. Named hot-money actors (`hm_list` + actor detail)

Do **not** create “famous seat = bullish.” Create actor histories:

- canonical actor identity → broker seats across time;
- sector/theme affinity;
- entry concentration;
- co-actor graph;
- typical holding horizon;
- post-entry MFE/MAE and forward-excess distribution;
- regime/board dependence;
- repeat-name behavior;
- wash/chase profile.

The output should initially be **actor-context**, not a direction score.

#### E. Full company announcement corpus (`anns_d` or equivalent)

One normalized corpus should replace dozens of brittle event-specific scrapers where possible. Preserve title, full text/PDF, publication/ingestion clocks and source URL/file hash.

This becomes the substrate for the Corporate Event Ontology in §8.

#### F. Licensed Q&A and full research reports

The repo is already accruing exchange Q&A and report revisions. Harden rights, historical coverage and document bodies rather than creating a second collector.

### 6.2 Buy one corporate entity resolver

Run a Tianyancha versus Qichacha (or equivalent) bake-off. Required capabilities:

- legal entity ↔ listed parent/subsidiary;
- historical names;
- ownership/control;
- executives;
- customers/suppliers where licensed;
- tenders/land/import-export/business qualifications when useful;
- legal/risk state.

This resolver should **feed canonical GMI/DataOS identity**, not become a parallel entity system.

### 6.3 Build on official public sources — high-value P1

#### Government procurement / public resources

Build from official national/provincial procurement and the National Public Resources Trading Platform where lawful/stable. Model the lifecycle:

`procurement intention → tender → candidates → award → contract → change/cancellation`.

Store buyer, agency, supplier, listed-parent mapping, category/theme, amount, units, contract period, geography, procurement method, candidate rank, repeat buyer, award share, source and timestamps.

#### SOE procurement

Prioritize high-capex/high-tech SOE buyers with structured portals: power grids, telecom operators, rail/transit and other publicly accessible procurement ecosystems. The signal is not “won a tender”; it is **new demand, repeat wins, win-share acceleration, product-mix change, bid-price economics and backlog visibility**.

#### Project/capacity approvals

Build a capacity graph from national/local investment-project approval, environmental review/acceptance, energy-project registration and other official project lifecycle sources. Normalize project owner/subsidiary→listed parent, project code, location, product, capacity, capex, milestone, expected commissioning and first-seen date.

### 6.4 Vendor bake-off — P2, after the core is live

Do not attempt terminal-table parity. Evaluate Wind, iFinD, DataYes and similar vendors for specific **rights-heavy data families**:

- online sales / SKU / e-commerce;
- app/mobile usage;
- recruitment/jobs;
- patents/R&D;
- land auctions;
- industry-chain mappings;
- high-frequency operational datasets.

Purchase only if the family offers a stable PIT clock, broad enough history, auditable correction behavior, legal downstream usage, and incremental value beyond our public-source families.

---

## [Old §11–§15] Vertical lobes, physical industry state, vendor map, priority matrix, feature grammar (old L617–760)

## 11. Vertical intelligence lobes

A sector gets a lobe only when it possesses a **distinct, earlier operational/regulatory clock** than ordinary earnings. Each lobe must share DataOS/GMI/event substrates and ship one independently useful end-to-end capability.

### 11.1 China BioPharma Intelligence

**Sources:** CDE/NMPA drug review/approval, clinical-trial registry, NHSA reimbursement and national volume procurement, provincial/hospital procurement, patents/competition, company disclosures.

**Events/features:** trial start/enrollment/status/phase, acceptance/priority/breakthrough review, approval, supplementary application, indication expansion, competing molecule progression, VBP/NRDL eligibility/bid/result/price/volume, hospital demand, patent expiry/challenge.

**Why asymmetric:** regulatory/commercial milestones can precede financial recognition by months.

### 11.2 Grid / Power / Renewable Intelligence

**Sources:** NEA project registrations, NDRC/MEE approvals, State Grid/China Southern Grid and related SOE procurement, equipment awards, renewable project construction, company disclosures.

**Features:** project additions, grid capex category demand, vendor award share, repeat wins, transformer/cable/storage/PCS/etc product mix, tender pricing, commissioning pipeline.

### 11.3 EV / Auto Intelligence

**Sources:** MIIT vehicle/product admission and pre-publication/candidate lists, NEV tax/exemption lists, company product filings, charging/battery procurement, relevant customs/industry data.

**Features:** model cadence, new product approval, manufacturer/product breadth, supplier relationships, battery chemistry/platform shift, charging infrastructure demand, export/product mix.

### 11.4 AI / Software / Games Intelligence

**Sources:** CAC generative-AI/algorithm/deep-synthesis filings, NPPA game approvals, government/SOE digital procurement, software/telecom qualifications, app/mobile usage only if licensed.

**Features:** product commercialization milestone, filing/approval velocity, licensed titles, publisher/operator mapping, enterprise/government adoption, procurement wins, active-use trajectory where licensed.

### 11.5 Semiconductor / Advanced Manufacturing Intelligence

**Sources:** project/EIA approvals, fab/equipment capacity projects, customs, patents, government/SOE procurement, company disclosures, industrial policy documents as context.

**Features:** new fabs/lines, localization wins, equipment/material qualification, import substitution exposure, capacity commissioning, upstream/downstream demand, competitor capacity.

### 11.6 Materials / Mining / Chemicals Intelligence

**Sources:** mine/mineral rights and public resources, project/EIA approvals, SHFE futures/warehouse receipts, customs, capacity disclosures.

**Features:** mine/project commissioning, output-capacity change, inventory/warehouse state, import/export shocks, product spread, competitor capacity, environmental shutdown/restart.

### 11.7 Property / Infrastructure Intelligence

**Sources:** land auctions, public-resource transactions, construction/project approvals, local government procurement, financing/credit context.

Use primarily as company/sector operating context and risk/falsifier until validated; avoid rebuilding a macro regime system inside Intelligence.

---

## 12. Physical industry state — map facts to companies, do not pretend macro is stock alpha

High-value public sources include exchange warehouse receipts/inventory/member positions, customs import/export series and official production/project data.

Their role is to create **industry state vectors**:

- inventory surprise;
- warehouse-receipt change;
- futures curve/carry;
- producer/importer/exporter concentration where observable;
- commodity/product import-export acceleration;
- regional/project capacity.

GMI then maps industry states to companies through supply-chain/exposure relationships. Direct stock-scoring authority requires separate validation.

---

## 13. Vendor/competitor map — what to learn and what not to copy

### Wind

Wind's current product surface demonstrates that Chinese institutional data products package far more than prices/fundamentals: enterprise databases, people/executives, policy/regulation, online sales, land auctions, carbon and industry data, plus database/API delivery. The lesson is not to reproduce Wind table-for-table. Use it as evidence that these operational categories are institutionally useful and selectively license those that are rights-heavy or difficult to normalize.

### iFinD

iFinD exposes broad report-table APIs, macro/high-frequency datasets, industry-chain information, research and investor-interaction surfaces. It also has alternative-data partnerships around mobile/app and geospatial/night-light type data. Again, buy only the specific family that clears PIT/rights/incremental-value gates.

### DataYes

DataYes is particularly relevant as a PIT/quant research comparison: public descriptions emphasize point-in-time A-share data, analyst/research features, patents, hiring and AI/factor datasets. It is a candidate vendor for a controlled bake-off in patents/jobs/expectations rather than a replacement for MastermindX modeling.

### Eastmoney Choice

Choice demonstrates integrated financial/industry/research workflows and industry-chain mapping. Eastmoney itself also remains useful as a broad public-market/disclosure/navigation ecosystem, but public page behavior and undocumented endpoints should not become a rights-fragile canonical plane where an official/licensed alternative exists.

### JoinQuant / BigQuant

These are useful workflow references: broad data → factor research → model/backtest → trading simulation. The competitive lesson is that MastermindX must close the same research loop, but its differentiation should be **event provenance + China-specific evidence graph + validated Prophet interaction**, not generic factor count.

---

## 14. Source acquisition priority matrix

| Priority | Family/source | Access strategy | PIT/history | Expected value | Main risk |
|---|---|---|---|---|---|
| P0 | Institutional visits | TuShare/licensed | Historical event dates; verify publication clock | **Very high** | survivorship/publication timing |
| P0 | Public-fund portfolios | TuShare/licensed | Quarterly lagged filings | **Very high** | false exits / disclosure lag |
| P0 | Holder/director trades | TuShare/exchange | Event-based | **High** | transaction motive heterogeneity |
| P0 | Top float holders | TuShare/licensed | Quarterly | **High** | snapshot/report lag |
| P0 | Full announcements | TuShare/licensed/exchange docs | >10y possible | **Very high substrate** | PDF parsing/corrections |
| P0 | Q&A | existing accrual + licensed history | Prospective + historical where lawful | **High** | text extraction/boilerplate |
| P0 | Sell-side research | existing revisions + full reports | report-time | **High** | vendor rights/revisions |
| P0/P1 | Named hot-money actor detail | TuShare/licensed | ~recent multi-year | **Research-high** | actor mappings/selection bias |
| P1 | National procurement | official interfaces/feeds | Event lifecycle | **Very high** | entity resolution |
| P1 | Public-resource transactions | official platform | Event lifecycle | **High** | heterogeneous schemas |
| P1 | Grid/telco SOE procurement | official portals | Event lifecycle | **Very high in covered sectors** | portal variability |
| P1 | Investment/project approvals | official NDRC/local | Event lifecycle | **Very high for industrials** | subsidiary/entity mapping |
| P1 | Environmental approvals | official MEE/local | Event lifecycle | **High** | OCR/document heterogeneity |
| P1 | MIIT vehicle admission | official | Monthly/batch | **High auto-specific** | supplier attribution |
| P1 | CDE/NMPA/NHSA/trials | official | Event lifecycle | **Very high biopharma** | complex indication/entity mapping |
| P1 | NPPA/CAC product filings | official | Event lifecycle | **High software/games** | commercialization vs filing gap |
| P2 | SHFE/futures physical state | official/TuShare | Daily/weekly | **High industry context** | stock mapping/cyclicality |
| P2 | Customs | official | Monthly | **High industry context** | HS-code mapping |
| P2 | Patents | CNIPA/vendor | Event/PIT | **Medium-high** | value heterogeneity, lags |
| P2 | Hiring | vendor | PIT essential | **Medium-high** | vendor history/coverage |
| P2 | Online sales | Wind/other licensed | Daily/weekly/monthly | **Potentially high consumer** | cost/coverage/brand mapping |
| P2 | App/mobile | iFinD/vendor | Daily/monthly | **Potentially high digital** | panel bias/rights |
| P3 | Satellite/night lights/footfall | licensed only | vendor-dependent | **Unknown until test** | high cost, mapping, leakage |
| Reject | daily per-stock Northbound direction | unavailable as prior public feed after 2024 rule change | — | — | invalid premise |
| Reject | unlicensed social scraping | do not use as canonical source | — | low reliability | ToS/rights/manipulation |

---

## 15. China Intelligence feature grammar

Every family should express the same **information-delta grammar** so models can combine evidence without pretending unlike sources are comparable raw counts.

For each family emit:

1. **Surprise** — deviation from company/peer/consensus baseline.
2. **Acceleration** — change in event/flow/attention rate.
3. **Breadth** — number of independent actors/sources supporting the change.
4. **Quality** — source/actor reliability and economic relevance.
5. **Novelty** — new relationship/product/project/theme versus repeated information.
6. **Materiality** — value/capacity/volume normalized by company economics.
7. **Time-to-impact** — expected operational/financial horizon.
8. **Persistence** — one-off versus repeated behavior.
9. **Contradiction** — evidence that weakens or falsifies the interpretation.
10. **Absorption** — how much the price/theme/crowding carrier has already moved, kept independent of Prophet authority.

This supports a better definition of asymmetry:

> **Independent high-materiality evidence is converging while price absorption remains incomplete and Prophet's timing state is favorable.**


---

## [Old §19] Experience architecture detail + failure-state taxonomy (old L918–989)

## 19. Experience architecture — what the user should actually see

### 19.1 Full-universe “Why this name now?” dossier

Every Prophet/Intelligence candidate should open into a single company intelligence dossier:

**Hero**
- listing/company;
- Intelligence interest percentile/version;
- Prophet lane/timing state;
- evidence freshness/coverage;
- “early / building / crowded / contradicted” state.

**Why now**
- 3–7 highest-materiality independent deltas, each with date/source/receipt.

**Who is acting**
- institutional visits;
- fund ownership changes;
- management/shareholder alignment;
- named actor context.

**What changed operationally**
- awards/contracts;
- approvals/capacity;
- product/regulatory milestones;
- guidance/expectation deltas.

**What could be wrong**
- contradictions;
- unlock/pledge/refinancing/regulatory risk;
- stale/missing evidence;
- crowding/absorption.

**Timeline**
- bitemporal evidence timeline with corrections.

**Prophet timing**
- explicitly separate read-only timing panel; never let UX blur “interesting company” with “good entry now.”

### 19.2 Opportunity shelf

The China Intelligence Hub should graduate from a narrow context deck into a full-universe shelf with explainable rank reasons:

- `New Information`;
- `Institutional Discovery`;
- `Demand/Order Acceleration`;
- `Capacity/Commercialization`;
- `Expectation Inflection`;
- `Alignment`;
- `Contradiction/Risk`;
- `Prophet-ready`.

These are views over one canonical evidence system, not separate score engines.

### 19.3 Failure states must be visible

Every page/object distinguishes:

- no event;
- source not covering this company;
- source stale;
- source failed;
- rights-suppressed;
- identity unresolved;
- prospective-only/not historically replayable;
- model/extraction low-confidence;
- evidence contradicted;
- Intelligence ordering fallback active.

A quiet page must never be indistinguishable from a broken collector.


---

## [Old §23–§26] Procurement recommendation, not-yet spends, asymmetry patterns, evidence anchors (old L1142–1243)

## 23. Procurement recommendation — what to buy first

If budget is available immediately, the highest-leverage purchase/activation order is:

1. **Institutional site visits** — first P0 because of China-specific empirical evidence and direct fit with information-discovery thesis.
2. **Public-fund portfolios** — China institutional ownership/history.
3. **Shareholder/executive trades + top float holders** — alignment/ownership delta.
4. **Full company announcements** — substrate for the event ontology.
5. **Named hot-money actor list/detail** — enrich the existing Dragon Tiger plane.
6. **Licensed exchange Q&A + broker-report history/body** — harden existing accrual and enable semantic features.
7. **One PRC corporate entity resolver** — Tianyancha/Qichacha bake-off.

Then build official government/SOE/project/regulatory lobes before spending heavily on satellite/social/consumer-exhaust data.

---

## 24. What not to spend time or money on yet

### No daily per-stock Northbound accumulator

Public Stock Connect disclosure changed in August 2024; the old daily per-name directional holding/buy/sell premise no longer exists in the same form. Use current public data honestly: aggregate turnover/top-active activity and quarterly individual holdings where applicable.

### No giant social-sentiment scraper

Retail narrative can matter, but unlicensed Xueqiu/Guba/Weibo/Douyin/Xiaohongshu scraping creates rights, manipulation, identity and survivorship debt. Existing Narrative Radar already covers theme ignition from market evidence. Only add a social/digital family through a licensed stable provider and only if it adds incremental value.

### No opaque “institutional quality = 20%, policy = 15% …” formula

Those weights should be learned/validated, not selected aesthetically.

### No large end-to-end black-box model on day one

A black box can hide duplicated carriers and leakage. The family architecture must first establish which source carries independent information.

### No duplicate graph/data platform

DataOS + GMI + existing collection/storage + `china_intel_interest` + `china_board_rank` are the canonical spine.

---

## 25. Expected asymmetry patterns to research

These are **hypotheses**, not trade rules:

### Pattern A — institutional discovery before ownership

`abnormal institutional visits ↑ → report revisions ↑ → fund ownership broadens later`, with limited price absorption.

### Pattern B — public demand before earnings

`government/SOE demand intention ↑ → company award → signed contract`, material relative to revenue, before consensus fully revises.

### Pattern C — capacity commercialization

`project/EIA/product approval → equipment procurement/commissioning → production`, with company exposure verified through entity/supply-chain graph.

### Pattern D — expectation repair after pain

Prophet identifies a washed-out/eligible name while `guidance/revisions/Q&A specificity/institutional attention` turn positive before trend fully repairs.

### Pattern E — quality versus chase separation

Two stocks have similar Prophet setups/theme heat; one has institutional/operational evidence while the other is driven primarily by hot-money/attention/late relay. Intelligence should rank the first higher *if prospective evidence proves this separation*.

### Pattern F — contradiction-aware demotion

Strong timing but capacity delay, repeated management non-answer, holder selling, unlock pressure or procurement cancellation. Intelligence should be able to demote an otherwise attractive setup once the falsifier family earns authority.

---

## 26. Research evidence anchors

### Primary/official source families reviewed

- TuShare API/catalog and special-data offerings: Dragon Tiger/institutional seats, margin, blocks, buybacks, pledges, holder trades, fund portfolios, top holders, announcements, Q&A, policy/research libraries, futures position/warehouse data.
- HKEX/SSE/SZSE Stock Connect disclosure rules/current data pages.
- China Government Procurement official interface specifications and notices.
- National Public Resources Trading Platform.
- National investment-project platform / NDRC project-code lifecycle.
- Ministry of Ecology and Environment project/EIA public notices.
- National Energy Administration project data.
- MIIT vehicle/product admission and NEV lists.
- CDE/NMPA review/trial sources and NHSA procurement/reimbursement sources.
- NPPA game approval lists.
- CAC generative-AI/algorithm/deep-synthesis filing/registration notices.
- SHFE market/warehouse/position data and China Customs trade data.
- CNIPA public patent data.
- major SOE procurement portals (including grid/telecom examples).

### Institutional product/vendor scan

- Wind Financial Terminal/WDS/API/enterprise/online-sales/policy/land/carbon/industry datasets.
- iFinD API/terminal/industry-chain/alternative-data surfaces.
- DataYes PIT/factor/research/patent/hiring products.
- Eastmoney Choice integrated financial/research/industry workflows.
- JoinQuant and BigQuant data→factor→research/backtest workflows.
- Tianyancha/Qichacha-style enterprise entity-resolution APIs.

### Academic evidence reviewed

China-specific literature on corporate/site visits was especially relevant: peer-reviewed work finds site-visit activity is informative for future returns/fundamentals and is stronger for some higher-information-content visit types. Literature on exchange investor Q&A also supports treating response timing/specificity/content as potentially informative, but those features still require MastermindX PIT replay and prospective validation before any ranking authority.

