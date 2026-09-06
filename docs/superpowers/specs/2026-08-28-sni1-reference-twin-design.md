# SNI-1 Reference Twin Contract + Alibaba/Tencent Source Qualification Design

**Date:** 2026-08-28  
**Status:** written SNI-1 architecture for Chairman review; no runtime, source purchase, product route, forecast, signal, model promotion, or trading authority is created by this document  
**Parent architecture:** `docs/superpowers/specs/2026-08-28-single-name-intelligence-os-design.md`  
**Operation key:** `sni1-ref-twin-20260828-sol-001`  
**Carrier:** `sol/sni1-reference-twin-20260828`  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@bdcb00132692b7e2dc40d35a2d2e226f81efe2f4`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap-major 1 compatible  
**Macro pickup:** `0863c549f728c718bbe82cc883e89843c0eb710a`  
**Terminal architecture pin:** `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`  
**Reference organisms:** Alibaba Group issuer with BABA ADS and Hong Kong 9988/89988 counters; Tencent Holdings issuer with Hong Kong 700/80700 counters  

---

## 0. Executive decision

SNI-1 freezes the **smallest trustworthy reference-twin contract** that can make Alibaba and Tencent feel like continuously monitored individual organisms without building another identity, event, market-data, filing, capital, options, China, evidence, or forecast system.

The selected architecture is a **derived read-model compiler**:

```text
canonical owner artifacts
        +
point-in-time identity and counter relationships
        +
source/status/rights/freshness/correction envelopes
        +
company-specific KPI and event ontologies
        =
mastermind.single_name.reference_twin/v1
```

The reference twin is not a database of truth. It is a deterministic, versioned answer to:

1. Which legal issuer is this?
2. Which economic security and trading counter is the user viewing?
3. Which facts and state objects are currently available from canonical owners?
4. Which important fields are missing, stale, unlicensed, provisional, or structurally inapplicable?
5. What materially changed since the previous accepted twin generation?
6. What evidence path supports every material statement?

SNI-1 deliberately contains **no directional probability, target price, stock-specific model, response surface, or trade recommendation**. Those belong to later separately preregistered programs after the reference truth model is frozen.

---

## 1. Outcome and acceptance

### 1.1 Primary user job

A serious investor opening Alibaba or Tencent should be able to identify, in one coherent workspace:

- the issuer and all linked traded forms;
- the current company reporting structure and key operating drivers;
- the latest reported results, business changes, capital actions, official announcements, and relevant HK/China context;
- the selected instrument’s path/market state and the coverage limits of that state;
- what changed materially since the prior accepted generation;
- where each claim came from;
- what the system cannot currently know and why.

### 1.2 Machine job

The machine must compose a stable, correction-safe, point-in-time envelope from existing owners while preserving:

- issuer versus security versus trading-counter identity;
- source-native clocks;
- market-calendar and asynchronous cross-venue state;
- reporting currency, trading currency, unit, share-class, and ADS conversion semantics;
- owner capability state (`PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, `BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`);
- evidence and correction lineage;
- rights and redistribution status;
- typed absence instead of empty or guessed values;
- explicit zero authority.

### 1.3 SNI-1 completion proof

SNI-1 implementation will be complete only when a real Alibaba and a real Tencent payload are generated from the real owner path, validate against the frozen contract, preserve every relevant absence, and can be read by one bounded reference consumer without creating or mutating upstream truth.

A schema file and green tests alone will be `BUILT_NOT_PROVEN`, not completion.

---

## 2. Current canonical capability ledger

