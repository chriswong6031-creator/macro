# SNI-1 Alibaba + Tencent Economic Ontology v0

**Date:** 2026-08-28  
**Authority:** descriptive source/measurement architecture only; no directional, valuation, forecast, rank, gate, size, or trade authority  
**Parent design:** `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md`  

This ontology defines the company-specific facts, series, event families, and version boundaries required for the first two Single-Name Intelligence reference organisms.

It is not a company thesis. It is the grammar that allows future facts, comparisons, research questions, and forecasts to refer to the same thing over time.

---

## 1. Metric contract

Every registered metric has this shape:

```text
metric_key
issuer_id
ontology_version
display_name_en
display_name_zh
description
scope: issuer | segment | product | geography | counter | security
basis: gaap_ifrs | non_gaap | operating_metric | management_measure | derived
unit
currency
period_type: point_in_time | quarter | half_year | fiscal_year | event
frequency
source_owner
source_locator
source_definition_text
known_at
valid_from
valid_to
comparable_series[]
non_comparable_reasons[]
derivation
coverage_state
authority
```

### 1.1 Laws

1. A metric is not identified only by its screen label.
2. A renamed or redefined metric receives a new ontology version or explicit mapping.
3. Management measures and IFRS/GAAP measures remain distinct.
4. “Not reported” is a value state, not zero and not prior-period carry-forward.
5. Currency and per-share unit travel with every observation.
6. A derived metric retains every component and formula.
7. A historical series may be joined only when the issuer supplied a recast or the mapping is explicitly graded `comparable`.
8. Model-generated interpretation never becomes a metric observation.

---

# Part A — Alibaba Group

## 2. Identity

```text
issuer_id: cik:0001577552
legal_name: Alibaba Group Holding Limited
reporting_currency: CNY/RMB
fiscal_year_end: March 31
```

Economic-security graph:

```text
alibaba_ordinary_share
  ├─ XHKG 9988 / HKD counter
  └─ XHKG 89988 / CNY counter

alibaba_ads
  └─ XNYS BABA / USD counter

conversion:
  1 BABA ADS = 8 Alibaba ordinary shares
  bidirectionally fungible, with operational/market frictions outside v0 basis arithmetic
```

Official identity sources:

- Alibaba Investor FAQ and IR;
- SEC CIK 0001577552;
- HKEX/issuer announcements.

---

## 3. Alibaba segment ontology versions

### 3.1 `alibaba.segment.v2026q2`

Effective with the June-quarter 2026 result presentation unless a later official filing gives a different effective/recast boundary.

| Segment key | Official segment | Required substructure |
|---|---|---|
| `alibaba_ecommerce_group` | Alibaba E-commerce Group | China E-commerce, China Quick Commerce, International E-commerce, Global Wholesale |
| `ai_cloud_compute_services` | AI Cloud and Compute Services | cloud/compute revenue, AI-related product revenue where reported, EBITA, infrastructure/capex context |
| `ai_labs_applications` | AI Labs and Applications | revenue, EBITA/loss, model/application adoption observations |
| `all_others` | All Others | reported residual; do not infer homogeneous economics |

### 3.2 Historical segment versions

Prior structures include, among others, Taobao and Tmall Group, Cloud Intelligence Group, International Digital Commerce, Local Services, Cainiao, Digital Media and Entertainment, and All Others.

SNI must not automatically concatenate them with `v2026q2`.

Required mapping states:

```text
issuer_recast_exact
issuer_mapping_partial
derived_mapping_reviewed
not_comparable
unknown
```

The first reference twin may display the current structure and named prior observations, but a historical chart across the reorganization remains absent until a lawful mapping is registered.

---

## 4. Alibaba metric registry v0

### 4.1 Group financials

