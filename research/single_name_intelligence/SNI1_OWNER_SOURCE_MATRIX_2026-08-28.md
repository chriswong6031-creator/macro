# SNI-1 Owner / Source / Clock Matrix — Alibaba and Tencent

**Date:** 2026-08-28  
**Authority:** architecture/research only; no source acquisition or product authority  
**Parent design:** `docs/superpowers/specs/2026-08-28-sni1-reference-twin-design.md`  
**Pickup:** Macro `0863c549f728c718bbe82cc883e89843c0eb710a`  

This matrix answers one question for every reference-twin field:

> Which existing Mastermind owner supplies it, at what clock and semantic precision, and what must SNI render when that owner cannot yet supply it?

It is deliberately not a list of every available dataset. A source belongs only when it serves a named user/machine job and does not duplicate an owner.

---

## 1. Status vocabulary

| State | Meaning here |
|---|---|
| `PROVEN_LIVE` | The owner path and a real output/consumer were previously accepted as live. |
| `BUILT_NOT_PROVEN` | Implementation exists; required natural or production proof remains open. |
| `PARTIAL` | Useful subset exists, with a named coverage/semantic gap. |
| `DARK_OR_DISCONNECTED` | Artifact exists but is not on the intended product path. |
| `BROKEN` | Intended current path is failing. |
| `SPEC_ONLY` | Architecture or reference composition only. |
| `NOT_BUILT` | No accepted implementation found. |
| `REJECTED_BY_DESIGN` | SNI must not build or consume the claimed capability. |

---

## 2. Identity and security relationships

| SNI field | Canonical owner/source | Current state | Native clock | Semantic precision | SNI treatment | Gap / typed absence |
|---|---|---:|---|---|---|---|
| `issuer.company_id` | `engine/company_intelligence/identity.py` | `BUILT_NOT_PROVEN` broadly | alias validity date | Legal issuer identity, CIK-anchored | Read canonical `company_id`; bind external IDs and source receipts | `identity_unresolved` when owner cannot resolve |
| Alibaba legal issuer | SEC filer CIK `0001577552`; Alibaba IR/HKEX | `PROVEN_LIVE` source identity | SEC accepted time / HKEX publication | Legal issuer and foreign private issuer | `cik:0001577552` | none for reference issuer |
| Tencent legal issuer | SEC entity CIK `0001293451`; HKEX issuer | `PROVEN_LIVE` source identity | SEC filing clock / HKEX publication | Legal entity identity; SEC is not Tencent’s primary results corpus | `cik:0001293451` plus HKEX external IDs | no claim of SEC company-event completeness |
| `economic_security` | No native canonical object yet; derived from identity + official listing mechanics | `NOT_BUILT` | relationship effective date | Same economic security across multiple counters | SNI relationship overlay only | `counter_relationship_unresolved` |
| Alibaba ordinary share | Alibaba IR FAQ + HKEX counters | source `PROVEN_LIVE` | effective listing/counter date | One ordinary-share security, HKD/RMB counters | group `9988` and `89988` under one security | none if source receipts current |
| Alibaba ADS | Alibaba IR/SEC | source `PROVEN_LIVE` | ADS/listing effective date | Distinct ADS security; one ADS = eight ordinary shares | distinct security, linked by conversion | `unsupported_unit_conversion` without ratio receipt |
| Tencent ordinary share | Tencent HKEX result/issuer page | source `PROVEN_LIVE` | counter effective date | One ordinary-share security, 700 HKD and 80700 RMB counters | one economic security, two counters | none if current issuer receipt available |
| `trading_counter` | Company identity listing alias + SNI relation overlay | `PARTIAL` | alias validity window | MIC/ticker/currency/session | compose counter object | `identity_unresolved` or `counter_relationship_unresolved` |
| Market calendar/session | `lib.hk_calendar`, U.S. market calendar owners | `PROVEN_LIVE` house infrastructure | session/calendar publication | Venue session identity | reference exact counter calendar | `owner_unavailable` |

### Identity finding