| Capability | State | SNI-1 treatment |
|---|---|---|
| `company_identity.v1` issuer/listing resolver | `BUILT_NOT_PROVEN` as broad production identity | Reuse as the current canonical identity owner; do not fork it. Add only a derived relationship projection for multi-counter securities. |
| Alibaba SEC/HKEX/IR source identity | `PROVEN_LIVE` source availability | Alibaba CIK `0001577552`; BABA and 9988/89988 mechanics are officially documented. |
| Tencent HKEX/IR source identity | `PROVEN_LIVE` source availability | Tencent CIK `0001293451` exists as an SEC entity identity; primary company reporting remains HKEX/issuer material, not SEC company-event coverage. |
| BABA Stock Identity W1 Atlas | `PROVEN_LIVE` descriptive artifact | Consume the current fingerprint/state/episode references, retaining provisional `epoch_0` and zero authority. |
| Stock Identity W3 ruler, W4 real epochs, W6 SIF | `NOT_BUILT` | Render typed absence; never recreate inside SNI. |
| Alibaba/Tencent HK daily market and current HK context | `PARTIAL` | Existing HK stores/engines provide useful context; exact production freshness and rights vary by owner. |
| `hk_adr_bridge` | `PROVEN_LIVE` house organ / display-only | BABA→9988 is a direct issuer bridge. Tencent currently uses KWEB as a group proxy and must remain labeled proxy, never issuer evidence. |
| `hk_market_drivers` | `PROVEN_LIVE` display context | Consume for HK market/factor context; never convert its deterministic read into an issuer signal. |
| `hk_filing_bus` | `PROVEN_LIVE` display context | Consume recent official results/buyback/placement/mandate/shareholder event flags. Do not treat its limited taxonomy as a complete company-event corpus. |
| Per-stock Southbound holdings | `PARTIAL` | Eastmoney-derived observation history exists. SNI renames it as a holdings/position context source; it may not inherit “smart money” or directional intent language. |
| First-party CCASS display data | `NOT_BUILT` in SNI/house | Candidate paid/licensed source; current public licence details require a Data OS/legal/commercial gate. |
| HKEX historical full-book securities | `NOT_BUILT` in house SNI | Paid first-party research candidate; lower-cost historical qualification precedes real-time procurement. |
| HKEX stock-options historical full book | `NOT_BUILT` in house SNI | Paid first-party research candidate for 9988/0700 where contracts exist. |
| HKEX OMD-C/OMD-D real-time full depth | `NOT_BUILT` / unlicensed | Separate future procurement/rights decision; not an SNI-1 implementation dependency. |
| Earnings Intelligence E0–E2 | `PROVEN_LIVE` first vertical | Reuse event workspace outputs where coverage exists. Do not call E3+ features live. |
| Capital Structure V2 W1/W2A/W2B | mixed `PROVEN_LIVE` | Consume only accepted owner outputs. W2C/W2D remain `BUILT_NOT_PROVEN`; W3+ state/UX is not available. |
| BABA U.S. options structure/GEX | `PROVEN_LIVE` or `PARTIAL` by owner field | Reference owner payloads with native authority and freshness. No new SNI options scoring. |
| 9988/0700 HK stock-options intelligence | `NOT_BUILT` as a governed SNI owner | Typed absence until a qualified owner/source exists. |
| qledger/Evaluation OS | `PROVEN_LIVE` house apparatus | SNI-1 does not write forecasts. Later SNI forecast families must register here. |
| `mastermind.single_name.reference_twin/v1` | `NOT_BUILT` | This is the new bounded SNI-1 capability. |

### 2.1 Adjacent active ownership

- Macro PR #6529 is the current Stock Identity W3→final recovery carrier. SNI-1 must not touch `engine/stock_identity/**`, its research law, partitions, ruler, epoch, SIF, or prospective ownership.
- Options Alpha has a separate recovery architecture. SNI reads its accepted artifacts but does not manufacture a browser-side options signal.
- Capital Structure remains its own issuer-capital owner.
- China/HK native-data owners retain their stores, buses, collectors, qledger families, and source laws.

---

## 3. Identity architecture: issuer → economic security → trading counter

### 3.1 Why the existing two-level vocabulary is insufficient for HK multi-counter names

The current Company Intelligence identity layer correctly separates issuer and listing alias, but its `security_id_for(mic, ticker)` naturally creates a distinct security identifier for every ticker.

For Hong Kong dual-counter securities, that is not always the economic truth:

- Alibaba `9988` HKD and `89988` RMB are trading counters for the same ordinary-share security.
- Tencent `700` HKD and `80700` RMB are trading counters for the same ordinary-share security.
- Alibaba `BABA` is a distinct ADS security whose unit represents eight Alibaba ordinary shares and is convertible with the Hong Kong ordinary shares.

Therefore SNI-1 adds a **derived relationship layer**, not a competing canonical identity store:

```text
issuer
  └─ economic_security
       ├─ venue_listing
       │    └─ trading_counter(s)
       └─ linked_security_relationship(s)
```

### 3.2 Frozen identity objects

#### `issuer_ref`

```text
company_id
legal_name
reporting_currency
fiscal_year_end
incorporation_jurisdiction
external_ids
canonical_identity_ref
```

