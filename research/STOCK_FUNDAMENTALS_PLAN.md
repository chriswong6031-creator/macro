# Single-Stock Fundamentals + Earnings + Options Suite — Definitive Plan

> Target: `site/stock.html` + `templates/stock.html.j2`, fed by `site/stockdata/<TICKER>.json` built by `scripts/build_stock_library.py`.
> House rule: FREE only, baked at build time (zero serve-time API), brutally honest about coverage/staleness/lag.
> All claims below are verified against the live repo on the `quant-factor-expansion` branch (2026-06-13).

---

## 1. Executive Summary

**The recommended approach in one breath:** Surface the fundamental fingerprint we *already compute but never show* (`factors.json` z-scores + `data/edgar/fundamentals.parquet` raw fields) on the single-stock page **first** (zero new data, zero CI risk, one PR); then extend the existing keyless SEC EDGAR pipeline from a latest-FY snapshot into a multi-year statements backbone via the **companyfacts** API (one keyless call/filer, weekly) for trends + Piotroski/Altman; add the **Wikipedia REST summary** for the one genuine prose gap (business descriptions) and the **Nasdaq keyless JSON** for earnings dates/surprises/estimate-revisions; build **per-equity GEX** by generalizing the existing `collectors/cboe.py` `GexAdapter` over the keyless CBOE delayed-quotes CDN (greeks ship server-side — no Black-Scholes); and reserve a dashed master-verdict slot to be wired (uncalibrated, validation-first) only after the context layer ships.

**The single biggest constraint — data feasibility at 1500-name scale:** `yfinance .info` is the only free source of forward analyst estimates / price targets / consensus ratings, and it **throttles past ~1000 symbols/run and is blocked far harder from GitHub Actions datacenter IPs** (verified: repo already caps `enrich_per_run: 120`, `collectors/sector_holdings.py` pulls `.info` for only ~110 holdings weekly, and the adversarial test reproduced 429s on Azure CI IPs). **Therefore forward-looking and analyst fields are permanently TIERED** (deep set ≈110 holdings + S&P 500 nightly/weekly; the long tail gets an honest "no free estimate" stub), while **everything backward-looking ships at full ~1335 coverage for free and keyless** from SEC EDGAR. Three sources answer the load-bearing questions and survive CI: **SEC EDGAR** (frames + companyfacts + submissions — keyless, weekly, ~1335 names), **CBOE delayed-quotes CDN** (keyless, nightly, ~90-95% of optionable names, greeks included — *confirmed* by adversarial test), and **Nasdaq public JSON** (keyless, date-keyed calendar = whole universe in ~45 calls). Finnhub free covers earnings-surprise + consensus rating as a cross-check (its price-target/estimate endpoints are *premium → 403*, confirmed). FMP (250/day) and Alpha Vantage (25/day) are rejected at this scale.

---

## 2. What We Already Have vs The Gap

