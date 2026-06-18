# Data / Signal Expansion — Viability Review (2026-06-14)

Evaluation of 11 proposed dashboard additions (sourced from an external "one-pager").
Method: 8 codebase-inventory readers + 11 free-data viability researchers + 1 synthesis,
all verified against the actual repo (not just the research dossier). Rigor bar = the
team's existing discipline: **free data only**, **Phase-0 validation (PIT, FDR, Deflated
Sharpe, costs) before any scored signal**, display/context held to a lower but still
honest bar, **A-shares mean-revert**, **MRS = subtract-only risk-off gate**.

## TL;DR verdict

| # | Proposal | Verdict | Why (one line) |
|---|----------|---------|----------------|
| 4 | Financial Conditions / **OFR FSI + CP spreads** | **MUST-BUILD** | Best ROI: 1 keyless CSV + 2 FRED series; net-new funding/EM stress decomposition; richest LLM cross-asset feed |
| 5 | Earnings Revision / **SUE from EDGAR** | **MUST-BUILD** | Only proposal with a path to a NEW Phase-0-passable scored alpha leg from data already on disk |
| 9 | Commodity **curve/basis** (+ EIA display) | NICE-TO-HAVE¹ | Genuine free tradeable leg (term structure) the board lacks; EIA collector already exists, just unwired |
| 2 | Fed Policy Path / repricing | NICE-TO-HAVE | Display: surface existing NTFS + dot-plot + forward ZQ/SR3 curve; predictive part = validation-only |
| 10 | China Property / Fiscal | NICE-TO-HAVE | 70-city home-price breadth is clean free net-new; rest mostly already computed; display/regime |
| 6 | ETF / Fund Crowding | NICE-TO-HAVE | VIP/overlap from already-collected 13F; contrarian risk overlay only — never "inflows = bullish" |
| 11 | Event-Risk / Catalyst Calendar | NICE-TO-HAVE | Display strip only; **do not** build the conviction-dampener (dead pre-FOMC drift, positive announcement premium ⇒ wrong-signed) |
| 3 | Treasury Supply / Auctions | nice-to-have, **deferred** | TreasuryDirect auctions API is net-new+free but the predictive core is ex-post; denser build, lower payoff |
| 1 | Macro Surprise Engine | **SKIP** | ~90% restates the nowcast residual we already score; no free consensus; surprises absorbed at the print |
| 7 | Short Interest / Squeeze | **SKIP** | Factor already **failed FDR** (q=0.32, sign-flips); net-new pieces are theater/paid/unbacktestable |
| 8 | Crypto Liquidity / Stablecoin | **SKIP** | Validated core (stablecoin tide, peg veto, SSR, MVRV) already shipped; net-new = coincident display for a BTC board |

¹ The #9 *curve/basis* leg is genuinely tradeable (storage theory: inventory becomes
tradeable through the futures basis) — higher-value than its "nice-to-have" label; the raw
*inventories* part is display.

**Recommended build order:** 4 → 5 → 9(curve) → 2 → 10 → 6 → 11.

## Key code-verified corrections to the original proposals
- **#9**: `collectors/eia.py` is already built and running (`data/eia/*.parquet`, last fetch 2026-06-13). The marquee "net-new" oil-inventory leg exists as a collector — just unwired. Roll-yield (`commodity_carry`) is collected but **not** fed to conviction.
- **#7**: `short_interest` factor already failed the team's own FDR bar (`data/edgar/ic_scorecard.json`: IC 0.033, t 1.73, q_fdr 0.32, `survives_fdr=false`, "size in disguise"). Empirically dead, not just redundant.
- **#4**: NFCI sub-indices + ANFCI + STLFSI4 are already collected (`config.yml:64-69`). The *only* net-new is **OFR FSI** (33-var daily global stress, functional + regional decomposition) and **CP-bill / A2-P2 spreads** — both confirmed absent. `cross_asset.py` (Kritzman-Page absorption ratio) is the natural home for the stress decomposition.
- **#1**: GDPNow, WEI, sticky/flex/median CPI, UMich exp, claims, Indeed, withheld-tax, SF-Fed sentiment are all already pulled and folded into recession_risk + nowcast blocks. A "surprise composite" re-skins the nowcast residual.
- **#2**: `bonds.py near_term_forward_spread()` (Engstrom-Sharpe implied-path proxy) + `curve_tp_adj` + `zq_implied_rate` already exist. Net-new = full forward ZQ/SR3 curve + dot-plot (FEDTARMD, never collected) + FOMC surprises (validation-only).