`security_id_for(mic, ticker)` is appropriate for canonical ticker resolution but cannot by itself express that two Hong Kong stock codes are counters of one economic security. SNI must not overwrite that owner. It emits `same_economic_security_as` / `counter_group_id` relationships and should return a future amendment request to the canonical identity owner only after the reference contract proves the need.

---

## 3. Issuer events, results, and evidence

| SNI field | Canonical owner/source | State | Clock | Precision | SNI treatment | Gap state |
|---|---|---:|---|---|---|---|
| canonical company event | Earnings Intelligence / Company Event | mixed `PROVEN_LIVE` first arc | published/accepted/available/observed | issuer event and source revisions | Read accepted event workspace when present | `owner_not_built`, `source_missing` |
| Alibaba results | Alibaba IR PDF + SEC/HKEX filing path | source `PROVEN_LIVE` | issuer publication / SEC acceptance | reported facts, segment tables, management text | bind official event/source refs; do not prefer marketing article over filing PDF | `source_missing`, `correction_pending` |
| Tencent results | HKEX results/interim report + Tencent IR | source `PROVEN_LIVE` | HKEX publication | official results, segments, operating KPIs | HKEX/issuer is primary; SEC CIK is identity only | `source_missing` |
| HK official event tape | `engine/hk_filing_bus.py` | `PROVEN_LIVE` display context | HKEX announcement date + owner observation | deterministic categories/flags over selected filing sources | use for current catalyst tape and source links | `insufficient_coverage` for unclassified/unseen event types |
| HK placements | `collectors.hk_placements` / filing bus | `PROVEN_LIVE` display context | HKEX publication | placement/rights/open-offer classification | use as event observation; capital owner remains authoritative for full state | `owner_unavailable` |
| narrative/Q&A/commitments | Earnings Intelligence E3+ architecture | `NOT_BUILT` or partial by field | source span known-at | claim/exchange-level evidence | typed absence unless accepted owner output exists | `owner_not_built` |
| correction lineage | Earnings/Company Event owner | `PARTIAL` | new source revision time | source supersession/correction | carry owner correction state; new twin generation | `correction_pending`, `conflicting_sources` |

### Source priority

For reported financial and business facts:

```text
regulatory/issuer filing or official result PDF
→ accepted canonical Company Event artifact
→ issuer IR explanatory article
→ external news/research context
```

Lower tiers may explain but never overwrite a higher-tier fact without a recorded conflict.

---

## 4. Company KPI ontology and financial series

| Domain | Source/owner | State | Clock | SNI use | Important law |
|---|---|---:|---|---|---|
| Alibaba current segment structure | June-quarter 2026 official results | source `PROVEN_LIVE` | result publication | ontology version `alibaba.segment.v2026q2` | Never splice onto older segment series without source-provided recast/mapping |
| Alibaba commerce KPIs | official results/annual/interim reports | `PARTIAL` | event publication | CMR, quick commerce, e-commerce group, 88VIP where reported | “not reported” is absence, not carry-forward |
| Alibaba AI/cloud KPIs | official results | `PARTIAL` | event publication | segment revenue/EBITA, AI-related product revenue, capex | management target/ARR and realized revenue are distinct |
| Tencent segment structure | Q2 2026 HKEX result | source `PROVEN_LIVE` | HKEX publication | VAS, Marketing Services, FinTech/Business Services, Others | Preserve segment revenue and gross-margin basis |
| Tencent operating KPIs | Q2 result | `PARTIAL` | event publication | Weixin/WeChat MAU, QQ MAU, subscriptions | definition and averaging basis travel with series |
| historical comparable series | Earnings/financial-series owners | `PARTIAL` | period end + known-at | render only source-compatible versions | definition change produces version boundary |
| consensus/estimates | licensed expectation owner where available | `PARTIAL` / source dependent | snapshot known-at | future SNI expectation lens; SNI-1 only reports coverage | no unlicensed consensus synthesis |

---

## 5. Capital structure and shareholder supply

