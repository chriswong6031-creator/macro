# BPC-RECON-0 — JV snapshot archaeology and source-system reconstruction freeze

Status: **ARCHITECTURE ACCEPTED** (Sol 2026-08-19). RECON-0 complete pending merge of PR #5909. Architecture freeze only. No runtime producer, no soak change, no Prophet authority, no new model, no snapshot ingestion in this PR. Do not start SNAPSHOT-ONBOARD or CONTINUOUS-RECON.

Date: 2026-08-18; rights amendment 2026-08-19; corpus-state correction 2026-08-19; Sol acceptance writeback 2026-08-19  
Workstream: `WS:BPC-JV-RECON`  
Program: `biocatalyst` (`authority_class: context_only`)  
Session: `claude/bpc-recon-0` at `macro-main/.claude/worktrees/bpc-recon-0`

Architectural DECs in this freeze are **accepted** (`DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK`, `DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE`, `DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE`; `decided_by: ceo-sol`, `decided_at: 2026-08-19`). The JV permission premise remains Chairman-confirmed (`DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN`; `decided_by: chairman`).

This document is the reconstruction spec. It tells later PRs which BioPharmCatalyst (BPC) snapshot columns are primary-source facts Mastermind can rebuild, which are export-time overlays that must never become historical pre-event features, and which stay BPC editorial or model output. Authorized snapshots are the only BPC evidence used here. BPC's continuous private API is unavailable by partnership design and was not inspected.

**Program completion** is not a hermetic Drugs@FDA matcher. The program is done when (1) the licensed snapshot corpus is onboarded and useful, (2) the necessary independent source producers can continuously regenerate the targeted data families, (3) owner-plane projections are wired to website/machine consumers, and (4) research can use the data under PIT rules. That work is split into two later concepts — **licensed snapshot onboarding** and **continuous source reconstruction** — and is **not built in this PR**.

---

## 0. Verdict

Mastermind can independently reconstruct the **approved-drug event spine** and the **earnings / IPO calendars**. It cannot reconstruct a live BPC-class product from these snapshots without new producers (device/CDRH, conference calendar, issuer-disclosed PDUFA NLP) and without a rights unlock on the already-written Drugs@FDA **continuous** collector.

A hermetic Drugs@FDA matcher against JV Historical FDA **Approved** rows remains a recommended **calibration / reconstruction component**. CI replay of a pinned ZIP is **not** production proof and is **not** an independently useful completed production vertical. A later real-input → real-consumer proof is specified in §11.

Accepted as foundation (Sol 2026-08-19): source archaeology, temporal poison list, owner-plane census, Historical FDA left-shift, options/W1A ruling, event-plane composition direction, source-reconstruction map.

Three rights facts that bound every later PR:

1. Keep `biopharmcatalyst_benchmark` verbatim. Add a **separate** source identity, `biopharmcatalyst_jv_snapshot`, with **finite-snapshot rights** distinct from **continuous-feed rights** (`DEC:BPC-JV-SNAPSHOT-IS-NOT-BENCHMARK`, `DEC:BPC-JV-FINITE-SNAPSHOT-RIGHTS-CHAIRMAN`).
2. Catalyst events share `company_identity.v1` and `company_event.v1` lifecycle / publication clocks. They do **not** reuse fiscal `event_workspace.v1` ids. Ticker + date + drug/device is a `jv_reconciliation_match_key`, never canonical event identity (`DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE`).
3. `pdufa_date` remains a forbidden claim on Drugs@FDA. Forward PDUFA is an issuer-disclosure problem owned by the corporate plane, not a second SEC ingest.

---

## 1. Evidence boundary

### 1.1 Four-workbook census

The original supply was four Excel workbooks in a 3→6→8→9-sheet sequence, plus four CSVs. Durable truth has three layers. Do not collapse them (`DSC:BPC-JV-PREDECESSOR-WORKBOOKS-NOT-ON-DISK`).

**1. Local operator state.** Only W4 bytes were available on the operator filesystem searched 2026-08-19 and hash-verified there. Search protocol: Spotlight `BioPharmCatalyst*`; content search for sheet name `Device Catalysts`; all `Downloads/New Folder With Items*`; `Mastermind/BioPharmCatalyst_Tables.xlsx`; Trash; recent `.xlsx` mtime 2026-08-01..19; Mail/Slack/Cursor attachment paths. Two copies, same SHA256, nine sheets. That local discovery is valid only as a local-environment statement.