| Capability | Already in repo (reuse) | Coverage (verified) | Gap → new work |
|---|---|---|---|
| **Sector / name** | `data/breadth/constituents.parquet`, `factors.json .sector`, already loaded by `build_stock_library.universe()` | ~1335–1500 | none — surface only |
| **Cross-sectional factor fingerprint** | `site/factordata/factors.json .table` (value/profitability/quality/accruals/investment/payout/low_vol/low_beta/short_interest/composite z + mktcap_bn) | **1335 rows, all legs populated** | none — **surface on stock page (highest leverage)** |
| **Latest-FY raw fundamentals** | `data/edgar/fundamentals.parquet` (cik, assets, equity, debt_lt, shares, ni, ni_prior, gross_profit, cfo, dividends, repurchases, revenue, assets_prior) | ni 1237, equity 1270, revenue 1172, cfo 1270, **gross_profit 536, dividends 522, debt_lt 661, repurchases 964, shares 1229** | trailing multiples computable NOW; **multi-year trends + capex + cash need companyfacts** |
| **Forward fundamentals (deep set)** | `data/stock_fundamentals/snapshots.parquet` (`<T>__fwd_pe` etc.) | **exactly 110 holdings, 110 fwd_pe cols** | forward P/E for the rest = TIERED, no free 1500-scale source |
| **Insider Form-4 net buy/sell** | `collectors/sec_insider.py` → `data/sec_insider/insider.parquet` | all filers (generated in CI; confirm it writes) | none — surface; verify CI emits it |
| **Short interest** | `collectors/finra.py` → `data/finra/short_interest.parquet` (short_shares, days_to_cover, si_change_pct) | **1499 names** | none — surface |
| **GEX engine pattern** | `collectors/cboe.py GexAdapter` + `config.cboe.gex` {mult 100, pct_move 0.01, window 0.25, 365d} + flip-crossing/±15% guard | SPX only | **generalize to per-equity** (keyless CBOE CDN) |
| **Macro regime context** | `data/regime/latest.json` (quad, liquidity_overlay, conditions.style_tilt[t=+3.0]/risk_appetite.roro/recession) | single object, all US names | none — feed the regime-fit layer |
| **Calibrated short-term ladder** | `engine/cycles.analyze()` → ladder{state,score,entry,eq_*,age_*} | full analyzable universe | none — **compose around, never replace** |
| **Business description (prose)** | — | **THE central gap** | **Wikipedia REST summary** (keyless, weekly) |
| **SIC / exchange / HQ / former names** | cik in fundamentals.parquet | resolvable | **SEC submissions API** (keyless, weekly) |
| **Earnings date / surprise / revisions** | — | — | **Nasdaq public JSON** (keyless) + Finnhub cross-check |
| **Multi-year statements / health scores** | — | — | **SEC companyfacts** (keyless, weekly) |

**Verdict: ~80% of the suite is either already collected or computable from already-collected data.** The new fetches are SEC companyfacts (1 call/filer weekly), SEC submissions (1 call/filer weekly), Wikipedia (1 call/name weekly), Nasdaq (≈45 + ~3000 calls weekly), and CBOE per-equity (~700 calls nightly).

---

## 3. Prioritized Data Dictionary

Legend: **P0** = ship first / load-bearing · **P1** = high value · **P2** = nice-to-have · **CFE** = computable-from-existing · **TIERED** = deep set only · **COV** = coverage-limited.

### 3A. Profile (identity / business panel)

| Field | P | Source | CFE | Formula / note |
|---|---|---|---|---|
| `business_summary` | P0 | Wikipedia REST `/page/summary/{title}?redirect=true` `.extract` + `.description` | no | THE gap. SEC `.description`/`.website` empty for operating cos (verified Apple). Trim to ~2 sentences at bake; label "source: Wikipedia, as of {date}". |
| `gics_sector` | P0 | `factors.json .sector` / constituents.parquet | **yes** | already loaded in `universe()` |
| `mktcap_tier` | P0 | `factors.json .mktcap_bn` | **yes** | Large/Mid/Small from float×price (better than SEC filer category) |
| `sic_code` + `sic_description` | P1 | SEC submissions `.sic`/`.sicDescription` | no | sub-industry proxy (Apple→3571 "Electronic Computers"). Label "SIC, not GICS sub-industry". |
| `primary_exchange` | P1 | SEC submissions `.exchanges[0]` | no | free in same call |
| `hq_location` | P2 | SEC submissions `.addresses.business` | no | mailing address caveat |
| `former_names` | P2 | SEC submissions `.formerNames` | no | disambiguates merged/renamed |
| `website`/`logo`/`ipo` | P2 | Finnhub `/stock/profile2` (free) | no | **not** for prose (no description field). Best-effort. |
| `employees_count` | P2 | yfinance `.info.fullTimeEmployees` | no | **TIERED** — no keyless full-coverage source |

### 3B. Valuation Multiples