---

## Per-module detail

### #4 Financial Conditions / OFR FSI + CP spreads — MUST-BUILD (difficulty: low)
- **Net-new:** OFR Financial Stress Index (daily, 33 vars, functional legs Credit/Equity-val/Safe-assets/Funding/Volatility + regional US/Other-advanced/EM) — the **Funding leg embeds a free x-ccy-basis proxy** (otherwise paid). Plus CP-bill (`DCPN3M-DGS3MO`) and A2/P2 (`RIFSPPNA2P2D90NB`) commercial-paper spreads.
- **Free source:** `financialresearch.gov/financial-stress-index/data/fsi.csv` (keyless, ~6,700 rows from 2000, 2-bday lag); FRED for CP spreads (already wired).
- **Predictive value:** coincident stress gauge → ships as **display + optional subtract-only risk-OFF gate** (same posture as MRS), gated behind a Phase-0 vs the NFCI leg before any scoring. Not cross-sectional alpha.
- **Integration:** `engine/conditions.py` (optional gate parallel to NFCI), `cross_asset.py` (decomposition home), macro.html + bonds.html (display), `latest.json` → LLM context.
- **Scoring:** surface FSI level + 5 functional + 3 regional sub-series; `cp_bill = DCPN3M - us3m`; `a2p2 = RIFSPPNA2P2D90NB - AA`. Gate only after Phase-0.

### #5 Earnings Revision / SUE from EDGAR — MUST-BUILD (difficulty: high)
- **Net-new edge:** a **SUE / earnings-momentum factor from SEC EDGAR actuals already on disk** (`statements.parquet`) — fully PIT, survivorship-free, zero ToS risk, can clear the existing FDR/DSR harness. Documented strong (SUE/PEAD drift; revision breadth ~7.6%/yr decile spread, Mill Street 2023).
- **Lead with SUE (scored).** Treat analyst-**revision breadth** (Nasdaq earnings-forecast up/down counts; yfinance eps_revisions) as **display/confluence only** until ~1yr of weekly PIT vintages accrue forward (snapshot data ⇒ lookahead in backtests).
- **Scoring:** `SUE = (EPS_actual_q − E[EPS_q]) / σ`, `E[]` = seasonal-random-walk (`EPS_{q-4}` + 4q drift); winsorized cross-sectional z over S&P1500; run through `factor_ic_scorecard.py` (FDR/DSR) exactly like the existing factor zoo. Drop the sector "profit cycle" framing (overlaps residual_alpha + sector RS).
- **Integration:** factors.html (+ ic_scorecard), discovery.html / `setups.py` confirmer tiebreaker (same shape as the validated insider chip), stock.html earnings panel.

### #9 Commodity curve/basis + EIA display — NICE-TO-HAVE, curve leg elevated (difficulty: high)
- **Tradeable leg (build first):** futures **term-structure / basis** signal — `ts_basis = (front − deferred)/deferred` annualized; storage theory (Gorton-Rouwenhorst; Symeonidis) shows basis-ranked L/S ≈ 81 bps/mo (t≈4). The board stores roll-yield but **doesn't feed it to conviction** — wire `commodity_carry` into `commodity_conviction.py`, validate via `calibrate_commodities` split-half/DSR.
- **Display/nowcast:** EIA (already collected) inventory z vs 5y seasonal, refinery util, days-of-supply; COMEX/SHFE warehouse stocks (self-archive for PIT), GLD tonnes. **Skip** TC/RC + LME history (paid).
- **Integration:** commodities.html; LLM commodity-demand nowcast.

### #2 Fed Policy Path — NICE-TO-HAVE display (difficulty: medium)
- Surface existing NTFS + `curve_tp_adj` as an explicit "market-implied policy path" block; add **FOMC dot-plot** (FRED `FEDTARMD`) + multi-contract ZQ/SR3 forward curve with implied cuts/hikes labels. Treat Bauer-Swanson FOMC surprises as Phase-0/event-study **only** (event-sparse, lagged publish). High narrative value, no new scored signal.

