# Corporate Credit Watch (CCW) — Masterplan (W0)

**Status:** CHARTERED (this PR). Date: 2026-07-14. Operator directive: track corporate
bonds — junk and high grade — by category/sector/theme (hyperscalers, neoclouds, memory
companies) in baskets and subsectors; bond values, changes, velocity of change, g-spread
vs Treasuries, momentum of the g-spread / of the bonds / of the Treasuries (flagship
RSI-MACD + StochRSI, 1D/2D/3D multi-timeframe confluence), and the momentum of velocity —
to see credit risk forming per theme and in the whole corporate bond market. Plus an
explicit adjudication: should the bond lobe fold into Transmission?

**Adjudicated by:** Fable (main loop), from an 8-lane census + live data-source probes +
a 3-lens adversarial review (2026-07-14; all three verdicts SHIP-WITH-FIXES, fixes
incorporated below). Sonnet builds, Opus reviews, Fable gates.

---

## 0. Scope fence

**What this program IS:** a display-tier program that builds the **credit side** of the
bond market, which no existing program owns (census §1.3): (a) a per-bond corporate
holdings PIT store accrued daily from index-fund holdings files; (b) an issuer→theme
registry (hyperscalers, neoclouds, memory, AI-power, data-center REITs, AI hardware +
control groups) plus a coarse **sector lens** (issuer→equity-ticker→GICS map), and
per-issuer/theme/sector aggregates: price, yield, **g-spread** (computed YTM minus
maturity-matched Treasury CMT), par outstanding, dispersion, **maturity wall**; (c)
**credit momentum organs** — canon RSI-MACD + StochRSI KD on spread and price series
across D/2B/3B/W grids with the house confluence cascade, velocity (Δ21/Δ63 +
percentile), and acceleration (histogram-velocity idiom) — with velocity-percentile as
the primary spread read and oscillator crosses secondary pending a spread-behavior sanity
study (§2.4-6); (d) **whole-market corporate bond breadth** from our own holdings store,
with FINRA aggregate breadth as a keyed enrichment; (e) a **fallen-angel / rising-star
watch** from index-membership transitions (ORCL is the standing archetype) plus a
**credit-vs-equity divergence** display series per theme; (f) surfaces on the existing
bonds page + integration contracts (bond_health.json block, risk-radar Tier-B path, RIC
Forward Path row); (g) field-guide research + pre-registered descriptive studies, forward
ledgers, loop enrollment.

**Authority ceiling (program-wide):** display/context. Every emitted artifact carries the
house authority contract exactly as `engine/index_momentum.py` emits it:
`"authority": {"rank": false, "size": false, "gate": false, "escalate": false}` plus the
plain-word accruing string — display-only, not validated. (The `may_*` phrasing used in
some engine headers is prose, not the JSON contract.) The gauntlet is a promotion gate,
not a build gate: nulls print, accrual continues, non-standalone survivors are retained
as confluence inputs.

**What this program is NOT:** not the rates side (RIC owns yield-series momentum, term
premium, event windows, Forward Path — CCW consumes read-only; the **Treasury-momentum
leg of the operator's ask is therefore deferred to RIC's chartered organ**, served
interim by a clearly-labeled ETF-price proxy, §3-P3 — the operator should know this leg
arrives at RIC's cadence, and §7 recommends pulling RIC's YIELD wave forward); not a
vol-suppression lens (VSB); not liquidity mechanics (RLT); not a re-open of any killed
construction; not calendar-gated anything; not an entry conditioner; not LLM-originated
scores. No CDS/CDX (no free source). Broad non-AI sector coverage ships only at the
coarse GICS-map granularity of §3-P2 — per-sector OAS curves à la ICE sub-indices are
out of scope until a sector-tagged bond source exists (FRED carries none).

**Operator action item (non-blocking):** register a free FINRA API credential
(gateway.finra.org/app/dfo-console, individual Public tier) and add
`FINRA_API_CLIENT_ID` / `FINRA_API_CLIENT_SECRET` repo secrets. W5 arms itself when the
secrets appear; nothing else waits on it.

---

## 1. Census — what exists (do not rebuild; wire it)

