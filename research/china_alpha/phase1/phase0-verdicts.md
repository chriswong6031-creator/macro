# China A-share pipeline — Phase-0 / Backtest Verdict Ledger

*research/china_alpha/phase1/phase0-verdicts.md · compiled 2026-07-03 · worktree `lucid-knuth-523979` (verified against local `data/` unless a fallback is flagged).*

**Purpose.** One authoritative table so the program never re-runs a dead test or re-derives a known
result. Every row cites a committed report, research doc line, or a command run in this session with
its output. Two hazard flags are attached where they apply:
**[DATA-HOLE]** the verdict's backtest is poisoned by a known substrate defect (survivorship top-N
universe, total-return/adjusted closes, retroactive column deletion, THS single-snapshot membership) and
must be re-run on a fixed substrate rather than trusted; **[FLOOR]** the finding is VALIDATED but wired
to no live surface (free alpha lying on the floor).

Sources of truth used: `reports/china-*.md` and `reports/hk-*.md` (committed phase-0 outputs);
`research/CHINA_HK_STOCK_SIGNALS.md`, `research/CHINA_ENGINE_REASSESSMENT.md` (the 2026-07-01 10-agent
re-measurement — the master synthesis), `research/ALLOCATION_CHINA_AUDIT.md`,
`research/CHINA_SECTOR_PATHWAY_PHASE0.md`, `research/CHINA_STOCKS_OVERHAUL.md`,
`research/CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md`, `research/INTL_FIX_MASTERPLAN.md`; plus two
scripts re-run live this session (`china_basket_momentum_backtest`, `china_basket_breadth_phase0`).

---

## A. The one-line ledger

Verdict codes: **VALIDATED** (survives its pre-registered gate), **FALSIFIED** (refuted / negative /
kills the edge), **MIXED-REGIME-GATED** (works in some eras/regimes only, sign-unstable across
splits), **UNTESTED** (no phase-0 run exists), **ACCRUING** (forward ledger open, not yet mature).
"Unit" = the level at which validation was measured (daily name-level, monthly cross-section, quarterly
basket, market-sizing, theme-slice, sector-phase context).