### #10 China Property / Fiscal — NICE-TO-HAVE display/regime (difficulty: medium)
- One clean net-new free series: **70-city new-home-price breadth** (`akshare macro_china_new_house_price`, same Eastmoney host already used) = `count(cities MoM>0) − count(<0)`; + floor-space/land YoY (de-cumulate YTD, Jan-Feb combined gotcha) + daily rebar/iron-ore construction proxy. Re-surface existing credit impulse + M1-M2 scissors. **Drop LGFV spreads** (paid + policy-administered); proxy stress free via CGB curve + property-ETF drawdown + offshore HY-developer USD-bond yields. No scored A-share signal (mean-revert + short history).
- **BUILT (`feat/china-property-fiscal`):** "🏗️ Property & Fiscal" card on china.html + `latest["property"]` context for the LLM brief. Net-new `collectors/china_property.py` + `engine/china_property.py` (display-only, None-safe). **Source correction:** `macro_china_new_house_price` returns only Beijing+Shanghai — the *full* `RPT_ECONOMY_HOUSE_PRICE` datacenter report carries all 70 cities, so breadth is computed there (live −35: 14↑/49↓, easing off −58). Floor-space/land YoY **dropped** in favour of the NBS **国房景气指数 climate composite** (`RPT_INDUSTRY_INDEX`/EMM00121987) — it already bundles the investment/sales/land cycle, sidestepping the Jan-Feb-combined de-cumulation. CGB curve **unblocked** via the Eastmoney `RPTA_WEB_TREASURYYIELD` datacenter (no chinabond legacy-SSL scrape). Property-ETF 512200 drawdown reused from the existing `china` price store. Offshore HY-developer yields skipped (paid). Commodities demand-nowcast wiring **declined**: the commodity engine is a scored-conviction system with no display-only demand hook, so wiring there would breach the Phase-0 discipline (rebar/iron-ore serve the construction-demand read on the China card instead). Discipline held: regime context only, NOT a scored axis.

### #6 ETF / Fund Crowding — NICE-TO-HAVE risk overlay only (difficulty: medium)
- Cheap net-new: cross-fund **VIP/overlap score** from already-collected 13F (`vip = count(tracked funds holding)`, `ownership_hhi = Σ weightᵢ²`). **Fold crowding into the existing risk path** as a contrarian/fragility overlay (extend `technicals.py` crowding penalty: high-RS-crowding + high-SI + extended ⇒ temper conviction, subtract-only, Phase-0-gated like COT). **Never** an "inflows = bullish" board (ETF inflows are contrarian dumb-money).
- **BUILT (display-only).** VIP/overlap → `engine/smart_money.overlap_stats` (vip / ownership_hhi / book conviction) on the stock-page 13F panel. Fragility tag → `engine/crowding.py` (crowded + heavily-shorted + extended) as a contrarian RISK chip on the stock page — **NOT in the score**: Phase-0 (`scripts/fund_crowding_phase0.py`, see `reports/fund-crowding-phase0.md`) found crowding+extension carries NO forward-return edge and only a marginal/weak worse-drawdown tendency, and short interest has NO point-in-time history (single FINRA snapshot) to validate the SI leg at all. So the sizing-temper stayed un-wired; display-only, exactly the discipline rule.

### #11 Event Calendar — NICE-TO-HAVE display only (difficulty: low)
- Unify the two existing `is_context_only` calendars (`macro_news`, `commodity_news`) into one shared `engine.event_calendar`; add CPI/PCE/PPI/claims dates (FRED releases/dates API, key wired) + Treasury auctions; render a "US high-impact next 14 days" strip. **Do NOT build the event-risk score / conviction-dampener** — pre-FOMC drift died after 2016 and the announcement premium (Savor-Wilson) is *positive*, so a dampener is wrong-signed.

### #3 Treasury Supply / Auctions — deferred
- TreasuryDirect `auctions_query` API is genuinely net-new + free (bid-to-cover, bidder splits, high-yield, issuance mix/WAM, no key). But bid-to-cover/tail are **ex-post demand surprises** (not forecastable from the schedule); term premium already summarizes the duration-supply effect. Worth a future "Supply & absorption" display sub-panel on bonds.html; not in the near-term build set.

### Skips
- **#1 Macro Surprise** — restates the nowcast residual; no free PIT consensus; near-instant absorption (Citi ESI ≈ −0.04 corr to S&P).
- **#7 Short Interest** — factor failed our own FDR; short-volume ratio = MM-hedging noise; borrow fee paid; IBKR snapshot has no PIT history.
- **#8 Crypto Liquidity** — validated core already shipped; DeFi TVL doesn't Granger-cause price (reverse-caused); exchange netflows (the tradeable part) are paid. Real crypto leverage = the methodology gates already on `VECTOR_FACTOR_ROADMAP_2026`.