| Field | P | Source | CFE | Formula |
|---|---|---|---|---|
| `trailing_pe` | P0 | EDGAR ni + EPS_diluted + live close | **yes** | `mktcap / ni` (guard ni≤0 → "n/m"). **Prefer EPS_diluted frame** (USD-per-shares unit, ~97% cov) over ni/shares (~85%). |
| `price_to_book` | P0 | EDGAR equity + price | **yes** | `mktcap / equity`; flag buyback-distorted book |
| `price_to_sales` | P0 | EDGAR revenue + price | **yes** | `mktcap / revenue` (survives ni<0) |
| `earnings_yield` | P0 | derived | **yes** | `ni / mktcap = 1/PE`; compare to 10y (macro store) |
| `fcf_yield` | P0 | EDGAR cfo − **capex (new)** | yes* | `(cfo − capex) / mktcap`. **Interim: CFO-yield labeled "pre-capex"** until capex frames concept lands. |
| `dividend_yield` | P1 | EDGAR dividends (522) + price | **yes** | `dividends / mktcap`, trailing FY. **COV** — show "n/a" for untagged, never impute 0. |
| `shareholder_yield` | P1 | EDGAR (div 522 + buyback 964) | **yes** | `(dividends + repurchases) / mktcap`; pair with payout z |
| `p_fcf` | P1 | EDGAR cfo − capex | yes* | reciprocal of fcf_yield; gap vs PE flags earnings quality |
| `ev_sales` | P2 | EDGAR rev + cash/debt (new) | no | **COV** — needs cash + full debt; render only where legs exist |
| `ev_ebitda` | P1 | EDGAR debt_lt(661)+cash+OpInc+D&A (new) | no | **COV** — debt_lt 661/1335 is binding; tier, "EV n/a (incomplete BS)" otherwise, never impute |
| `forward_pe` | P1 | yfinance `forwardPE` (snapshots.parquet) | yes | **TIERED** — 110 deep only; "forward unavailable" for the rest |
| `peg_ratio` | P2 | yfinance `trailingPegRatio` (deep) / EDGAR proxy | yes | deep: native; 1500-scale: `trail_pe/(100·g)`, g=`ni/ni_prior−1`, label "trailing-growth proxy" |
| `valuation_context` | P0 | `factors.json` (sector + value z) + new weekly snapshot parquet | **yes** | **THE presentation choice**: sector-median + within-sector pctile + value-z badge + self-history pctile (accrues from a new weekly multiples snapshot) |

### 3C. Financials / Growth / Health (multi-year)

All from **SEC companyfacts** (one keyless call/filer, weekly). All concepts verified present with multi-year FY history.

| Field | P | Concept(s) | CFE | Formula / note |
|---|---|---|---|---|
| Revenue 5y + YoY + 3y/5y CAGR | P0 | `Revenues` → `RevenueFromContractWithCustomerExcludingAssessedTax` | no | **tag-migration fallback chain mandatory** (verified: AAPL Revenues ends FY2018) |
| Gross/Operating/Net margin 5y | P0 | `GrossProfit` (else `Revenue−CostOfGoodsAndServicesSold`), `OperatingIncomeLoss`, `NetIncomeLoss` | no | **per-filer COGS fallback closes the 536/1335 GrossProfit gap** |
| Diluted EPS 5y + CAGR | P0 | `EarningsPerShareDiluted` (USD-per-shares) | no | reported, avoids share-count timing noise |
| FCF 5y + FCF margin | P0 | `NetCashProvidedByUsedInOperatingActivities` − `PaymentsToAcquirePropertyPlantAndEquipment` | no | hardest-to-fake quality gauge |
| ROE / ROA / ROIC 5y | P1 | NI/equity, NI/assets, OpInc·(1−tax)/(equity+debt) | no | ROIC uses EBIT proxy + best-effort invested capital — flag approximate |
| D/E + interest coverage + current ratio 5y | P1 | `LongTermDebtNoncurrent`+`DebtCurrent`, `OperatingIncomeLoss/InterestExpense`, `AssetsCurrent/LiabilitiesCurrent` | no | companyfacts resolves the right debt tag (frames misses the split) |
| **Piotroski F-Score (0–9)** | P0 | derived | no | 9 binary signals; needs 2y deltas companyfacts provides |
| **Altman Z-Score** | P1 | derived + mktcap | **yes** | `1.2·X1+1.4·X2+3.3·X3+0.6·X4+1.0·X5`; use Z'' for non-manufacturers |
| Buyback + dividend trend 5y | P2 | `PaymentsForRepurchaseOfCommonStock`, `PaymentsOfDividendsCommonStock`, `CommonStockSharesOutstanding` | no | net shareholder yield + share-count trend |
| Cash + inventory trend | P2 | `CashAndCashEquivalentsAtCarryingValue`, `InventoryNet` | no | **COV** — cash tag fragments (3M stale post-2016), multi-tag fallback; lower priority |
| Beneish M-Score | — | sparse tags | no | **defer** — ship F + Z first, M is best-effort/partial |

