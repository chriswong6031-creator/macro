# E0 Opportunity Data Census

**Mission:** GROK-E0 — inventory current inputs for a structured Opportunity Evidence Vector.  
**Not this document:** a master Opportunity Score, rank weights, or a new truth store.  
**Base:** `origin/main` @ `3d12412e561e` (2026-08-18).  
**Primary checkout used for artifact peeks:** `/Users/chriswong/Documents/Cluade/macro-main` (read-only).  
**Future consumer (existing owner):** `WS:LIVE-ENTRY-RADAR` PR-7 Opportunity model is **todo / do not start**. W6 Research Priority (`RP1`) is ACCRUING and is **not** an Opportunity Score (`research/live_entry_radar/W6_RP1_POLICY.md`).

Claim tags used below: **CODE VERIFIED** · **PRODUCTION VERIFIED** · **PRIMARY SOURCE VERIFIED** · **INFERRED** · **UNKNOWN**.

---

## 0. Existing adjacent objects — do not duplicate

| Object | What it already is | Authority | Do not do |
|---|---|---|---|
| `data/us_prophet_rank/candidates/` US Context Vector | Nightly per-name feature join including theme, attention, insider, short interest, options, forensics, spine, regime, sector, Prophet legs | Context / miss-audit memory. Producer `engine/us_context_vector.py`. README: store **remembers the score**; it is not a new Opportunity Score. | Do not mint a second per-name nightly feature store. **CODE VERIFIED** `data/us_prophet_rank/README.md` |
| Live Entry Radar RP1 | Deterministic Research Priority: equal Borda of available dimension percentiles. Missing ≠ 0. Not probability, not edge. | ACCRUING. `schema: mastermind.research_priority.v1`. W7 gated. | Do not treat RP1 as Opportunity Score. Do not start W7. **CODE VERIFIED** `W6_RP1_POLICY.md:1-50` |
| Prophet `prophet_score` / lane | Existing conviction + board admission (`buy`/`watch`/`leaders`/`laggards`/`not_on_board`) | Prophet selection/gating is **untouchable** from Radar (`WS:LIVE-ENTRY-RADAR` landmine). | Do not fuse Prophet score into an Opportunity Score. **CODE VERIFIED** PR-0 contract §1 |
| DRL `engine/price_pressure` | Residual shock vs sector/market peer; display ledger | All authority flags false. **PRODUCTION VERIFIED** `data/price_pressure/latest.json` 2026-08-18 generate, `asof` 2026-08-14 | Do not promote DRL to entry/rank. `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` |
| `engine/residual_alpha.py` | Market + sector residual momentum, ranked within GICS sector, 12-1 window | Context / setups weight. Did **not** clear BH-FDR/DSR on modern era. **CODE VERIFIED** module docstring | Do not treat as standalone Opportunity Score. `DNR:KILL-PSS-F3-RESIDUAL` is a *different* construction (entry-timing residual reset) |
| Winner Autopsy `research/winners/cases/` | 154 parsed `winner_case.v1` files (108 winner / 46 failed_breakaway) | Case library + mechanical census. **No composite scores (WA-R1).** | Do not score these cases. Use as PIT casebooks only. **CODE VERIFIED** `research/winners/README.md` |
| Track C lobe census | 32 producers across 9 families for Radar nominations | Display / nomination bus. **CODE VERIFIED** `TRACK_C_LOBE_PRODUCER_CENSUS.md` | Do not recensus those 32 as if undiscovered; extend only. |

**Standing score kills that bind this lane**

- `DNR:KILL-SPONSORSHIP-SCORE` — fused 100-point sponsorship score struck; per-axis AND-gate instead.  
- `DNR:KILL-REGIME-SCORECARD` — composite regime scorecard forbidden (duplicates risk_radar→market_state→regime_vector).  
- Radar contract P-9: detector score and Priority/Opportunity score are **separate objects**.

---

## 1. Audit categories

Latest US Context Vector stamp used for coverage rates: **2026-08-17**, **2,936 tickers**. **PRODUCTION VERIFIED** `data/us_prophet_rank/candidates/2026-08.parquet`.