| Metric key | Definition/basis | Unit | Notes |
|---|---|---|---|
| `ali.group.revenue` | Reported group revenue | RMB million | IFRS/issuer reported |
| `ali.group.income_from_operations` | Reported operating income | RMB million | Keep distinct from adjusted EBITA |
| `ali.group.net_income` | Reported net income | RMB million | Basis must follow source |
| `ali.group.non_gaap_net_income` | Issuer non-GAAP net income | RMB million | Preserve reconciliation/source |
| `ali.group.free_cash_flow` | Issuer-defined free cash flow | RMB million | Definition version required |
| `ali.group.capex` | Capital expenditure as reported/derived from cash-flow disclosure | RMB million | Infrastructure use must be separately sourced |
| `ali.group.cash_liquid_investments` | Cash, equivalents and liquid investments per issuer basis | RMB million | Point-in-time |
| `ali.group.ordinary_shares_outstanding` | Ordinary shares outstanding | million shares | Treasury/issued basis explicit |
| `ali.group.ads_equivalent` | Ordinary shares / 8 | million ADS equivalent | Derived; never replace original share count |

### 4.2 Alibaba E-commerce Group

| Metric key | Scope | Definition/basis |
|---|---|---|
| `ali.ecom.segment_revenue` | Segment | Current official segment revenue |
| `ali.ecom.adjusted_ebita` | Segment | Issuer non-GAAP segment EBITA |
| `ali.ecom.china_ecommerce_revenue` | Subsegment | Current reporting definition |
| `ali.ecom.customer_management_revenue` | Operating revenue family | CMR under issuer definition/version |
| `ali.ecom.china_quick_commerce_revenue` | Subsegment | Revenue under current segment structure |
| `ali.ecom.international_ecommerce_revenue` | Subsegment | Current definition |
| `ali.ecom.global_wholesale_revenue` | Subsegment | Current definition |
| `ali.ecom.88vip_members` | Operating metric | Approximate or exact member count as issuer states |
| `ali.ecom.order_volume` | Operating metric | Only when issuer reports a precise definition |
| `ali.ecom.monetization_rate` | Derived/management | Requires numerator, denominator and definition; no inference from CMR alone |

### 4.3 AI Cloud and Compute Services

| Metric key | Definition/basis |
|---|---|
| `ali.cloud.segment_revenue` | Current segment revenue |
| `ali.cloud.external_revenue` | External-customer revenue only when explicitly reported |
| `ali.cloud.ai_related_product_revenue` | Issuer-defined AI-related product revenue |
| `ali.cloud.ai_product_growth_streak` | Count of consecutive quarters satisfying issuer-stated growth condition; derived only from registered observations |
| `ali.cloud.adjusted_ebita` | Issuer segment non-GAAP measure |
| `ali.cloud.adjusted_ebita_margin` | Adjusted EBITA / segment revenue at matched period/basis |
| `ali.cloud.model_application_arr` | Issuer management ARR measure, separate from recognized revenue |
| `ali.cloud.compute_capacity_investment` | Source-backed capital/infrastructure observation; not automatically equal to total group capex |
| `ali.cloud.external_customer_count` | Only when source defines population/period |

### 4.4 AI Labs and Applications

| Metric key | Definition/basis |
|---|---|
| `ali.ai_apps.segment_revenue` | Current segment revenue |
| `ali.ai_apps.adjusted_ebita` | Current segment EBITA/loss |
| `ali.ai_apps.qwen_or_app_mau` | Product/application active users only at issuer definition |
| `ali.ai_apps.model_downloads` | Source-specific ecosystem observation; not revenue/adoption equivalence |
| `ali.ai_apps.enterprise_adoption` | Named customer/industry observations; not a synthetic score |

### 4.5 Capital allocation and supply

| Metric key | Definition/basis |
|---|---|
| `ali.capital.repurchased_ordinary_shares` | Shares repurchased in period/event |
| `ali.capital.repurchased_ads_equivalent` | Ordinary shares / 8, derived |
| `ali.capital.repurchase_cash` | Cash paid, source currency |
| `ali.capital.new_ordinary_shares_issued` | New ordinary shares issued by event |
| `ali.capital.placement_gross_proceeds` | Gross proceeds, source currency |
| `ali.capital.placement_net_proceeds` | Net proceeds if reported |
| `ali.capital.use_of_proceeds_compute` | Stated amount/percentage for computing infrastructure |
| `ali.capital.use_of_proceeds_datacentres` | Stated amount/percentage for data-centre/cloud infrastructure |
| `ali.capital.convertible_principal` | Convertible note principal at issuance |
| `ali.capital.exchangeable_principal` | Exchangeable bond principal at issuance |