| SNI field | Owner/source | State | Clock | Precision | SNI treatment | Gap |
|---|---|---:|---|---|---|---|
| issuer capital twin | Capital Structure V2 | W1/W2A/W2B `PROVEN_LIVE`; W2C/D `BUILT_NOT_PROVEN`; W3+ held | first-known/retrieval/source publication | source manifests, events, later issuer state | consume accepted fields with owner status | `owner_built_not_proven`, `owner_not_built` |
| Alibaba Aug 2026 placement | Alibaba/HKEX official announcement; capital owner when compiled | source `PROVEN_LIVE`, owner convergence pending | pricing/completion publication | 710m new shares, price, proceeds/use | material event; do not compute final diluted share basis until capital owner publishes | `provisional_owner_output` |
| Alibaba buybacks/convertibles | official IR/HKEX/SEC + capital owner | `PARTIAL` | transaction/filing clocks | exact action and unit | read source event; owner state controls current capital calculation | `source_missing` |
| Tencent daily buybacks | HKEX next-day disclosure returns | source `PROVEN_LIVE` | submission/publication, transaction dates inside form | repurchase shares/prices and cancellation state | event stream; distinguish purchased-not-yet-cancelled from issued-share balance | `source_missing` |
| Tencent awards/options/debt | HKEX announcements | `PARTIAL` | publication | source events | display event/state only | `insufficient_coverage` |
| share count | canonical capital/issuer source | `PARTIAL` | period/event publication | issued/treasury/outstanding at named basis | never infer from one event alone | `owner_not_built`, `provisional_owner_output` |

---

## 6. Instrument behavior and market path

| SNI field | Owner/source | State | Clock | Precision | SNI treatment | Gap |
|---|---|---:|---|---|---|---|
| BABA Identity Atlas | Stock Identity W1 | `PROVEN_LIVE` | artifact as-of | fingerprint, state, path episodes; zero authority | reference artifact and its coverage mask | none for W1 fields |
| BABA identity epoch | Stock Identity W4 | `NOT_BUILT` | future `knowable_from` | true PIT epoch | render provisional `epoch_0` disclosure only | `owner_not_built` |
| expert fit/SIF | Stock Identity W3–W6 | `NOT_BUILT` | future owner clocks | conditional fit/abstention | no SNI substitute | `owner_not_built` |
| 9988/0700 daily bars | existing HK stock/data owners | `PARTIAL` | completed HK session | daily OHLC/volume at owner basis | reference source and freshness | `source_stale`, `insufficient_history` |
| current HK quote | existing live quote/HK product owners | `PARTIAL` | exchange/source timestamp | display quote | selected counter quote only; no issuer-wide price | `source_stale`, `owner_unavailable` |
| HK market drivers | `engine/hk_market_drivers.py` | `PROVEN_LIVE` display context | daily source as-of | deterministic driver projections | context only | `owner_unavailable` |
| HK regime/axes | existing HK owners | owner-specific | daily/session | market context | consume accepted owner output | owner-state-specific absence |

### BABA W1 evidence already available

The existing BABA dossier provides deep adjusted history, a metric fingerprint, diagnostic gap features, and path-anchored episode catalog. It explicitly declares:

- zero authority;
- provisional listing-to-date `epoch_0`;
- survivor-only limitations;
- coverage/unstable flags.

SNI must preserve those disclosures, not summarize them away.

---

## 7. Cross-listing and overnight context

| SNI field | Owner/source | State | Clock | Precision | Treatment | Gap |
|---|---|---:|---|---|---|---|
| BABA→9988 overnight context | `engine/hk_adr_bridge.py` | `PROVEN_LIVE` display organ | U.S. close after HK close on same calendar date | direct same-issuer percent move context | label direct bridge, next-HK-session context | `source_stale`, `asynchronous_market` |
| BABA/9988 ordinary-equivalent basis | SNI derived from official ratio + FX + counter prices | `NOT_BUILT` | exact price/FX clocks | diagnostic basis only | allowed deterministic composition with market-state flags | `unsupported_currency_conversion`, `asynchronous_market` |
| Tencent overnight context | current ADR bridge uses KWEB | `PARTIAL` proxy only | KWEB U.S. close | China internet group proxy | preserve `proxy, no direct ADR`; never call Tencent-specific | `insufficient_coverage` for issuer bridge |
| TCEHY or other Tencent-specific source | no qualified owner | `NOT_BUILT` | — | unknown quality/rights | future qualification only | `owner_not_built` |