**2. Global corpus state.** W1, W2, W3, and W4 all still exist in the Chairman's File Library and are members of the authorized licensed corpus. Sol independently verified this on 2026-08-19. They are not lost and not globally unrecovered.

| Capture | Filename in File Library | Tabs | Created (File Library) | Local SHA256 |
|---|---|---:|---|---|
| W1 | `BioPharmCatalyst_Tables.xlsx` | 3 | 2026-08-16T08:33:25Z | *not invented — hash only when bytes are in the implementation environment* |
| W2 | `BioPharmCatalyst_Tables(1).xlsx` | 6 | 2026-08-16T08:36:13Z | *not invented* |
| W3 | `BioPharmCatalyst_Tables(2).xlsx` | 8 | 2026-08-16T08:36:58Z | *not invented* |
| W4 | `BioPharmCatalyst_Tables(3).xlsx` | 9 | 2026-08-16T08:38:14Z | `946c5f725ebfd3b71d254f229e006ba055a868a1d5d02d3344a74efb3882b535` (local operator copies only; 353,040 bytes; File Library W4 is not independently hashed here) |

**3. Relationship state.** `UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS`. Do **not** call W4 a proven superset of W1–W3. Do **not** call W1–W3 lost. The unresolved question is whether W4 is a superset of W1–W3 with identical common-sheet content.

**4. Temporal law.** W1→W4 must **not** be treated as four temporal vintages or as evidence of BPC row revisions unless a later deterministic comparison proves time-varying common-sheet content. Creation timestamps span ~5 minutes. Sol's spot checks: Device Pipeline reaches the same row 838 in W1/W2/W3/W4; PDUFA rows 71–77 agree across W1/W2/W3/W4. Those observations make progressively broader export packages the leading hypothesis. Full common-sheet equality has not been proven.

**5. SNAPSHOT-ONBOARD census obligation (not this PR).** When the actual four workbook bytes are made available to that implementation environment, compute for each:

workbook SHA-256 → ordered sheet set → dimensions per sheet → deterministic normalized row hash / exact worksheet-content hash → common-sheet equality/delta.

Classify each pair as one of:

- `ADDITIVE_SHEET_EXPORT_IDENTICAL_COMMON_CONTENT`
- `COMMON_SHEET_CONTENT_CHANGED`
- `DISTINCT_CAPTURE`
- `UNRESOLVED`

Preserve any genuinely unique predecessor rows if found. Do not invent predecessor SHA-256 values from File Library metadata.

W4 facts from the local copies, re-read: nine visible sheets, no hidden sheets. Dates are DD/MM/YYYY, usually with an `ET` timezone label rather than a time. Earnings Calendar carries `HH:MMAM ET`.

### 1.2 Four additional CSVs (kept; hashes unchanged)

| File | Bytes | SHA256 |
|---|---:|---|
| `BioPharmCatalyst_All_Companies_Sorted_By_Ticker.csv` | 86,364 | `a08afff0430c06138997f6b8a3e28fee63bb742eecdb4ea936c8bea99f225ee0` |
| `biopharmcatalyst_historical_fda_all_verified_2009_2026.csv` | 5,630,777 | `f3852d34aad9b65d95e31db807f9509cfb84770eb91998533cb3687cea3d9002` |
| `biopharmcatalyst_mergers_acquisitions.csv` | 268,490 | `aa33b6dea553b982b32621a3ee759d20283c25b1e6d267289f6e7d38e5afb3fd` |
| `biopharmcatalyst_hedge_funds.csv` | 63,192 | `fbb968bae5f4f5f6a33f21ee6c02db4450f26cf19aa765ae6e2a6e7212164640` |

**Historical FDA correction:** 4,404 / 15,700 rows (28.1%) are left-shifted (`DSC:BPC-HISTORICAL-FDA-CSV-LEFT-SHIFT`). Later onboarding must preserve the **raw** CSV (this SHA256) and a **deterministic repaired** form as separate artifacts. Do not overwrite the raw bytes with the unshifted table.

This PR does **not** ingest snapshot rows. Licensed snapshot onboarding is a later wave. Untracked `scraped_*.json` / `scraped_biopharmcatalyst_*.csv` under occupied checkouts are **out of scope** and are not evidence.

Unique tickers across the locally hashed eleven sources (9-sheet W4 + 4 CSVs): **1,907**. Largest overlap: Earnings ∩ Historical FDA = 358. This count is a local-W4 census, not a four-workbook union.

---

## 2. Rights split

