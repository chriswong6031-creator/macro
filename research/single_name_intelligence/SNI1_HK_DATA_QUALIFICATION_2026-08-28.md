# SNI-1 Hong Kong Data, Rights, and Economics Qualification

**Date:** 2026-08-28  
**Authority:** research recommendation only; no purchase, licence acceptance, source activation, collector, redistribution, or non-display use is authorized  
**Reference names:** Alibaba 9988/89988 and Tencent 700/80700  
**Parent design:** `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md`  

This docket asks a narrower question than “what HK data exists?”

> Which additional Hong Kong observations could materially improve the Alibaba/Tencent reference twins, what does Mastermind already possess, and which source should be qualified first under honest cost, rights, clock, and product-value constraints?

All prices below are published HKEX line items observed on 2026-08-28. They are not quotes, legal interpretations, or commitments. The exact agreement, taxes, vendor/network costs, minimums, reporting obligations, permitted derived use, and customer-display rights must be confirmed with HKEX or an authorized vendor before any decision.

---

## 1. Executive recommendation

### Recommended order

1. **Repair semantics and expose existing house coverage first.** No purchase is needed to stop calling a third-party holdings snapshot “smart money,” to distinguish direct BABA context from KWEB proxy context, or to show owner/freshness/rights states.
2. **Qualify historical first-party microstructure before real-time depth.** HKEX historical full-book securities and stock-options files are the highest-information, lowest-commitment way to test whether L2/L3-style information materially improves Alibaba/Tencent research.
3. **Run a separate CCASS licence/coverage comparison.** The current Eastmoney Southbound plane is useful but not first-party and has semantic/rights limitations. First-party CCASS may improve identity, correction, participant and display rights—but the public fee terms are not yet sufficient for approval.
4. **Defer real-time OMD-C/OMD-D until historical research proves value.** A full direct end-user stack is materially more expensive and operationally complex than historical files. Real-time depth should be a measured product decision, not prestige infrastructure.
5. **Do not buy IIS merely to duplicate public HKEX announcements.** Issuer Information Feed Service is a latency/redistribution product. SNI first needs to prove that public-source latency materially harms the user job.

### Core ruling

```text
historical research value proof
→ rights/economics decision
→ bounded real-time product proof
```

not

```text
buy real-time full depth
→ search for a reason to use it
```

---

## 2. Current house coverage

| Capability | Current house source/owner | State | Strength | Limitation |
|---|---|---:|---|---|
| HK daily price/volume and broad stock context | existing HK market/library stores | `PARTIAL` | sufficient for current daily state and charts | exact adjusted-history depth/freshness varies; no first-party full book |
| Current HK quote/display | existing quote/product owners | `PARTIAL` | current price display where live | not a governed full-depth/microstructure history |
| HK regime and driver attribution | `engine/hk_market_drivers.py` and adjacent HK owners | `PROVEN_LIVE` display context | HK-native global/China/funding/flow context | not issuer-specific alpha |
| HK official event tape | `engine/hk_filing_bus.py`, `hk_placements` | `PROVEN_LIVE` display context | results/buyback/placement/mandate context | taxonomy/corpus incomplete versus full issuer-information feed |
| BABA→9988 overnight bridge | `engine/hk_adr_bridge.py` | `PROVEN_LIVE` display context | direct same-issuer U.S.-to-HK context | no ordinary-equivalent basis, order-book or intraday detail |
| Tencent overnight context | KWEB proxy in ADR bridge | `PARTIAL` | China-internet group context | not Tencent-specific evidence |
| Per-stock Southbound holdings | Eastmoney-derived `hk_southbound` owner | `PARTIAL` | daily-ish holdings/share/value/change observations | third-party mirror, value changes price-contaminated, rights/display unknown, no participant-level first-party view |
| CCASS participant/shareholding data | none accepted | `NOT_BUILT` | — | licensed/rights decision open |
| HK stock-options history | none accepted | `NOT_BUILT` | — | paid first-party qualification open |
| HK securities full-book history | none accepted | `NOT_BUILT` | — | paid first-party qualification open |
| HK real-time full depth | none licensed | `NOT_BUILT` | — | materially higher fee/operational stack |

---

## 3. User and machine jobs by source class