| # | Signal / hypothesis | Verdict | Key numbers (n) | Unit-of-validation & caveat | Source |
|---|---|---|---|---|---|
| 1 | **3-month within-sector reversal, deepest quintile, NO gates** | **VALIDATED** (the ONE name-selection edge) | excess **+0.56%/mo, ann Sharpe 0.58**, hit 56%, maxDD −37.6%, n=388 monthly rebal (1990→2026, ~790 names). Gated re-run: full-era FLAT gross Sharpe 0.67 / net 0.57, IC +0.047, t_HAC 5.56, survives FDR | Monthly cross-section, EXCESS over EW-universe = cross-sectional SKILL, **not net-of-cost** (high turnover). **[DATA-HOLE]** deep panel is survivorship top-mcap-today AND `china_search` retroactively deletes dropped names → 0.58 is an **upper bound** | `reports/china-reversal-phase0.md`; `reports/china-reversal-gated.md`; `CHINA_HK_STOCK_SIGNALS.md:98-128` |
| 2 | **Reversal + turn-confirmation** (buy after early bounce, ret_5d>0) | **FALSIFIED** (destroys the edge) | excess **−0.29%/mo, Sharpe −0.29, maxDD −78.9%**, n=363. +quality floor −0.21%/−0.19. The edge is in the UNCONFIRMED dip | Monthly cross-section. Every confirmation/quality gate flips the edge negative & doubles drawdown | `reports/china-reversal-phase0.md`; `CHINA_HK_STOCK_SIGNALS.md:117-123` |
| 3 | **1-month within-sector reversal** | VALIDATED but dominated | +0.37%/mo, Sharpe 0.38, maxDD −49.3%, n=388. Worse than the 3-mo construction | Monthly cross-section, same caveats as #1 | `reports/china-reversal-phase0.md` |
| 4 | **Subsector-state gate on reversal** (gate to LEADING / stretched subsectors) | **FALSIFIED** (PR #754) | Gating to LEADING drains vs FLAT in every era; 2021+ LEADING net **−0.52% Sharpe −0.42** (fails FDR) vs FLAT +0.06/+0.09. WASHED-OUT also underperforms FLAT (2021+ net −0.32) | Monthly cross-section. FLAT (no subsector gate) is best in every era. China edge = WHEN not WHICH-subsector | `reports/china-reversal-gated.md`; memory `china-subsector-gate-falsified` |
| 5 | **Cross-sectional momentum (12-1, all frames), total & residual** | **FALSIFIED** on deep history | Deep full 12-1/f21: IC −0.009 (tot) / −0.005 (res), LS net Sharpe −0.37 / −0.11, **nothing clears BH-FDR**. 5y GO was a favourable-window artifact | Monthly cross-section. **[DATA-HOLE]** top-mcap survivorship biases momentum UP → failure is *conservative* | `reports/china-residual-alpha-deep.md`; `CHINA_HK_STOCK_SIGNALS.md:34-96` |
| 6 | **Residual (beta-stripped) momentum `ir_res`** as durable winner-picker (US analog) | **FALSIFIED** on deep history (5y GO overturned) | Deep full IC −0.0045, LS Sharpe negative; only weakly +/insignificant at 6-1/f63. DSR never ≥0.90 in any config | Monthly cross-section. The SHIPPED board sort still leads on this dead signal (CN_ALPHA_WEIGHT 0.35) | `reports/china-residual-alpha-deep.md`; `CHINA_ENGINE_REASSESSMENT.md:9` (R2) |
| 7 | **Short-frame reversal `rev_st\|SN` as cross-sectional signal** | **VALIDATED** (only FDR-survivor on deep panel) | Deep full IC −0.036, **t_HAC −5.02, survives FDR** across full/modern/connect eras & both market proxies; modern t −2.82. (negative IC = reversal) | Monthly cross-section, ENTRY-TIMING overlay not a long book. Confirms #1 mechanism | `reports/china-residual-alpha-deep.md`; `CHINA_ENGINE_REASSESSMENT.md:41-43` |
| 8 | **Acceleration `acc_res`** | **FALSIFIED** (anti-predictive) | Deep IC −0.012 to −0.026, t to −2.4, survives FDR at 6-1/f63 with NEGATIVE sign. KILLED, same as US | Monthly cross-section | `reports/china-residual-alpha-deep.md`; `CHINA_HK_STOCK_SIGNALS.md:80` |
| 9 | **Low-volatility / low-beta defensive sleeve** | **VALIDATED as a defensive TILT only** (NOT long-short) | Q1 (lowest-vol) ann Sharpe **0.96–0.98 vs market 0.88**, monotone-ish Sharpe decline Q1→Q5. **BUT low−high long-short spread Sharpe −0.08 (ann −2.2%), maxDD −96.7%** — no tradable spread | Monthly cross-section, sleeve. Low-turnover so cost bites less. Ship as risk-adjusted defensive tilt, not higher-raw-return | `reports/china-lowvol-phase0.md` |
| 10 | **Basket/theme TIME-SERIES momentum** ("ride the prevailing narrative basket") | **FALSIFIED** as a predictor (0/36 FDR); positive raw excess is survivorship | rank-IC **0/36 configs survive BH-FDR(10%)** (all p≥0.05). Best net config lb63/h21/k1 excess Sharpe 0.85 but no FDR survivor. Re-run live this session | Quarterly-ish basket rotation, EW-all-basket benchmark. **[DATA-HOLE]** THS membership single 2026 snapshot back-applied (survivorship); only 2021+ price data exists | `scripts/china_basket_momentum_backtest.py` **[run 2026-07-03: "0/36 configs survive Benjamini-Hochberg FDR(10%)"]** |
| 11 | **Cross-sectional basket rank-IC rotation** (narrative_rotation composite → fwd sector return) | **FALSIFIED** (no forward alpha) | Shenwan 26.5y: 1m IC +0.024 (t 0.93), de-overlapped 6m IC +0.056 **t 0.88 n=33 NOT sig**. Lead-lag: **k=0 IC +0.51 vs k=+1 IC +0.02** — describes the past 25× more than it forecasts | Monthly cross-section, Shenwan L1 (survivorship-clean, 1999→2026). A lagging/coincident CONFIRMER | `ALLOCATION_CHINA_AUDIT.md:58-88` |
| 12 | **Narrative-rotation BOOK** (top-4 dual-gate rotation) beats naive baseline | **FALSIFIED** (worse than equal-weight) | Book 6m-hold CAGR +2.9% Sharpe 0.25 vs **equal-weight buy-hold +6.6% Sharpe 0.37**. Drawdown reduction is just ~57% cash, not crash-avoidance. Net IR negative | Book backtest, Shenwan 26.5y. "Contaminated" basket book Sharpe 0.67-0.91 is curation not logic (EW matches at 0.74) | `ALLOCATION_CHINA_AUDIT.md:90-114` |
| 13 | **Low-breadth conditioning** ("money concentrates into a few baskets when breadth is low") | **FALSIFIED** (no significant tilt) | LOW−HIGH breadth-month diff **+0.76%/mo Welch t +0.58 p=0.566** (NS). Breadth-CONFIRM filter actively HURTS: **Sharpe −1.56**, maxDD −68.9% | Basket book, monthly. Re-run live this session; matches memory #773 "low-breadth thesis refuted" | `scripts/china_basket_breadth_phase0.py` **[run 2026-07-03: "LOW - HIGH mean diff +0.76%/mo Welch t +0.58 p 0.566"]** |
| 14 | **Global AI-semis → CN AI-supply basket weekly confirmer** (SMH+SOXX+TSM 4w mom → next-week THS) | **VALIDATED for the CPO slice; MIXED for others** | **ths_cpo t 3.27 (pre-2024 t 3.03, survives SPY+CN horse-race mv_t 2.27/2.06)**; ths_pcb t 2.93 (pre-2024 1.99); storage_chip/adv_pkg significant full but NOT pre-2024 (2024-run only); ths_ai itself NS. Placebos (baijiu/gold/innovative_rx) correctly ~0 | Theme-slice, weekly W-FRI, HAC lags=4, n=241 (117 pre-2024). Survivorship-mild (external signal). **[FLOOR]** zero consumers | `reports/china-global-theme.md`; `CHINA_ENGINE_REASSESSMENT.md:101` |
| 15 | **External-driver forward-DRAWDOWN radar** (`risk_radar_intl.CN_PROFILE`: breadth + US rates/USD/CN-US diff) | **VALIDATED** (market-sizing unit) | Composite ≥10%/42d drawdown lift **2.07× (p=0.01), 2016+ 2.53×**, CSI300-confirmed. Legs: breadth 1.97–3.13×, US 2y/real-10y shocks 1.5–3.3×, US-CN 10y diff 1.61–2.78×, USD/CNH 1.9–2.6× | Market-SIZING (not name selection). External drivers → doesn't cancel the internal dip edge. Display-only until `can_force` (≥30 graded / ≥8 alerts / lift ≥1.25×). **[FLOOR]** zero CN board consumers (live caution/87, boards ungated) | `INTL_FIX_MASTERPLAN.md:21,39`; `CHINA_ENGINE_REASSESSMENT.md:101,239` |
| 16 | **China INTERNAL drawdown/slowdown gauges** (Shanghai-Comp-derived stress → fwd DD) | **FALSIFIED** (no forward edge) | Slowdown gauge Spearman(gauge, fwd-3m maxDD) **0.076** (split-half 0.10 / −0.128, unstable sign); drawdown gauge **−0.108** (H1 −0.059 / H2 −0.182). Flat/non-monotone across bands; only 4 independent ≥20% bear episodes | Single-asset TS. A-shares mean-revert; if anything mildly contrarian-bullish. Kept strictly display-only, bands history-anchored | `reports/china-conditions-calibration.md` |
| 17 | **Sector pathway conditional** (4 GS sectors: Banks/Consumption/RealEstate/Auto — do drivers LEAD turns) | **MIXED-REGIME-GATED → display-only conditional** | **0 of 152 tests clear the strict bar** (IC≥0.15 + sign-stable + BH). 73 sign-stable, 1 BH-survivor (Auto southbound 6m IC +0.43) which FAILS sign-stability (train −0.16/test +0.49, Connect-era artifact) | Monthly sector, Shenwan L1, train pre-2020/test 2020+. Ships as CONDITIONAL tilt + descriptive turn-signature, no point forecast | `CHINA_SECTOR_PATHWAY_PHASE0.md` |
| 18 | **Sector washout↔euphoria STATE signature** (bottoms = capitulation; tops = crowding) | **VALIDATED as descriptive CONTEXT only** | Median own-history pctile: at bottoms dist-from-200d 0.02–0.17, drawdown 0.05–0.20, breadth 0.16–0.19; at tops 0.75–0.95. Consistent across all 4 sectors, sign-stable | Sector-PHASE context (full-sample percentiles, labeled descriptive). NOT a per-name edge and NOT a forecast | `CHINA_SECTOR_PATHWAY_PHASE0.md` |
| 19 | **Sign-stable macro lead CLUSTER** (credit impulse +, PPI −, drawdown −, PMI − for RE) | MIXED (below FWER, directionally consistent) | Individually below BH: Consumption TSF 6m IC +0.25 (p 0.006), PPI 3m −0.25 (p 0.025); used only to CONDITION a tilt, never alpha | Monthly sector, conditioning-only. M1−M2 gap reads NEGATIVE → coincident gauge not a lead | `CHINA_SECTOR_PATHWAY_PHASE0.md` |
| 20 | **Per-NAME washout-reclaim confirmation** (2W-StochRSI washout boost, #748/#749) | **UNTESTED cross-sectionally / adjacent design FALSIFIED** | Never cross-sectionally validated. The adjacent "confirmed-pullback / reclaim" design was REFUTED (see #2). Requiring per-name reclaim re-imports the confirmation gating that flips the edge negative | Name-level, no phase-0. Correct form = top-quartile rev_z + SECTOR in washout band | `CHINA_ENGINE_REASSESSMENT.md:45-47` |
| 21 | **Anti-chase extension penalty** (`EXT_PENALTY`=0.5, #791 extended-demote) | **VALIDATED as a hygiene screen — NOT as forward alpha** | Measured effect: board 20d vol NOT elevated, winner tail excluded (120d p90 +18% vs universe +127%), 0 ST names. It works as construction hygiene; never forward-return-validated as a standalone alpha | Board-construction lever, name-level. Related: fund crowding+extension carries NO forward-return edge (`reports/fund-crowding-phase0.md`) | `CHINA_ENGINE_REASSESSMENT.md:193,255`; `DATA_SIGNAL_EXPANSION_2026.md:70` |
| 22 | **COILED cohort-washout (CN)** as ranking bonus | **"VALIDATED"/wired (wave-3) — but no CN-specific forward-return gate found** | Wired as a cross-sectional ranking bonus (CN wave-3). The only direct squeeze phase-0 in the repo is the US panel: **bare squeeze forward-|move| lift 0.93× = NO lift** (`reports/US_STOCKS_SIGNALS_PHASE0.md`). No committed CN COILED forward-alpha report located | Name-level ranking bonus (chip). Treated as validated by pipeline audit but the numeric CN gate is not in `reports/` — **verify before trusting as alpha** | `CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md:254`; `US_STOCKS_SIGNALS_PHASE0.md:10` |
| 23 | **COILED (HK)** | **FALSIFIED** (failed its OOS gate) | Failed out-of-sample; not wired on HK. "Do not force-port" | Name-level. HK is a macro/global-beta product, not stock-selection | `CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md:254,271` |
| 24 | **COILED-FIRE** (wave-4 fire extension) | Display-only, no rank change | Chip only, `:1202-1210`; no forward-return validation | Name-level display chip | `CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md:87-88` |
| 25 | **QVIX regime overlay (CN, inverted vs US)** | **UNTESTED as an edge — asserted, called "dead/mean-reverting"** | Design-asserted: China has positive return-vol correlation → invert (z>+2 halt, z<−1 size-up). But it is "an unvalidated QVIX-spike overlay from the class the radar's own research calls dead/mean-reverting"; the validated drawdown leg (#15) should replace it | Name-level stress overlay, no forward grade. Display/context only | `CHINA_STOCKS_OVERHAUL.md:28,50`; `CHINA_ENGINE_REASSESSMENT.md:101,239` |
| 26 | **HK residual (beta-stripped) momentum** | **FALSIFIED** (KILL the leg) | Deep 447-reb: `mom_res` IC +0.004 **LS Sharpe −0.22**; modern −0.35. Only plain `mom_tot` IC +0.032 t 2.0 positive but weak (fails DSR) and is BETA not alpha. `acc_res\|SN` survives FDR negative (killed). **[REFRESH 2026-07-03: original numbers were the 73-name panel; the 2026-06-18 expansion to 157 names sign-flips mom_res LS to +0.17 full / +0.31 modern (IC +0.012, t_HAC 1.28) — still fails DSR in every window; KILL stands on DSR/IC grounds, not sign]** | Monthly cross-section, ~40y HK panel. HK cross-section is global-beta-dominated (~2×) | `reports/hk-residual-alpha-phase0.md`; `CHINA_HK_STOCK_SIGNALS.md:145-176` |
| 27 | **HK global-risk-beta context read** (amplifiers vs cushions) | VALIDATED as risk CONTEXT (modest) | High−low global-beta fwd-21d **+0.41% Risk-on, −0.74% Risk-off** (risk-off cleaner, t −1.3). Directionally correct, modest → sizing context not forecast | Name-level exposure, deep 40y panel, lagged-SPY. Wired on hk.html | `CHINA_HK_STOCK_SIGNALS.md:177-191` |
| 28 | **HK southbound-vs-price divergence** | **FALSIFIED** (no incremental content) | Incremental Frisch-Waugh t_HAC −1.85 (fwd21), fails FDR + split-half; overlay excess Sharpe −0.01, DSR 0.14. Fails all GO bars | Single-asset TS, n=1853. Display-only positioning context | `reports/hk-southbound-divergence-phase0.md` |
| 29 | **CN regime quad → market forward return** | **MIXED-REGIME-GATED** (split-unstable) | Growth-scare edge survives both halves (f63 +5–9%, hit 70%+); Goldilocks/Reflation/Stagflation flip sign or magnitude across split-halves (Stagflation pre −22% / post +1.1%) | Market TS, Shanghai Comp, 2008→2026. Regime-unstable quads = context not allocation rule | `reports/china-calibration.md` §1 |
| 30 | **CN liquidity overlay (PBoC M2 direction) → fwd return** | Weak-positive, kept as overlay | Expanding f63 +1.71% hit 53.5% vs contracting +0.59%; "unknown" bucket catastrophic (data gap artifact) | Market TS. Context overlay, not standalone | `reports/china-calibration.md` §2 |
| 31 | **CN cycle ladder states → forward DRAWDOWN** | VALIDATED as drawdown-asymmetry context | Ladder value is the dd_* columns (asymmetric setups = scary state + shallow typical dip); avg_fwd alone is U-shaped/misleading (macro D43). FRESH BUY avg_fwd +2.48% | Market/name TS, deep panel. Drawdown-shape read, not a return forecast | `reports/china-calibration.md` §3 |
| 32 | **Discovery LHB raw hot-money flag as positive confirmer** | **FALSIFIED** (wrong sign, DRAINS) | Raw LHB flag on dip names **−1.43%/21d (cluster-t ≈ −2.2, n=931)**; the code weights it +0.10 positive. Invert → demotion | Name-level event, single 18-24mo regime, survivorship universe. Sign evidence not sizing | `CHINA_ENGINE_REASSESSMENT.md:107,205` |
| 33 | **Block-trade PREMIUM as accumulation** | **FALSIFIED** (wrong sign, DRAINS) | Premium blocks **−0.60%/5d (t ≈ −2.8)**. But deep-DISCOUNT blocks (≤−15%) **+3.45%/21d (t ≈ 3.4, n=669)** — the inverted leg is the best northbound replacement found | Name-level event. Deep-discount block = candidate confirmer (probationary) | `CHINA_ENGINE_REASSESSMENT.md:107,205,211` |
| 34 | **Limit-up (涨停/连板) continuation as positive rank** | **FALSIFIED** (uncapturable / negative fwd) | Naive dip+ZT +1.74%/5d collapses to **+0.04% fill-realistic, −1.16%/21d**. Belongs to chase-veto/froth only, never positive buy-rank | Name-level, fill-realistic. First session unbuyable | `CHINA_ENGINE_REASSESSMENT.md:107,199` |
| 35 | **Aggregate northbound / southbound / A-H premium / margin velocity as TIMING legs** | **FALSIFIED** (≈0 IC / dead) | Margin velocity +0.035, southbound z +0.022, A/H premium z ≈0 vs fwd CSI300 — all dead. Northbound net confirmed dead 2024-08-16 (97.3% null since). Southbound sign-unstable (train −0.16/test +0.49) | Market/name timing. Reject as timing legs | `CHINA_ENGINE_REASSESSMENT.md:205,211` |
| 36 | **Inst-seat LHB net-buy (≥2 seats)** | **ACCRUING** (weak-positive, probationary) | +1.57%/21d (t ≈ 0.8, n=140) — never negative. Put on forward ledger, not scored | Name-level event, low n. Accrue-and-grade | `CHINA_ENGINE_REASSESSMENT.md:205,211` |
| 37 | **ETF create/redeem flow as northbound replacement** | **UNTESTED** (no history) | History starts 2026-06-13, not backfillable; current gauge sums unit-incommensurable share counts (bug). Accrue ~1y after unit fix | Name/sector flow. Most orthogonal candidate but no substrate yet | `CHINA_ENGINE_REASSESSMENT.md:211,243` |
| 38 | **Per-name margin velocity as fast flow** | **UNTESTED** (local cache = 1 day) | Fast & daily but `china_margin_detail` holds 1 date; ~250 akshare calls/yr/exchange to backfill. Top untested follow-up | Name-level flow | `CHINA_ENGINE_REASSESSMENT.md:211,243` |
| 39 | **fundflow (主力) / chip-distribution intel legs** | **FALSIFIED** (wrong sign) | `data/china_validation/scorecard.json`: 0/6 families proven; fundflow t_hac **−1.019** (wrong sign). Intel layer is honestly leaf-status | Name-level. Do not wire before sign tests | `CHINA_ENGINE_REASSESSMENT.md:55` |
| 40 | **Forward base-effect / continuous-P(Quad) / HMM regime suite (CN)** | **UNTESTED / display-only** (validator never written) | The base-effect/HMM forward suite is display-only until `scripts/validate_regime_fwd.py` — which did not exist at audit time; ledger had 1 null row. This is primarily a US-engine concern; CN uses the split-half quad (#29) | Market regime. No CN forward-IC validation of the scored quad exists | `research/ENGINE_PROBLEM_AUDIT.md:35,300-306` (US engine; CN inherits pattern) |

---

## B. The two flag lists (explicit, as required)

### (a) Verdicts poisoned by a known data hole — RE-RUN on fixed substrate, do not trust as-is

1. **Reversal Sharpe 0.58 (#1, #3) and short-frame reversal (#7).** Two compounding holes:
   - The deep panel `data/china_search/closes_deep.parquet` **is ABSENT from the repo** (verified this
     session: `ls` returns "No such file or directory"; `china_basket_momentum_backtest.py` docstring
     states "closes_deep.parquet is absent"). The flagship 388-rebalance reversal report **cannot be
     reproduced on the current substrate without re-fetching** ~35y of history.
   - `collectors/china_universe.py:306` **retroactively DELETES** the price-history columns of any name
     that drops out of the current Sina top-N — i.e. it deletes exactly the deep-decliner failures the
     reversal signal buys. So even the numbers we have are an **upper bound** (`CHINA_ENGINE_REASSESSMENT.md`
     new-problem #2). Re-run only after the trim is stopped (append-only + dropped-date marker) and PIT
     membership exists.
   - Both price stores are `auto_adjust=True` total-return (**no raw A-share price plane exists anywhere**);
     `combine_first` merges leave adjustment seams that **seasonally bias rev_z** (17/300 names >0.4% seam
     step in 250d, May-dividend clustered) and can fabricate MACD/StochRSI crosses inside cascade/washout
     lookbacks (`CHINA_ENGINE_REASSESSMENT.md` new-problem "adjusted-close seams"). Memory:
     `yahoo-close-is-total-return`.

2. **Momentum "failure" (#5, #6).** Survivorship (top-mcap-today) biases momentum UP, so the failure-to-find
   is *conservative* — but the magnitude is not trustworthy. Directionally safe, numerically not.

3. **Basket TS momentum (#10) and basket rank-IC (#11-13).** THS membership is a **single 2026 snapshot
   back-applied** (all 22/50 baskets have zero removed members = pure survivorship curation, `ALLOCATION_CHINA_AUDIT.md:54`).
   Only 2021+ price data exists so "full" == "2021+". Basket-level TS rotation is more robust than name
   selection (EW-all benchmark cancels most of it), but absolute levels are inflated.

4. **All discovery-leg sign tests (#32-36).** Single 18-24mo regime, top-N survivorship universe (21-55%
   price-match), cluster-t. "Sign evidence, not sizing evidence — re-run on the W1 PIT universe before
   wiring weights" (`CHINA_ENGINE_REASSESSMENT.md:207`).

5. **Close-to-close grading tax (all name-level backtests).** Close-to-close overstates a realistic T+1
   (H+L)/2 fill by ~0.9-1.1pp/entry and ~2pp hit; marker-date grading embeds **+5.7pp/10d look-ahead**
   (`engine/signal_quality.py:163`). Any hit-rate not graded from the first knowable close is inflated.
   No `Open` column is collected (`_OHLC` = Close/High/Low/Volume) so honest T+1 fills are only proxyable.

**Also unauditable (not a verdict, a measurement blocker):** 46-49% of the universe/board carry a placeholder
`mktcap` (30亿 exactly) → size-factor exposure and Altman-Z distress zones are fabricated from a constant
until real caps land; the ST screen matches ZERO names across 1,483 (`CHINA_ENGINE_REASSESSMENT.md:159-163,193`).

### (b) VALIDATED but wired to NO live surface — free alpha on the floor

1. **External-driver forward-drawdown radar `risk_radar_intl.CN_PROFILE` (#15).** Composite 2.07× drawdown
   lift (p=0.01), the suite's ONLY closed grade→tune→can_force loop, **zero CN board consumers** (live
   state caution/breadth/87 while all five China boards run ungated). Thread `gross_factor` (1.0→0.62) as a
   sleeve-size chip; it keys on EXTERNAL drivers so it does not cancel the internal dip edge. **Name hazard:**
   `risk_radar_intl.CN_PROFILE`, NOT the display-only `engine/china_radar.py`.
   (`INTL_FIX_MASTERPLAN.md:21,39`, `CHINA_ENGINE_REASSESSMENT.md:99-103,239`.)

2. **Global AI-semis → CN-CPO weekly confirmer (#14).** t=3.27 (pre-2024 3.03), survives the SPY+CN
   horse-race, fully orphaned (grep = zero consumers). Wire as a slice-scoped weekly confirmer chip on
   AI-supply THS concepts (cpo/pcb/storage_chip live on 2 of 5 pages). (`CHINA_ENGINE_REASSESSMENT.md:99-103`.)

3. **The validated reversal edge itself is ~orthogonal to the acted-on board (#1 vs the live surface).**
   Not "unwired" but effectively so: the 110-name live board overlaps the reversal top-16 watch **1/110** and
   the low-vol sleeve **0/110**; board sort leads on residual-alpha (dead signal), rev_z has **zero weight**
   in board order (`CHINA_ENGINE_REASSESSMENT.md:185-189`). The validated edge exists in the repo but does not
   drive the picks.

4. **Deep-discount block-trade tape (#33 inverted).** +3.45%/21d (t≈3.4) — the strongest tested dip confirmer,
   a defensible northbound replacement, currently unwired (and its raw-premium sibling is wired with the WRONG
   sign).

5. **Low-vol defensive tilt (#9)** is wired as a sleeve but does NOT reach the board (0/110 overlap) — partial floor.

---

## C. Program guidance the ledger implies (do not re-derive)

- **There is exactly ONE validated name-selection edge: 3-month within-sector reversal (#1).** Every
  confirmation/quality/subsector/regime-timing refinement of it has been tested and FALSIFIED (#2, #4).
  Do not re-propose "cycle-confirmed pullbacks of quality names" — it is refuted at −0.29%/mo, Sharpe −0.29.
- **The other four validated findings operate at DIFFERENT units** and are not name-selection: drawdown radar
  = market sizing (#15), AI-semis = theme slice (#14), low-vol = defensive sleeve (#9), washout signature =
  sector-phase context (#18). "Manufacture a second selection edge" is the wrong instruction — wire the
  sizing/slice edges that already exist.
- **Momentum in any form is dead on A-shares** (#5, #6, #8, #11, #12). A momentum/trend engine in a reverting
  tape loads on what just ran (k=0 IC +0.51) and earns ~0 forward.
- **HK is a macro/global-beta product, not a stock picker** (#26, #27) — do not port CN reversal weights.
- **Before any grader-feeds-rank work:** the #791 board ledger is structurally dead-on-arrival (wrong store
  group, `china_standout_track.py:82` reads 30 ETFs; 0/120 board tickers resolve; n_graded=0 forever). Fix the
  store group + CSI300-relative returns + fill realism + the retroactive-deletion trim in the SAME pass so the
  first published number is unbiased (`CHINA_ENGINE_REASSESSMENT.md` new-problems #1, #2).

---

## D. Provenance notes

- Two scripts were **re-run live this session** on the local `data/` substrate (both wrote no files; stdout
  only): `scripts.china_basket_momentum_backtest` (result: 0/36 FDR survivors) and
  `scripts.china_basket_breadth_phase0` (result: low-breadth diff Welch t +0.58 p 0.566; breadth-confirm
  Sharpe −1.56). All other rows are cited to committed `reports/*.md` or research-doc line numbers.
- **No main-checkout fallback was needed** — every data file referenced (`closes.parquet`, `membership.json`,
  `510300.SS.parquet`, calibration artifacts) was present in the worktree `data/`. The one absence
  (`closes_deep.parquet`) is a genuine repo-wide gap, not a worktree/R2 artifact — flagged in B(1).
- The 2026-07-01 `CHINA_ENGINE_REASSESSMENT.md` is treated as the master synthesis: it re-verified the
  primary reversal artifact (60/60 ledger reproduce on the correct plane) and corrected several earlier
  claims, all folded into the caveats above.