Current reference IDs:

- Alibaba Group Holding Limited: `cik:0001577552`
- Tencent Holdings Limited: `cik:0001293451`

A CIK is an identity anchor, not proof that the SEC is the primary company-event source. Tencent’s primary result/issuer disclosure path remains HKEX/issuer materials.

#### `economic_security`

```text
security_group_id
issuer_ref
security_kind: ordinary_share | ads | other
share_class
base_unit
conversion_relationships[]
canonical_security_refs[]
```

#### `trading_counter`

```text
counter_id
security_group_id
mic
stock_code_or_ticker
trading_currency
market_calendar
session_template
is_primary_display_counter
valid_from
valid_to
canonical_listing_ref
```

### 3.3 Reference identity graph

```text
Alibaba Group (cik:0001577552)
  ordinary_share:alibaba
    XHKG counter 9988 / HKD
    XHKG counter 89988 / CNY
  ads:alibaba:baba
    XNYS counter BABA / USD
    conversion: 1 ADS = 8 ordinary shares
    fungibility: bidirectional, subject to operational frictions

Tencent Holdings (cik:0001293451)
  ordinary_share:tencent
    XHKG counter 700 / HKD
    XHKG counter 80700 / CNY
```

### 3.4 Identity laws

1. Issuer financial truth attaches to `issuer_ref`.
2. Price, order book, options, liquidity, and session state attach to the selected `trading_counter` or economic security at their actual grain.
3. Multi-counter prices may be compared only after timestamped FX and common-unit conversion.
4. A trading counter is not automatically a different economic security.
5. An ADS is not the ordinary share, even when fungible.
6. Cross-venue basis is descriptive until separately studied and promoted.
7. Missing/ambiguous mapping produces `identity_unresolved`; no fallback ticker guess.
8. SNI-1 does not rewrite `company_identity.v1`; it emits a relationship overlay and records the canonical refs it composed.

---

## 4. Reference Twin contract

### 4.1 Contract name and authority

```text
schema: mastermind.single_name.reference_twin/v1
authority:
  can_rank: false
  can_size: false
  can_gate: false
  can_originate_signal: false
  can_escalate: false
  can_trade: false
```

### 4.2 Top-level envelope

```text
schema
spec_hash
generation_id
generated_at
as_of
selected_counter_id
issuer
securities[]
counter_relationships[]
owner_views{}
material_changes[]
next_known_events[]
evidence_health
lineage
rights_summary
authority
```

### 4.3 Owner-view envelope

Every canonical source projection is wrapped independently:

```text
owner_key
owner_contract
capability_state
payload_ref
payload_digest
source_as_of
observed_at
available_at
generated_at
freshness_state
correction_state
rights_state
coverage_state
typed_absence
owner_authority
```

`capability_state` is never inferred from whether a JSON object was non-empty. It comes from the accepted owner state/contract and current evidence.

### 4.4 Initial owner keys

```text
identity
company_event
reported_financials
company_kpis
capital_structure
hk_official_filings
stock_identity
market_path
live_quote
hk_market_context
cross_listing_context
options_structure_us
options_structure_hk
southbound_holdings
short_activity
relationships_themes
news_narrative
valuation_expectations
forecast_book
```

The list is closed for v1. A new key requires a contract revision, owner assignment, and failure-state tests.

### 4.5 What the reference twin may derive

The compiler may derive only deterministic composition facts:

- identity relationships;
- counter currency/unit normalization with exact FX vintage;
- owner coverage/freshness/correction/rights summaries;
- field-level `available | absent | stale | provisional | not_applicable` state;
- diff against the previous accepted twin generation;
- evidence links and source ordering;
- plain-language typed-absence copy from fixed reason codes.

It may not derive:

- business direction from free-form prose;
- stock direction;
- probabilities;
- target prices;
- sentiment-derived signals;
- “smart money” intent;
- implied trade actions;
- a unified conviction score.

---

## 5. Clock, unit, currency, and correction law

### 5.1 Closed clock vocabulary

```text
event_time        — when the underlying event occurred
published_at      — issuer/exchange/public publication clock
accepted_at       — regulatory acceptance clock where applicable
available_at      — earliest lawful machine availability
observed_at       — when the canonical owner observed it
generated_at      — owner artifact generation
reference_as_of   — twin cut-off time
market_session    — selected counter session identity
```

No later observation may be backdated to `event_time`.