| Source class | User job | Machine/research job | What it cannot establish alone |
|---|---|---|---|
| Historical full-book securities | Understand how 9988/0700 actually trade through auction, open, lunch, close, event and stress states | Learn queue/depth/spread/order-flow/session distributions; build normal-vs-abnormal microstructure baselines | investor identity, future direction, causality |
| Historical stock-options full book/trades | Understand actual HK options structure and event response | Build IV/skew/liquidity/aggression/campaign observations and event history | opening intent, investor identity, profitable signal |
| CCASS shareholding | Understand holder/participant concentration and changes | Point-in-time ownership/participant observations and corrections | beneficial-owner intent, live flow, directional conviction |
| Southbound holdings | Understand mainland Connect ownership level/change | Compare share-count and value changes through time | “smart money,” investor motive, all mainland activity |
| Real-time OMD-C | See live depth/session changes | Real-time anomaly and execution-quality research | alpha without prospective validation |
| Real-time OMD-D | See live options depth/trades | intraday options event/campaign research | trade direction or signal authority by default |
| Issuer Information Feed | Faster official announcements | low-latency event intake | complete company intelligence without parsing/evidence/ontology |
| Short-selling statistics | Observe disclosed short-sale activity | native short-volume/turnover history | short interest, net bearish positioning, future returns |

---

## 4. Historical HKEX products

Official product page observed:

`https://sc.hkex.com.hk/TuniS/www.hkex.com.hk/eng/ods/historicalData.aspx`

### 4.1 Securities market

| Product | Published content | Delivery clock | Published price | SNI assessment |
|---|---|---|---:|---|
| Historical Full Book — Securities Market, binary | every order and trade for Main Board/GEM | daily, normally ~20:30 | HK$5,000/month | **Preferred H1 research candidate** if internal use/selection/storage rights qualify |
| Historical Full Book — Securities Market, CSV | same content, CSV | daily, normally ~22:00 | HK$5,000/month | preferred for fastest research start; measure size/parse cost |
| Historical Order Book and Statistics Update | intraday order-book/statistics CSV | daily | price not fully resolved in this pass | compare with full book; may be sufficient for some session features |

### 4.2 Stock-options market

| Product | Published content | Delivery clock | Published price | SNI assessment |
|---|---|---|---:|---|
| Historical Full Book — Derivatives Market (SOM), binary | every order/trade on stock-options market | daily, normally ~14:30 next/post trading day | HK$1,500/month | **Preferred H1 options candidate** |
| Historical Full Book — Derivatives Market (SOM), CSV | same in CSV | daily, normally ~14:30 | HK$1,500/month | fastest research start |
| Trade File — Derivatives Market (SOM) | stock-options trades | daily | HK$750/month | lower-cost alternative if book depth is not necessary |
| Tick-by-Tick — Stock Futures/Options | transaction details for stock futures/options | daily | HK$500/month | low-cost transaction-history candidate; verify exact coverage/contracts |
| Bid and Ask Record — All Futures/Options | intraday best bid/ask | daily/monthly file | HK$300/month daily or HK$150/month monthly on current profile page | useful low-cost quote baseline; less complete than full book |

### 4.3 Illustrative pilot economics

A three-month CSV research pilot using:

- Securities Full Book: 3 × HK$5,000
- Stock-Options Full Book: 3 × HK$1,500

has published file charges of approximately **HK$19,500**, before tax, delivery, storage, legal/commercial review, or any other charges.

This is not a purchase recommendation. It demonstrates why historical qualification should precede a six-figure annual real-time stack.

### 4.4 H1 required questions before purchase

1. Does the product deliver whole-market files, and may Mastermind retain/filter only 9988/0700 internally?
2. What historical start date is available and at what backfill price?
3. What are internal research, model-training, derived-data, screenshot, and customer-display rights?
4. Are identifiers stable across corporate actions, counter changes and contract adjustments?
5. Does stock-options SOM cover both 9988 and 0700 for the intended period and maturities?
6. Are auction, odd-lot, broker/participant, order amend/cancel and trade-condition fields present?
7. What is the file-size/storage/parse budget for one, three and twelve months?
8. What corrections/replacements occur after delivery?
9. Can a short paid sample or historical trial be purchased without a standing real-time licence?
10. Does historical data require non-display or derived-use fees beyond the posted file charge?

---

## 5. Real-time OMD-C securities economics

Official fee pages:

- End users: `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Market-Data/End_users?sc_lang=en`
- Vendors: `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Market-Data/Market-Data-Vendors?sc_lang=en`