| # | Category | Owner (code) | Artifact | Grain | Universe / history | PIT? | Authority | Status this session | Gaps |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Fundamental delta | `engine/stock_fundamentals.py`; CalcBench/forensics `data/fundamental_forensics/`; EDGAR `data/edgar/statements_quarterly.parquet` + `fundamentals_panel.parquet` | `data/stock_fundamentals/snapshots.parquet` is **thin** (51 rows, wide `TICKER__fwd_pe` only). Forensics public summary: 1,492 companies / 1,054 findings, generated **2026-07-12** (stale vs 08-18). | Issuer-period | EDGAR panel exists for US filers; Canadian/FPI often **zero rows** (CCJ case). | Filing date + first-seen on some EDGAR tables | Display / forensics `display_only` on context-vector join | **PARTIAL.** Context-vector `forensics__absent` **50.3%** on 2026-08-17. | No licensed standardized actual-vs-consensus delta. QoQ/YoY live in statements but not a single Opportunity-ready delta object. |
| 2 | Catalyst materiality | BioCatalyst / special situations / earnings 8-K / `engine/group_linked_outsiders.py` | `data/edgar/earnings_8k_dates.parquet`; `data/special_situations/`; BioCatalyst program artifacts; winner-case catalyst ladders | Event | Uneven. Material 8-K coverage is ticker-dependent (NVDA 31 rows; CCJ 0). | Publication/filing date in winner cases is PIT law | Display. Special-situations classify cache is nightly. | **PARTIAL.** Materiality is **not** a scored field. Winner cases carry qualitative `durability`. | No house materiality model. LLM prose must not fill it. |
| 3 | Analyst estimates / revisions | `collectors/equity_revisions.py` | `data/revisions/latest.parquet` (1,539 names); `history.parquet` (12,998 rows) | Ticker-day snapshot | History **2026-06-16 → 2026-08-18** only. Yahoo `eps_revisions` / `eps_trend` `+1y`. | Append-only daily snapshots from mid-June 2026 — PIT **forward from birth**, not before. | Research / live score reads `latest`. Not licensed IBES/FactSet. | **ACCRUING, SHORT HISTORY.** `n_covering` / dispersion / revenue fields often **NaN** on older rows (HARD HONESTY: never substitute reviser count). | No street consensus history before 2026-06-16. Revenue 30d/90d drift **structurally omitted** (yfinance has no endpoint). Earnings Intelligence CEI: `consensus: unlicensed_absent`. **CODE VERIFIED** collector docstring + parquet peek. |
| 4 | Theme state | `engine/neuralweb/thematic_state.py`; `scripts/build_theme_graph.py`; baskets | `site/neuralwebdata/theme_state.json`; `data/theme_graph/` (3,878 nodes, 8,292 edges, belief_time 2026-08-18); `data/baskets/membership.json` | Theme / basket, not ticker (Track C gap) | Dozens of themes + GMI graph. Graph nightly meta stamped 2026-08-18. | Theme graph `era: observed`, `belief_time` | Display / nomination via membership expansion | **LIVE as theme, PARTIAL as ticker.** Context-vector theme fields exist. | Theme pages have **no single-name producer** at headline level (Track C). Two sector maps (GICS vs Finviz) un-reconciled. |
| 5 | Residualized price returns | `engine/residual_alpha.py`; DRL `engine/price_pressure/` | Residual alpha consumed by setups; DRL `data/price_pressure/latest.json` + ledger | Daily residual | DRL panel **4,315 names**, span **2021-07-06 → 2026-08-14**. Residual alpha uses nightly closes + GICS. | Causal betas lagged 1d (residual_alpha). DRL resid_z uses shifted 60d σ. | Residual alpha: context. DRL: all-false authority. | **TWO DIFFERENT residualizations.** See dislocation spec. | Factor residual **not** on context vector: `factor__absent` **100%** on 2026-08-17. Theme residual only as DRL context (`basket_context_share` 0.172). |
| 6 | Market / factor / sector / theme drawdown attribution | Pieces: `engine/factor_exposure.py` (watchlist-scoped ETF names); DRL day banner + peer_basis; residual_alpha market+sector; theme graph | No single name-level attribution pack | Mixed | Factor_exposure ~30 macro/sector ETFs, **not** the 2,966-name universe. | UNKNOWN as a unified PIT pack | Display | **NOT ASSEMBLED.** Statistical parts exist; no 5-layer attribution object. | Must not infer economic cause from residual. |
| 7 | Attention / news | Quiver `data/quiver/news.parquet`; Hot Tape (no `data/` artifact); `attention__*` on context vector | Quiver news; marketing outbox; context-vector `attention__views` | Ticker / item | Context-vector `attention__absent` **59.4%** on 2026-08-17. Hot Tape 5-min, ephemeral. | Quiver fileDate / asof. Hot Tape historically unreconstructible (Track C / Radar §5). | Display / marketing | **PARTIAL + EPHEMERAL HIGH-FREQ.** | No durable PIT attention lifecycle before Quiver/Hot Tape birth. Social volume **UNKNOWN** as a house series. |
| 8 | Analyst coverage | Same revisions collector (`n_covering`, `n_analysts`, `rev_n_analysts`) | Revisions parquets | Ticker-day | 1,539 names on latest; `n_covering` often null | Same as #3 | Display | **PARTIAL.** Coverage count ≠ quality. | No historical coverage backfile. No target-price history in-repo (winner README: analyst-target data does not exist). |
| 9 | Active-manager behavior | `engine/smart_money.py`; `engine/manager_trades.py`; curated 13F slugs under `data/smart_money/` | Per-manager dirs + `smart_money_runs.parquet` | Manager-holding, quarterly | Curated super-investor cohort, **not** full 13F universe | ReportPeriod + 45d | Display. **WA-R2 / NEXTL-U13: never a positive signal.** | **LIVE, LAGGED, CURATED.** | Cannot represent “the market’s active managers.” |
| 10 | 13F / ownership | `collectors/edgar_13f.py`; `data/institutional_13f/`; Quiver `sec13f.parquet` | Public census `data/institutional_13f/public/census_latest.json` | Filer × holding × period | **8,750** current original filings; **2,232,608** long positions; **mapped 1,004,749 (45.0%)**. Freshness as_of **2026-08-09**. | Filing window + 45d. Amendments tracked. | Context. Value units **excluded_mixed_reported_units**. | **LIVE CENSUS, MAPPING HOLE.** | 55% of long positions unmapped. 45d lag. Confidential omissions exist in source quality findings. |
| 11 | ETF / theme flows | `data/flows/{SPY,QQQ,sectors}.parquet`; `data/etf_holdings/`; `data/holdings/ARK*` | Flow proxy: nav / aum_mn / so_mn. Holdings: ARK + thematic ETFs | Fund-day | SPY flow file **27 rows**, 2026-07-12 → 2026-08-17. AUM last two days **identical** (795,306.88512) while NAV moved — treat AUM as **stale or carry-forward**. | Shares-outstanding change is the honest flow proxy; AUM can lie. | Display | **THIN + RECENT.** | No long PIT creation/redemption tape. Theme-ETF holdings exist; flow ≠ holdings change without so_mn. |
| 12 | Short interest | FINRA `data/finra/short_interest.parquet` + history; `engine/ownership_crowding.py`; `engine/short_volume.py` | Latest SI: **1,521** names, settlement **2026-07-31**, asof **2026-08-17**. History: **4,564** rows, settlement 2026-06-30 → 2026-07-31. | Biweekly settlement | Display cohort, not full FINRA tape. Context-vector `short_int__absent` **49.8%**. | Settlement date is the information date; asof is capture. | Display | **LIVE, BIWEEKLY, SHORT HISTORY IN THIS STORE.** | Utilization / CTB / locate **UNKNOWN** (not in these files). Days-to-cover uses FINRA ADV, not borrow. |
| 13 | Capital structure / ATM / converts / warrants / lockups | `engine/capital_structure/*`; `app/capital_structure.py`; `data/edgar/dilution_events.parquet` | CS store: event_versions, document terms, projection, health. Dilution events: **48,824** rows (accession, cik, ticker, form, filing_date, `_first_seen`). | Filing / instrument-candidate | CS health: **19,018 pending**, 18,818 deferred, authority all-false. Dilution table is form-level (many 424B2), not a clean ATM/convert/warrant taxonomy. | `_first_seen` / filing_date | Context only. `entry_authority/prophet/rank/sizing` all false. **PRODUCTION VERIFIED** `data/capital_structure/health.json` | **BUILT, BACKLOGGED, NOT NOMINATION-READY.** Track C: API-gated, not a static site artifact. | Lockups **UNKNOWN** as a structured field. Do not read 424B2 count as dilution intensity. |
| 14 | Options | `engine/gex_model.py`; `data/polygon_gex/`; `data/options_flow/`; `data/options_dislocation/snapshots.parquet`; `site/gex/` | Dislocation snapshots: **15,753** rows, **408** underlyings, **2026-06-15 → 2026-08-13**. GEX screener ~384 / flow ~353 (Track C). | Daily chain summary | Per-ticker options history **starts 2026-06** (Winner Autopsy WA). Context-vector `options__absent` **86.1%**. | Snapshot date | Display. Signed flow **forbidden** without trade-level NBBO (`research/OPTIONS_FLOW_DATA.md`). | **ACCRUING FROM 2026-06.** | Cannot fingerprint 2023–2025 incorporation via options. Dealer gamma is modeled, not observed. |
| 15 | Liquidity | `engine/stock_technicals.py` (`dollar_vol_20d`, `rel_volume`); context-vector `mdv20_usd`, turnover percentiles | Nightly snapshots + live `rvol_tod` on flow_pulse | Ticker-day | ~2,966 universe stamp | Confirmed close vs live quote basis-audited | Display | **LIVE SNAPSHOT.** | Float-based share turnover **not found** (Track C). Full-history series in `entry_primitives` is research-only, not live-wired. |
| 16 | Peer sets | GICS via `data/breadth/ticker_sectors.parquet`; baskets `data/baskets/membership.json`; DRL sector ex-self; theme graph member edges | Multiple parallel peer languages | Name / basket / GICS | S&P 1500 GICS authoritative; Finviz heatmap map separate; baskets curated | Membership files dated | Display | **SEVERAL PEER LANGUAGES, NO SINGLE CANONICAL PEER SET.** | DRL `peer_basis` is sector only **52.79%** of the time; **47.21% market** (coverage in latest.json). Theme member edges 2,365 Finviz. |
| 17 | Prophet / Radar entry state | Prophet: `engine/prophet_*` (owned by `WS:PROPHET-US-ENTRY-TIMING`); Radar: `engine/entry_radar/` (`WS:LIVE-ENTRY-RADAR`) | Prophet context vector + `data/prophet/ledger.jsonl` (42 lines, last `INTU-BULL-20260706`). Radar `data/entry_radar/ledger_state.json`. | Name-night / episode | Prophet latest stamp 2,936 names: lane `not_on_board` 2,796 · `buy` 65 · `watch` 48 · `leaders` 15 · `laggards` 12. `buyable` 127. `eligible` 148. `prophet_entry` / `prophet_signal` **empty** on 2026-08-17 rows. Radar: `state=WAITING_FOR_LIVE_SOURCE`, `forward_rows_total=0`, `live_forward_epoch=2026-08-15T08:58:10Z`. | Nightly stamp_date; Radar live-forward only for 1D LIVE | Prophet gates/ranks its board. Radar display/accruing, not armed (`ENTRY_RADAR_LIVE_ENABLE`). | **PROPHET LIVE AS BOARD; RADAR NOT LIVE-SOURCED.** | Do not read empty `prophet_entry` column as “no entry state” — entry may live in `engine/entry_signal` / `site/stockdata/<T>.json` (Track C #23). **UNKNOWN** without opening those dossiers this session. Radar W4 is STAGED NOT ARMED. |

---

## 2. Shared-upstream clusters (do not double-count)

From Track C plus this session:

1. **Yahoo/Massive OHLCV** — every residual, DRL, Prophet, Radar detector.  
2. **EDGAR 13F** — smart_money, manager_trades, ownership_flow, institutional_13f census. One filing cycle.  
3. **FINRA** — short volume, short interest, OTC ATS / dark pool.  
4. **`site/stockdata/<T>.json`** — composite dossier; a miss degrades flow leaders and others.  
5. **`data/earnings/earnings.parquet`** — 1,987 rows; calendar EPS forecast, not licensed consensus. Feeds Hot Tape, public wire, stock_fundamentals.  
6. **`engine.options_universe.gex_symbols()` ~360** — shared restriction for flow, dark pool, some options.  
7. **Polygon options chains** — GEX, screener, dislocation, flow. One vendor, history from 2026-06.

---

## 3. Latest Prophet board snapshot (not a score recommendation)

**PRODUCTION VERIFIED** 2026-08-17 context-vector stamp:

| Lane | N |
|---|---|
| not_on_board | 2,796 |
| buy | 65 |
| watch | 48 |
| leaders | 15 |
| laggards | 12 |

Context-dimension absence on that stamp: attention 59.4% · insider 51.7% · short_int 49.8% · options 86.1% · factor **100%** · forensics 50.3% · spine 39.4% · personality 0% · regime 0% · sector 0%.

**Missing ≠ 0.** An Opportunity Evidence Vector, if ever assembled, must omit these, never impute.

---

## 4. What is *not* in the estate

| Need | Status |
|---|---|
| Licensed IBES/FactSet/Bloomberg consensus + revision history | **NOT_BUILT** / unlicensed_absent |
| Pre-2026-06 options PIT | **STRUCTURALLY ABSENT** |
| Utilization / CTB / locate | **UNKNOWN** |
| Float-based turnover | **NOT FOUND** (Track C; this session did not find a contradicting module) |
| Dealer positioning (true, not GEX model) | **UNKNOWN** |
| Lockup expiry calendar | **UNKNOWN** as a structured store |
| Systematic ETF/ETN/3x wrapper classifier on the 2,966-name universe | **NOT FOUND** |
| Durable 5-min attention tape | Hot Tape has **no `data/` artifact** |
| Unified 5-layer dislocation pack | **NOT ASSEMBLED** |

---

## 5. Evidence vector implication (research only)

A structured Opportunity Evidence Vector can be **described** as a typed bag of the rows above, each with `value | unavailable | stale | unlicensed`, never as a weighted score.

The nearest existing bag is the **US Context Vector**. Extending *that* join — or defining a research view over it — is the boring baseline. A new store would violate the commission’s “do not create a new truth store when an owner already exists.”

No weights are proposed here.