---

## 8. Options, volatility, and positioning

| SNI field | Owner/source | State | Clock | Precision | Treatment | Gap |
|---|---|---:|---|---|---|---|
| BABA U.S. options structure | canonical U.S. options owners; current site GEX/structure artifacts exist | mixed owner state | event/EOD/source clocks | IV/OI/GEX/campaign observations at owner grain | reference exact owner authority and freshness | owner-specific absence |
| BABA live-flow/campaign | Options Alpha/live-flow owners | `PARTIAL` | event/observation/decision/available clocks | observed trade+NBBO/campaign evidence | consume only accepted artifacts | `owner_built_not_proven`, `source_missing` |
| 9988 stock options | no accepted SNI owner | `NOT_BUILT` | — | — | typed absence; HKEX source qualification | `owner_not_built`, `source_unlicensed` |
| 0700 stock options | no accepted SNI owner | `NOT_BUILT` | — | — | typed absence; HKEX source qualification | `owner_not_built`, `source_unlicensed` |
| HKEX historical stock-options full book | paid first-party candidate | `NOT_BUILT` | daily post-session file | every order/trade | research qualification only | `source_unlicensed` |
| HKEX real-time OMD-D | paid first-party | `NOT_BUILT` | real time | market depth/full order | future commercial gate | `source_unlicensed`, `rights_blocked` |

Options semantics remain native observations. OI, volume, skew, GEX, and trade location do not establish investor identity or direction by themselves.

---

## 9. Holdings, flow, and ownership

| SNI field | Owner/source | State | Clock | Precision | Treatment | Gap |
|---|---|---:|---|---|---|---|
| Southbound holdings level | `engine/hk_southbound_stocks.py` / Eastmoney mirror | `PARTIAL` | latest disclosed hold date | holding shares/value and ratios | label third-party holdings observation | `source_stale`, `rights_state_unknown` |
| Southbound share-count change | same owner | `PARTIAL` | captured dates | price-independent change when history has depth | context, not directional intent | `insufficient_history` |
| holding-value change | same owner | `PARTIAL` | captured dates | price-contaminated change | never label pure net buying | `insufficient_coverage` |
| first-party CCASS | HKEX candidate | `NOT_BUILT` | licensed publication | participant/shareholding data according to product | compare to current source under formal licence | `source_unlicensed` |
| short selling | HKEX official statistics / current house owners where present | `PARTIAL` | daily publication | turnover/volume, not short interest intent | native observation | `owner_unavailable` |
| treasury/issuer buybacks | HKEX issuer filings + Capital Structure | `PARTIAL` | transaction/publication | issuer supply action | separate from investor flow | owner-specific absence |

### Required semantic repair

Existing source comments sometimes use “smart money” and “dominant marginal buyer.” SNI cannot propagate those phrases into the reference twin. The source proves a disclosed holdings observation and derived change, not investor sophistication, motive, or future direction.

---

## 10. China/HK policy, news, and narrative

| SNI field | Owner/source | State | Clock | Precision | Treatment | Gap |
|---|---|---:|---|---|---|---|
| official China policy context | China official corpora / policy owners | `PROVEN_LIVE` or owner-specific | publication/observation | source-level policy text/diffs | issuer exposure context only | `owner_unavailable` |
| HK/China native news | China/HK native wire owners | `PARTIAL` | article/wire time | title/body/timing per rights | link/derived topic context; no raw restricted redistribution | `rights_blocked`, `source_missing` |
| onshore/offshore narrative divergence | existing GDELT/native owner | `PARTIAL` | source aggregation time | descriptive divergence | context only | `insufficient_history` |
| issuer official announcements | HKEX/IIS/IR | `PROVEN_LIVE` public source | publication | primary issuer facts | highest priority | `source_missing` |
| issuer-information real-time feed | HKEX IIS paid redistribution | `NOT_BUILT` | real time | issuer announcement feed | not needed for SNI-1; future latency/rights decision | `source_unlicensed` |