### 5.1 Published end-user line items

| OMD-C product | End-user licence / quarter | first direct connection / quarter | individual streaming / month |
|---|---:|---:|---:|
| Securities Standard | HK$33,300 | HK$45,000 | Level 1 HK$120 |
| Securities Premium | HK$43,200 | HK$58,500 | Level 2 up to 10 levels/broker queue HK$200 |
| Securities FullTick | HK$64,800 | HK$87,600 | Full Book HK$400; Level 2+One HK$240 |

Other published items include:

- HK$10,000 one-off connection fee;
- non-display usage categories: automated trading and tradable derived data at HK$20,000/firm/month, “others” at HK$400/firm/month on the current fee page;
- Mainland Market Data Hub connection multipliers;
- network, hardware, certification, test, and operational costs outside the table.

An illustrative FullTick direct end-user licence plus first direct connection totals HK$152,400 per quarter, or HK$609,600 per year, before user, non-display, network, test, support, tax, redundancy and other costs. This arithmetic does not determine which licence category applies to Mastermind.

### 5.2 Vendor/redistribution stack

The current Securities FullTick vendor fee page lists:

- redistribution: HK$99,300/quarter;
- first direct connection: HK$87,600/quarter;
- full-book subscriber: HK$400/month;
- third-party/minimum, non-display and related-company rights separately.

Customer-facing SNI depth would therefore require a materially different decision from internal research.

### 5.3 OMD-C conclusion

Do not purchase OMD-C for SNI-1. Re-open only if:

1. historical full-book studies demonstrate a reproducible user/research capability unavailable from existing feeds;
2. a real-time experience has a concrete latency/freshness requirement;
3. Data OS/legal classify internal non-display and customer-display use;
4. source delivery and runtime ownership are assigned without creating an SNI market-data plane;
5. annual economics fit the product tier.

---

## 6. Real-time OMD-D derivatives economics

Official fee pages:

- End users: `https://www.hkex.com.hk/services/rules-and-forms-and-fees/fees/listed-derivatives/market-data/end_users?sc_lang=en`
- Vendors: `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Listed-Derivatives/Market-Data/Market-Data-Vendors?sc_lang=en`

### 6.1 Published end-user line items

| OMD-D product | End-user licence / quarter | first direct connection / quarter | individual streaming / month |
|---|---:|---:|---:|
| Derivatives Standard | HK$12,600 | HK$15,000 | Level 1 HK$25 |
| Derivatives Premium | HK$16,500 | HK$19,500 | Level 2 HK$75; Level 2+One HK$90 |
| Derivatives FullTick | HK$24,750 | HK$29,250 | Full Book HK$300 |

Other current line items:

- HK$10,000 one-off connection fee;
- non-display automated trading / tradable derived products HK$10,000/firm/month; other non-display HK$150/firm/month;
- direct/indirect connection and user reporting conditions.

An illustrative Derivatives FullTick direct end-user licence plus first connection totals HK$54,000 per quarter, or HK$216,000 per year, before user, non-display, network, testing, support, tax and redundancy.

### 6.2 OMD-D conclusion

Historical SOM data is the correct first step. Real-time OMD-D becomes relevant only after the system proves that:

- 9988/0700 stock-options liquidity and coverage are sufficient;
- book/trade observations improve research or the user workflow;
- an existing options owner can ingest and govern the data;
- no duplicate HK options campaign/event lifecycle is created;
- rights and annual cost are accepted.

---

## 7. CCASS Shareholding Data Display Licence

HKEX launched/advertises a dedicated **CCASS Shareholding Data - Display Licence** application surface (Form D1/D1m). Public pages observed in this pass confirm the licence/form and current information-vendor listings, but do not expose enough fee, field, historical, internal-use, derived-use, or redistribution terms to approve capture.

Official forms surface:

`https://www.hkex.com.hk/services/rules-and-forms-and-fees/forms/securities-%28hong-kong%29/market-data/hkex-is?sc_lang=en`

### 7.1 Why CCASS may matter

Potential user/machine value:

- first-party participant/shareholding observations;
- better identity/coverage/correction semantics than a third-party mirror;
- potential history and participant concentration;
- customer display rights if properly licensed;
- direct comparison with Southbound holdings and issuer/custody changes.

### 7.2 What CCASS cannot be called without additional evidence