### 5.2 Cross-venue state

Every cross-listing comparison records:

```text
left_counter
right_counter
left_price_time
right_price_time
left_market_state: open | closed | auction | lunch | stale | holiday
right_market_state: open | closed | stale | holiday
fx_pair
fx_time
conversion_ratio
fees_and_friction_included: false in v1
comparison_state: synchronous | asynchronous | stale | unavailable
```

A stale or asynchronous basis may be displayed only as such; it is not an arbitrage reading.

### 5.3 Currency and unit law

- Issuer reporting currency is separate from counter trading currency.
- A financial statement number never inherits the selected counter’s currency.
- Currency conversion requires an exact source/vintage and preserves the original amount.
- Alibaba BABA ordinary-share equivalence uses the officially documented `1 ADS = 8 ordinary shares` relationship.
- Tencent and Alibaba RMB/HKD counter comparison is same-security/multi-counter comparison, not a security-return splice.
- Share-count, per-share, ADS, and ordinary-share denominators must name their unit explicitly.

### 5.4 Correction law

Each owner view records one of:

```text
current
superseded
corrected
correction_pending
conflict
unknown
```

A corrected owner artifact causes a new twin generation. Previous twin generations remain reconstructable and are never overwritten as if the correction had always been known.

---

## 6. Typed-absence contract

Every absent material field carries one code, plain-language explanation, and fill condition.

Closed v1 reason vocabulary:

```text
owner_not_built
owner_built_not_proven
owner_unavailable
source_missing
source_stale
source_unlicensed
rights_blocked
identity_unresolved
counter_relationship_unresolved
unsupported_unit_conversion
unsupported_currency_conversion
asynchronous_market
insufficient_history
insufficient_coverage
provisional_owner_output
correction_pending
conflicting_sources
not_applicable
not_yet_reported
not_yet_matured
withheld_by_design
```

Required shape:

```text
reason_code
field_path
plain_en
plain_zh
last_checked_at
looked_in[]
fill_condition
owner_key
```

Missing is never zero, neutral, bearish, or 50%.

---

## 7. Canonical owner map

The detailed field/source matrix lives in `research/single_name_intelligence/SNI1_OWNER_SOURCE_MATRIX_2026-08-28.md`. The governing ownership summary is:

| Domain | Canonical owner | SNI role |
|---|---|---|
| Issuer/listing identity | Company Intelligence identity | Read/compose; add derived counter relationships only. |
| Earnings/results/guidance/source evidence | Earnings Intelligence / Company Event | Read; no second event corpus. |
| HK issuer announcements | HK filing/placement owners + future canonical event convergence | Read as current official-event context; expose incompleteness. |
| Capital state | Capital Structure V2 | Read accepted outputs; preserve mixed capability states. |
| Instrument behavior | Stock Identity | Read W1/W2; abstain on W3+ outputs. |
| HK regime/drivers | HK market owners | Read display context. |
| BABA U.S. options | Canonical options owners | Read native observations/authority. |
| 9988/0700 options | No accepted SNI owner yet | Typed absence; qualify HKEX source separately. |
| Southbound holdings | HK southbound owner | Read native holdings/change fields; no intent label. |
| Relationships/themes | Existing graph/ontology owners | Read only resolved evidence. |
| Forecasts/evaluation | qledger/Evaluation OS | Not written in SNI-1. |
| Product composition | SNI + Terminal | SNI emits read model; Terminal later owns interactive composition. |

---

## 8. Alibaba company ontology v0

The complete ontology registry is in `research/single_name_intelligence/SNI1_ALIBABA_TENCENT_ONTOLOGY_V0_2026-08-28.md`.

### 8.1 Versioned segment model

Alibaba’s June-quarter 2026 reporting introduced a four-segment structure:

1. Alibaba E-commerce Group
2. AI Cloud and Compute Services
3. AI Labs and Applications
4. All Others

The ontology must preserve `definition_version`, `effective_from`, source receipt, and historical mapping state. It must not silently splice this structure onto prior reported series.

### 8.2 Core Alibaba KPI families