---

## 11. Relationships, themes, and read-through

| SNI field | Owner | State | Clock | Treatment | Gap |
|---|---|---:|---|---|---|
| customer/supplier/partner/competitor | canonical graph/relationship owners | mixed | evidence first-known/last-known | use resolved, evidence-backed edges only | `identity_unresolved`, `source_missing` |
| theme exposure | theme/ontology owner | mixed | membership known-at | context with source-root versus economic-dependence distinction | `owner_unavailable` |
| reporting-wave context | Earnings/relationship owner | partial/spec | event known-at | no independent SNI graph | `owner_not_built` |
| Alibaba/Tencent pair view | SNI composition over owner outputs | `NOT_BUILT` | component clocks | compare factors, residuals, capital, events; never merge identities | `insufficient_coverage` |

---

## 12. Rights states

Closed SNI v1 rights vocabulary:

```text
public_primary_derived_display_allowed
public_primary_raw_display_allowed
internal_research_allowed
customer_display_licence_required
non_display_licence_required
redistribution_licence_required
contract_review_required
rights_unknown
rights_blocked
not_applicable
```

A repository collector comment is not a legal grant. Every new source adapter must bind a Data OS rights decision or render `rights_unknown`.

---

## 13. Reference source manifests

### 13.1 Alibaba priority

1. Alibaba official financial reports / HKEX / SEC filings.
2. Accepted Earnings/Company Event object.
3. Capital Structure owner.
4. Company identity owner.
5. BABA Stock Identity.
6. BABA U.S. market/options owners.
7. HK 9988/89988 market owners.
8. HK market drivers/ADR bridge.
9. China/HK official policy/news owners.
10. Licensed expectations/relationships where available.

### 13.2 Tencent priority

1. HKEX/Tencent official results, interim/annual reports, issuer announcements.
2. Accepted Earnings/Company Event object where coverage exists.
3. Capital Structure/HK issuer-capital owners.
4. Company identity owner.
5. HK 700/80700 market owners.
6. HK market drivers.
7. Official buyback/share-change disclosures.
8. Southbound/ownership context with explicit source semantics.
9. China/HK policy/news owners.
10. Qualified HK stock-options source when available.

---

## 14. SNI-1 owner-adapter boundary

An adapter is allowed only to:

- read an accepted owner artifact;
- validate its schema/authority/freshness;
- reference or project declared fields;
- attach typed absence when the artifact is not lawful/current;
- preserve payload digest and lineage.

It may not:

- re-run the owner’s research or scoring;
- scrape a substitute because the owner is absent;
- change owner state from `BUILT_NOT_PROVEN` to live;
- write to the owner store;
- make an LLM summarize missing facts into existence;
- fuse native observations into direction.

---

## 15. First implementation entrance checks

Before SNI-1A planning/execution:

1. Re-fetch current protected Skillpack and Macro/Terminal heads.
2. Reconcile open PR #6529 and any new Company Identity/Earnings/Capital/HK/options carriers.
3. Confirm no canonical owner has since added economic-security/trading-counter relationships.
4. Confirm official Alibaba/Tencent counter mechanics and current KPI definitions.
5. Reconfirm HKEX fee/licence pages and Data Marketplace products.
6. Record one carrier per bounded PR.
7. Keep all forecast, rank, gate, size, signal, and trade authority false.

---

## 16. Matrix conclusion

The reference twin is feasible without new upstream collection because the estate already contains much of the required truth. The principal gaps are:

1. a governed issuer/security/counter relationship projection;
2. deterministic owner/status/absence composition;
3. versioned Alibaba/Tencent KPI ontologies;
4. current coverage convergence across official event, capital, path, and options owners;
5. first-party HK microstructure/CCASS qualification;
6. a real read-model consumer.

Those gaps justify SNI-1. They do not justify another data platform.