---

## 5. Alibaba June-quarter 2026 reference facts

These facts seed the ontology and the real-payload acceptance fixture. They are not a permanent hard-coded company state.

Source: official Alibaba June-quarter 2026 result PDF/IR publication dated 2026-08-20.

| Observation | Current source value |
|---|---:|
| Group revenue | RMB268,953 million, +9% YoY |
| Alibaba E-commerce Group revenue | RMB205,862 million, +4% |
| AI Cloud and Compute Services revenue | RMB48,437 million, +45% |
| AI Labs and Applications revenue | RMB3,338 million, +16% |
| All Others revenue | RMB28,803 million, +1% |
| E-commerce adjusted EBITA | RMB39,749 million, -1% |
| AI Cloud/Compute adjusted EBITA | RMB5,628 million, +133% |
| AI Labs/Applications adjusted EBITA | loss RMB13,861 million |
| All Others adjusted EBITA | loss RMB3,343 million |
| China CMR | -7% reported; issuer described like-for-like +1% excluding a contra-revenue program effect |
| China Quick Commerce revenue | +45% |
| 88VIP members | approximately 64 million |
| AI-related product revenue | RMB12,376 million; issuer described twelfth consecutive quarter of triple-digit growth |
| Capital expenditure | RMB67,678 million, +75% |
| Cash and liquid investments | RMB474,505 million |
| Repurchases | 13.4 million ordinary shares, approximately 1.7 million ADSs, US$162 million |

Required interpretation boundaries:

- CMR reported growth and like-for-like growth are two observations with different bases.
- AI-related product revenue is not the whole cloud segment.
- ARR targets/management forecasts are not recognized revenue.
- Capex is not automatically allocated to one segment without source support.
- Segment reorganization breaks naive historical continuity.

---

## 6. Alibaba event ontology

| Event family | Required object | Important distinction |
|---|---|---|
| `results_event` | official facts, guidance, segment/KPI definitions | reported versus non-GAAP versus management measure |
| `segment_definition_change` | old/new version, effective date, recast status | no silent series splice |
| `ai_model_product_event` | product/model fact, availability, adoption evidence | capability/adoption is not revenue |
| `cloud_capacity_event` | amount, capacity type, timing, dependency | planned capex is not delivered capacity |
| `commerce_investment_event` | program, spend/contra-revenue, KPI effect | accounting presentation versus underlying economics |
| `equity_placement_event` | share count, price, proceeds, closing, use | dilution, cash received and strategic investment separate |
| `repurchase_event` | shares, cash, cancellation/treasury state | announcement, execution and cancellation separate |
| `convertible_exchangeable_event` | principal, terms, collateral/security linkage | debt financing is not common-share issuance at event time |
| `spin_listing_event` | entity, stage, ownership, exchange | proposed, filed, priced and completed separate |
| `regulatory_policy_event` | authority, text, affected mechanism, effective date | policy mention is not impact direction |
| `counter_listing_event` | counter/security mechanics | counter is not new economic security by default |

### 6.1 August 2026 placement acceptance case

Official completion announcement:

- 710,000,000 newly issued ordinary shares;
- HK$112.70 per share;
- HK$80 billion gross placement size;
- net proceeds stated for AI infrastructure and data-centre/cloud buildout, with source percentages/amounts.

The reference twin must show:

1. event fact and source;
2. new shares as an event quantity;
3. proceeds and stated use;
4. capital-owner publication state;
5. no stock-direction label;
6. no final outstanding-share denominator unless sourced by the canonical owner.

---

# Part B — Tencent Holdings

## 7. Identity

```text
issuer_id: cik:0001293451
legal_name: Tencent Holdings Limited
reporting_currency: CNY/RMB
fiscal_year_end: December 31
```

Economic-security graph:

```text
tencent_ordinary_share
  ├─ XHKG 700 / HKD counter
  └─ XHKG 80700 / CNY counter
```

Tencent’s SEC CIK is useful as a stable legal-entity identifier. Tencent’s company results and issuer disclosure truth are HKEX/issuer-first; SNI must not treat the existence of a CIK as U.S. issuer-event coverage.

---

## 8. Tencent segment ontology

### `tencent.segment.v2026q2`

| Segment key | Official segment | Required substructure |
|---|---|---|
| `value_added_services` | Value Added Services | Domestic Games, International Games, Social Networks |
| `marketing_services` | Marketing Services | ad/recommendation/closed-loop mechanism observations where officially reported |
| `fintech_business_services` | FinTech and Business Services | payment, wealth management, consumer loan, cloud/business services observations |
| `others` | Others | reported residual; negative gross margin possible |

The current structure is historically familiar but definitions and subcomponent disclosures may change. Every observation still carries source definition and period.

---

## 9. Tencent metric registry v0

### 9.1 Group financials

| Metric key | Definition/basis |
|---|---|
| `tencent.group.revenue` | IFRS reported revenue |
| `tencent.group.gross_profit` | IFRS gross profit |
| `tencent.group.gross_margin` | gross profit / revenue |
| `tencent.group.operating_profit` | IFRS operating profit |
| `tencent.group.profit_attributable` | IFRS profit attributable to equity holders |
| `tencent.group.basic_eps` | RMB per ordinary share |
| `tencent.group.diluted_eps` | RMB per ordinary share |
| `tencent.group.non_ifrs_operating_profit` | issuer non-IFRS measure |
| `tencent.group.non_ifrs_profit_attributable` | issuer non-IFRS measure |
| `tencent.group.adjusted_ebitda` | issuer measure with source reconciliation |
| `tencent.group.adjusted_ebitda_margin` | matched-basis derived ratio |
| `tencent.group.net_cash` | issuer-defined point-in-time measure |
| `tencent.group.capex` | issuer-defined capital expenditures |

### 9.2 Value Added Services

| Metric key | Definition/basis |
|---|---|
| `tencent.vas.revenue` | segment revenue |
| `tencent.vas.gross_profit` | segment gross profit |
| `tencent.vas.gross_margin` | segment gross margin |
| `tencent.games.domestic_revenue` | domestic games revenue |
| `tencent.games.international_revenue` | international games revenue; reported and constant-currency growth separate |
| `tencent.social_networks.revenue` | social networks revenue |
| `tencent.vas.fee_based_subscriptions` | average daily subscriptions during quarter under issuer footnote |
| `tencent.games.major_title_observation` | named contribution/release observation, not a synthetic revenue allocation |

### 9.3 Marketing Services

| Metric key | Definition/basis |
|---|---|
| `tencent.marketing.revenue` | segment revenue |
| `tencent.marketing.gross_profit` | segment gross profit |
| `tencent.marketing.gross_margin` | segment gross margin |
| `tencent.marketing.ai_recommendation_observation` | source-backed product/mechanism statement |
| `tencent.marketing.closed_loop_observation` | issuer-described ecosystem integration |
| `tencent.marketing.advertiser_category_breadth` | observation only when issuer provides measurable scope |

### 9.4 FinTech and Business Services

| Metric key | Definition/basis |
|---|---|
| `tencent.fbs.revenue` | segment revenue |
| `tencent.fbs.gross_profit` | segment gross profit |
| `tencent.fbs.gross_margin` | segment gross margin |
| `tencent.fintech.commercial_payment_observation` | issuer narrative/fact |
| `tencent.fintech.wealth_management_observation` | issuer narrative/fact |
| `tencent.fintech.consumer_loan_observation` | issuer narrative/fact |
| `tencent.business_services.cloud_revenue_observation` | revenue growth observation only at reported precision |
| `tencent.business_services.ai_demand_observation` | issuer evidence; not quantified unless reported |

### 9.5 User/product operating metrics

