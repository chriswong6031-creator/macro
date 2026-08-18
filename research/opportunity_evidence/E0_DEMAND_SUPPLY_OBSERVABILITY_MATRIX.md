# E0 Demand / Supply Observability Matrix

**Rule:** preserve unknowns. Do not fabricate latent net demand. Missing ≠ 0.  
**Base:** `origin/main` @ `3d12412e561e`. Artifact peeks 2026-08-18 against the primary checkout.

Legend: **OBS** = observable in-repo now · **LAG** = information lag · **PIT** = reconstructible at a past decision date · **COV** = coverage · **RIGHTS** = vendor/rights constraint.

---

## 1. Matrix

| Construct | Observable now? | What you actually see | Lag | PIT? | Coverage (this session) | Must stay UNKNOWN | Rights / vendor | Owner |
|---|---|---|---|---|---|---|---|---|
| Active 13F holders (full) | **PARTIAL** | Mapped long positions, not all filings | ~45 calendar days after period-end | Yes after ReportPeriod+45d | 8,750 original filings; 2.23M long positions; **45.0% mapped**; census as_of 2026-08-09 **PRODUCTION VERIFIED** | Unmapped 55%; confidential omissions; intra-quarter trading | SEC 13F bulk; mixed value units **excluded** | `data/institutional_13f/` + EDGAR collector |
| Curated “super-investor” 13F | **OBS** | Per-slug holdings under `data/smart_money/` | Same 45d | Yes for filed periods | Curated cohort (~dozens of managers), not the market | Whether they are still in the name today | Same SEC | `engine/smart_money.py` |
| 13D / 13G activist | **OBS** (event) | `data/special_situations/events.parquet` via `engine/beneficial_ownership.py` | Days after filing | Filing date | Names with active events only | Intent beyond the filing | SEC | special_situations |
| Form 4 / insider | **OBS** | Quiver `insiders.parquet`; SEC panel `data/sec_insider/` | Days | `fileDate` | Context-vector `insider__absent` **51.7%** on 2026-08-17 | Whether insider is “smart”; cluster meaning | Quiver license + SEC | `engine/insider_intel.py` |
| Short interest (shares) | **OBS** | FINRA SI shares, DTC, change | Biweekly settlement; latest settlement **2026-07-31**, capture asof **2026-08-17** | Settlement date | Latest 1,521 names; history 4,564 rows from 2026-06-30 **PRODUCTION VERIFIED** | True borrow, who is short | FINRA | `data/finra/short_interest*.parquet` |
| Short volume (daily) | **OBS** | FINRA short-sale **volume**, not SI | T+1-ish nightly | Trade date | Broad FINRA, display-scoped | Short interest level; locate | FINRA | `engine/short_volume.py` |
| Utilization / CTB / locate | **NO** | — | — | — | — | **Entire construct** | Would be paid vendor | **UNKNOWN / NOT_BUILT** |
| ETF creations / redemptions | **THIN** | `so_mn` change in `data/flows/*.parquet` | Daily-ish; file is short | If so_mn is true shares | SPY 27 rows 2026-07-12→08-17; **AUM frozen** on last two days while NAV moved **PRODUCTION VERIFIED** | True authorized-participant flow; theme-ETF creations beyond this set | Fund-reported | `data/flows/` |
| Thematic ETF holdings | **OBS** | ARK + many theme ETFs under `data/etf_holdings/` | Daily/weekly per issuer | Vintage of file | Tracked funds only (Track C ~15–40) | “Theme demand” as a single number | Issuer sites / ARK | `engine/holdings_signals.py` |
| Index add/delete | **PARTIAL** | S&P/Russell constituent files exist | Rebalance effective vs announce | Constituents as-of | S&P 500/400/600 + Russell breadth | Announce-date PIT for historical adds | Index provider via existing breadth files | `data/breadth/`, `data/russell_breadth/` |
| Buybacks | **PARTIAL** | May appear in EDGAR / forensics; not a dedicated Opportunity field | Filing | Filing date | UNKNOWN completeness | Authorization vs actual repurchase | SEC | **PARTIAL / UNKNOWN as a series** |
| ATM / secondary / 424B | **PARTIAL** | `data/edgar/dilution_events.parquet` 48,824 rows of form-level events (many 424B2) | Filing + `_first_seen` | Filing date / first_seen | Broad EDGAR, noisy taxonomy | Economic dilution %, ATM vs ordinary shelf takedown | SEC | `collectors` dilution ingest |
| Converts / warrants / pref | **PARTIAL** | Capital-structure instrument **candidates** + document terms | Filing; large backlog | Event spine `as_of` | Health: 19,018 pending, 18,818 deferred, 403 parked **PRODUCTION VERIFIED** | Normalized share-count impact | SEC; parser deferred on conflict/media | `engine/capital_structure/` |
| Lockups | **NO structured store found** | — | — | — | — | **Entire construct** unless a filing text happens to be in CS queue | — | **UNKNOWN** |
| Options OI / volume / IV / skew | **OBS from 2026-06** | `data/options_dislocation/snapshots.parquet`; GEX; flow summaries | Same day / next bake | Snapshot date only after 2026-06-15 | 408 underlyings in dislocation store; context-vector options **86.1% absent** | Signed initiator; dealer inventory | Polygon | options_* / polygon_gex |
| Dealer gamma (modeled) | **MODELED** | `engine/gex_model.py` / `site/gex/` | Nightly + closing-bell | After 2026-06 | Liquid optionable subset | True dealer book | Model assumption | GEX board |
| Dark pool / off-exchange | **OBS** | FINRA ATS weekly + short-volume panel | Weekly ATS / daily short vol | Vendor date | ~360 gex_symbols display universe | Buyer identity | FINRA | `engine/darkpool_signals.py` |
| Off-exchange ADV / impact | **PARTIAL** | Dollar-vol 20d, rel_volume, mdv20 | Daily | Confirmed close | ~2,966 nightly | Kyle lambda / implementation shortfall | Yahoo/Massive prints | `engine/stock_technicals.py` |
| Float / share turnover | **NO distinct float turnover found** | Volume vs own history only | — | — | — | Shares traded ÷ float | Would need share-count truth | Track C gap; CS share_count_truth exists but is not a live turnover series |
| Passive / index ownership | **INFERRED only if** a name is in a constituent file | Membership, not weights over time for all indexes | Rebalance | Constituent vintage | S&P/Russell | Weight, lender of record, inclusion *announcement* alpha | Index files | breadth stores |
| Quiver congress / flights / lobbying | **OBS** | Separate parquets under `data/quiver/` | Days | file dates | Quiver universe | Causal demand | Quiver license | collectors/quiver |
| Latent net demand | **NO** | — | — | — | — | **Always UNKNOWN.** Residual price is not demand. | — | Do not invent |