### 3D. Earnings

| Field | P | Source | CFE | Note |
|---|---|---|---|---|
| `next_earnings_date` | P0 | Nasdaq `/api/calendar/earnings?date=YYYY-MM-DD` (date-keyed) | no | **~45 calls covers ALL 1500** (cheap, nightly). yfinance `.calendar` fallback. Mark estimated. |
| `eps_surprise_history` | P0 | Nasdaq `/api/company/{sym}/earnings-surprise` | no | 4 qtrs actual vs consensus + %surprise. ~90% cov. yfinance 25-row fallback. |
| `estimate_revision_trend` | P0 | Nasdaq `/api/analyst/{sym}/earnings-forecast` (up/down counts) | no | **standout free find** — revision alpha pre-computed; guidance-direction proxy |
| `revenue_estimate_vs_actual` | P1 | yfinance `.calendar` (estimate, TIERED) + EDGAR revenue (actual) | yes* | Nasdaq is EPS-only; rev-estimate deep set only |
| `post_earnings_drift` | P1 | **compute in engine** from `data/yahoo/<t>.parquet` + dateReported | **yes** | **highest-value original signal**: t+1, t+1..t+5, t+1..t+20 returns. Zero-cost. |
| `guidance_direction_proxy` | P2 | derived from revision up/down | yes | guidance TEXT not free anywhere — label "showing revision direction as proxy" |

### 3E. Factor Fingerprint (surface existing)

| Field | P | Source | CFE | Note |
|---|---|---|---|---|
| 6-axis radar (value/profitability/quality/investment/payout/low_vol) | P0 | `factors.json .table` | **yes** | **zero new data, highest-leverage surface item** |
| `composite` → `fundamental_score_long` | P0 | `factors.json .composite` rescaled [−100,100] | **yes** | relative rank vs S&P 1500 — label as such, not "good company" |
| per-leg z bars | P0 | `factors.json` legs | **yes** | shows WHY |

### 3F. Options / GEX (per-equity)

All from **CBOE delayed-quotes CDN** (`/options/{TICKER}.json`, keyless, greeks server-side — **confirmed by adversarial test**). Reuse `GexAdapter` methodology verbatim.

| Field | P | Source | CFE | Formula / note |
|---|---|---|---|---|
| `net_gex_bn` | P0 | CBOE per-contract gamma + OI | no | `Σ sign·gamma·OI·100·spot²·0.01`. Pos=pinned/mean-revert, neg=trend-amplify. **TIERED to optionable (~700)**. |
| `flip_strike` + `spot_vs_flip_pct` | P0 | CBOE | no | zero-gamma crossing, ±15% guard (existing logic) |
| `iv30` | P0 | CBOE top-level `iv30` | no | day-one; **IV-rank needs ~252 stored snapshots** ("building history") |
| `put_call_oi/vol_ratio` | P1 | CBOE | no | per-name positioning vs flow |
| `max_pain` | P1 | CBOE front/next expiry | no | soft pin magnet near OpEx |
| `skew_25d` + term | P2 | CBOE per-contract delta+iv | no | **COV** — flag low-confidence when OI>0 rows < ~40 |
| `unusual_activity` | P2 | CBOE + accumulated baseline | no | **defer** — needs history baseline |

**Tiering (house honesty):** (a) full panel for OI>0 names; (b) "thin chain — low confidence" when OI>0 rows < ~40; (c) "no listed options" when 0 rows. Never fabricate GEX. **Dealer-sign caveat on-page**: assumes dealers long-call/short-put; weaker for single equities (retail call-buying, covered-call ETFs can flip true positioning) — "structural estimate, not positioning truth".

### 3G. Analyst / Positioning