| Metric key | Definition/basis |
|---|---|
| `tencent.wechat_weixin.combined_mau` | combined MAU as of period end |
| `tencent.qq.mobile_mau` | mobile-device MAU as of period end |
| `tencent.vas.fee_based_subscriptions` | average daily subscriptions in quarter |
| `tencent.video_accounts.time_spent_growth` | issuer-stated growth at named basis |
| `tencent.ai.workbuddy_adoption` | source-backed adoption observation |
| `tencent.ai.codebuddy_adoption` | source-backed adoption observation |
| `tencent.ai.hy_model_release` | model release/capability event, not a financial metric |

### 9.6 Capital and supply

| Metric key | Definition/basis |
|---|---|
| `tencent.capital.issued_shares_ex_treasury` | point-in-time shares at disclosure basis |
| `tencent.capital.treasury_shares` | point-in-time treasury shares |
| `tencent.capital.repurchased_for_cancellation` | transaction shares not yet cancelled |
| `tencent.capital.repurchase_price` | per-share transaction price, HKD or source currency |
| `tencent.capital.cancellation_date` | actual cancellation event |
| `tencent.capital.awards_options` | grant/vesting/issue event with plan/source |
| `tencent.capital.debt_issuance` | principal/currency/terms/source |
| `tencent.capital.net_cash` | issuer-defined net cash |
| `tencent.capital.capex` | issuer-defined capex |

---

## 10. Tencent Q2 2026 reference facts

Source: Tencent HKEX result announcement dated 2026-08-12.

| Observation | Current source value |
|---|---:|
| Revenue | RMB204,785 million, +11% YoY |
| Gross profit | RMB118,433 million, +13% |
| Operating profit | RMB67,276 million, +12% |
| Profit attributable to equity holders | RMB56,022 million, +0.7% |
| Non-IFRS operating profit | RMB75,636 million, +9% |
| VAS revenue | RMB98,414 million, +8%, 48% of revenue |
| Domestic Games revenue | RMB47.3 billion, +17% |
| International Games revenue | RMB18.6 billion, -0.8% reported / +4% constant currency |
| Social Networks revenue | RMB32.5 billion, +0.8% |
| Marketing Services revenue | RMB43,565 million, +22%, 21% of revenue |
| FinTech and Business Services revenue | RMB60,286 million, +9%, 30% of revenue |
| VAS gross margin | 64% versus 60% prior year |
| Marketing Services gross margin | 57% versus 58% |
| FinTech/Business Services gross margin | 52% versus 52% |
| Group gross margin | 58% versus 57% |
| Combined Weixin/WeChat MAU | 1,439 million, +2% |
| Mobile QQ MAU | 520 million, -2% |
| Fee-based VAS subscriptions | 259 million, -2% |
| Net cash | RMB58,191 million |
| Capital expenditures | RMB52,784 million for Q2; RMB84,720 million for six months |

Required interpretation boundaries:

- reported international-games growth and constant-currency growth are separate series;
- AI product/model statements are not revenue unless the issuer quantifies revenue;
- capex includes IT infrastructure, data centres, land use rights, office premises and intellectual property under the issuer footnote; do not label all capex “AI capex”;
- segment gross margin is more informative than a single group margin but remains accounting context, not stock direction.

---

## 11. Tencent event ontology

| Event family | Required object | Important distinction |
|---|---|---|
| `results_event` | official facts, segment/KPI basis, outlook | IFRS versus non-IFRS |
| `game_release_performance_event` | title, geography/platform, release/contribution evidence | release is not quantified financial contribution unless reported |
| `marketing_ai_event` | product/mechanism change, adoption/effect evidence | capability is not revenue |
| `cloud_ai_infrastructure_event` | model/product/compute/capex fact | procurement, deployed capacity and monetization separate |
| `fintech_regulatory_event` | authority, service, requirement, effective date | policy impact direction not assumed |
| `repurchase_event` | trade date, shares, price, cancellation state | purchase, treasury/cancellation and issued-share balance separate |
| `share_award_option_event` | plan, grant, vesting/issue mechanics | compensation dilution versus issued share event separate |
| `debt_gmtn_event` | principal, currency, maturity/terms | debt funding not equity supply |
| `investee_portfolio_event` | entity, stake/action, carrying/economic evidence | portfolio mark is not operating segment revenue |
| `counter_event` | 700/80700 counter mechanics | same economic security |