---

## Cross-asset AI integration
Both must-builds feed the **existing default-off, firewalled LLM layer** (DeepSeek Flash digest →
Opus/DeepSeek-Pro narrator, **never in the scoring path**) as richer *deterministic context vectors* —
same contract as `bond_health.json drivers_for` and the `cross_asset.py` absorption snapshot.

- **#4** is the high-leverage feed: its functional + regional stress decomposition lets the narrator
  *name the channel* when six markets move as one ("today's drop is the Funding leg + EM stress, not equity
  valuation"), pairing with the absorption-ratio "one-bet" verdict. Add to a `stress` block in `latest.json`.
- **#5** feeds `catalyst_stock.py` single-stock briefs + the profit-cycle narrative as a citation-able PIT
  SUE z-score; the LLM reads and explains it, never invents it.

Contract stays strict: the LLM only narrates already-computed deterministic numbers (degrade-never-raise,
public-data firewall, default-off). These proposals enlarge the *facts* the narrator can cite, not its authority.

---

## Build status (2026-06-14, branch `feat/stress-layer`)

### #4 OFR FSI / systemic-stress layer — SHIPPED (display + LLM context)
`collectors/ofr_fsi.py` (named `ofr_fsi`, decoupled from the separate OFR funding collector
`collectors/ofr.py` on PR #31) + a `systemic_stress` block in `engine/conditions.py` + a "Systemic stress"
card on the macro dashboard + the A2/P2 & CP-bill FRED spreads. **Phase-0 (`scripts/validate_stress_gate.py`):
DISPLAY-ONLY** — OFR FSI is a coincident gauge; its forward-drawdown AUC collapses out-of-sample (0.79 in
2000-2013 → 0.58 in 2013-2026) and adding it to NFCI fails the both-halves +0.02 bar. Ships as display + a
deterministic `latest['conditions']['systemic_stress']` context vector for the LLM, **not** in the scoring path.

### #5 SUE earnings-momentum factor — SHIPPED (scored factor)
Reality check changed the plan: the on-disk EDGAR panel is **annual only** (no quarterly EPS), so a real
SUE/PEAD signal needed a NEW quarterly-EPS pipeline. Built `collectors/edgar_eps.py` (keyless SEC XBRL
`EarningsPerShareDiluted` quarterly frames → `data/edgar/eps_quarterly.parquet`: 65k rows, 1,317 tickers,
2008-2026, PIT via period_end + a 60d reporting lag) + `engine/sue.py` (seasonal-random-walk
SUE = (EPS_q − EPS_year-ago)/σ, calendar-matched, point-in-time, stale-dropped). **Phase-0
(`scripts/validate_sue.py`): PASS** — on the leak-free quarterly IC grid SUE is the STRONGEST positive factor
and the only positive leg that survives BH-FDR across the whole factor family (mean IC 0.033, IC-IR ann 1.07,
t_HAC 2.81, q_FDR 0.059, quintile L/S Sharpe 1.26) — the bar the insider factor cleared and short_interest
failed. Wired as a **standalone scored leg** (`equity_factors.compute_factors`, not in the value/quality
composite, mirroring short_interest) → factors.html leaderboard + IC scorecard. **Caveat:** validated on the
2023-2025 price window because the price-universe cache is shallow there — the *same* caveat the entire
existing factor zoo carries (committed `ic_scorecard.json` spans the same 11 rebalances); the EPS history is
deep, so a deep-history + PIT-survivorship re-validation (as the insider factor earned separately) is the
honest follow-up. Deferred follow-ups: a per-stock SUE chip on stock.html + a `setups.py` SUE confirmer.

> **⚠️ Follow-up DONE → SUE DEMOTED (2026 — `reports/sue-deep-history-phase0.md`).** The
> deep-history + PIT-survivorship re-validation flagged above is complete: on deep 2011-2026 closes
> SUE's cross-sectional edge COLLAPSES (IC 0.033→0.0006, HAC t 2.81→0.06, no longer survives BH-FDR;
> the lone marginal survivor is now `payout`, on a survivorship-biased / optimistic panel). SUE is
> demoted scored→display on factors.html / signal_lab.html and reframed everywhere downstream
> (stock.html, the `engine/stock_score.py` EDGE leg, the dashboard SUE chips) as earnings-momentum /
> PEAD context — not a validated standalone alpha. The "SHIPPED (scored factor)" status above is the
> original record.