| Capability | Home | State |
|---|---|---|
| Bond health dashboard: curve/credit/real/stress pillars, cycle clock, calibrated composite, `data/bonds/bond_health.json` AI contract, bonds.html | `engine/bonds.py`, `scripts/build_bonds.py` (BOND_HEALTH_DASHBOARD.md, calibrated Phases 0–4) | MATURE. Index-level credit only (HY/IG OAS, Moody's Baa−Aaa) |
| Risk radar credit/rates Tier-A scares: `credit_oas_roc` (HY OAS 21d Δ pctile), `credit_hyg_tlt`, `rates_move`, `rates_realrate` | `engine/risk_radar.py` | LIVE. The only radar↔bond wiring that exists (predates this program) |
| Momentum canon: `rsi_macd()` (EMA14−EMA60 of RSI, signal EMA5), `stoch_rsi_kd()`; confluence T1–T4 cascade on 2B/3B session-grouped grids (200 daily-bar min); `mtf_snapshot` D/3D/W/M; IHM organ pattern (roster → grids → events → forward ledger, display-only) | `engine/canon.py`, `engine/confluence_tiers.py`, `engine/cycles.py`, `engine/index_momentum.py` | MATURE, series-agnostic with known sparse-series hazards (§2.4) |
| Theme baskets (equity side): `ai_neoclouds` (CRWV, NBIS, CORZ, IREN…), `memory_storage` (MU, WDC, STX, SNDK), `ai_semiconductors`, AI-adjacency tags | `data/baskets/membership.json`, `scripts/build_ai_adjacency_tag.py` | LIVE. No hyperscaler basket; equity tickers only, no bond linkage |
| ETF holdings collector with a working SSGA XLSX fetch idiom (equity funds; URL constant + UA + header-row detection reusable; **parser is NOT reusable** — it hard-requires a ticker column and filters non-equity rows) | `collectors/etf_holdings.py` (`SSGA_XLSX`, `_fetch_ssga`, `_normalize`) | LIVE nightly. Zero bond funds in universe |
| FRED collector: config-enrolled series, API-key + keyless fallback, append-only upsert (rolling-window-proof); archive merge idiom exists for exactly TWO series (`hy_oas`, `ig_oas` — `engine/inputs.py` combine_first) | `collectors/fred.py`, `data/archive/BAML*.parquet` | LIVE. Archives: HY OAS 1996→2026-06; IG OAS 1996→2026-06. **Rating-bucket ladder series have NO archive** |
| Treasury curve on disk: DGS3MO/6MO/1/2/3/5/7/10/30 daily (DGS10 1962→); Moody's `DAAA`/`DBAA` daily (1983→/1986→) — the only deep-history ladder-like credit read | `data/fred/` | LIVE. **DGS20 absent** (RIC P4 needs it too — §5 R7 ownership) |
| Already-enrolled credit series (do NOT re-add — duplicate alias KeyError kills the whole FRED adapter, see tests/test_fred_series_alias_conflicts.py): `BAMLH0A0HYM2`, `BAMLC0A0CM`, `BAMLH0A3HYC` (=ccc_oas), `BAMLHYH0A0HYM2TRIV` (=hy_total_return), `BAMLEMCBPIOAS`, DBAA/DAAA | `config.yml` fred.series | LIVE |
| Single-name rate sensitivity | `engine/stock_macro_sensitivity.py` | LIVE, display-only, US single stocks |

**What is genuinely missing (the build surface):** per-bond corporate price data; any
g-spread anywhere; issuer/theme/sector credit aggregation; momentum organs on any spread
series (zero callers); corporate bond market breadth; fallen-angel tracking; a credit
block in bond_health.json; credit theme surfaces; maturity-wall and credit-vs-equity
divergence reads.

---

## 2. Data doctrine (probed live 2026-07-14; corrected per adversarial review)

### 2.1 Primary backbone — SSGA daily holdings files (free, keyless, verified)

Use the repo's verified constant `collectors/etf_holdings.py:SSGA_XLSX`
(`https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{fund}.xlsx`)
— the live probe observed this 301-redirect to the `/library-content/...` path; the
collector imports the constant and follows redirects rather than re-typing a URL.
Observed per-bond columns (header row 5): `Name | Identifier (ISIN) | SEDOL | Weight |
Coupon | Par Value | Market Value | Local Currency | Maturity`. **MarketValue/ParValue is
treated as a DIRTY price until proven otherwise** (§2.4-1). Cadence T+1 business day
(~10:00 UTC). US ISINs embed the CUSIP (chars 3–11), so CUSIP6 issuer prefixes ARE
derivable from this source.

| Fund | Universe | Probed |
|---|---|---|
| SPSB | IG 1–3y (short) | pattern-inferred — **W1 verifies live** |
| SPIB | IG 1–10y, ~5,200 bonds | ✅ live probe |
| SPLB | IG long (10y+; the META 2055/2065, AMZN 2066 tranches live here) | pattern-inferred — **W1 verifies live** |
| JNK | HY broad, ~1,221 bonds | ✅ live probe |
| SPHY | HY broad, ~1,929 bonds | ✅ live probe |

The bond collector reuses only the URL constant, browser-UA/http idiom, and
`read_excel(header=None)` + Name-row header detection. The column mapping is **new
ISIN-keyed code**: no ticker column exists, and rows must NOT route through
`is_non_equity_holding` (which would drop every bond).

### 2.2 FRED adds (W1, config-only — audited against current enrollment)

Genuinely new: `DGS20` (**frozen alias `us20y`, group `curve`** — §5 R7), rating ladder
`BAMLC0A1CAAA`, `BAMLC0A2CAA`, `BAMLC0A3CA`, `BAMLC0A4CBBB`, `BAMLH0A1HYBB`,
`BAMLH0A2HYB`; effective yields `BAMLC0A0CMEY`, `BAMLH0A0HYM2EY`; total-return
`BAMLCC0A0CMTRIV` (IG). Already enrolled — consume, never re-add (§1): CCC OAS, broad
IG/HY OAS, HY TRIV, EM OAS, Moody's pair. **History honesty:** every BAML series is a
~3y rolling window; only broad IG/HY OAS carry 1996→ via `data/archive` combine_first.
The six new ladder buckets therefore start ~2023→ and accrete forward — no archives
exist for them; the deep-history ladder-like read is Moody's Baa−Aaa (1986→). W1
extends the archive-merge idiom to snapshot today's 3y window of the new series into
`data/archive/` on first collect (so the program's own start date is the permanent
history floor, not a rolling edge).

### 2.3 Fallbacks and enrichments

- **iShares LQD/HYG** (per-bond CUSIP, YTM, duration, rating, sector): endpoint live but
  behind a SourceDefense JS challenge — needs Playwright. Used once in W2 as the manual
  validation sample; wave-scoped later only if SSGA proves insufficient (it would also
  unlock a true per-bond sector field and ratings).
- **FINRA Query API** (free registration): `fixedincomemarket/trace` per-CUSIP real trade
  prices/yields (~12mo rolling) + `TRACE HISTORIC` to 2002 (the backfill path that
  unlocks multi-timeframe confluence early, §2.4-5) + `corporateDebtMarketBreadth` /
  `…Sentiment` daily market aggregates. OAuth client-credentials; keyless impossible
  (live 401s). W5.
- **Vanguard / Invesco / Schwab holdings:** probed UNUSABLE (quarterly-lag / 406 / 403).

### 2.4 Issuer universe (probed; registry v1 in §3-P1)

Hyperscalers are now mega IG issuers: MSFT (~$103B debt, Aaa/AAA), AMZN ($119B LT debt;
Jul-2026 $25B 8-tranche deal, 2029–2066), META (Oct-2025 $30B, 2030–2065, Aa3/AA−),
GOOGL (Feb-2026 ~$32B multi-currency incl. $20B USD, Aa1/AA+), ORCL ($108B total debt,
Baa2/BBB **negative outlook at all three agencies — the standing fallen-angel watch**).
Neoclouds: CRWV is the only one with straight HY notes (9.25%/2030, 9.75%/2031,
9.625%/2032 — in HY index funds); IREN/NBIS are converts-only (not index-eligible —
disclosed coverage gap). Memory: MU (IG, BBB positive), STX (HY, Ba1), WDC (split-rated);
SNDK (private term loan), Samsung (no USD paper), SK Hynix (one RegS bond) — disclosed
gaps. Adjacent AI credit: EQIX/DLR (DC REITs, IG), VST (rising star, HY→IG 2025-26),
CEG, NEE, DELL, HPE. Control: T + VZ (`telecom_legacy` — **created by this program in
W1**; the 1990s telecom capex-debt boom is the standing historical rhyme for the AI
capex credit cycle). These external facts (ratings, outlooks, deal sizes) are registry
`coverage_notes`, **never matching keys** — matching runs on harvested identifier
prefixes + name patterns, refreshed nightly (§3-P1).

### 2.5 Data honesty (printed on every surface that shows levels)

1. **Dirty prices / accrued-interest sawtooth.** Sponsor MarketValue for bond funds
   plausibly includes accrued interest, making MV/Par a dirty price. Solving YTM from a
   dirty price as if clean injects a coupon-cycle **sawtooth** (≈0→30bp on a 5% coupon,
   8y-duration bond) into YTM/g-spread series — a time-varying error that aliases
   directly into Δ/velocity/oscillators; it does NOT cancel in changes. **Law:** W2
   verifies dirty-vs-clean empirically (MV/Par vs independent clean prices on a liquid
   sample) and, if dirty, subtracts computed accrued (coupon, semiannual, 30/360, last
   coupon date inferred from maturity anniversary) BEFORE the YTM solve. The validation
   gate samples bonds across accrual fractions (per-coupon-cycle test), not one
   snapshot day.
2. **Matrix prices.** Sponsor prices are evaluated/matrix prices, T+1, stale for illiquid
   line items. Levels are approximate context; Δ and momentum are the primary read for
   pricing-model bias (which is roughly stable) — but NOT for accrued (point 1) or
   composition (point 3), which need their own guards.
3. **Composition churn.** Index funds add new issues (AMZN's Jul-2026 $25B enters
   SPIB/SPLB), roll off maturities, and migrate fallen angels between funds — each event
   mechanically jumps a naive par-weighted aggregate with zero credit-quality change.
   **Law:** theme/issuer/sector Δ series are computed on a **matched panel** (same-bond
   basis): entry/exit dates flagged, a newly-entered tranche contributes no Δ for its
   first 5 bars, aggregate-level composition-change markers suppress confluence-cross
   firing on affected bars. Level series may show the full-panel value with the
   composition marker drawn. Pre-registered W2 exit item alongside the YTM gate.
4. **Callables.** Without call schedules we compute YTM, not YTW. The bias is
   **HY-concentrated** (IG paper is mostly make-whole callable, YTW≈YTM; HY carries
   binding par-plus call schedules) — i.e. largest exactly in the junk themes. Near-par
   premium flips (market re-prices to call) put a spurious kink in our to-maturity
   g-spread that momentum would misread. **Law:** near-par callable HY tranches are
   flagged and excluded from momentum contributions (they still count in levels/par
   aggregates); YTW acquisition is prioritized for HY themes when a call-schedule source
   lands (iShares W-later or TRACE reference data).
5. **No pre-accrual history + confluence horizons.** Holdings files have no archive:
   per-issuer series begin the day W1 lands (R12 urgency). Day-one momentum runs on the
   1996→ broad IG/HY OAS (+ EY / TRIV / Moody's pair) and deep-history ETF prices
   (LQD/HYG/JNK/TLT via yahoo store). Two honest unlock horizons for new series: the
   daily-grid cascade needs 200 daily bars ≈ 9.5 months; the 2B/3B multi-timeframe
   confluence tiers need ~400–600 daily bars ≈ 19–29 months. The W5 TRACE HISTORIC
   backfill is the early-unlock path for both. Builders: 2B/3B means canon
   session-grouped resample (`canon.resample_sessions`), never pandas calendar
   `resample('3B')` (the canon docstring's ~80% signal-relocation warning).
6. **Spread-series oscillator caveat.** Canon RSI/StochRSI are validated on equity price
   golden vectors, not spreads. Spreads are floored near zero, unbounded above, and trend
   persistently in blowups — StochRSI pins at extremes exactly when warning matters.
   **Law:** on spread series, velocity-percentile (Δ21/Δ63 vs 10y window, era-split) is
   the PRIMARY read; oscillator crosses ship as secondary context only after the W3
   pre-ship sanity study replays them across historical widening episodes (2008, 2011,
   2015-16, 2020, 2022) on the deep broad-index history and documents behavior. Bond
   PRICE series (ETFs, theme price aggregates) use the canon organs normally.
7. **Sparse-series law.** Momentum organs run only on dense daily series: broad/ladder
   FRED series, ETF prices, and aggregates that clear a **per-theme density gate**
   evaluated at runtime (≥8 distinct tranches AND ≥60% of member tranches repricing on a
   rolling 21d window). Sub-threshold themes (neoclouds ≈ 3 CRWV tranches, split-name
   memory) render price/level/Δ/velocity only — no oscillator, no confluence — with a
   plain-word "too few traded bonds for trend gauges" note. Single names likewise.
8. **Index-fund lens.** The store sees index-eligible bonds only (144A-unregistered/
   RegS/converts excluded). Printed as a plain-word coverage note ("tracks the bonds
   inside the big index funds — private loans and convertibles are not visible here").

---

## 3. Architecture — seven pillars

### P1 — Holdings PIT store + issuer→theme registry (W1)

New adapter `collectors/corp_bond_holdings.py` (imports `SSGA_XLSX` + UA/http idiom from
`etf_holdings.py`; **new ISIN-keyed parser** per §2.1): 5 funds →
`data/corp_bonds/holdings/<FUND>/<YYYY-MM-DD>.parquet` (PIT, append-only, keep-FIRST per
date), schema `[isin, cusip6, name, coupon, par_value, market_value, weight_pct,
maturity, currency, fund, as_of]` (cusip6 derived from US ISINs). Registry
`data/corp_bonds/issuer_themes.json`: theme → issuers → `{equity_ticker,
name_match_patterns, id_prefixes, tier(IG/HY/split), coverage_notes}`. Matching is a
**maintained mapping, not a one-time freeze**: W1 seeds it from the first live fetch;
every nightly, unmatched rows are logged with a match-rate stat, and a clock alarm fires
when a high-par unmatched issuer appears (candidate missing finance-subsidiary — the
NEE-Capital / Equinix-Europe-2 class). Unmatched rows still feed whole-market breadth.
Registry membership amendments by PR (R5); the nightly refresh only updates matching
patterns for already-registered issuers.

### P2 — G-spread engine + aggregates (W2)

`engine/corp_credit.py`: per bond — accrued-interest correction per §2.5-1, YTM solve
(vectorized Newton with bisection fallback — no per-bond Python loops; measured step
cost is a merge gate), tenor = years-to-maturity, g-spread = YTM − interpolated CMT
(DGS3MO…DGS30 incl. `us20y`) at tenor, joined **last-available-on-or-before** (never
exact date−1; Monday/holiday/year-boundary join tests live in THIS wave, standing law).
Aggregations, all matched-panel-guarded per §2.5-3:

- **Issuer:** par-weighted price/YTM/g-spread + n_bonds + WAM.
- **Theme:** par-weighted across member bonds + **tranche-level dispersion** (p90−p10 of
  member-bond g-spreads, n≥8 floor; below floor → max−min with plain-word small-n
  disclosure; n<3 → null printed). Dispersion at ISSUER level is degenerate (most themes
  have ≤5 issuers) and is not computed.
- **Sector (coarse):** issuer→equity_ticker→GICS sector via the existing equity
  universe reference; every mappable bond aggregates into sector g-spread/Δ series
  (financials, energy, industrials, utilities, healthcare, tech…). Coverage stat
  printed; unmappable par disclosed. This is the operator's broad-sector lens at the
  granularity the data supports (§0 fence).
- **Maturity wall:** par outstanding by maturity bucket (0-1y/1-3y/3-5y/5-10y/10y+) per
  theme/issuer — refinancing-cliff read, free from the P1 schema.
- **Market:** IG and HY full-panel aggregates + IG−HY quality spread.

**Validation gate (pre-registered W2 exit criteria):** (a) dirty-vs-clean resolved
empirically; (b) computed YTM within ±25bp of sponsor/iShares displayed YTM on a ≥20-bond
liquid sample **spanning accrual fractions** (per-coupon-cycle); (c) computed broad-IG
par-weighted g-spread within ±30bp of BAMLC0A0CM on overlapping dates; (d) matched-panel
guard demonstrably suppresses a synthetic composition-jump fixture. Results printed to
`data/corp_bonds/validation.json`. Misses → fix before any series ships. Runs in the
COLLECT lane (after the holdings step), never the render job; emits parquet series +
snapshot JSON that `build_bonds.py` only reads. `[timing]` ticks + measured cost in the
PR body; config/dag.yml declaration in the same PR.

### P3 — Credit momentum organs (W3)

`engine/credit_momentum.py` (`credit_momentum.v1`), IHM-pattern sibling, canon math only:

- **Roster, day-one (real deep history):** broad IG OAS + HY OAS (archive-merged 1996→),
  their EY/TRIV mirrors, Moody's Baa−Aaa (1986→), **IG−HY quality spread**, and price
  mirrors LQD/HYG/JNK (yahoo store, deep history). **Roster, ~3y history (rolling-window
  start):** the six new ladder buckets — daily-grid organs only until bars accrue
  (§2.5-5). **Roster, accruing:** theme/sector g-spread + price series from P2, subject
  to the §2.5-7 density gate; issuer series display Δ/velocity only.
- **Grids:** D / 2B / 3B / W-FRI via session-grouped resample; canon `rsi_macd` +
  `stoch_rsi_kd` per grid; cross events with the IHM quality-tag vocabulary; T1–T4
  cascade where the two-horizon bar requirements of §2.5-5 are met.
- **Velocity & acceleration:** velocity = Δ21/Δ63 with 10y-window percentile (era-split
  display); acceleration = `hist_vel3` histogram velocity + Δ of the 21d velocity
  series. On spread series these percentiles are the PRIMARY read (§2.5-6). Spread
  orientation: widening = deterioration = severity semantics EN and ZH (§5 R13).
- **Credit-vs-equity divergence (display series):** per theme, 21d spread Δ direction vs
  the linked equity basket's 21d return direction — the four-quadrant read ("equity up
  while its credit deteriorates" is the named risk-formation quadrant). Descriptive,
  no score.
- **Confluence tags (pre-declared, K-of-N, density-gated):** `credit_theme_stress` per
  qualifying theme — ≥2 of {spread velocity pctile ≥85, matched-panel 3B spread
  up-cross (secondary, post-sanity-study), theme price 3B down-cross};
  `credit_market_turn` — ≥2 of {broad HY velocity pctile ≥85, IG−HY quality spread
  widening 21d, CCC−BB differential widening 21d}. Display states; fade base-rate
  context prints once measured; before that, plain words: "no track record yet — first
  events accruing."
- **Pre-ship sanity study (W3 gate):** replay the oscillator constructions across the
  1996→ broad-index history's widening episodes; document StochRSI saturation/asymmetry
  behavior; demote/re-spec any construction that fires pathologically (verdict printed,
  display-tier — this is estimator hygiene, not a promotion gauntlet).
- **T-bond leg (RIC-owned):** consume `yield_momentum.v1` read-only when it lands. Gate
  at W3 ship time: if RIC's organ is already live, mount it and build NO interim; else
  mount the interim TLT/IEF ETF-price momentum block (canon math, display, plainly
  labeled "interim proxy — the rates program's yield organ replaces this"), removed the
  release after RIC ships (§5 R6).
- **Forward ledger:** `data/corp_bonds/forward_log.jsonl`, keep-FIRST, one row per
  velocity-threshold/cross/confluence event; ruler frozen before first stamp: primary
  h21 / secondary h63 — (a) spread-direction hit vs same-side base rate, (b) Δbp
  magnitude, (c) descriptive equity-twin follow-through. Era split; episode permutation
  at read; first read at §7 clock. Runs in the COLLECT lane; dag.yml declared;
  `[timing]` ticks; measured cost gates the merge.

### P4 — Whole-market breadth (W3 core; W5 enrichment)

From our own store (~8–9k bonds across 5 funds): daily advancing/declining share (price
Δ on matched panel), % above 20d median price, new 4-week/52-week-low share (as accrual
allows), issuer-level advance/decline, IG-vs-HY breadth split. Computable from day ~21
onward, no external key. FINRA `corporateDebtMarketBreadth`/`Sentiment` (trade-based,
includes non-index bonds) mounts alongside when the operator key lands — two sources,
labeled distinctly, never blended.

### P5 — Fallen-angel / rising-star watch (W3)

Membership-transition detector on the PIT store: an issuer's bonds appearing in JNK/SPHY
having been in SPSB/SPIB/SPLB (or vice versa) = observed index migration — the
mechanical fallen-angel/rising-star event (VST 2025-26 is the rising-star archetype;
ORCL is the standing watch on the other side). Transition events feed the composition
guard (§2.5-3) so the watch never doubles as a spread-jump artifact. Plus the named
display series: watched-issuer g-spread minus the matched-maturity BBB-median ("the
market's downgrade vote, before the agencies"). New-issuance events (large new tranches
entering the panel) surface on the same watch strip — the debt-raise tape the AI capex
story runs on. No rating data claimed; agency actions arrive only as registry
coverage_notes.

### P6 — Surfaces + integration (W4; mockups-first, operator ratification)

- **bonds.html gains a "Corporate credit" desk** (bonds stays the credit home — §4):
  glance tier = market state + plain-word stance within doctrine budgets (subtitle ≤14
  words, no comparative-vs-market constructions, no "spread/g-spread/OAS" vocabulary —
  Tier 1 says "extra yield lenders demand"; exemplar: *"Company-bond stress is low. AI
  borrowing costs: watch — don't chase."*), theme tiles (hyperscalers / neoclouds /
  memory / AI power / DC REITs / hardware / telecom control): level (approx-labeled), Δ,
  velocity arrow, momentum state where density-qualified, stance word. Whole-market
  breadth strip. Fallen-angel + new-issuance watch chips. Maturity-wall mini-view.
  Credit-vs-equity divergence quadrant per theme. Receipts, coverage notes, construction
  detail on Tier 2/3 per DESIGN_DOCTRINE checklist.
- **Equity-twin cross-links:** each credit theme tile links its equity basket
  (`ai_neoclouds` ↔ neocloud credit) and vice versa (basket detail pages gain a credit
  chip when the theme has one).
- **Contracts:** `bond_health.json` += `corporate_credit` block (market state, per-theme
  states, breadth, watch list, divergence quadrants) — master brain + hub consume
  automatically; RIC Forward Path board may mount a credit row read-only (their board,
  their choice); risk radar gets nothing until W6's Tier-B accrual path.
- ZH parity; severity semantics on spread gauges in both languages (R13); adversarial ZH
  review pass (opus over-flip pattern).

### P7 — Studies + loop enrollment (W6)

Field guide FIRST (understanding-before-backtest law): the AI-capex credit cycle field
guide — telecom-1990s rhyme (the W1 `telecom_legacy` control exists for exactly this),
hyperscaler issuance-wave timeline 2025-26, neocloud financing structures (straight HY vs
converts vs private credit vs SPV/vendor financing), what widens first historically,
fallen-angel mechanics. THEN pre-registered descriptive studies **scoped to data that
actually has history** (adversarial-review correction): S1 — on the 1996→ broad IG/HY
OAS + Moody's Baa−Aaa: do spread-velocity/momentum constructions lead broad-index turns
and equity drawdowns (full era-split pre/post-2010 + 2021+); S1b — the rating-ladder
lead/lag version, **gated on** W5 TRACE backfill or ~2y ladder accrual (era-split
impossible before then — stated, not hidden); S2 — does tranche-level theme dispersion
lead index widening (accrual-gated); S3 (post-W5) — issuer-level spread momentum vs
equity drawdown for the theme universe. Episode-permutation nulls (month-block bootstrap
ban honored), overlap-corrected long horizons, printed verdicts. Loop enrollment: synapse
entries for every emitted artifact (producer, cadence, storage, tier, consumers, and
`horizon_role` — the hard-fail field), lobe charter + fitness sensors, scorecard pattern
on the forward ledger.

---

## 4. Adjudication — should the bond lobe fold into Transmission? **NO (with wiring).**

The operator asked whether the whole bond lobe should be integrated into Transmission
("interest rate lobe… just integrated with Risk Radar lobes"). Ruling, from census facts:

1. **The premise, precisely.** Nothing recently merged Transmission into Risk Radar: the
   radar's `credit`/`rates` Tier-A scares have read bond signals since inception
   (`engine/risk_radar.py`). What IS chartered is RIC P6 — transmission.html rebuilt as
   the unified **Rates & Inflation Command** page (Forward Path + Release Radar + yield
   momentum + event windows). Only RIC's W0 charter has merged; its waves are unbuilt.
2. **The real alternative, steelmanned.** The strongest opposite ruling is not "merge
   the lobes" but: *ship the CCW credit desk as a fifth block on RIC's unified page*,
   so one page carries the whole bond market. Rebuttal: (a) RIC P6 is already a
   four-block merge whose glance tier will be at its word-budget ceiling — a fifth
   block re-creates the mega-page defect DESIGN_DOCTRINE exists to prevent (Law 4 is
   enforced like the render budget); (b) sequencing — RIC P6 is waves away; parking CCW
   surfaces on it would block the credit desk on another program's UI schedule while
   the credit data is already accruing; (c) the credit desk's natural neighbors are the
   calibrated credit pillar, cycle clock, and health composite that ALREADY live on
   bonds.html — the user reading "is credit risk forming?" needs those adjacent, not
   OPEX windows; (d) the contract layer gives RIC's page a credit row read-only anyway,
   so the unified page still shows credit state without hosting the desk.
3. **Mechanism split, not page split.** Transmission/RIC prices the **discount rate**
   (Fed path, inflation, yields); Bonds prices **default risk** (credit spreads, credit
   cycle, bond-market health). These are the two distinct things bond markets tell you;
   coupling the pages couples two different user questions.
4. **Lobe accountability.** Bonds is a charter-enrolled lobe surface with its own
   fitness/accountability clock; merging lobes collapses attribution granularity the
   metabolism layer depends on.

**Therefore:** the bond lobe stays sovereign; CCW lands the credit desk on bonds.html.
Integration at the **contract layer**: bond_health.json `corporate_credit` block; RIC
Forward Path credit row (read-only mount, their choice); risk-radar enrollment only via
RRX's three-tier path (Tier-B accrual first, calendar-agnostic constructions only); CCW
consumes RIC `yield_momentum.v1` read-only for the Treasury momentum leg. Cross-links
both ways. If, after RIC P6 ships, the operator wants one physical page, that is a
page-composition decision to re-ratify at mockup time — not an engine or lobe merge, and
not this program's call.

---

## 5. Ruling table

| # | Ruling |
|---|---|
| CCW-R1 | The corporate-credit domain (spread series as primary tracked instruments, credit momentum, corporate bond breadth, credit-regime organs, IG/HY ladder reads) is unowned; CCW claims it. Boundary map: RIC = yields/rates momentum/event windows (consumed read-only); VSB = vol-suppression + AI-bifurcation lens (HY OAS appears there only as a lagging display confirmer); RLT = liquidity/rebalance mechanics (consumed read-only); RRX = radar enrollment path only. |
| CCW-R2 | Bond lobe does NOT merge into Transmission/RIC (§4, incl. the fifth-block steelman). Integration via contracts + links; page composition revisitable only at operator mockup ratification after RIC P6 ships. |
| CCW-R3 | SSGA daily holdings = primary backbone via the repo's verified `SSGA_XLSX` constant; matrix-price/T+1 caveats printed wherever levels show; Δ/momentum primary for pricing-model bias — with the accrued and composition guards of §2.5 as their own laws (Δ does NOT neutralize those). |
| CCW-R4 | G-spread = accrued-corrected YTM − last-available-on-or-before interpolated CMT. YTM not YTW; callable bias is HY-concentrated and near-par callable HY tranches are excluded from momentum contributions (§2.5-4). The W2 validation gate (§3-P2, four criteria incl. per-coupon-cycle sampling and the composition-guard fixture) is a hard exit criterion. |
| CCW-R5 | Issuer→theme registry: membership frozen at W1, amendments by PR; matching patterns are a nightly-maintained mapping with an unmatched-high-par alarm (§3-P1). External facts (ratings/outlooks/deal sizes) are coverage_notes, never matching keys. Coverage gaps (converts, private loans, RegS, non-index bonds) disclosed in plain words on every affected tile. |
| CCW-R6 | Treasury momentum belongs to RIC P4. CCW consumes `yield_momentum.v1` when it lands. Interim TLT/IEF ETF-price block ships ONLY if RIC's organ is not live at CCW-W3 ship time, is plainly labeled interim, and is removed the release after RIC ships. |
| CCW-R7 | DGS20 FRED enrollment ships in CCW-W1 with **frozen alias `us20y`, group `curve`** (matching the us{N}y convention). CCW-W1 owns the add; RIC's fred-config touch must be a no-op on DGS20 — recorded bilaterally via the RIC masterplan status-log amendment shipped in this same PR. CCW builds no other part of RIC's organ. |
| CCW-R8 | No calendar-gated legs anywhere (standing `_SCARES` kill honored). No positioning fusion (credit state never fuses with entry/size). Risk-radar entry only via the documented three-tier path, Tier-B accrual first. LLMs de-escalate only; never originate credit states. |
| CCW-R9 | Every study: era split where history exists (stated impossible where it does not — S1b), episode-permutation nulls, overlap-corrected long horizons, time-preserving nulls for issuer-cluster inference, nulls printed. |
| CCW-R10 | Display-tier ceiling program-wide; the emitted contract is the index_momentum `authority` dict (rank/size/gate/escalate all false) — §0. Promotion only through pre-registered Lane-(ii) gauntlets adjudicated separately. Nulls never block building or accrual. |
| CCW-R11 | VSB's adjudicated stance — "HY OAS LAGS in valuation-driven bubbles; calm ~270bp is NOT reassurance" — is inherited on every aggregate-spread surface. "Theme-level spreads may move before the aggregate" is a hypothesis for S2/S3, never a claim, until measured. |
| CCW-R12 | Accrual urgency: the holdings store is unrecoverable history. W1 ships collectors before any engine polish; W1 also archives the current 3y window of newly-enrolled FRED series (§2.2) so the rolling window never erodes our floor. |
| CCW-R13 | Spread orientation: widening = deterioration = severity colors in BOTH languages (no zh directional flip on spread gauges; bond-PRICE direction gauges follow the standing 红涨绿跌 law). Adversarial ZH review on the W4 surface. |
| CCW-R14 | FINRA lane is an operator action item; the program never blocks on it. When keys land: breadth/sentiment collector + TRACE HISTORIC one-shot backfill for the registry universe (off-render; async API; R2 publish if heavy). Two breadth sources render distinctly labeled, never blended. |
| CCW-R15 | Density gate (§2.5-7) and the spread-oscillator demotion (§2.5-6: velocity-percentile primary, crosses secondary pending the W3 widening-episode sanity study) are program law. No oscillator ships on a series that fails the gate. |
| CCW-R16 | Every W2/W3 engine step runs in the COLLECT lane (or an off-render lane), never the render job; each wave PR states its measured `[timing]` step cost (measure, don't code-read-estimate) and confirms its job stays under cap; config/dag.yml declaration + synapse entries ship in the same PR as each new organ (dead-wire law). |

---

## 6. Wave plan (each wave = one PR; branch off fresh origin/main; same-day squash-merge; Sonnet builds, Opus reviews, Fable gates; no git ops inside build agents)

| Wave | Contents | Notes |
|---|---|---|
| **W0** | This masterplan + the RIC status-log DGS20 amendment (R7) | this PR |
| **W1 — data spine** | `collectors/corp_bond_holdings.py` (5 SSGA funds; SPSB/SPLB verified live in-build; new ISIN-keyed parser per §2.1; PIT parquet store; cusip6 derivation; match-rate logging + unmatched-high-par alarm) + FRED config adds per §2.2 audit (incl. `us20y`; first-collect archive snapshot of new series) + `data/corp_bonds/issuer_themes.json` v1 (incl. `telecom_legacy` control) + dag.yml/daily.yml wiring (collect lane, after collect_us, inside the us_scope gate) + tests (parser fixtures, alias-conflict expectations; new test files into the ci.yml pytest whitelist) | NO surface. Ships same-day as W0 if capacity allows (R12) |
| **W2 — g-spread engine** | `engine/corp_credit.py` per §3-P2: accrued correction, vectorized YTM, CMT join (+ Monday/holiday/year-boundary join tests — they live HERE with the join, not W1), matched-panel composition guard, theme/sector/maturity-wall/market aggregates, tranche-level dispersion, validation gate → `data/corp_bonds/validation.json`, dag.yml + synapse entries, measured `[timing]` cost | Exit gate = R4 four criteria |
| **W3 — momentum + breadth + watch organs** | `engine/credit_momentum.py` per §3-P3 (incl. the widening-episode sanity study as a ship gate, IG−HY quality spread, credit-vs-equity divergence, density gates, RIC-gated interim block) + own-store breadth + membership-transition/new-issuance watch + `bonds_alerts.py` extension (debounced state flips) + forward ledger + dag.yml/synapse + measured cost | Collect lane; dead-wire law |
| **W4 — surfaces** | Mockups → operator ratification → bonds.html Corporate credit desk per §3-P6 + `bond_health.json` corporate_credit block + equity-twin cross-links + ZH parity + adversarial ZH review | DESIGN_DOCTRINE checklist; Playwright verify 1280/375, light/dark, EN/ZH; template/site byte-sync law for any paired asset |
| **W5 — FINRA lane** (armed by operator keys) | OAuth client + breadth/sentiment collector + TRACE HISTORIC backfill one-shot (registry universe per-CUSIP daily series → early confluence unlock per §2.5-5) | Off-render; async API mode; R2 publish if heavy |
| **W6 — field guide + studies + loop** | AI-capex credit field guide; S1 run on real 1996→ history; S1b/S2 accrual- or backfill-gated (stated); S3 post-W5; RRX Tier-B docket for `credit_theme_stress` (calendar-agnostic legs only); lobe charter + fitness sensors + scorecard | Verdicts printed; promotion (if any) = separate adjudication |

Wave collisions: none with open PRs (map checked 2026-07-14: #2536 flow-ML prereg, #2535
ZH draft). RIC W1 (OPEX docket, due 2026-07-20) touches different files; the only shared
line is the DGS20 config add, owned by CCW-W1 with the alias frozen and the RIC-side
no-op recorded in this PR (R7). VSB is fully merged (W1–W6); no shared files.

---

## 7. Clocks

- **W1+1 nightly:** artifact check — 5 fund parquets present, match-rate ≥90% of
  theme-registry par matched, new FRED series + archive snapshots on disk.
- **W2 exit:** validation gate four-criteria pass, `validation.json` printed.
- **W3 ship gate:** widening-episode sanity study verdict printed; RIC `yield_momentum.v1`
  live-check decides the interim block (R6).
- **W3+30d:** breadth sanity read (advancing share vs broad OAS Δ sign-coherence);
  density-gate coverage report per theme.
- **W3+60d:** first forward-ledger read (h21 ruler; era/permutation discipline).
- **FINRA keys land:** arm W5 within the week; backfill one-shot; re-check confluence
  unlock horizons per theme.
- **RIC `yield_momentum.v1` ships:** remove any interim block same week (R6).
  Standing recommendation to the RIC program: pull the YIELD wave forward — CCW surfaces
  create immediate demand for the Treasury-momentum artifact.
- **~2028-H1:** ladder accrual passes ~2y — revisit S1b feasibility if W5 never armed.
- **2027-01:** program review — accrual health, study verdicts, any promotion dockets.

## 8. Key sources

SSGA holdings endpoints (live probes 2026-07-14: JNK/SPIB/SPHY HTTP 200 via the
`/library-content/` redirect target; repo constant `collectors/etf_holdings.py:39`);
FINRA Query API docs + live 401 probes (developer.finra.org; Fixed Income ToS: free
redistribution); FRED release 209 (192 BAML series; Apr-2026 3y-window policy; no sector
OAS); issuer facts: SEC filings and financial press probes 2026-07-14 (Meta FWP
000119312525258837; AMZN Jul-2026 deal coverage; ORCL outlook actions; CRWV note terms
via ratings coverage); local: BOND_HEALTH_DASHBOARD.md,
RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md, VSB masterplan, DO_NOT_REBUILD.md (no
credit kills), engine/collector census + 3-lens adversarial review 2026-07-14.

### Status log

- 2026-07-14 — W0 chartered (this PR). Census + live source probes + 3-lens Opus
  red-team complete (verdicts: SHIP-WITH-FIXES ×3; all majors incorporated — dirty-price
  accrued law, matched-panel composition guard, corrected FRED history claims, density
  gate, tranche-level dispersion, DGS20 alias ownership, SSGA URL/parser corrections,
  sector lens + maturity wall + IG−HY + divergence additions, §4 steelman).
  Adjudication §4 ruled: bond lobe stays sovereign; contract-layer integration.