| Field | P | Source | CFE | Note |
|---|---|---|---|---|
| `insider_flow` (Form-4 net buy/sell) | P0 | `collectors/sec_insider.py` (existing) | **yes** | **highest-conviction signal**; verify CI writes the parquet |
| `short_interest_pct_float` | P0 | FINRA short_shares / EDGAR shares; yfinance for freshness | **yes** | FINRA 1499 names (bi-monthly+2wk lag); yfinance `shortPercentOfFloat` fresher (TIERED) |
| `days_to_cover` | P1 | FINRA `days_to_cover` (existing) | **yes** | 1499 names, surface directly |
| `si_change_pct` (build/cover) | P1 | FINRA `si_change_pct` (existing) | **yes** | direction > level; pair with price |
| `short_interest_z` | P2 | `factors.json .short_interest` | **yes** | "vs peers" framing |
| `consensus_rating` | P0 | yfinance `recommendationMean`/`Key` | no | **TIERED**. Often None on small-caps → "rating N/A, low coverage". Finnhub `/stock/recommendation` free cross-check. |
| `price_target` (mean/median/high/low + n) | P0 | yfinance `targetMeanPrice` / `analyst_price_targets` | no | **TIERED**. Broader cov than rating; show n, gray out n<5. Finnhub `/stock/price-target` is **premium→403**. |
| `rating_drift` | P1 | yfinance `.recommendations` (TIERED, +1 call) | no | leading signal; net migration delta, deep set only |
| `upgrades_downgrades` tally | P1 | yfinance `.upgrades_downgrades` (TIERED, +1 call) | no | rolling 30/90d #up/#down/#PT-raise/#PT-cut, deep set only |
| `inst/insider ownership %` | P1/P2 | yfinance `heldPercentInstitutions`/`Insiders` | no | **clamp [0,1], flag ">100% (Yahoo float artifact)"** (verified EMBC/AAT/AAMI) |

---

## 4. Verified Source Table

| Source | Endpoint | Auth | Real rate limit | Coverage (S&P 1500) | Cadence | Backing verdict |
|---|---|---|---|---|---|---|
| **SEC EDGAR frames** (existing) | `data.sec.gov/api/xbrl/frames/us-gaap/{C}/{unit}/CY{y}.json` | keyless + UA | ~10 req/s; 1 call = all filers | 1335 latest-FY, tag-sparse | weekly-all | *confirmed* — in production (`edgar.py`) |
| **SEC EDGAR companyfacts** | `data.sec.gov/api/xbrl/companyfacts/CIK{10}.json` | keyless + UA | 10 req/s; **payload-bound** (3.5–7.5MB/filer, ~1s) | 1335 (CIK-mapped); ~32 min/run wire ~0.45GB gzip | **weekly-all** (NOT nightly) | **confirmed** — live 200, 503 concepts, 18y history; hit + recovered the 403 rate wall |
| **SEC EDGAR submissions** | `data.sec.gov/submissions/CIK{10}.json` | keyless + UA | 10 req/s | ~all (CIK in parquet) | weekly-all | **confirmed** — live: sic/exchange/category/formerNames; **`.description`/`.website` empty** |
| **Wikipedia REST summary** | `en.wikipedia.org/api/rest_v1/page/summary/{title}?redirect=true` (+ opensearch resolver) | keyless (500/hr anon; 5000/hr free token) | 500/hr per IP → **weekly** (1500 @500/hr ≈ 3hr); token = ~18min | high (most names; small-cap tail misses → fallback) | **weekly-all** | **confirmed** — live extract+description for AAPL/GOOGL/BRK/LMT/WELL/ZTS |
| **Nasdaq public JSON** | `api.nasdaq.com/api/{calendar/earnings?date= , company/{s}/earnings-surprise , analyst/{s}/earnings-forecast}` | keyless + **browser UA** | unpublished; pace ~3-4/s | ~90% (CALM-type odd fiscals miss); **calendar date-keyed = ~45 calls/all** | calendar **nightly**, surprise/revisions **weekly** | **confirmed live** this session; **unofficial → needs CI canary + yfinance fallback** |
| **CBOE delayed-quotes CDN** | `cdn.cboe.com/api/global/delayed_quotes/options/{TICKER}.json` (plain ticker; DOT for BRK.B; UA req) | keyless | **no observed limit** (CloudFront+Cloudflare, s-maxage=5); 30-burst 0×429 | **~90-95% optionable**; ~1500 ≈ 21min serial / ~3-5min @8-way; ~0.26GB wire | **nightly-all** | **CONFIRMED** (adversarial): greeks (gamma/delta) + iv + OI + `current_price` per-contract → **no Black-Scholes**; 36/40 small-caps |
| **Finnhub free** | `finnhub.io/api/v1/{stock/metric?metric=all , stock/earnings , stock/recommendation , calendar/earnings , stock/profile2}` | free key (CI secret) | **60/min** (hard 30/s ceiling) | full US trailing; ~28min metric pass | metric nightly / earnings+rec weekly | **partially-confirmed**: metric/earnings/recommendation/profile2 **FREE**; **price-target/eps-estimate/revenue-estimate/upgrade-downgrade/candle = PREMIUM (403)** |
| **yfinance** `.info`/`.calendar`/`.recommendations`/`.upgrades_downgrades` | Yahoo quoteSummary scrape | none | unofficial; **~0.47s/name residential but DATACENTER-IP BLOCKED** | nominally all; **infeasible nightly all-1500 from CI** | **TIERED** (deep ≈110+S&P500 weekly) | **partially-confirmed**: fields present but sparse (JPM missing recommendationMean); future earnings dates often dropped; 429 on Azure CI |
| FINRA (existing) | `api.finra.org/.../consolidatedShortInterest` | keyless | generous | 1499 | weekly-all | confirmed — `short_interest.parquet` (1499,6) |
| SEC Form-4 (existing) | insider-transactions zip | keyless + UA | trivial | all filers | weekly-all | confirmed — `collectors/sec_insider.py`; **verify CI writes the parquet** |