- beneficial-owner truth;
- live fund flow;
- “smart money”;
- bullish/bearish intent;
- a trade signal;
- complete mainland ownership.

### 7.3 Required CCASS qualification packet

Before any licence decision, obtain written answers on:

1. exact fields and entity/participant identifiers;
2. history depth and update/publication clock;
3. amendments/corrections;
4. display versus internal/non-display rights;
5. derived aggregates/models;
6. screenshots, charts and API delivery to customers;
7. storage/retention;
8. per-user/reporting requirements;
9. fees/minimums/deposit;
10. relationship to public CCASS search;
11. whether historical bulk purchase exists;
12. whether only licensed vendors may redistribute.

### 7.4 Comparison experiment

For 9988 and 0700, compare first-party CCASS against the current Eastmoney-derived Southbound store on:

- date coverage;
- share-level agreement;
- missing/revision behavior;
- participant versus aggregate detail;
- latency;
- actionability for research;
- display rights;
- maintenance risk.

A mismatch is a discovery, not permission to overwrite either source.

---

## 8. Issuer Information Feed Service

The current HKEX market-data vendor fee page lists Issuer Information Feed Service redistribution at HK$45,000 per quarter.

Potential value:

- lower-latency structured issuer-announcement feed;
- less brittle discovery than scraping public pages;
- clearer service-level and redistribution terms under licence.

Why it is deferred:

- SNI-1 can build correct reference twins from public official documents and existing owners;
- latency value has not been measured;
- the canonical Company Event/HK filing owner should own any feed, not SNI;
- HK$180,000/year published redistribution fee precedes implementation/network/support costs;
- buying IIS without event convergence would accelerate fragmented truth.

Re-open when event-latency loss is measured and the Company Event owner has an ingestion design.

---

## 9. Short selling and Stock Connect

### 9.1 Short-selling data

Use official HKEX daily short-selling observations where the house owner is accepted. Preserve:

- eligible-security status;
- trade date/publication time;
- short-sale turnover/volume;
- coverage and market share.

Do not label daily short-selling volume as short interest or investor conviction.

### 9.2 Stock Connect

Preserve distinct objects:

- market-level quota/use;
- Southbound aggregate flow;
- per-stock holdings level;
- per-stock share-count change;
- participant/CCASS observations where licensed.

Market-level quota is not per-stock flow. Holding-value change is not pure share flow. Northbound daily net-flow fields curtailed/zeroed since 2024 must not be treated as a live zero.

---

## 10. Rights decision tree

```text
Can the source be accessed?
  ↓
Is the source first-party or an accepted canonical proxy?
  ↓
What exact use is proposed?
  ├─ internal viewing
  ├─ non-display analytics/model training
  ├─ derived display
  ├─ raw display
  ├─ redistribution/API
  └─ automated trading
  ↓
Does a public term explicitly permit it?
  ├─ yes → record receipt and constraints
  ├─ no/unclear → contract review required
  └─ prohibited → rights_blocked
  ↓
Does an existing Mastermind owner already possess it?
  ├─ yes → extend owner/consumer seam
  └─ no → source owner ruling before build
```

Access is never treated as a licence.

---

## 11. Historical research preregistration before H1 purchase

A purchase should answer predeclared questions rather than begin open-ended data mining.

### H1-Q1 — session grammar

Does first-party full-book history materially improve descriptive prediction of:

- spread/depth distribution;
- auction/open/lunch/close liquidity;
- high/low formation time;
- abnormal volume/depth states;
- event-day liquidity;
- cross-counter price alignment;

relative to existing OHLCV/quote baselines?

### H1-Q2 — event response

Can 9988/0700 full-book features measured before/at an official event explain or classify subsequent liquidity/volatility regimes out of sample better than simple price/volume baselines?

This is research context, not direction or trade authority.

### H1-Q3 — stock options

Do HK stock-options quote/book/trade observations provide stable, sufficiently covered state variables around results and major events for 9988/0700?

Primary outputs are coverage, liquidity, skew/term/expected-move and event evolution—not P&L.

### H1-Q4 — incremental product value

Can a user answer a real question with the new data that cannot be answered from existing feeds? Examples:

- “Is today’s liquidity impairment abnormal for Tencent at this session time?”
- “Did Alibaba’s event reprice stock-options expectations before the underlying move?”
- “Is the cross-counter basis explained by asynchronous market state or an unusual order-book imbalance?”