```text
commerce_platform
  customer_management_revenue
  china_ecommerce_revenue
  china_quick_commerce_revenue
  international_ecommerce_revenue
  global_wholesale_revenue
  88vip_members

ai_cloud_compute
  segment_revenue
  external_revenue_where_reported
  ai_related_product_revenue
  ai_model_application_arr_where_reported
  adjusted_ebita
  adjusted_ebita_margin
  capex_and_compute_investment

ai_labs_applications
  segment_revenue
  adjusted_ebita_loss
  model/application adoption metrics where officially reported

capital
  ordinary_shares_outstanding
  ads_equivalent
  repurchases
  equity_issuance
  convertibles_exchangeables
  cash_and_liquid_investments
  capex
```

### 8.3 Alibaba event families

- results/guidance;
- segment/KPI definition change;
- AI/cloud infrastructure and model/product milestones;
- commerce monetization/quick-commerce investment;
- major capital issuance, repurchase, convertible/exchangeable financing;
- spin-off/listing/corporate action;
- material China platform/regulatory policy;
- major customer/supplier/partner relationship event;
- cross-listing/counter mechanics change.

Alibaba’s August 2026 HK$80 billion placement is a canonical test case: it must update capital context, use-of-proceeds evidence, and unit/share-count state through the proper owner without assigning positive or negative stock direction by fiat.

---

## 9. Tencent company ontology v0

### 9.1 Core segment model

```text
value_added_services
  domestic_games_revenue
  international_games_revenue
  social_networks_revenue
  segment_revenue
  segment_gross_profit
  segment_gross_margin

marketing_services
  segment_revenue
  segment_gross_profit
  segment_gross_margin
  advertising product/mechanism observations where officially reported

fintech_business_services
  segment_revenue
  segment_gross_profit
  segment_gross_margin
  commercial_payment
  wealth_management
  consumer_loan_services
  cloud_services

others
  segment_revenue
  segment_gross_profit_or_loss
```

### 9.2 Operating KPI families

```text
weixin_wechat_combined_mau
mobile_qq_mau
fee_based_vas_subscriptions
video_accounts_time_spent_or_views_where_reported
major_game_release_and_contribution observations
cloud_ai_demand observations
```

### 9.3 AI and infrastructure

Track separately:

- foundation-model releases;
- AI office/coding/application adoption claims;
- AI recommendation/advertising improvements;
- AI-related cloud demand;
- compute/data-centre procurement;
- capital expenditure;
- depreciation/operating-cost effects;
- revenue or monetization only when explicitly reported.

### 9.4 Tencent capital families

- ordinary shares and treasury shares;
- daily/next-day repurchase disclosures;
- cancellation status;
- awards/options/share-based compensation;
- debt/GMTN issuance;
- investee/portfolio transactions where material and source-grounded;
- net cash and capital expenditure.

The current repeated August 2026 buyback disclosures are a first-class capital-state stream, not a generic “bullish” input.

---

## 10. HK data qualification ruling

The detailed research is in `research/single_name_intelligence/SNI1_HK_DATA_QUALIFICATION_2026-08-28.md`.

### 10.1 Selected sequencing

#### Phase H0 — reuse and semantic repair

Use existing house HK daily/quote, filings, regime, ADR bridge, southbound, and China/HK context owners. Repair semantics at the SNI projection boundary:

- KWEB remains a Tencent group proxy, not Tencent-specific overnight evidence;
- Eastmoney southbound data is holdings/change context, not “smart money” truth;
- current HK filing taxonomy is useful but incomplete;
- source/capability/rights state is explicit.

#### Phase H1 — historical first-party microstructure research

Before purchasing a real-time redistribution stack, qualify first-party historical files:

- HKEX Historical Full Book — Securities Market;
- Historical Order Book/Statistics Update where needed;
- Historical Full Book — Derivatives Market Stock Options;
- stock-options trade files/tick-by-tick files.

Current published fee pages indicate materially lower monthly research costs than a real-time vendor stack. The first study should procure the smallest lawful sample window that can answer whether full-book and stock-options data materially improve Alibaba/Tencent research.

#### Phase H2 — CCASS first-party qualification

Compare the existing Eastmoney-derived Southbound holdings plane against HKEX’s CCASS Shareholding Data Display Licence:

- identity and coverage;
- publication clock;
- history depth;
- correction semantics;
- permissible internal use and customer display;
- cost and operational reporting;
- uniqueness versus current holdings data.

No CCASS capture or display begins without written licence/rights confirmation.

#### Phase H3 — real-time depth only after value proof

