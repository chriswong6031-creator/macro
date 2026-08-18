# BPC-RECON-0 — JV snapshot archaeology and source-system reconstruction freeze

Status: **AWAITING SOL REVIEW**. Architecture freeze only. No runtime producer, no soak change, no Prophet authority, no new model.

Date: 2026-08-18  
Workstream: `WS:BPC-JV-RECON`  
Program: `biocatalyst` (`authority_class: context_only`)  
Session: `claude/bpc-recon-0` at `macro-main/.claude/worktrees/bpc-recon-0`

This document is the reconstruction spec. It tells the next implementation PR exactly which BioPharmCatalyst (BPC) snapshot columns are primary-source facts Mastermind can rebuild, which are export-time overlays that must never become historical features, and which stay BPC editorial or model output. Authorized snapshots are the only BPC evidence used here. BPC's continuous private API is unavailable by partnership design and was not inspected.

---

## 0. Verdict

Mastermind can independently reconstruct the **approved-drug event spine** and the **earnings / IPO calendars**. It cannot reconstruct a live BPC-class product from these snapshots without new producers (device/CDRH, conference calendar, issuer-disclosed PDUFA NLP) and without a rights unlock on the already-written Drugs@FDA collector.

**First vertical (this freeze's only implementation recommendation): RECON-1 — Drugs@FDA approved-event reconstruction ledger.** Hermetic replay of the existing dark collector against the JV Historical FDA **Approved** rows after unshift. Live ZIP ingest stays blocked. The CT.gov B1S2c / `b2_history_canary` soak is not touched.

Three rights facts that bound every later PR:

1. Keep `biopharmcatalyst_benchmark` verbatim. This freeze adds a **separate** source identity, `biopharmcatalyst_jv_snapshot`, for finite authorized-seed matching only (`DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK`).
2. Catalyst events share `company_identity.v1` and `company_event.v1` lifecycle / publication clocks. They do **not** reuse fiscal `event_workspace.v1` ids (`DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE`).
3. `pdufa_date` remains a forbidden claim on Drugs@FDA. Forward PDUFA is an issuer-disclosure problem owned by the corporate plane, not a second SEC ingest.

---

## 1. Evidence boundary

Operator dump (local, 2026-08-17 00:51–01:20). **Do not commit row dumps.** Hashes belong in this freeze; importing proprietary rows as a production feed is the existing `proprietary_historical_row_import` prohibition.

| File | Bytes | SHA256 |
|---|---:|---|
| `BioPharmCatalyst_Tables.xlsx` | 353,040 | `946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535` |
| `BioPharmCatalyst_All_Companies_Sorted_By_Ticker.csv` | 86,364 | `a08afff0430c06138997f6b8a3e28fee63bb742eecdb4ea936c8bea99f225ee0` |
| `biopharmcatalyst_historical_fda_all_verified_2009_2026.csv` | 5,630,777 | `f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002` |
| `biopharmcatalyst_mergers_acquisitions.csv` | 268,490 | `aa33b6dea553b982b32621a3ee759d20283c25b1e6d267289f6e7d38e5afb3fd` |
| `biopharmcatalyst_hedge_funds.csv` | 63,192 | `fbb968bae5f4f5f6a33f21ee6c02db4450f26cf19aa765ae6e2a6e7212164640` |

Workbook facts, re-read this session: nine visible sheets, no hidden sheets. Dates are DD/MM/YYYY, usually with an `ET` timezone label rather than a time. Earnings Calendar carries `HH:MMAM ET`. Duplicate xlsx also sits untracked at `Mastermind/BioPharmCatalyst_Tables.xlsx`; the Downloads dump is the hashed evidence.

The "nine datasets" are the nine xlsx sheets. The four CSVs are extra authorized snapshots and are specified below. Untracked `scraped_*.json` / `scraped_biopharmcatalyst_*.csv` under occupied checkouts are **out of scope** and are not evidence.

Unique tickers across all eleven sources: **1,907**. Largest overlap: Earnings ∩ Historical FDA = 358.

---

## 2. Rights split

| Identity | What it is | What it may do | What it may not do |
|---|---|---|---|
| `biopharmcatalyst_benchmark` | Historical clean-room policy. **Unchanged.** | Behavioral parity review, public feature inventory, clean-room acceptance benchmark | Production feed, authenticated scraping, asset/code copy, proprietary historical row import |
| `biopharmcatalyst_jv_snapshot` | **New.** Finite authorized seeds (this dump). `production_ingest_allowed: false` | Schema/clock census, reconstruction matching, coverage scoring | Production feed, continuous BPC API, committing BPC rows, joining export-time fields onto historical event rows as pre-event features |

`license_class: finite_jv_snapshot_seed` is added beside `benchmark_only`. Projection, bulk redistribution, and model training stay blocked. Raw bytes stay operator-held, never git.

Do not silently rewrite the benchmark YAML. Tests in this PR pin both the old meaning and the new distinct id.

---

## 3. Clock split and poison list

Two clocks exist in every snapshot. Mixing them is the failure mode this freeze exists to prevent.

**Event-clock** — a fact as-of a named historical date (catalyst date, offer date, JPM window, earnings print). Reconstruct from a date-keyed primary source or from dated daily OHLCV. Label dated OHLCV as **non-W1A**: Market Memory W1A is a go-forward `operational_pit` store and cannot backfill past catalyst PIT (`DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT`; `WS:MARKET-MEMORY-W2C`).

**Export-time** — the market/options overlay as of dump capture (~2026-08-17). Never a pre-event feature on a 2009–2026 historical row.

### Poison (never join onto historical event rows as pre-event features)

| ID | Field family | Why |
|---|---|---|
| P1 | Current Price (`Price`, `Price % $`) | Composite `$X ±Y ±Z%` at export |
| P2 | 30 Day Price Change | Sparkline blob or trailing window at export |
| P3 | Market Cap | Export snapshot |
| P4 | Volume, Average Daily Volume, Relative Volume | Export snapshot |
| P5 | Open, Previous close | Intraday/session snapshot, not event date |
| P6 | Current IPO price and Return | Live tape vs offer; first-day close is event-clock and allowed |
| P7 | Implied Volatility, Open Interest, Days to Expiration, Strike, Call/Put, Expiration Date | Polygon EOD options chain via `engine/options_hub.py` / `engine/gex_model.py` — **nightly, not live**, and still today's chain |
| P8 | Option bid/ask/last | ThetaData is wired for **option contracts** only and is DARK; no equity NBBO plane exists |
| P9 | Expected Move ($ / % / up / down) | Derived `engine/gex_model.py:376 expected_move(iv30, …)` from tonight's IV |
| P10 | live `Options` flag | The string `View` — a BPC UI link indicator, not a chain |
| P11 | export `Last Updated`, BPC `company_url` / `catalyst_url` / `fund_url` | Site chrome and BPC permalinks |

Equity bid/ask (a Catalyst Impact cousin of P8 on the **underlying**) is **NONE** anywhere in the estate.

### Event-clock tape (allowed if date-keyed and labeled non-W1A)

Price at Catalyst Date, Catalyst Price Movement, IPO price, Price after first day, JPM Price at Start / End / Change.

---

## 4. Reconstruction ledger states

Every reconstructable fact in a later matcher emits one of:

| State | Meaning |
|---|---|
| `JV_SNAPSHOT_SEED` | Present in the authorized dump; not yet reproduced |
| `REPRODUCED_PRIMARY` | Independent primary source emitted the same fact (date-keyed, receipt-backed) |
| `MASTERMIND_DERIVED` | Mastermind computed it from primary facts (dated OHLCV return, expected-move formula on a **historical** IV if one exists) |
| `MODEL_RECREATED` | A Mastermind model would have to be built to approximate a BPC model (LoA/LoP). Out of scope for RECON-0/1 |
| `UNEXPLAINED` | Seed fact with no primary owner and no honest derivation |

Coverage scores below count **primary-source facts only**. Model, community-vote, and BPC editorial prose are excluded from the denominator.

---

## 5. Column classification

Legend — **clock**: `identity` / `event` / `export` / `editorial` / `model` / `community` / `link`. **Owner**: existing plane, missing producer, or none.

### 5.1 Device Catalysts (11 × 12)

| Column | Clock | Owner | Ledger |
|---|---|---|---|
| Ticker, Name | identity | `company_identity.v1`; healthcare baskets ~92 tickers, not a device-applicant join | `REPRODUCED_PRIMARY` only after issuer map |
| Price, 30 Day Price Change, Options, Last Updated | export | poison P1/P2/P10/P11 | never historical |
| Device, Indication | event | **missing** CDRH / openFDA 510k/PMA (+ De Novo/HDE HTML) | `JV_SNAPSHOT_SEED` until device pack |
| Device Stage | editorial | BPC taxonomy, not FDA's | `UNEXPLAINED` as FDA stage; keep as BPC label |
| Catalyst Date, Catalyst | event / editorial | pending-catalyst prose is BPC; clearance date may later match CDRH | mix |
| Bullish or Bearish | community | HTML vote blob | `MODEL_RECREATED` / community — not first vertical |

### 5.2 Device Pipeline (839 × 18)

Same identity / device / stage / catalyst pattern as 5.1, plus export-time capital/tape overlay:

| Column | Clock | Owner | Notes |
|---|---|---|---|
| No Of Shares, Market Cap, Volume, ADV, RVOL, Open, Previous close | export | poison P3–P5 | |
| Price to Book | export | `engine/stock_fundamentals.py` `price_to_book` via yfinance, ~110 names; FIF-2 still `todo` (`WS:FINANCIAL-INTELLIGENCE-FABRIC`) | Coverage for biotech/small-cap unconfirmed |

### 5.3 PDUFA Calendar (78 × 10)

| Column | Clock | Owner | Notes |
|---|---|---|---|
| Ticker, Name | identity | identity plane | |
| Price, 30 Day Price Change, Options | export | poison | |
| Drug | event | name string; Drugs@FDA product names cover **approved** corpus, not pending | |
| Notes | editorial | BPC | |
| PDUFA Date | event | **no official complete forward calendar** (already recorded: teardown 2026-08-01 §12.3). Issuer 8-K / press via **corporate plane** (`sec_company_facts_and_filings` owner `corporate_intelligence`; biocatalyst `direct_duplicate_sec_ingest` is prohibited). `pdufa_date` stays in Drugs@FDA `prohibited_claims` | 50/78 filled |
| Priority Review Date | event | same issuer-disclosure path | 28/78 filled |
| Advisory Committee Date | event | FDA AdCom calendar / Federal Register — **missing producer** | **0/78 filled** on this dump |

### 5.4 Device History (666 × 9)

| Column | Clock | Owner |
|---|---|---|
| Ticker, Name | identity | identity plane |
| Catalyst Price Movement, Price at Catalyst Date | event | dated daily OHLCV, **non-W1A labeled** |
| Device, Indication | event | CDRH history (missing) |
| Device Stage | editorial | BPC taxonomy |
| Catalyst Date | event | CDRH decision date where the event is a clearance |
| Catalyst | editorial | BPC prose |

### 5.5 IPO Calendar (407 × 7)

| Column | Clock | Owner |
|---|---|---|
| Ticker, Company | identity | `collectors/ipo_calendar.py` + `engine/ipo_radar.py` (`SCORED=False`) |
| IPO price | event | Nasdaq IPO calendar / prospectus (`collectors/ipo_prospectus.py`) |
| Price after first day | event | dated OHLCV, non-W1A |
| Current price, Return | export | poison P6 |
| Offer date | event | existing IPO collector |

Highest existing-infra coverage of the nine sheets. Remaining work is a biopharma filter plus PIT first-day close wiring, not a new producer.

### 5.6 JPM26 Conference (237 × 12)

| Column | Clock | Owner |
|---|---|---|
| Time (ET), Ticker, Company | event / identity | **missing** conference producer; best public-company path is 8-K Item 7.01 via corporate plane; organizer sites have no APIs |
| Market Cap, Price | export | poison |
| Presentation Info, Notes | editorial | |
| Catalyst Change, Deals | editorial | **fill = 0** on this dump |
| Price at Start, Price at End, Price Change | event | dated OHLCV over the JPM window, non-W1A |

### 5.7 Catalyst Impact (124 × 24)

JV overlay sheet. Stage / drug / indication / catalyst date are event-clock; everything from Options through Open Interest is export-time options; LoA/LoP are BPC models; Bullish or Bearish is community.

| Column | Clock | Owner |
|---|---|---|
| Ticker, Drug, Indication, Stage, Catalyst Date, Catalyst | identity / event / editorial | CT.gov current-state + record-history canary may confirm **trial stage** for some names; PDUFA clocks are not Drugs@FDA |
| Price, Options | export | poison P1/P10 |
| Expiration Date, Call or Put, Days to Expiration, Strike, IV, EM $/%/up/down, Bid, Ask, Last, OI | export | `WS:ADVANCED-DATA-OPTIONS` — Polygon EOD chain, nightly; EM formula `gex_model.expected_move`; option NBBO DARK; **poison P7–P9** |
| Likelihood of Approval, Likelihood of Progressing | model | BPC; 122/124 numeric. `MODEL_RECREATED` only — **no new model in RECON-0/1** |
| Bullish or Bearish | community | HTML blob |

### 5.8 Conferences (150 × 16)

| Column | Clock | Owner |
|---|---|---|
| Ticker, Name | identity | |
| Price, 30 Day Price Change, Options | export | poison |
| Conference, start date, end date, Acronym, Type, indication type, drugs, abstract date, description | event / editorial | **missing** conference producer |
| abstract link, link | link | organizer URLs; not a Mastermind source identity |

### 5.9 Earnings Calendar (504 × 13)

| Column | Clock | Owner |
|---|---|---|
| Ticker, Name | identity | |
| Price, 30 Day Price Change, Options | export | poison |
| Date | event | `collectors/equity_earnings.py` (Nasdaq unofficial earnings calendar) |
| Prior EPS, EPS, EPS Est, EPS Surprise | event | surprise history on the same collector |
| Revenue, Rev Est, Revenue Surprise | event | **licensed revenue consensus is not this collector**; treat estimates as coverage-gap unless a licensed feed is already owned elsewhere |

Do not start a parallel earnings producer. `WS:EARNINGS-INTELLIGENCE-OS` E2 owns that plane.

### 5.10 All Companies CSV (134 tickers × 13)

| Column | Clock | Owner |
|---|---|---|
| Ticker, Name, Description | identity / editorial | universe list, not a fact spine |
| Price % $, 30 Day Price Change, Market Cap, Options | export | poison; 30d column is a **sparkline blob** (`price,unix_ts,…`), not a scalar |
| P1, P2, P3, PDUFA, Approved, Pipeline | derived counts | **integers, not booleans**. Reconstructable only after the pipeline/PDUFA/approval planes exist. Not a first-vertical target |

### 5.11 Historical FDA CSV (15,700 × 13)

**Load-bearing defect (`DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT`):** 4,404 / 15,700 rows (**28.1%**) are left-shifted (missing `row` index), so `stage` holds a date. Unshift before any seed matching. Independently re-counted this session against SHA256 `f3852d34…d9002`.

| Column | Clock | Owner |
|---|---|---|
| row | artifact | drop after unshift |
| ticker, name | identity | reviewed CT.gov sponsor map is **not** a general device/applicant join (`engine/biocatalyst/sponsor_identity.py`) |
| catalyst_price_movement, price_at_catalyst_date | event | dated OHLCV, non-W1A |
| drug, indication | event | Drugs@FDA product names for **Approved**; otherwise 8-K / editorial |
| stage | event / editorial | **`Approved` + date** is the only cell plausibly `REPRODUCED_PRIMARY` from Drugs@FDA after unshift + rights unlock. CRL / Phase / PDUFA-stage rows are BPC editorial or issuer 8-K |
| catalyst_date | event | Drugs@FDA submission action date for approvals; else issuer |
| catalyst | editorial | BPC prose. `catalyst_url` hosts are mostly `biopharmcatalyst.com` (6,285), then BusinessWire; ~17 `accessdata.fda.gov` |
| conference | editorial | |
| company_url, catalyst_url | link | poison P11 as a feature; URL host is allowed as a **match hint**, not a production source |

### 5.12 Mergers & acquisitions CSV (1,433 × 13)

No Mastermind owner. `engine/capital_structure/` plus `biocatalyst_pit_adapter.py` is **lifecycle / share count**, not deal intelligence. `acquirer_company` embeds ticker + “Add to portfolio”. Entire sheet stays `JV_SNAPSHOT_SEED` / `UNEXPLAINED` until a dedicated M&A plane exists. Not RECON-1.

### 5.13 Hedge funds CSV (594 rows / 38 funds × 9)

`engine/institutional_census/` + `engine/company_institutional_context/` can reconstruct a **13F subset**, not BPC's product view (largest holding, QoQ change as BPC computes it, empty `fund_url`). Overlap scoring is a later research consumer, not a producer.

---

## 6. Owner map — existing planes vs missing

Do not duplicate an owner plane that already exists.

| Plane | Status | Notes |
|---|---|---|
| CT.gov v2 | **live ingest** (`production_ingest_allowed: true`) | current-state API; `BIOCATALYST_ENABLED` default false |
| CT.gov record history | **live ingest**, canary | `b2_history_canary` / `BIOCATALYST_HISTORY_ENABLED`; allowlist NCT04528082, NCT05020236, NCT06602479, NCT07218380. This is the running soak. **Do not modify.** Committed label is not the string `B1S2c` |
| Soak window | `config/biocatalyst_launch_slo_manifest.yml` `state: soak_scheduled` | 2026-08-12T02:00:00Z → 2026-08-26T02:00:00Z; `aggregate_passed: false` |
| AACT | dark, `review_required_before_b1` | |
| openFDA | **stub** | YAML names `collectors.biocatalyst.openfda_regulatory`; module **does not exist** (`DSC:BPC-OPENFDA-PRODUCER-IS-STUB`). `collectors/biocatalyst/` = CT.gov modules + `drugs_at_fda.py` only. Legacy `collectors/openfda.py` is a non-biocatalyst display adapter |
| Drugs@FDA | **collector fully implemented, dark** | `rights_state: review_required_before_b4`; `production_ingest_allowed: false`. Graph: `engine/biocatalyst/regulatory.py` — approved-product corpus, not pending/PDUFA/IND/CRL completeness. `scripts/biocatalyst_regulatory_worker.py` raises `no B4A production collection path is installed` |
| SEC / EDGAR | **corporate_intelligence** | biocatalyst prohibited: `direct_duplicate_sec_ingest` |
| Identity | `engine/company_intelligence/identity.py` | CIK-anchored `cik:XXXXXXXXXX`; ticker is PIT alias. `WS:STOCK-IDENTITY` is Prophet fingerprints — orthogonal |
| Events | `company_event.v1` | `canonical_event_id = evt_cik{10}_{year}{qN\|fy}_{type}` from earnings-shaped `EVENT_TYPES` (`events.py:93-100`). `event_workspace.v1` is an **earnings payload**; live universe AAPL FY2026 Q3 only; `claim_citations_pending` must stay True |
| Earnings calendar | live | `collectors/equity_earnings.py` |
| IPO calendar | live | `collectors/ipo_calendar.py` |
| Capital structure | live / PIT adapter | shares outstanding, not M&A deals |
| 13F | live | institutional census |
| Live quotes | latest-only | `engine/live_quotes.py` Polygon US / Yahoo fallback; **no equity bid/ask** |
| Options IV / OI / EM | nightly EOD | `engine/options_hub.py`, `engine/gex_model.py` |
| Market Memory W1A | go-forward only | cannot supply PIT prices for past events |

**Missing (net-new, not RECON-1):** device/CDRH producer + device-applicant→issuer join; conference calendar producer; M&A deal intelligence; forward PDUFA NLP on the corporate plane; FDA AdCom scraper.

`engine/earnings_narrative/biocatalyst_transcript_adapter.py` is a reader wrapper, `persistence_authorized: False`.

---

## 7. Entity and event model

Compose; do not fork a second event bus.

- **Issuer** = `company_identity.v1` (CIK). Ticker is a PIT alias.
- **Asset / product** = FDA application / device 510(k)|PMA|De Novo identifier where one exists; otherwise an explicit `unidentified_asset` coverage class. Do not invent ticker-as-drug.
- **Catalyst event** shares identity, lifecycle (`observed_at`, `source_available_at`), and publication discipline with `company_event.v1`.
- **Do not** stuff PDUFA / device / conference / IPO into `evt_…_{year}fy_action`. That id function requires a fiscal period (`events.py:102`, `canonical_event_id`). A later PR may extend `EVENT_TYPES` and generalize the id function. Until then, reconstruction matching keys (ticker + date + drug/device name) are the join, not a new bus.
- `event_workspace.v1` stays earnings: fiscal period, facts/deltas/guidance/claims. Catalysts do not inherit those keys.

Authority remains `context_only`. All prophet flags stay false. `DNR:KILL-PHASE3-START-WEIGHT` is untouched.

---

## 8. Pipeline map (target shape, not this PR)

```
producer (primary, Mastermind-owned)
  → immutable evidence (pinned ZIP / filing / page receipt)
  → normalized fact (existing contracts: fda_regulatory_event.v1, company_event.v1, …)
  → entity join (company_identity.v1; reviewed sponsor map only where attested)
  → reconstruction matcher (JV seed, operator-held, never git)
  → reconstruction_ledger.jsonl (states in §4)
  → product projection (existing app/biocatalyst.py context cards)
  → research consumer (coverage report; not Prophet)
```

Export-time overlays (quotes, IV, OI, EM, P/B) attach only to **as-of-now** product views, never to historical matcher rows.

---

## 9. Coverage scores

Denominator = reconstructable **primary-source facts** on the sheet (identity + event-clock dates/names that a public primary source could emit). Excludes poison overlay, BPC editorial prose, community votes, and BPC models.

Calibrated, not row-exact. “Existing infra” includes dark-but-implemented collectors.

| Dataset | Existing infra | Needs new producer | Never (editorial / model / community) | Read |
|---|---:|---:|---:|---|
| Device Catalysts | ~10% | CDRH + applicant→issuer join | Device Stage taxonomy, sentiment, pending prose | Overlay only until device pack |
| Device Pipeline | ~10% | same | same | P/B overlay is ~110-name yfinance, not biotech-complete |
| PDUFA Calendar | ~5% | 8-K NLP on corporate plane; AdCom scraper | Notes | No official forward calendar; Drugs@FDA cannot emit `pdufa_date` |
| Device History | ~15% | CDRH history | Catalyst prose, BPC stage | Dated OHLCV can fill price-at-date as `MASTERMIND_DERIVED` |
| IPO Calendar | **~70%** | PIT first-day close wiring | — | Filter existing Nasdaq collector; current price/return poison |
| JPM26 Conference | ~10% | 8-K 7.01 + agenda | Deals/Notes/Catalyst Change (empty here) | Window tape via dated OHLCV |
| Catalyst Impact | ~15% | PDUFA clocks; historical options PIT | LoA/LoP, community | Overlay is export-time; do not back-join |
| Conferences | ~10% | conference producer | Type/indication/links editorial | Organizer sites: no API |
| Earnings Calendar | **~65%** | licensed revenue consensus | — | Collides with `WS:EARNINGS-INTELLIGENCE-OS` if rebuilt |
| Historical FDA CSV | **~5–15%** after unshift | 8-K for CRL/Phase/PDUFA-stage | catalyst prose | Approved+date only from Drugs@FDA |
| All Companies counts | ~0% | after pipeline/PDUFA/approval planes | Description | Integers, not booleans |
| M&A CSV | **0%** | deal-intelligence plane | BPC chrome in acquirer field | Capital structure ≠ deals |
| Hedge funds CSV | ~30% as 13F subset | BPC product metrics | empty fund_url | Not a BPC clone |

---

## 10. Ranked backlog

Ordered by user value × missing coverage × research value × implementation leverage. One first vertical only.

| Rank | Item | Why this order |
|---|---|---|
| **1. RECON-1** | Drugs@FDA approved-event spine vs JV Historical FDA clean Approved rows | Collector already written; contract `fda_regulatory_event.v1` exists; hermetic tests possible; soak untouched; rights stay dark |
| 2 | IPO biopharma filter + dated first-day close | High existing coverage; small wiring; poison current return |
| 3 | Earnings calendar consume-existing (no new producer) | Already live; do not collide with E2 |
| 4 | Device/CDRH pack + applicant→issuer identity | Largest missing plane; identity is the hard part |
| 5 | Forward PDUFA as corporate-plane 8-K monitoring | Source hole; forbidden on Drugs@FDA; NLP + exact-wording confidence |
| 6 | Conference producer (8-K 7.01 + bounded agenda pages) | Net-new; no organizer API |
| 7 | Historical FDA unshift + CRL/Phase as 8-K editorial, not FDA | After RECON-1 matcher exists |
| 8 | Dated OHLCV overlay for price-at-catalyst / JPM window | `MASTERMIND_DERIVED`, non-W1A labeled; depends on matched event dates |
| 9 | 13F overlap vs hedge-fund snapshot | Research consumer, not a BPC clone |
| 10 | M&A deal plane | No owner; large; not catalyst-critical |
| — | LoA/LoP / community vote | `MODEL_RECREATED`; **no new model in this program until Sol asks** |
| — | Equity NBBO / ThetaData undark | Out of BioCatalyst scope; `WS:ADVANCED-DATA-OPTIONS` |

---

## 11. RECON-1 — first vertical specification

`DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE`

**Not done unless** all of the following land in a later implementation PR (not this freeze PR):

1. **Producer** — existing `collectors.biocatalyst.drugs_at_fda` over a **pinned ZIP fixture** already used by tests. Do not flip `production_ingest_allowed`. Do not call the live archive URL from production.
2. **Immutable evidence** — exact `archive_sha256` receipt + table manifest (already the collector's identity rule).
3. **Normalized fact** — `engine/biocatalyst/regulatory.py` `fda_regulatory_event.v1` / `fda_application_dossier.v1`. No new event bus.
4. **Join** — ticker via existing identity / reviewed sponsor map only where attested; unmatched rows stay `unidentified_issuer`, never guessed.
5. **Real consumer** — context-only reconstruction report consumed by existing `app/biocatalyst.py` (or a sibling context card). `authority_class: context_only`. Zero Prophet flags.
6. **Matcher** — operator-held Historical FDA CSV (this dump's SHA256). Unshift 28.1% shifted rows first. Restrict to `stage=Approved` after unshift. Match drug name + date ±1 calendar day + ticker when identity exists. Emit `reconstruction_ledger.jsonl` with the five states in §4.
7. **Tests** — hermetic. A shifted-row fixture must fail until unshifted. An export-time Price/IV column must be rejected if offered as a pre-event feature.
8. **Production proof** — CI replay of the pinned archive. Live Drugs@FDA ZIP ingest remains blocked until Sol advances `rights_state`.

**Out of RECON-1:** PDUFA NLP, device pack, LoA model, soak/env changes, committing BPC rows, W1A backfill, `event_workspace.v1` reuse, `biopharmcatalyst_benchmark` edits.

**Why not the alternatives:** forward PDUFA is a source hole plus a forbidden collector claim; device is unbuilt plus identity; conference is net-new; IPO is already live (filter only); earnings collides with E2.

---

## 12. Questions for Sol (`needs_ceo`)

Primary (blocks the next build session):

1. **Approve RECON-1 as specified in §11** (hermetic Drugs@FDA approved spine, rights stay dark, soak untouched), versus starting with device/CDRH or PDUFA NLP instead?

Secondary (do not block the freeze; answer before RECON-1 merges):

2. Confirm `biopharmcatalyst_jv_snapshot` as a distinct finite-seed identity — operator-held rows, never git, never a production feed. Default: **yes**, landed as architecture in this PR.
3. Confirm catalyst events must not reuse fiscal `event_workspace.v1` ids. Default: **yes** (`DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE`).
4. Advance `drugs_at_fda` `rights_state` to allow live ZIP ingest? Recommendation: **not in RECON-1**. Replay first.

---

## 13. Landmines and do-not-redo

- Occupied `macro-main` / `Macro Dashboard` checkouts may contain unauthorized `scraped_*.json` BPC artifacts. They are not this freeze's evidence. Do not census, commit, or cite them.
- `macro-main` is a linked worktree of `Macro Dashboard/.git`. Never delete or relocate that folder.
- Sibling `biocatalyst-p0-*` worktrees own the soak/product path. Open PRs to be aware of: #5821 (BCI architecture docs), #5901 (Capital Structure V2 freeze).
- `scripts/biocatalyst_worker.py` is `canary_poll` only.
- GitHub annotations must start the line; not relevant to this docs PR except if a later producer logs inside Actions.
- A write into a sparse worktree's omitted `data/` **truncates** committed artifacts. RECON-1 must not `git add -A` under `data/`.
- Disarming `merge-on-green` is never silent; this freeze PR **must not be armed** — it waits on Sol.

### Do not redo

- Re-hash this dump (hashes in §1, re-verified 2026-08-18).
- Re-count the Historical FDA 28.1% left-shift.
- Re-litigate `biopharmcatalyst_benchmark` permitted/prohibited uses.
- Propose stuffing PDUFA into `evt_…_fy_action`.
- Build LoA/LoP or a community-vote scraper as the first vertical.
- Duplicate SEC ingest inside biocatalyst.
- Touch `b2_history_canary` allowlist, `BIOCATALYST_HISTORY_ENABLED`, or the soak window.
- Treat Market Memory W1A as a historical PIT price source for past catalysts.
- Treat `collectors.biocatalyst.openfda_regulatory` as implemented.

---

## 14. This PR's architecture land

In the same research PR as this freeze, and still not a runtime:

- `license_class: finite_jv_snapshot_seed`
- source row `biopharmcatalyst_jv_snapshot` with `production_ingest_allowed: false`
- tests that the benchmark YAML meaning is unchanged and the new id is distinct
- Agent OS: `WS:BPC-JV-RECON`, three DECs, three DSCs, one handoff

No producers. No collectors. No soak YAML edits other than the new source key.