---

## 2. How to use the matrix in an evidence vector

Each row becomes a **typed slot**:

```
{ construct, state: observed|unavailable|stale|unlicensed|unknown,
  asof, known_at, value_or_null, coverage_flag }
```

Rules:

1. A 13F increase known only after t0+45d **cannot** explain a t0 entry.  
2. SI asof 2026-08-17 describing settlement 2026-07-31 is **stale** for mid-August tape.  
3. Options fields before 2026-06-15 are `unavailable`, not 0.  
4. Capital-structure backlog means “no event in projection” ≠ “no ATM.”  
5. GEX / modeled gamma is `modeled`, a different state than `observed`.  
6. Never emit `net_demand = f(price, residual, volume)`.

**WA-R2 / NEXTL-U13:** ownership and 13F are **context / crowding hazard**, never a positive Opportunity input.

---

## 3. Observable buyers vs observable supply (honest split)

### 3.1 Observable *possible* buyers (lagged or partial)

- 13F filers after 45d  
- Curated super-investors after 45d  
- 13D/G activists after filing  
- ETF holding adds (when holdings files print)  
- Insider buys after Form 4  

None of these are contemporaneous demand.

### 3.2 Observable *possible* supply

- FINRA SI (biweekly)  
- Dilution form events (noisy)  
- Capital-structure instrument candidates (backlogged)  
- Secondary / 424B2 (form-level)  
- Insider sells after Form 4  

### 3.3 Not observable

Net institutional flow this week · borrow tightness · lockup unlocks as a calendar · dealer inventory · retail lot composition · latent “dry powder.”

---

## 4. Rights risks

- Quiver: licensed alt-data; do not republish raw vendor dumps beyond existing site contracts.  
- 13F: public SEC, but bulk zip SHA and mixed units already constrain the census.  
- Options: Polygon; signed-flow inference is a **rights-and-epistemics** violation (`OPTIONS_FLOW_DATA.md`).  
- Capital structure: source documents may be unsupported media / blocked; parser defers. Do not scrape paywalled transcripts into this matrix.

---

## 5. No-build warnings

- Do not create a “net demand score.”  
- Do not use SI days-to-cover as utilization.  
- Do not treat identical AUM across days as zero flow (SPY 08-13 vs 08-17).  
- Do not fill CS “no projection row” as “clean cap table.”