OMD-C Securities Premium/FullTick and OMD-D Derivatives Premium/FullTick are not SNI-1 dependencies. They require separate commercial, technical, non-display/redistribution, subscriber, and operational approval after H1/H2 evidence shows sufficient incremental value.

### 10.2 Procurement law

- SNI research may recommend a product; it cannot purchase or accept terms.
- Data OS/legal/commercial review owns licence interpretation.
- Customer-facing display and internal non-display/model use are separately licensed questions.
- Derived data rights are not assumed from access.
- Historical files do not automatically grant real-time or redistribution rights.

---

## 11. Real-data reference payload

SNI-1 implementation must ship one Alibaba and one Tencent payload generated from current real sources.

### 11.1 Alibaba required state

At minimum:

- issuer and counter graph: BABA, 9988, 89988;
- official ADS ratio and fungibility receipt;
- latest official result event and versioned segment/KPI definitions;
- latest major capital action, including the August 2026 placement;
- BABA Stock Identity W1 reference and provisional-epoch disclosure;
- direct BABA→9988 overnight bridge state;
- current HK market context;
- U.S. options owner state;
- HK options typed absence unless a qualified owner exists;
- evidence/rights/freshness summary.

### 11.2 Tencent required state

At minimum:

- issuer and 700/80700 counter graph;
- latest official result event;
- segment revenue/gross-margin and operating KPI definitions;
- AI/capex/net-cash context;
- current official buyback/share-change event state;
- current HK path and market context;
- explicit statement that KWEB is group proxy only;
- Tencent-specific U.S. overnight owner absence;
- HK options typed absence unless a qualified owner exists;
- evidence/rights/freshness summary.

### 11.3 No synthetic completeness

The payload examples may contain many absences. That is an acceptance feature. A reference twin that looks complete by inventing owners or copying stale numbers fails SNI-1.

---

## 12. Implementation wave design after approval

This written design does not itself authorize implementation. After Chairman review, the implementation plan should decompose into these bounded PRs:

### SNI-1A — identity/counter relationship contract

- pure contract/types/validator;
- no owner reads;
- fixtures for Alibaba and Tencent;
- hostile tests for ADS ratio, multi-counter identity, stale FX, duplicate economic-security mapping, and ambiguous issuer identity.

### SNI-1B — owner/source manifest and ontology registry

- declarative owner field map;
- Alibaba/Tencent ontology version manifests;
- source priority, rights, clocks, null semantics;
- no runtime composer yet.

### SNI-1C — pure reference-twin compiler

- consumes explicit owner envelopes supplied in memory;
- emits deterministic v1 payload;
- no I/O, no store, no scheduler, no LLM;
- typed-absence and diff engine.

### SNI-1D — real owner adapters and reference payloads

- read-only adapters to existing owners;
- real Alibaba/Tencent generation;
- no new upstream collection;
- exact source/capability-state receipts.

### SNI-1E — one bounded reference consumer

- read-only reference composition in the selected existing host;
- real data, correction/degraded states;
- browser proof at relevant breakpoints;
- still zero forecast/signal authority.

Each PR must be independently useful and reviewable. No mega-branch may combine SNI-1A through SNI-1E.

---

## 13. Testing and acceptance law

### 13.1 Contract tests

Must reject:

- issuer facts attached only to a counter;
- 9988 and 89988 represented as unrelated economic securities;
- 700 and 80700 represented as unrelated economic securities;
- BABA treated as one ordinary share rather than one ADS/8-share relationship;
- unstamped FX conversion;
- cross-market basis without market-state clocks;
- owner payload without capability/authority block;
- missing field represented as zero/neutral;
- rights-unknown source rendered as customer-display-safe;
- Stock Identity W3/W4/W6 output fabricated from W1;
- KWEB proxy described as Tencent issuer evidence;
- southbound holdings described as directional intent.

### 13.2 Determinism and correction tests

- same owner inputs produce byte-stable canonical payload;
- changed source digest produces new generation/diff;
- superseded source remains reconstructable;
- future correction cannot rewrite an older generated belief state;
- selected counter change does not duplicate issuer facts.

### 13.3 Real proof

- real Alibaba and Tencent owner inputs;
- exact payload digests;
- every material claim opens a source/owner path or typed absence;
- no unsupported field is silently omitted;
- one real consumer renders current, stale, corrected, unlicensed, and absent states;
- production path proof is distinct from CI.

---

## 14. Failure states

The SNI-1 consumer must have complete designs for:

- identity conflict;
- counter relation unknown;
- owner artifact missing;
- owner `BUILT_NOT_PROVEN`;
- official source stale;
- market data stale while issuer facts remain current;
- cross-venue asynchronous comparison;
- rights unknown/unlicensed;
- corrected result/announcement;
- KPI definition changed;
- source available in one language only;
- no Stock Identity epoch;
- no HK options owner;
- proxy-only overnight context;
- data provider degraded;
- selected counter on holiday while sibling venue traded;
- no prior twin generation for diff.

The product must remain useful in every one of these states.

---

## 15. Explicit non-goals

SNI-1 does not:

- build a new stock page;
- build a new issuer registry;
- rebuild Company Intelligence, Earnings, Capital Structure, Stock Identity, HK market engines, China Hub, Options Alpha, qledger, or Evaluation OS;
- create a new event database;
- purchase HKEX data;
- add a real-time market feed;
- create a company score;
- train a forecast model;
- backtest a ticker-specific strategy;
- infer investor intent from options, Southbound, CCASS, short, or ownership data;
- grant rank, gate, size, signal, escalation, portfolio, or trade authority;
- roll out beyond Alibaba/Tencent.

---

## 16. Open decisions deliberately deferred

These are named future dockets, not missing requirements:

1. Whether `company_identity.v1` should eventually natively represent economic security versus trading counter rather than consume SNI’s relationship overlay.
2. Whether Tencent-specific off-hours evidence can be sourced lawfully and with sufficient quality to improve on a KWEB proxy.
3. Whether HKEX historical full-book securities and stock-options data produce useful incremental research value over the current house stack.
4. Whether first-party CCASS adds enough identity, history, correction, and rights value over the Eastmoney Southbound plane.
5. Which SNI product surface should host SNI-1E after a real-payload reference composition is reviewed.
6. Whether a non-CIK global issuer identifier should be added by the canonical identity owner for issuers with no meaningful SEC reporting role.

None of these blocks the SNI-1 contract.

---

## 17. Source anchors

Official/current anchors used by this design include:

- Alibaba investor FAQ: BABA ADSs represent eight ordinary shares; 9988 HKD and 89988 RMB counters; bidirectional fungibility; Hong Kong dual-primary status.  
  `https://www.alibabagroup.com/en-US/faqs-investor-information`
- Alibaba June-quarter 2026 official results and segment disclosure.  
  `https://www.alibabagroup.com/en-US/document-2026456290057781248`
- Alibaba August 2026 placement completion and use of proceeds.  
  `https://www.alibabagroup.com/en-US/document-2029365886510432256`
- SEC Alibaba filer identity CIK 0001577552.  
  `https://www.sec.gov/Archives/edgar/data/1577552/`
- Tencent Q2 2026 HKEX result announcement, stock codes 700 and 80700.  
  `https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0812/2026081200296.pdf`
- Tencent August 2026 next-day disclosure/buyback return.  
  `https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0827/2026082700758.pdf`
- SEC Tencent entity identity CIK 0001293451.  
  `https://www.sec.gov/Archives/edgar/data/1293451/`
- HKEX OMD securities/derivatives market-data fee schedules and licence requirements.  
  `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Market-Data/Market-Data-Vendors?sc_lang=en`  
  `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Listed-Derivatives/Market-Data/Market-Data-Vendors?sc_lang=en`
- HKEX historical full-book securities and stock-options files.  
  `https://sc.hkex.com.hk/TuniS/www.hkex.com.hk/eng/ods/historicalData.aspx`
- HKEX CCASS Shareholding Data Display Licence application surface.  
  `https://www.hkex.com.hk/services/rules-and-forms-and-fees/forms/securities-%28hong-kong%29/market-data/hkex-is?sc_lang=en`

---

## 18. Self-review

- Scope is one reference-twin contract, not the whole SNI program.
- Issuer, economic security, listing, and trading counter are separated.
- Alibaba/Tencent current reporting ontologies are versioned.
- Existing owners remain canonical.
- HK paid data is qualified, not purchased.
- Rights, time, correction, currency, unit, and absence semantics are explicit.
- No forecast or authority leaks into SNI-1.
- The implementation is decomposed into five bounded verticals.
- No `TBD`, hidden placeholder, or undefined completion claim remains.

**Review gate:** implementation planning begins only after the Chairman approves this written SNI-1 design and any requested amendments are folded into the same carrier.