Chairman confirms (2026-08-19) the supplied BPC datasets are authorized for Mastermind storage/use, website/product incorporation, repository incorporation, and research / pattern / signal-development programs. The restriction is that Mastermind does **not** receive continuing BPC API access. Research permission is **not** Prophet or trade authority.

`production_ingest_allowed` on this registry is the **continuous live-producer** gate (`scripts/biocatalyst_worker.py`). It stays `false` on the JV snapshot identity. Finite-snapshot import/storage is a **separate** capability block and is allowed.

| Identity | What it is | Finite snapshot | Continuous feed |
|---|---|---|---|
| `biopharmcatalyst_benchmark` | Historical clean-room policy. **Unchanged.** | Not a JV snapshot. Permitted: behavioral parity, public feature inventory, clean-room benchmark. `proprietary_historical_row_import` still prohibited **here**. | Authenticated scraping, production feed, asset/code copy prohibited |
| `biopharmcatalyst_jv_snapshot` | **New.** Licensed finite snapshots (this corpus). `license_class: licensed_finite_snapshot` | **Allowed:** import/storage, repo normalization, product projection, research/pattern/signal development | **Forbidden:** continuous BPC API, authenticated BPC scraping. `production_ingest_allowed: false` |

Export-time fields remain forbidden as historical pre-event features. They **may** be used as correctly time-stamped snapshot observations in research from their actual capture time onward (§3).

Do not silently rewrite the benchmark YAML. Tests pin (a) the old benchmark meaning, (b) the distinct JV id, (c) finite-snapshot use allowed, (d) continuous API/scraping and temporal leakage forbidden.

---

## 3. Clock split and poison list

Two clocks exist in every snapshot. Mixing them is the failure mode this freeze exists to prevent.

**Event-clock** — a fact as-of a named historical date (catalyst date, offer date, JPM window, earnings print). Reconstruct from a date-keyed primary source or from dated daily OHLCV. Label dated OHLCV as **non-W1A**: Market Memory W1A is a go-forward `operational_pit` store and cannot backfill past catalyst PIT (`DSC:BPC-W1A-CANNOT-BACKFILL-CATALYST-PIT`; `WS:MARKET-MEMORY-W2C`).

**Export-time / snapshot-capture** — the market/options overlay as of dump capture (~2026-08-17 00:51–01:20 local). Never a pre-event feature on a 2009–2026 historical row.

**Complement (research from capture time onward):** those same fields **may** be used as correctly time-stamped snapshot observations in research from their actual capture timestamp forward. They are observations of 2026-08-17, not of the catalyst date.

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

Snapshot Price / mcap / IV / OI / EM / volume as **2026-08-17 capture observations** (research from that timestamp onward; never back-joined to earlier events).

---

## 4. Reconstruction ledger states

Every reconstructable fact in a later matcher emits one of:

| State | Meaning |
|---|---|
| `JV_SNAPSHOT_SEED` | Present in the authorized dump; not yet reproduced |
| `REPRODUCED_PRIMARY` | Independent primary source emitted the same fact (date-keyed, receipt-backed) |
| `MASTERMIND_DERIVED` | Mastermind computed it from primary facts (dated OHLCV return, expected-move formula on a **historical** IV if one exists) |
| `MODEL_RECREATED` | A Mastermind model would have to be built to approximate a BPC model (LoA/LoP). Out of scope for this PR; no new model until Sol asks |
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
| Likelihood of Approval, Likelihood of Progressing | model | BPC; 122/124 numeric. `MODEL_RECREATED` only — **no new model in this PR** |
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

No Mastermind owner. `engine/capital_structure/` plus `biocatalyst_pit_adapter.py` is **lifecycle / share count**, not deal intelligence. `acquirer_company` embeds ticker + “Add to portfolio”. Entire sheet stays `JV_SNAPSHOT_SEED` / `UNEXPLAINED` until a dedicated M&A plane exists. Later Concept B; not this PR.

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

**Missing (net-new; later Concept B, not this PR):** device/CDRH producer + device-applicant→issuer join; conference calendar producer; M&A deal intelligence; forward PDUFA NLP on the corporate plane; FDA AdCom scraper.

`engine/earnings_narrative/biocatalyst_transcript_adapter.py` is a reader wrapper, `persistence_authorized: False`.

---

## 7. Entity and event model

Compose; do not fork a second event bus. **Accepted** (`DEC:BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE`, `decided_by: ceo-sol`).