**Resolved best-source decisions:**
- **Descriptions** → **Wikipedia REST** (keyless, verified live). Fallback SEC `sicDescription`. *Drop yfinance/Finnhub for prose* (no description field). FMP only for the residual <250 Wikipedia can't resolve.
- **Forward estimates / price targets** → **No honest free 1500-scale source.** yfinance deep set only (TIERED + stale label). Finnhub estimate/target endpoints are **premium-403** (confirmed). FMP 250/day = ~6-week rolling drip (deep set only). **Default: render trailing-only + "forward n/a (no free estimate)" for the lite tier.**
- **Earnings** → **Nasdaq public JSON** primary (date/surprise/revisions, keyless), **Finnhub `/stock/earnings`** free cross-check on deep tier, **yfinance** fallback for Nasdaq nulls. **post-earnings drift computed in-engine** (zero-cost).
- **Multi-year statements** → **SEC companyfacts** (confirmed: one keyless call/filer, 18y history, all F/Z inputs present; weekly only — payload-bound). Keep frames for the daily cross-section.
- **Per-equity options/GEX** → **CBOE delayed-quotes CDN, CONFIRMED.** Greeks ship server-side, no Black-Scholes, ~100% optionable empirically, nightly-feasible. *Reject* yfinance option_chain (no greeks + multi-call/expiry → infeasible), Tradier (brokerage account), ORATS/dxFeed (paid).

---

## 5. Interface Spec — `templates/stock.html.j2`

Reuses the existing pattern verbatim: per-ticker JSON fetched client-side, `render(d)` populates by `getElementById`, **`display:none` guards** for missing data (exactly like the current `r_eq`/`r_age`/`r_early`), bilingual via `l-en`/`l-zh` + the `T` dict + `lz(en,zh)` helper, colors via theme `var()` tokens only, inline-SVG for sparklines/radar/gauge (zero new libs, zero serve-time calls).

**Page order (new panels inserted after the existing identity/ladder panel, before/around the chart):**

**0. At-a-glance header strip** (extends the existing topline). Add to the `#result` identity panel:
- `#r_archetype` pill (reuse `.eqbadge` + `.help`) — one of {quality compounder / dividend defensive / deep value / high-beta momentum / speculative-unprofitable / mixed}; `display:none` for names absent from factors.json (ETFs/crypto/~165 gaps).
- 5 metric chips (new `.fcard` flex row): valuation-vs-history+pctile · quality grade A–F · shareholder yield · next-earnings countdown · **dashed master-verdict placeholder** (reserves the Phase-2 slot to avoid re-layout). Each chip degrades to "—".

**1. Profile panel** — `business_summary` paragraph (already have `#r_summary`; repurpose/add `#r_profile`) + chips for SIC/exchange/HQ/mktcap-tier. Footer: "source: Wikipedia, as of {date} · SIC from SEC filing".

**2. Valuation panel** — `.leadbar` rows (reuse the regline/bar pattern): each multiple as a bar to its **self-history percentile** (now-tick + pctile, red rich / green cheap), rows = trailing PE, P/S, P/B, FCF-yield, EV/EBITDA. `<3yr` history greys the bar; forward PE shown only for deep set else "forward n/a".