### 11.1 August 2026 buyback acceptance case

Tencent’s 2026-08-27 next-day disclosure return shows:

- 700 HKD and 80700 RMB counters;
- opening/closing issued-share balance in the disclosure;
- a sequence of daily shares repurchased for cancellation but not yet cancelled;
- transaction dates and weighted/average prices.

The twin must preserve each stage and must not infer a current outstanding-share reduction until cancellation/issued-share evidence supports it.

---

# Part C — Shared reference ontology

## 12. Shared event/fact classes

The two issuers share vocabulary only where the economic object is truly comparable:

```text
reported_financial_fact
company_specific_kpi
segment_definition
management_target
capital_action
official_policy_event
product_or_model_event
relationship_event
security_counter_event
market_reaction_observation
source_correction
```

Company-specific KPIs retain issuer namespaces. `ali.cloud.ai_related_product_revenue` and a Tencent AI-demand narrative are not collapsed into one generic `ai_revenue` metric.

---

## 13. Relationship ontology v0

A relationship observation requires:

```text
subject_issuer
object_entity
relationship_type
mechanism
source_type
source_receipt
first_known_at
last_confirmed_at
precision
materiality_state
correction_state
```

Initial relationship families:

- customer;
- supplier;
- cloud/compute customer;
- strategic partner;
- investee;
- competitor;
- platform ecosystem participant;
- regulatory authority;
- index/ETF membership;
- theme/subtheme exposure.

SNI creates no second relationship graph. It declares what a resolved canonical relationship must look like before it can appear in the twin.

---

## 14. KPI definition-change behavior

When a source changes a definition:

1. close the prior metric version at the latest period for which the old definition applies;
2. mint the new ontology version;
3. record whether the issuer recast history;
4. show an explicit series break in the product;
5. prevent automatic growth/acceleration calculations across the break;
6. allow a separately reviewed mapping only with source evidence and a reproducible transform.

The user should see “series definition changed” rather than a smooth but fabricated chart.

---

## 15. Ontology acceptance cases

The future implementation must pass these real cases:

1. Alibaba June-quarter 2026 current four-segment structure renders without overwriting historical segment labels.
2. Alibaba CMR shows reported and like-for-like values as different bases.
3. Alibaba ADS/share arithmetic uses 8:1 with original units retained.
4. Alibaba placement shows issuance, proceeds, use and capital-owner status separately.
5. Tencent international games displays reported and constant-currency growth separately.
6. Tencent group, segment and non-IFRS measures remain distinct.
7. Tencent capex is not entirely labeled AI.
8. Tencent buybacks preserve purchase-versus-cancellation state.
9. Both issuers render missing KPI observations as typed absence.
10. Neither ontology produces a company score or stock-direction statement.

---

## 16. Source anchors

Alibaba:

- `https://www.alibabagroup.com/en-US/faqs-investor-information`
- `https://www.alibabagroup.com/en-US/document-2026456290057781248`
- `https://www.alibabagroup.com/en-US/document-2029365886510432256`
- `https://www.sec.gov/Archives/edgar/data/1577552/`

Tencent:

- `https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0812/2026081200296.pdf`
- `https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0827/2026082700758.pdf`
- `https://www.tencent.com/investors/announcements/`
- `https://www.sec.gov/Archives/edgar/data/1293451/`

---

## 17. What this ontology does not claim

- It does not claim these are the only economically important metrics.
- It does not authorize scraping or redistribution.
- It does not create historical comparable series automatically.
- It does not determine materiality, valuation, probability, or stock direction.
- It does not replace the canonical Company Event or Capital Structure owners.
- It does not hard-code current facts as permanent state.

The ontology is successful when future evidence can be stored and compared honestly without every worker reinventing what “Alibaba cloud growth” or “Tencent buyback” means.