- **Issuer** = `company_identity.v1` (CIK). Ticker is a PIT alias.
- **Asset / product** = FDA application / device 510(k)|PMA|De Novo identifier where one exists; otherwise an explicit `unidentified_asset` coverage class. Do not invent ticker-as-drug.
- **Canonical events** prefer **source-native IDs** (NCT, Drugs@FDA ApplNo, CDRH 510(k)/PMA number, SEC accession, Nasdaq IPO deal id) and the existing owner event plane (`company_event.v1` envelope: identity, lifecycle, `observed_at`, `source_available_at`).
- **`jv_reconciliation_match_key`** = ticker + date + drug/device name. This is a **reconciliation key against the JV snapshot**, never canonical event identity. Do not mint `evt_…` ids from this triple.
- **Do not** stuff PDUFA / device / conference / IPO into `evt_…_{year}fy_action`. That id function requires a fiscal period (`events.py:102`, `canonical_event_id`). A later PR may extend `EVENT_TYPES` and generalize the id function under Sol review.
- `event_workspace.v1` stays earnings: fiscal period, facts/deltas/guidance/claims. Catalysts do not inherit those keys.

Authority remains `context_only`. All prophet flags stay false. `DNR:KILL-PHASE3-START-WEIGHT` is untouched.

---

## 8. Pipeline map (target shape, not this PR)

```
producer (primary, Mastermind-owned)
  → immutable evidence (pinned ZIP / filing / page receipt)
  → normalized fact (existing contracts: fda_regulatory_event.v1, company_event.v1, …)
  → entity join (company_identity.v1; reviewed sponsor map only where attested)
  → jv_reconciliation_match_key (ticker + date + drug/device; never canonical id)
  → reconstruction_ledger.jsonl (states in §4)
  → product projection (existing app/biocatalyst.py context cards)
  → research consumer (PIT-safe; not Prophet)
```

Licensed snapshot onboarding (separate later concept) lands the corpus under `biopharmcatalyst_jv_snapshot` finite-snapshot rights, then the continuous producers above regenerate the targeted families. Export-time overlays attach only to **as-of-now** product views and to research observations timestamped at capture, never to historical matcher rows as pre-event features.

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

## 10. Two later concepts (not this PR)

Architecture sequencing, **not** authorization to implement these waves in #5909.

### Concept A — Licensed snapshot onboarding

Onboard the Chairman-authorized corpus under `biopharmcatalyst_jv_snapshot` finite-snapshot rights: storage, repo normalization, product projection, research use. Preserve raw Historical FDA bytes and a deterministic repaired form as **separate** artifacts. All four Excel captures (W1–W4) are licensed corpus members in the Chairman's File Library. When those bytes are in the implementation environment, run the §1.1 census (SHA-256 → sheet set → dimensions → content hashes → pair class). Do not invent predecessor hashes from File Library metadata. Do not call W4 a proven superset until that census says so. Preserve any genuinely unique predecessor rows. This is not a continuous BPC producer. Do not start this concept from PR #5909.

### Concept B — Continuous source reconstruction

Independent Mastermind-owned producers that regenerate targeted data families, wired to website/machine consumers, with PIT-safe research. Durable sequence (not a build order for this PR):

1. Licensed snapshot corpus (Concept A)
2. Approved-drug spine (Drugs@FDA continuous, after rights; calibration matcher is a component, not the proof)
3. CDRH / device spine + applicant→issuer identity
4. Issuer-disclosed PDUFA / revision intelligence (corporate plane)
5. AdCom
6. Conference events
7. Existing Earnings / IPO adapters (consume, do not duplicate)
8. Market / options overlays (capture-time observations; never historical pre-event)
9. M&A
10. Institutional context
11. Historical event-study / PIT research
12. Prospective research ledger

Hermetic Drugs@FDA ZIP replay is a **calibration component** inside item 2. It is not production proof.

---

## 11. Drugs@FDA calibration component (accepted, not program-done)

`DEC:BPC-RECON-1-DRUGSATFDA-APPROVED-SPINE` is **accepted** (`decided_by: ceo-sol`, 2026-08-19) and is **not** “done for the program.”

Recommended later component: hermetic replay of the existing dark collector against JV Historical FDA **Approved** rows after unshift, joined by `jv_reconciliation_match_key`, emitting reconstruction-ledger states. Soak untouched. `production_ingest_allowed` on Drugs@FDA stays false until a separate rights advance.

**CI replay of a pinned ZIP is not production proof.** A future real-input → real-consumer proof must, in a later PR:

1. ingest a real Drugs@FDA source release (once rights allow) or a dated operator-held archive that is the actual production input, not only the unit-test fixture;
2. emit `fda_regulatory_event.v1` facts into the owner plane;
3. reconcile against the licensed JV Approved rows via `jv_reconciliation_match_key` (never as canonical ids);
4. project to a live website or machine consumer (`app/biocatalyst.py` or successor) with `context_only` authority;
5. show a PIT-safe research read that refuses export-time Price/IV as pre-event features.

Until that chain exists, the matcher is calibration, not a completed production vertical. **Do not start it in this PR.**

---

## 12. Sol acceptance (resolved)

Sol accepted the architecture and the corpus-state correction on 2026-08-19 (PR #5909). RECON-0 is complete pending merge. After merge, return to Sol for commissioning of the first bounded SNAPSHOT-ONBOARD vertical. Do not begin SNAPSHOT-ONBOARD, CONTINUOUS-RECON, Drugs@FDA work, device/CDRH, PDUFA work, or any runtime implementation from this PR.

Accepted corpus laws remain: local filesystem had W4 only; W1/W2/W3/W4 exist globally in the Chairman's File Library; relationship is `UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS`; no predecessor hashes invented; W1→W4 are not temporal vintages without deterministic proof; export-time market/options fields cannot become historical pre-event features; finite JV snapshot rights remain separate from continuous BPC feed rights.

---

## 13. Landmines and do-not-redo

- Occupied `macro-main` / `Macro Dashboard` checkouts may contain unauthorized `scraped_*.json` BPC artifacts. They are not this freeze's evidence. Do not census, commit, or cite them.
- `macro-main` is a linked worktree of `Macro Dashboard/.git`. Never delete or relocate that folder.
- Sibling `biocatalyst-p0-*` worktrees own the soak/product path. Open PRs to be aware of: #5821 (BCI architecture docs), #5901 (Capital Structure V2 freeze).
- `scripts/biocatalyst_worker.py` is `canary_poll` only. `production_ingest_allowed` there means continuous producer.
- A write into a sparse worktree's omitted `data/` **truncates** committed artifacts. Snapshot onboarding must not `git add -A` under `data/` on a sparse tree.
- Disarming `merge-on-green` is never silent; this freeze PR **must not be armed**. Sol has accepted; keep `merge-on-green` off. Merge is a later session act after CI, not this writeback.

### Do not redo

- Re-hash the locally verified W4 workbook and four CSVs (hashes in §1).
- Re-count the Historical FDA 28.1% left-shift.
- Re-litigate `biopharmcatalyst_benchmark` permitted/prohibited uses.
- Call W4 a proven superset of W1–W3, or call W1–W3 lost / globally unrecovered. Relationship is `UNRESOLVED_PENDING_SNAPSHOT_ONBOARD_CENSUS`. The open question is whether W4 is a superset of W1–W3 with identical common-sheet content.
- Treat W1→W4 as four temporal vintages or as evidence of BPC row revisions unless a later deterministic comparison proves time-varying common-sheet content.
- Invent predecessor SHA-256 values from File Library metadata. Hash only when actual bytes are available.
- Propose stuffing PDUFA into `evt_…_fy_action`, or using ticker+date+drug as canonical event identity.
- Build LoA/LoP or a community-vote scraper.
- Duplicate SEC ingest inside biocatalyst.
- Touch `b2_history_canary` allowlist, `BIOCATALYST_HISTORY_ENABLED`, or the soak window.
- Treat Market Memory W1A as a historical PIT price source for past catalysts.
- Treat `collectors.biocatalyst.openfda_regulatory` as implemented.
- Describe CI ZIP replay as production proof.
- Start SNAPSHOT-ONBOARD, CONTINUOUS-RECON, RECON-1, device/CDRH, PDUFA NLP, or snapshot ingestion from this PR.

---

## 14. This PR's architecture land

In the same research PR as this freeze, and still not a runtime:

- `license_class: licensed_finite_snapshot` (replaces the withdrawn `finite_jv_snapshot_seed` matching-only class)
- source row `biopharmcatalyst_jv_snapshot` with `production_ingest_allowed: false` (continuous-producer gate) **and** explicit finite-snapshot capabilities allowed
- tests that the benchmark YAML meaning is unchanged; finite licensed snapshot use is allowed; continuous BPC API/scraping and temporal leakage remain forbidden
- Agent OS: `WS:BPC-JV-RECON` active, RECON-0 done pending merge; Chairman rights DEC unchanged; architectural DECs Sol-accepted (`decided_by: ceo-sol`); predecessor-workbook DSC bounded to local operator state (File Library members still exist)

No producers. No collectors. No snapshot row ingest. No soak YAML edits other than the JV source key.