**3. Financials trend panel** — 5 rows (rev / gross-margin / NI / FCF / shares) each = inline-SVG sparkline (80px) + 5y CAGR + latest. `<details>` discloses ROE/ROA/ROIC/net-debt/accruals + **Piotroski F (0–9) chip** + **Altman Z chip**. Until ~5 FY snapshots accrue, honest 2-point slope.

**4. Earnings panel** (`.twocol`, collapses <560px) — left: big countdown over a 3–4 row surprise table (qtr / EPS-est / actual / surprise%) + "beat X of Y"; right: post-earnings-drift mini-stats + revision-trend (up/down). No date → hide panel.

**5. Factor fingerprint panel** — inline-SVG hexagon radar (6 axes from factors.json z) + composite tercile + per-leg z bars. Reuses FHELP bilingual caveat. `<3` of 6 factors → bars not a sparse polygon. **(Phase A — zero new data.)**

**6. Options/GEX panel** (P2, tiered) — semicircular inline-SVG gauge (short-red→long-green) + needle + regime label, gamma-flip-vs-spot, call/put walls, iv30 (+ "IV-rank building history" until 252 snaps). Three states: full / "thin chain — low confidence" / "no listed options". On-page dealer-sign + delayed-data caveats.

**7. Positioning panel** (`.twocol`) — left: short interest %float, days-to-cover, si-change (high DTC/build = red); right: net insider $ flow with quarter-lag label. Reuses FINRA + Form-4.

**8. Analyst panel** (P2, tiered) — buy/hold/sell counts + consensus target vs spot stacked bar, n shown. Lite tier → locked stub "analyst data: deep set only". Never breaks the page.

**Cross-cutting acceptance criteria:** theme tokens only; every panel bilingual + `.help` honest caveats (lag/coverage/estimated); `display:none` guard when its JSON block is empty; both `.twocol` pairs collapse under ~560px; SVGs scale legibly; build emits each block under a namespaced key in `stockdata/<T>.json` (`profile`, `valuation`, `financials`, `earnings`, `factors`, `gex`, `positioning`, `analyst`) so a missing key = a hidden panel.

---

## 6. Master-Signal Wiring (next phase, uncalibrated-until-backtested)

**Principle: TWO axes, never collapsed.** Compose *around* the calibrated `engine/cycles.analyze()` ladder — never mutate its state key (calibration JSON must keep matching, per the `LIQ_NUDGE` comment).

**Step 1 — archetype classifier** (transparent rule cascade over `factors.json` z + derived raw, first-match-wins):
1. `speculative_unprofitable` if `ni≤0` OR (profitability z < −0.75 AND value z < −0.5 AND low_beta z < −0.5) — **unprofitable veto FIRST** so a money-loser never reads "quality".
2. `high_beta_momentum` if low_beta z ≤ −0.6 AND low_vol z ≤ −0.4, not unprofitable.
3. `dividend_defensive` if payout z ≥ 0.5 AND low_vol z ≥ 0.4 AND low_beta z ≥ 0.3.
4. `quality_compounder` if quality z ≥ 0.5 AND (profitability z ≥ 0.3 OR net_margin top-tercile) AND value z ≤ 0.75.
5. `deep_value` if value z ≥ 0.75 AND quality z < 0.5.
6. else `mixed`.
Emit `archetype_confidence` = margin-to-cutoff. Use `net_margin = ni/revenue` (n~1117) as primary profitability gate since profitability z is sparse (536).

**Step 2 — `fundamental_score_long`** = `factors.json .composite` rescaled to [−100,100] with factor decomposition. NOT recomputed. Label "relative to S&P 1500, lagged to FY filing". NaN (not 0) for no-coverage names.

**Step 3 — `regime_fit_score`** [−100,100] = transparent additive `archetype × regime-context` lookup driven by `regime/latest.json` (quad, liquidity_overlay, conditions.style_tilt[measured t=+3.0], risk_appetite.roro[measured], recession.label) + sector_rs/preference_check. **Macro enters the stock ONLY through the archetype** (contracting liquidity → speculative −2 / defensive +1). **EXCLUDE the net-liquidity-on-buy-setup effect the ladder already applies** (no double-count; reuse `cycles.LIQ_TAILWIND/HEADWIND` magnitudes to subtract). Lean hardest on the measured cells (style_tilt, roro); ship the rest as a labeled uncalibrated prior, no return claims.