No user capability means no real-time escalation.

---

## 12. Storage and compute qualification

Before purchase, run a sample-file sizing exercise and record:

- compressed/uncompressed bytes/day;
- rows/messages/orders/trades/day;
- parse throughput;
- partition scheme;
- retention cost at 3/12/60 months;
- corrections/re-delivery behavior;
- minimum data needed for one-name research versus whole-market context;
- whether licensing permits filtered retained extracts;
- R2/store-host home;
- no git storage.

SNI must not create a parallel market-data lake. The accepted Data OS/market-data owner stores the source; SNI reads derived/qualified artifacts.

---

## 13. Decision matrix

| Candidate | Unique value | Cost/complexity | Rights certainty | Recommendation |
|---|---|---|---|---|
| Existing house HK + Eastmoney Southbound | immediate broad context | low incremental | mixed/unknown for public raw display | **Use now with semantic/rights disclosure** |
| Historical securities Full Book | high microstructure research value | HK$5k/month file charge + storage/parse | requires purchase terms | **First paid research candidate** |
| Historical SOM Full Book | high HK options research value if liquid | HK$1.5k/month + parse | requires purchase terms | **Pair with H1 pilot** |
| Lower-cost SOM trade/bid-ask files | cheaper coverage/viability probe | HK$150–750/month depending file | requires terms | **Fallback/minimum viable options probe** |
| CCASS display licence | potentially high ownership/participant value | fee/terms not public in this pass | unresolved | **Obtain formal quote/terms; no build yet** |
| OMD-C Premium/FullTick real time | premium live market product | high recurring + ops | formal licence available | **Defer until H1 value proof** |
| OMD-D Premium/FullTick real time | premium live options product | meaningful recurring + ops | formal licence available | **Defer until H1 coverage/value proof** |
| IIS | low-latency issuer event feed | HK$45k/q redistribution + integration | formal licence | **Defer; event owner must justify** |

---

## 14. Exact next commercial action

No purchase should be made from this document.

After SNI-1 design approval, the lawful bounded commercial-research action is:

> Request non-binding product documentation/terms and sample-file access for HKEX Historical Full Book Securities CSV, Historical Full Book Derivatives SOM CSV, the lower-cost SOM quote/trade alternatives, and CCASS Shareholding Data Display Licence. Ask explicitly about internal research, model training, derived display, retention, filtered extracts, customer screenshots/API, historical backfill, corrections, and fees. Return the packet to Data OS/legal/Chairman before purchase.

The request itself should not promise purchase, accept terms, or disclose confidential company strategy beyond the minimum product-use description.

---

## 15. Source anchors

- Securities market-data vendor fees:  
  `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Market-Data/Market-Data-Vendors?sc_lang=en`
- Securities end-user fees:  
  `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-%28Hong-Kong%29/Market-Data/End_users?sc_lang=en`
- Derivatives market-data vendor fees:  
  `https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Listed-Derivatives/Market-Data/Market-Data-Vendors?sc_lang=en`
- Derivatives end-user fees:  
  `https://www.hkex.com.hk/services/rules-and-forms-and-fees/fees/listed-derivatives/market-data/end_users?sc_lang=en`
- Historical data product list/prices:  
  `https://sc.hkex.com.hk/TuniS/www.hkex.com.hk/eng/ods/historicalData.aspx`
- CCASS display licence forms:  
  `https://www.hkex.com.hk/services/rules-and-forms-and-fees/forms/securities-%28hong-kong%29/market-data/hkex-is?sc_lang=en`
- OMD-D FAQ/licence distinction:  
  `https://www.hkex.com.hk/Global/Exchange/FAQ/Market-Data/Getting-Market-Data/Orion-Market-Data-Platform-Derivatives-Market-OMDD?sc_lang=en`

---

## 16. Final ruling

For Alibaba/Tencent, **historical full-book securities + historical stock-options qualification is the rational first paid-data frontier**. It can create genuine research capability at a fraction of the published direct real-time stack and tell us whether live depth is worth owning.

CCASS is potentially strategic but cannot be approved from public information alone. Real-time OMD-C/OMD-D is a later product/economics decision. IIS is a latency option, not a prerequisite for truthful single-name intelligence.

The reference twin should become excellent first by composing truth, identity, clocks, corrections and existing intelligence correctly. Expensive data should then deepen a proven organism, not compensate for an unfrozen architecture.