**Step 4 — dual verdict (compose, never collapse):**
- **SHORT-TERM TRADE axis** = existing `ladder.score` (backbone, calibrated) × `entry_quality` × GEX risk-character, **GATED (capped, never improved) by earnings proximity**.
- **LONG-TERM INVESTMENT axis** = `fundamental_score_long` × `regime_fit_score` × archetype.
- **Confluence chip** fires ONLY when both axes agree in sign. Each axis degrades gracefully if its data is missing (no fundamentals → trade axis only).

**Step 5 — `verdict_provenance`** block: which inputs present/missing + each as-of date/lag + a "data completeness" chip. A missing fundamental must NOT silently read neutral.

**Honesty gate:** ship the new long-term + regime-fit weights EQUAL-WEIGHT and visibly UNCALIBRATED ("not a validated alpha") until a per-stock backtest harness proves the fused verdict beats the ladder alone (mirror the narrative-shock "validation-first" rule). The ladder stays the only calibrated number.

---

## 7. Phased Build Plan

**Phase 1 — Surface what we have (ZERO new data).** Files: `scripts/build_stock_library.py` (join `factors.json` row + `fundamentals.parquet` row in `_one()`; derive net_margin/ni_growth/archetype/fundamental_score; compute trailing PE/PB/PS/EY/shareholder-yield/CFO-yield from EDGAR×close), `templates/stock.html.j2` (header strip + factor radar + positioning + trailing-multiple bars + financials 2-pt slope), surface FINRA + Form-4. Effort **M**. Unlocks: the entire fundamental fingerprint + archetype + trailing valuation + positioning on the page in one PR, no CI risk. *Verify `data/sec_insider/insider.parquet` is emitted by CI first.*

**Phase 2 — Cheap SEC + Wikipedia + Nasdaq additions.** Files: new `collectors/sec_profile.py` (submissions: sic/exchange/HQ/former-names — **first upgrade `config.edgar.user_agent` to a compliant "name email/URL"**), new `collectors/edgar_facts.py` (companyfacts: multi-year statements → `data/edgar/statements.parquet` with per-concept fallback chains + capex; resumable per-CIK cache; **weekly only**), new `collectors/wiki_profile.py` (descriptions, weekly, cached title map), new `collectors/equity_earnings.py` (Nasdaq date/surprise/revisions; calendar nightly, surprise/revisions weekly; CI canary + yfinance fallback). `engine/equity_factors.py` (optionally add net_margin as a 2nd profitability leg). `build_stock_library.py` + `.j2` (financials sparklines/CAGR + Piotroski F + Altman Z + earnings panel + post-earnings-drift computed from `data/yahoo`). Effort **L**. Unlocks: real multi-year trends, health scores, descriptions, earnings event-gate, valuation self-history percentiles.

**Phase 3 — Per-equity Options / GEX (TIERED).** Files: generalize `collectors/cboe.py` `GexAdapter` to a per-equity function (drop `_SPX`, loop optionable subset, read `data.current_price` as spot, reuse flip/window logic verbatim; DOT-class symbol map; ~6-8-way concurrency + jitter; commit only the ~10-field summary to `data/cboe/equity_gex.parquet`, discard raw chains). Weekly "who is optionable" sweep + nightly pull of that subset. `build_stock_library.py` + `.j2` (GEX gauge panel + tier states). Effort **M**. Unlocks: per-name vol-regime/pin/squeeze context; iv30 day-one, IV-rank after ~252 snaps.

**Phase 4 — Master signal (validation-first).** Files: `engine/` new `verdict.py` (archetype cascade + regime_fit + dual-verdict composition reading `regime/latest.json` + factors + ladder), `build_stock_library.py` (assemble verdict + provenance into JSON), `.j2` (fill the dashed verdict chip + confluence chip + provenance). **Build a per-stock backtest harness FIRST**; ship weights equal-weight/uncalibrated with explicit "not a validated alpha" labels until it measures the fused verdict beats the ladder. Effort **L**. Unlocks: the fused buy/sell verdict — honestly gated.