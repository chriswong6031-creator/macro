# International Engine — Problem Audit for Fable

**Repo:** Macro Dashboard (`/Users/chriswong/Documents/Cluade/Macro Dashboard`)
**Date:** 2026-07-02
**Scope:** The entire international vertical — comparative macro dashboard (`intl.html`), regime & recession engine (`engine/intl_regime.py`, `engine/intl_run.py`, `engine/intl_inputs.py`), rates/bonds/equity-risk gauges (`engine/intl_rates.py`, `engine/intl_bonds.py`, `engine/intl_equity_risk.py`), the intl stock desks (`engine/intl_stocks.py`, `scripts/build_intl_library.py`), and the intl basket suite (`engine/baskets_intl.py`, `scripts/seed_intl_baskets.py`) — evaluated against **one central question: how can international / cross-market data sharpen US & China stock signals?**
**Method:** Static code inspection of the seven core intl engine modules plus their build scripts, cross-referenced against the US/China stock-signal path (`engine/stock_score.py`, `engine/residual_alpha.py`, `engine/conditions.py`, `scripts/build_stock_library.py`, `scripts/build_china_library.py`), grep audits for cross-module imports, on-disk inspection of `data/intl_macro/*.parquet`, `data/intl/latest.json`, `data/intl_search/*.parquet`, and `data/baskets_intl/membership.json`, and comparison against the existing validation reports (`reports/residual-alpha-phase0.md`, `scripts/thematic_rotation_phase0.py`). All file:line citations were verified against the working tree; where the evidence only supported a file/dir-level claim, no line number is asserted.

---

## Severity legend

| Severity | Meaning |
|---|---|
| **CRITICAL** | Actively wrong output or a silent failure that corrupts a decision surface today. |
| **HIGH** | A structural gap or unvalidated surface that either blocks the core goal (intl → US/China feedback) or would silently mislead a user acting on the page. |
| **MEDIUM** | Real methodology / coverage / UX defect that degrades quality but does not, on its own, produce a wrong trade today. |
| **LOW** | Cosmetic, redundancy, or documentation defect. |

> **A framing note that governs the whole doc.** The entire intl suite is *self-declared display-only* — `engine/intl_run.py:1-5` states "Every read is descriptive / display-only." That declaration is the single most important fact in this audit and it cuts two ways. It **lowers the immediate blast radius** of every unvalidated gauge (nothing here trades money today), but it is also **the root cause of the doc's centerpiece problem**: the richest cross-market dataset in the repo has been architecturally quarantined from the signal engines that could most benefit from it. Most severities below are therefore rated *conditional on the feedback bridge being built* — the moment intl data feeds US/China scoring, every "display-only, so low risk" caveat inverts into a live risk. Fable's job is to build that bridge **and** harden the data underneath it at the same time, because doing one without the other propagates untested assumptions into live trades.

---

# PART 1 — CONFIRMED PROBLEM LEDGER

Severity-ordered. Feedback-gap and data-quality items are front-loaded because they are the load-bearing problems for the user's core question.

---

## INTL-1 — HARD SILO: intl signals never reach the US/China stock scorers *(HIGH · feedback-gap)*

**File(s):** `engine/intl_run.py`, `engine/stock_score.py`, `engine/residual_alpha.py`, `engine/conditions.py`, `scripts/build_stock_library.py`, `scripts/build_china_library.py`

**Evidence:**
- `engine/stock_score.py`, `engine/residual_alpha.py`, `engine/conditions.py`, `engine/cycles.py`, `engine/factor_exposure.py`, `engine/stock_desk.py` contain **zero imports of any `intl_*` module** (verified by grep across all seven core scorers).
- The US macro context fed to US cycles is built *entirely* from US FRED data (`engine/conditions.py` — nfci, recession_prob, ebp, curve, claims) with no intl integration.
- The only modules that touch intl-adjacent data are BTC-facing and never reach the stock pipeline: `engine/global_liquidity.py` (CB assets → `btc_signals.py`) and `engine/narrative_crossmarket.py` (cross-theme detector, explicitly `DISPLAY-ONLY`, degated as non-tradeable).
- `data/intl/latest.json` (the full 7-economy regime output) is read downstream only by `build_vector.py` for the Globe visualization — never by `build_stock_library.py` or `build_china_library.py`.

**Impact:** A US or China trader has no structured path to ask "Is the Eurozone turning goldilocks before the US?", "Do Japan/Korea equity regimes lead US semi/tech rotation?", or "Is developed-market inflation diverging?" The single comparative advantage the intl suite *should* unlock — early regime detection across time zones and supply chains — is completely unmined. The 7-economy unified regime framework is fully built and fully disconnected.

**Direction for Fable:** This is the spine of PART 2. Build a cross-country regime **spillover layer** that feeds US/China stock selection as a MACRO CONTEXT axis (e.g. EU goldilocks + rising real yields tilting US growth/rate/sector screening; Japan/Korea equity regimes conditioning US semis timing). Wire `intl_run.py → intl_feed.py → build_stock_library.py / build_china_library.py`, not just the dashboard.

---

## INTL-2 — ZERO FEEDBACK from the intl regime engine to US/China signal generation *(HIGH · feedback-gap)*

**File(s):** `engine/intl_run.py`, `engine/regime.py`, `engine/run.py`, `scripts/build_china.py`, `engine/global_liquidity.py`, `engine/narrative_crossmarket.py`

**Evidence:**
- `engine/regime.py`, `engine/run.py`, `scripts/build_china.py` contain zero intl-regime imports.
- `data/intl/latest.json` (7-country regime, e.g. JP Q1 Goldilocks, growth_score 0.714, recession_score 7.0) is read only by `build_vector.py` (Globe hub card), never by US/China scoring.
- `engine/global_liquidity.py` has zero intl references; `engine/narrative_crossmarket.py:~107` explicitly states "Intl has no single regime snapshot → None (never claims alignment)."

**Impact:** International growth/inflation regimes (JP growth strong, EZ stagflationary, AU drawdown-risk) provide **zero** signal to US equity selection. China's regime is built in isolation from its Asian peers (only vs. China-internal rates/growth). This is the same silo as INTL-1 viewed from the regime side: the classification system was deliberately siloed as display-only and never wired to any scoring path.

**Direction for Fable:** Design `engine/intl_feed.py` that (a) aggregates intl regimes into blocs (Asia = JP/KR/TW/IN/AU; Europe = EZ/GB), (b) computes relative growth/inflation momentum (JP vs KR, EZ vs GB), (c) emits signals like "EM growth accelerating" / "developed inflation divergence", and (d) feeds `build_us`/`build_china` as cross-macro sector/beta tilts. Publish research on lagged intl→US/China returns (e.g. Q2 EZ growth slowdown → US cyclicals 4-8 weeks later) before wiring.

---

## INTL-3 — Intl stock desks have ZERO integration to core US/China stock engines *(HIGH · feedback-gap)*

**File(s):** `scripts/build_intl_library.py`, `engine/intl_stocks.py`, `scripts/build_stock_library.py`, `engine/residual_alpha.py`, `engine/signal_gate.py`

**Evidence:**
- `engine/intl_stocks.py:~23,69` imports `compute_residual_alpha` only for within-market alpha; it is never exported.
- `scripts/build_intl_library.py` imports `intl_stocks` only to self-score the intl standout board.
- `scripts/build_stock_library.py` has **zero** `intl` or `residual_alpha`-cross imports; grep confirms `intl_stocks` appears in exactly 2 files total (`build_intl_library.py`, `build_intl.py`).
- `intl_setups.json` (written to `site/factordata/`) has **zero** consumers in any US/China desk.

**Impact:** A standout in TSMC (Taiwan) or Samsung (Korea) — logical read-throughs to US semis (SMH) — never informs US selection. Cross-border supply-chain signal (TSMC health → US semi demand) is systematically ignored. EZ/GB names' currency-adjusted momentum never becomes a conviction modifier on US/EU-exposed names.

**Direction for Fable:** Wire `intl_stocks.compute_intl_alpha` into `build_stock_library.py` as a global-signal feature (`intl_momentum_tilt`, `cross_border_supply_chain_beta`). For TSMC/Samsung → US semis, add an explicit lead/lag correlation read. See PART 3 §3.1 (supply-chain read-through) — this is the single most concrete edge seed in the doc.

---

## INTL-4 — Intl baskets never feed US/China stock signals (thematic read-through gap) *(HIGH · missing-feature)*

**File(s):** `engine/baskets_intl.py`, `scripts/build_baskets_intl.py`, `engine/theme_scoring.py`, `engine/narrative_crossmarket.py`, `engine/stock_score.py`

**Evidence:**
- `scripts/build_stock_library.py:~660` calls `theme_scoring.compute_theme_intel("us")` **only** — no intl region.
- `engine/stock_score.py:~796-819` (`_axis_tailwind`) reads `rec["spotlight"]`, populated only from US/CN/HK/CA baskets.
- `build_china_library.py` does not call `theme_scoring` at all.
- Intl baskets *are* computed (`engine/theme_scoring.py:~568-582` supports `region="intl"`) but serve only `baskets_intl.html`.
- `engine/narrative_crossmarket.py:38-70` defines a CANON of globally-traded themes with cross-market analogs (semis, software, defense, robotics, autos, pharma, energy, mining, luxury) and admits "no reliable lead-lag" for thematic momentum — **but that gate is never opened toward the stock scorer.**

**Impact:** The suite has access to global lead-lag information (does Taiwan/Japan "Global Semis" lead US "AI Semiconductor" by 1-2 weeks?) and does nothing with it. A Japan Inc. re-rating or Korea Tech surge that leads a US rotation is invisible to the trading core.

**Direction for Fable:** Build a cross-market thematic read-through: for each US basket ID with an intl analog (from the CANON list), measure same-day correlation and 1-5d lead/lag IC, then surface it to `stock_score._axis_tailwind` as a gate or continuous blend ("intl_semis leading up-tick → boost US semi tailwind"). Backtest first on the 27y thematic-rotation phase-0 data (`scripts/thematic_rotation_phase0.py`). See PART 3 §3.2.

---

## INTL-5 — Macro data staleness masks confidence via silent ffill collapse *(HIGH · data-quality)*

**File(s):** `engine/intl_inputs.py`, `engine/intl_regime.py`, `engine/intl_run.py`

**Evidence:**
- `engine/intl_inputs.py:~125-155`: ffill limits are 70d (CPI), 90d (unemployment), 130d (rates), 160d (GDP). After the limit, the column becomes NaN and drops from the component count.
- On-disk staleness (verified against `data/intl_macro/`, as of 2026-07-02): **JP CPI last 2021-06** (~1,857d stale), **KR CPI last 2023-11** (~974d), **EZ unemployment last 2023-01** (~1,278d). M2 for JP/KR/EZ dead since 2017 (>3,300d) — but M2 is not in scoring, so it is display cruft only.
- `engine/intl_regime.py:71-93` (`score_axis`): NaN components are excluded from `n_comp`; the confidence gate is `n_comp >= min_components` (config `min_components=2`). So confidence stays **non-zero** even when CPI is entirely absent.
- `engine/intl_run.py:~55`: the `data_limited` flag fires only when `n_comp < 2`. With stale CPI, JP/KR/IN/AU/GB usually still have 3+ items, so the flag does **not** fire.
- Asymmetry: `engine/intl_inputs.py:~207-208` gates `real_yield` on CPI freshness (490d), but that gate is **not** applied to `regime_confidence`.

**Impact:** For Japan, CPI stopped driving the inflation axis in mid-2021, yet `regime_confidence` remains ~0.607 with `inflation_score=-0.5` and no indicator that CPI contributes zero. The user reading "JP inflation = Q1 today" cannot tell it is really "commodity + bond proxy." If this regime *ever* feeds a US/China tilt (the PART 2 goal), predictive power silently degrades as more series expire.

**Direction for Fable:** Add explicit freshness gates in `score_axis()` — zero confidence when any *critical* component (CPI > 365d, unemployment > 180d) is stale, or apply the existing `real_yield` freshness gate to `regime_confidence` too. Emit a per-country `data_age_risk` field (days-stale per leg) into `latest.json`. Decide intent: is the fix `min_components >= 3` for inflation, or symmetric freshness gating, or a `data_limited` trigger at "needs 3, has 2"?

---

## INTL-6 — Rates desk is ECB-centric; BoJ/BoK monetary transmission is invisible *(HIGH · coverage-gap)*

**File(s):** `templates/intl.html.j2`, `engine/intl_rates.py`, `engine/intl_regime.py`, `config.yml`

**Evidence:**
- `templates/intl.html.j2:403-427`: per-country rates cards show only 10y, 3m, curve, real yield, carry, drift — **no** balance-sheet or monetary-stance indicator.
- `templates/intl.html.j2:451-462`: ECB liquidity impulse only, with note at line 461 "ECB only — the one major CB with a clean keyless weekly series here."
- `engine/intl_rates.py:~118-141`: `ecb_liquidity_impulse()` reads only `ez_cb_assets`; **no BoJ/BoK equivalent function.**
- `engine/intl_regime.py:~96-109`: the per-country "liquidity" field is a 3-month **policy-rate direction** proxy (expanding/neutral/contracting), NOT a balance-sheet impulse.
- `config.yml`: BoJ assets (`JPNASSETS`) are configured in `cb_liquidity` (used by `global_liquidity.py`) but **not** in `intl_macro` extra_series; JP/KR configs have no `policy_rate`, no balance-sheet.

**Impact:** A user cannot see whether BoJ yield-curve control is becoming a macro **drag** (growth rolling over while BoJ caps 10y) or a **tailwind** (BoJ softening as growth picks up). Japanese monetary transmission has been *the* dominant cross-asset channel this cycle (yen weakness, carry trade, carry-unwind crashes) and it is completely dark in the intl desk.

**Direction for Fable:** Add BoJ balance-sheet + YCC state (even scraped from press releases if no keyless weekly series exists) and a "yen weakness % from BoJ softness" metric linking JPY/USD to Japanese rate policy. This is also a **novel cross-market edge seed** (PART 3 §3.3): BoJ softness → yen weakness → global carry → ex-Japan asset correlation.

---

## INTL-7 — Intl standout stocks are alpha-ranked but never validated forward (asymmetric-disclosure) *(HIGH · no-validation)*

**File(s):** `templates/intl.html.j2`, `engine/intl_stocks.py`, `engine/residual_alpha.py`, `reports/residual-alpha-phase0.md`, `discovery.html`

**Evidence:**
- `templates/intl.html.j2:578-610` + `engine/intl_stocks.py:~47-87`: standouts ranked by sector-neutral residual momentum *within each country* (`intl_stocks.py:~69` calls `compute_residual_alpha` per market via `_index_returns(cc)`).
- The caveat at `intl.html.j2:~608` says "alpha is sector-neutral residual momentum computed per market, never pooled raw across currencies" — but it does **not** cite any validation report.
- Contrast: `discovery.html:~292` cites `reports/top-picks-phase0.md` with measured IC. `reports/residual-alpha-phase0.md` validates the engine on the *global developed-market* universe (modern IC ~0.0065-0.0071, modest) — but there is **no** per-market JP/KR/TW point-in-time backtest and no `intl_stocks_phase0.py`.

**Impact:** The standout cards look actionable (alpha badge, flag, momentum) but carry no per-market empirical weight and disclose *less* than the US board. Residual momentum is proven on SPY-linked developed indices; its generalization to thin bourses (Korea, Taiwan, India) is untested, and momentum is known to decay/fail in EM/Asia.

**Direction for Fable:** Either (a) run an intl-specific Phase-0 (per-market residual-momentum IC, DSR, MaxDD, crisis-gated) and publish a banner, or (b) downgrade the badge to "relative-strength lens, unvalidated" with an explicit "validated on global developed markets; per-market generalization not tested" caveat. Prefer (a) if intl stocks are meant to feed US/China conviction (INTL-3). See also INTL-12, INTL-16, INTL-20.

---

## INTL-8 — Intl universe has survivorship bias; current UCITS holdings are lookahead *(HIGH · data-quality)*

**File(s):** `collectors/intl_universe.py`, `data/intl_search/closes.parquet`, `data/intl_search/members.parquet`, `engine/universe_history.py`

**Evidence:**
- `collectors/intl_universe.py:~120-178`: `_fetch_holdings()` fetches **CURRENT** iShares UCITS holdings (2026-06-19 snapshot). Lines ~230-257: closes are requested only for current members with valid price data; both `closes.parquet` and `members.parquet` are written only for that intersection.
- On-disk: `closes.parquet` is 1,310 days × 1,000 tickers (2021-06-15 → 2026-06-19); `set(members.index) == set(closes.columns)` (perfect sync = the corpse is auto-buried each run).
- Any company in UCITS on 2021-06-15 but delisted by 2026-06-19 is **permanently absent** — never requested, never in either parquet — so historical momentum uses survivors only. The bias is invisible and unquantifiable with current data.
- `engine/universe_history.py:~1-17` implements point-in-time membership tracking for the US S&P 1500 and explicitly flags the survivorship problem — **no intl equivalent exists.**
- *Correction to a prior claim:* the sparse tickers (VAML.NS 0.4%, 285A.T 27.6%, SWIGGY.NS 30.3%) are **recent IPOs, not delistings** — do not cite them as delistings.

**Impact:** Backtested intl alpha is inflated by the standard small-cap survivorship premium (plausibly ~1-3% annualized, but *unmeasurable* without historical snapshots). The standout board self-selects for winners; losers vanish. Every validation number in INTL-7/INTL-12/INTL-16 inherits this bias.

**Direction for Fable:** Port `engine/universe_history.py` to the intl suite: snapshot UCITS membership+weights to `data/intl_search/snapshot_YYYYMMDD.parquet` on each run; build a point-in-time honest membership backtest (names known-to-exist in month T rank month T+1). Warn users that current momentum uses a survivor-only universe until enough snapshots accrue.

---

## INTL-9 — Recession composite is an unbacktested display-only gauge with arbitrary thresholds *(HIGH · no-validation)*

**File(s):** `engine/intl_regime.py`, `config.yml`, `tests/test_intl_regime.py`

**Evidence:**
- `engine/intl_regime.py:112-142` documents `recession_composite` as "DISPLAY-ONLY 0-100 recession-pressure gauge … NOT a backtested probability." Three legs hardcode thresholds: curve inversion scaled +1.5pp→-1.0pp (2.5pp band), unemployment 6-month rise ±1.0pp, drawdown-from-1y-high over -25%.
- `config.yml` recession bands (45/65) are asserted, not backtested; `hysteresis_days=7`, `shock_override_z=0.85` are tuned for whipsaw reduction (on **US** data), not predictive power.
- `tests/test_intl_regime.py:~62-67` only checks bounds [0,100] and band classification — never predictive power. No research script validates against actual recession timing/drawdown leads.

**Impact:** `latest.json` shows `recession_score` prominently (e.g. AU=63.7 "watch"). If a global desk hedged on it — or if this ever feeds US/China signals (PART 2) — it would propagate untested levels. Immediate risk is LOW *only* because it is currently isolated; the risk is entirely **conditional on integration**.

**Direction for Fable:** Backtest `recession_score(t)` vs forward 21d/63d/252d index returns; publish hit-rate / false-positive rate. Recalibrate thresholds to percentile-based (e.g. elevated = top 20% of 10y history) rather than asserted levels. If modest, relabel as "historical stress-comparison tool," not "recession predictor."

---

## INTL-10 — Intl equity-risk gauges (drawdown_risk, bubble_flag) are unvalidated *(HIGH · no-validation)*

**File(s):** `engine/intl_equity_risk.py`, `engine/intl_run.py`, `tests/test_intl_equity_risk.py`

**Evidence:**
- `engine/intl_equity_risk.py:39-76` (verified): `ddrisk = (0.5·dd_leg + 0.3·trend_leg + 0.2·vol_leg)·100`, where `dd_leg = clip(-off_high/25,0,1)`, `trend_leg = 1 if price<200dMA`, `vol_leg = clip((rv-15)/25,0,1)`. `bubble = grade in ('stretched','parabolic') or (rsi>=72 and off_high>-3)`.
- Live output matches: India ~47, Australia ~39 (`data/intl/latest.json`). The 50/30/20 weights are undocumented priors.
- Docstring (lines 1-9) says "None of this is a backtested signal … DISPLAY-ONLY." `intl_run.py:~64` calls `equity_risk_all()` and never validates. `tests/test_intl_equity_risk.py` only checks bounds + synthetic ordering.
- *Correction:* the "already MEASURED" comment in `scripts/calibrate_bonds.py` refers to **US bonds** drawdown_risk (calibrated vs forward S&P 63d drawdowns), **not** intl equity. No intl calibration script exists.

**Impact:** Dashboard shows 0-100 "drawdown_risk" bars and "watch" bands across all 7 economies (JP/KR/TW/IN/AU/GB/EZ) with zero evidence they correlate to realized forward drawdowns. Readers may hedge/mis-allocate on decorative numbers.

**Direction for Fable:** `backtest_intl_equity_risk.py`: per country, rolling 90d forward drawdown vs signal-day score; measure IC, long-high/short-low Sharpe, OOS persistence. If IC>0.15 / Sharpe>0.5, promote to an MRS leg feeding US equity hedging. Else simplify to a 3-state qualitative read. Add "last validated" dating.

---

## INTL-11 — Eurozone unemployment 42 months stale (Jan 2023); M2 9+ years dead *(HIGH · data-quality)*

**File(s):** `data/intl_macro/EZ_unemployment.parquet`, `data/intl_macro/EZ_m2.parquet`, `engine/intl_inputs.py`, `engine/intl_regime.py`

**Evidence:**
- `EZ_unemployment.parquet` last date 2023-01-01 (~1,278d / 42mo stale); `EZ_m2.parquet` last date 2017-03-01 (~3,400d / 9.3y).
- `engine/intl_inputs.py:~144` reads unemployment with `ffill_limit=90`; after ~90 business days it goes NaN. Lines ~152-154 read M2 similarly. `intl_inputs.py:~234` correctly dates the freshness marker ("2023-01").
- `engine/intl_regime.py:~58` uses `unemployment_trend` (weight 1.0) in the growth axis; but since NaN is excluded (`intl_regime.py:80`), EZ growth now scores on 3 components (gdp, index, global_growth), not 4. M2 has **no** regime reference (pure display cruft).
- *Correction to a prior over-statement:* the stale unemployment does **not** actively degrade the growth score (NaN is filtered, score renormalizes), but `latest.json` **exports** the 3.5y-old 6.7% value; the real defect is signal loss + a display-vs-reality mismatch, not corruption.

**Impact:** A Eurozone employment deterioration (the classic recession trigger) is undetectable — EZ can enter/stay in the Reflation quad on oil+yields alone, blind to labor-market risk. Low confidence (~0.183) reflects the degradation but nothing tells the user *why*.

**Direction for Fable:** Replace `EZ_unemployment` with Eurostat LFS rapid estimates / ECB API (monthly, fresh). Deprecate `EZ_m2` (dead feed; use M3 or narrow money). Add a `data_stale` flag per leg to `latest.json` so the UI greys out ghost legs.

---

## INTL-12 — Intl basket momentum / IC / Sharpe never measured vs forward outcomes *(HIGH · no-validation)*

**File(s):** `tests/test_baskets_intl.py`, `engine/baskets_intl.py`, `engine/baskets_region.py`, `scripts/thematic_rotation_phase0.py`, `scripts/seed_intl_baskets.py`

**Evidence:**
- `tests/test_baskets_intl.py:~50-72`: only smoke tests (cache-hit, contract, ≥3 members). Zero forward-return / IC / Sharpe tests.
- `scripts/thematic_rotation_phase0.py` (the source of the "rank-IC ~0" verdict) validates **US sectors only** (REGION_SECTORS ~66-78 lists US/CA/CN, no intl entry). No intl analog exists.
- `engine/baskets_intl.py:~168` passes `proxy_reader = lambda s: None`, so unlike US/CN/CA baskets there is **no** tradeable-ETF proxy cross-check (`baskets_region.py:~113-125` only computes reference correlation when a proxy is truthy).
- `seed_intl_baskets.py:~20-21` states membership is "hindsight-curated and descriptive — not out-of-sample."

**Impact:** 17 intl themes are presented as a coherent read on cross-country rotation with no evidence that (a) equal-weight beats cap/dividend weighting, (b) 20d momentum ranks predict next-month winners, or (c) the regional sleeves have alpha vs their single-country index. Dead weight could be carried for years undetected.

**Direction for Fable:** Run `intl_basket_validation_phase0.md`: rank-IC of 20d momentum vs forward 20d returns; regional-sleeve alpha vs local MSCI index (MXJP/MXKR/MXIN/MXGB); trend-gate drawdown reduction; and the region lead-lag hypothesis (intl_semis today → SPY semi-sector in 5d — the seed for INTL-4). Same gates as US/China phase-0 (`engine/validation.py`): DSR, split-half, crisis LOCO.

---

## INTL-13 — Intl basket membership frozen since 2021-06-15 seed (5-year stale holdings) *(HIGH · coverage-gap)*

**File(s):** `scripts/seed_intl_baskets.py`, `data/baskets_intl/membership.json`, `engine/baskets_region.py`

**Evidence:**
- `scripts/seed_intl_baskets.py:~39-40`: `SEED='2021-06-15'`, `CURATED='2026-06-19'`.
- `data/baskets_intl/membership.json`: **all 280 members across 17 baskets have `added='2021-06-15'` and `removed=null`**; every changelog has a single "create" entry dated 2021-06-15. Zero adds, removals, or rebalances in 5 years (git audit: only a 2026-06-19 launch commit + a single surgical MONC.MI removal not on this branch).
- `engine/baskets_region.py:~100-102` computes a `partial` list for display only; it does **not** auto-remove — partial members accumulate.

**Impact:** Holdings reflect 2021 market structure (post-COVID, pre-inflation, pre-AI-boom), not 2026. India/Korea IPO unicorns (LG Energy Solution IPO 2020, SK On 2022, fintech/logistics IPOs) are missing; delisted/acquired names still listed. "Global Semis" may miss critical TSMC/SK Hynix supply-chain shifts — the exact names that would carry the INTL-3/INTL-4 read-through edge.

**Direction for Fable:** 6-monthly maintenance cadence: re-run the seeder against the live universe (rule-based membership refresh), persist a changelog with rationale (acquired/delisted/reclassified), auto-flag partials to the page, and git-track `membership.json` diffs.

---

## INTL-14 — Carry ranking (intl 10y vs US) computed but never wired to FX / rate-relative signals *(MEDIUM · feedback-gap)*

**File(s):** `engine/intl_rates.py`, `engine/intl_bonds.py`, `engine/forex_signals.py`, `engine/forex_inputs.py`

**Evidence:**
- `engine/intl_rates.py:~97-113`: `carry_vs_us` computed (y10 − us10; India ~7% − US ~4% = ~300bp) and `carry_ranked` list produced. grep: `carry_vs_us` appears **only** in `intl_rates.py`.
- `engine/intl_bonds.py:~230-234,310-320`: `us_premium_bp` ("the FX value/carry anchor") computed and included in a `drivers_for['forex']` hand-off — never read anywhere. grep: `us_premium_bp` exists only in `intl_bonds.py` output.
- `engine/forex_signals.py:~93-148`: `carry_signal()` / `rates_signal()` source rates from a **separate** pair-specific config (`fx_rates_short/long`), not from the intl rig — no cross-reference.

**Impact:** Carry is a primary FX driver, computed twice in the intl suite and consumed by nothing. (Partial mitigation on severity: several intl currencies — INR, KRW, TWD — aren't in the G10+managed-EM forex universe, so some carry can't be traded directly.)

**Direction for Fable:** Wire the carry ranking into `engine/forex_signals.py` as a carry-flip detector (US premium narrowing = USD tailwind); backtest rolling 21d carry vs 63d USD performance (target IC>0.10); feed as a FX-pair leg where the pair exists. See PART 3 §3.4.

---

## INTL-15 — Global 10y aggregate + US-vs-world premium never scored or fed to signal engines *(MEDIUM · missing-feature)*

**File(s):** `engine/intl_bonds.py`, `scripts/build_bonds.py`, `engine/cross_asset_confirm.py`, `engine/master_brain.py`

**Evidence:**
- `engine/intl_bonds.py:~202-268`: `snapshot()` computes `avg_10y` (GDP-weighted global cost of capital), `us_premium_bp`, and EM OAS/trend. Docstring (line ~7): "imports nothing from the scoring core, and nothing in the scoring path imports it."
- All fields land in `data/bonds/bond_health.json` (`build_bonds.py:~665`). `cross_asset_confirm.py:~318` and `master_brain.py` read `bond_health.json` but access only the **US** bond fields (pillars/cycle/credit/curve/sovereign) — never the `intl_bonds` block. `btc_signals.py` / `holdings_signals.py` never reference it.

**Impact:** Global 10y rising (higher worldwide cost of capital) is a broad equity headwind, especially growth/tech; US-vs-world premium narrowing signals a dollar headwind / risk-on. Both are high-signal cross-asset reads locked in the display-only suite. US/China scoring has no visibility into global rate momentum.

**Direction for Fable:** Create `engine/global_rates.py` (leaf, like `global_liquidity.py`) exposing `avg_10y`, direction, `us_premium_bp`, premium direction. Backtest 63d global-10y rise vs SPY/QQQ forward returns; add `global_rates_signal()` to duration-sensitive engines (BTC via duration channel; equity term-premium overlay). Validate independence from existing curve/credit legs. See PART 3 §3.5.

---

## INTL-16 — Intl momentum edge never validated for intl markets (ported from US on faith) *(MEDIUM · no-validation)*

**File(s):** `scripts/build_intl_library.py`, `engine/intl_stocks.py`, `engine/residual_alpha.py`, `reports/residual-alpha-phase0.md`

**Evidence:**
- No `intl_stocks_phase0.py` exists; `scripts/intl_macro_sleeve_phase0.py` validates macro *timing*, not stock selection.
- `build_intl_library.py:~40` sets `INTL_ALPHA_WEIGHT=0.55` (vs 0.6 US); line ~9 notes markets are "momentum-persistent like the TSX"; line ~294 frames intl as "unvalidated context" (honest but evasive).
- Empirical: intl universe 1-yr mean ~+6.4% / median ~+2.0%, loses to SPY (~+21%) ~77% of names; India ~+5.5%, Australia ~+9.2% both under global beta.
- *Correction:* US residual momentum **also** failed modern-era DSR (`reports/residual-alpha-phase0.md`: DSR≈0.0014, Sharpe≈-0.29). So the real issue is **weak edge quality applied globally as a light context leg**, not concealment (code discloses "unvalidated context").

**Impact:** The 60-name board is ranked by a rule that does not survive DSR in the US, let alone thin EM/Asia markets where momentum is known to decay. Opportunity cost vs. a validated edge.

**Direction for Fable:** Run per-market + pooled `intl_stocks_phase0.py` (DSR, crisis-gated, ≥3 crises/market). If only US/CA survive, retire intl standouts and replace with regional-macro rotations. If JP/UK survive, split the board validated-vs-unvalidated and weight accordingly. (Note this is the *validation* companion to INTL-8's data fix — do both.)

---

## INTL-17 — Renormalization over available components creates hidden regime-meaning shifts *(MEDIUM · methodology)*

**File(s):** `engine/intl_regime.py`, `engine/intl_inputs.py`, `data/intl_regime/*.parquet`

**Evidence:**
- `engine/intl_regime.py:71-87` (verified): `axis_score = Σ(score·w) / Σ(available w)`. With CPI present (w=1.5) inflation divides by 3.0; when CPI drops after ffill, the same oil+yield signal divides by 1.5 — **effectively doubling** the score.
- Component values (`c_inflation_*`) are computed but **not persisted** to history (`intl_run.py:~57` filters them out), so historical composition is unrecoverable.
- Result: `growth_score=0.714` for JP (4 components) is **not comparable** to AU's 0.714 (4 *different* components with different availability).

**Impact:** The dashboard's advertised "every economy on the same axes" premise is compromised — cross-country regime comparisons mix apples and oranges when macro availability differs. A downstream tilt (PART 2) would mistake compositional drop-out for economic signal change.

**Direction for Fable:** Persist per-day component availability (`growth_components=[...]`, `inflation_components=[...]`). Add `data_quality_score = confidence · (n_used / n_ideal)`. For cross-country comparison require a minimum component set (GDP+CPI+unemployment) or mark "thin regime."

---

## INTL-18 — Taiwan & India regimes reflect global (oil/yield) signals more than domestic macro *(MEDIUM · coverage-gap)*

**File(s):** `engine/intl_inputs.py`, `engine/intl_regime.py`, `config.yml`, `data/intl_regime/{TW,IN}_history.parquet`, `data/intl/latest.json`

**Evidence:**
- Taiwan has **no** macro in `intl_macro/` (config specifies `TWNCPIALLMINMEI` but the FRED fetch fails/skips — no TW CPI/yield/unemployment/GDP parquet). Latest: TW growth=2 (index_trend + copper_gold), inflation=**1** (oil only) — below `min_components=2` yet still emitting inflation=-1.0, confidence 0.167.
- India: only `IN_cpi_yoy` + `IN_yield_10y` on disk (no GDP/unemployment/3m/M2); IN CPI stale (last 2025-03), so effective inflation is oil+yield only. Confidence ~0.417.

**Impact:** TW/IN regime scores contain little-to-no domestic information — they are essentially "what are global oil/yields doing?" plotted with confidence numbers that imply legitimate reads. This is misleading cross-country comparison and useless for local relative value.

**Direction for Fable:** Add a `regime_type ∈ {full, thin, global_only}` flag per country. Either commit to collecting TW/IN domestic macro (national statistics offices / CEIC) or drop them and label their confidence "global cycle, not local."

---

## INTL-19 — Cross-country comparison grid mixes regime/macro/equity with no causal layering *(MEDIUM · methodology)*

**File(s):** `templates/intl.html.j2`

**Evidence:**
- `templates/intl.html.j2:344-392`: a 15-column horizontally-scrolled table mixing regime (col 3), macro (cols 4-12), equity (cols 13-15). Sequence lacks causal order — CPI (col ~11) comes *after* Real10y (which is 10y−CPI); policy rate precedes 10y/curve despite driving them.
- "Equity stretch" (col 15) uses per-market own-history extension (`intl_equity_risk.py:~51`) with no cross-market calibration: JP and KR both read "stretched" but are incomparable (JP −4.2% off-high, realvol 40.1; KR −7.7% off-high, realvol 75.3). Caveat at 391-392 discloses "no keyless implied-vol."

**Impact:** The grid encourages checklist thinking over causal macro-transmission reasoning; "stretched" has no cross-country baseline (what is normal for Japan vs Korea?).

**Direction for Fable:** Split into (1) a MACRO DRIVERS panel (growth score, inflation score, curve, real yield) showing cross-country clustering, and (2) an EQUITY TAPE panel (RSI, momentum, drawdown risk, extension), mirroring the `rate_inflation_transmission` design to surface macro→equity causality.

---

## INTL-20 — No per-name conviction tier / institutional risk gates on the intl board *(MEDIUM · missing-feature)*

**File(s):** `scripts/build_intl_library.py`, `scripts/build_stock_library.py`, `engine/signal_gate.py`

**Evidence:**
- `build_intl_library.py:~274-299` computes `signal_gate.gate()` (T1→T4 tiers) per name; `~361-363` `blend_sorted()` does apply a tier-weighted cascade (T1=1.0 … T4=0.4). *Correction:* the tier is **not** ignored — it reorders. But there is **no** explicit tier-split field, no UI tier filter, and (line ~360) code notes "Intl has no alignment tiers."
- `build_intl_library.py` lacks `entry_signal`, `risk_sizing`, `gex_confirm`, `demand_chain` — all present in `build_stock_library.py:~1247-1375`.

**Impact:** Intl standouts cannot be filtered to "T1 only," and lack the pullback-entry / vol-managed-sizing / gamma-confirm layers that make the US board institutionally usable. A name can rank #1 by alpha with no entry zone or confirmer.

**Direction for Fable:** Add an explicit `tier`/`buy_by_tier` split to `intl_setups.json` + UI filter; add `entry_signal` + `risk_sizing` + (where options exist) `gex_confirm`; for options-less markets (JP/KR) use realized-vol percentile + volume as proxy confirmers.

---

## INTL-21 — Correlation heatmap is weekly-only, masking daily/intraday diversification *(MEDIUM · methodology)*

**File(s):** `engine/intl_performance.py`, `site/intl.html`

**Evidence:**
- `engine/intl_performance.py:~280` resamples to `W-FRI` (deliberate, to avoid holiday-calendar zero-return noise). The average off-diagonal (~0.54) collapses to a single "diversification on offer" gauge but hides pair variation (JP-TW≈0.88 vs TW-IN≈0.26).
- **Doc bug:** `site/intl.html:~999` says "daily USD-return streams"; the engine is weekly (line ~1305 correctly says weekly). *Correction:* the "masks diversification" framing is overstated — weekly is appropriate for allocation; the real gap is no daily view for daily traders.

**Impact:** A daily-rebalancing PM cannot see daily diversification; and the page mislabels its own frequency.

**Direction for Fable:** Fix the "daily" label. Add an optional daily-correlation panel (noted as holiday-noisier) and disaggregate the heatmap into tightest vs loosest pairs.

---

## INTL-22 — Monthly macro diff'd without smoothing → spurious daily confidence oscillation *(MEDIUM · methodology)*

**File(s):** `engine/intl_regime.py`, `engine/intl_inputs.py`, `data/intl_regime/JP_history.parquet`

**Evidence:**
- `engine/intl_regime.py:~45-51` `_monthly_sign()` = `np.sign(series.diff(63))` on **forward-filled** monthly data (`intl_inputs.py:~121-126` ffills to daily). As the 63-day window slides through ffill plateaus, component signs flip with no new data.
- `intl_regime.py:~157` recomputes `regime_confidence` fresh each day, no rolling window.
- Verified in `JP_history.parquet`: 2026-02-23 → 04-02 `growth_confidence` oscillates 0.0 → 0.857 → 0.714 → 0.286 → 0.095 with no new releases; ~22% of days show confidence swings >0.1.

**Impact:** False daily precision — confidence appears volatile without economic change. When many components are near threshold, the agreement metric swings 75%↔100% on noise.

**Direction for Fable:** Apply a 2-3 month rolling average before `sign()`, or require a component to hold a flipped sign for 2+ months before it registers. Alternatively re-score agreement as simple majority (>50%). Document the inherent 1-3 month regime-recognition lag.

---

## INTL-23 — Real-yield uses point-in-time CPI, not forward inflation expectations *(MEDIUM · methodology)*

**File(s):** `engine/intl_inputs.py`, `engine/intl_rates.py`

**Evidence:**
- `engine/intl_inputs.py:~164`: `real_yield = yield_10y − cpi_yoy` (10y nominal minus latest lagged YoY CPI). Contrast US, which uses FRED DFII10 (TIPS) + T10YIE/T5YIFR breakevens (market-implied, forward-looking).
- CPI sources are lagged/stale (AU quarterly; JP ends 2021; KR ends 2023). The 490d freshness gate (lines ~207-208) is binary, not a degradation.

**Impact:** Where a country's inflation *expectations* are moving but measured CPI is stale, the real-yield read misprices the discount-rate channel — precisely the leg you'd want to feed a US/China duration/rate-sensitive-sector tilt.

**Direction for Fable:** For markets with linkers/swaps (AU/GB/EZ) use implied breakeven inflation (10y nominal − 10y linker); for JP/KR use survey/central-bank inflation expectations. Backtest breakeven-based vs lagged-CPI real yield as an equity-return predictor.

---

## INTL-24 — No cross-validation between equity-risk froth and recession score *(MEDIUM · missing-feature)*

**File(s):** `engine/intl_equity_risk.py`, `engine/intl_regime.py`, `engine/intl_compare.py`

**Evidence:** `intl_equity_risk.py:~66` (bubble_flag) and `intl_regime.py:~156` (recession_score) both ship to `latest.json` but there is **no joint analysis** (`intl_compare.py:~84-101` counts them separately). Live: India recession=34 + drawdown_risk=47 + bubble=false; Korea recession=14 + bubble=true.

**Impact:** No logic flags internally inconsistent reads (froth+low-recession = euphoric top; high-drawdown+rising-price = capitulation), and no early-warning composite exists.

**Direction for Fable:** Add `engine/intl_coherence.py` computing a `coherence_check()` per country; log warnings on incoherence; optionally gate the equity-risk board when >50% of countries are incoherent.

---

## INTL-25 — Bubble gauge's RSI+off_high branch is unvalidated *(MEDIUM · no-validation)*

**File(s):** `engine/intl_equity_risk.py`, `engine/extension.py`

**Evidence:** `intl_equity_risk.py:66`: `bubble = grade in ('stretched','parabolic') OR (rsi>=72 and off_high>-3)`. The `parabolic` leg is validated (`engine/extension.py:~14-18`; top-picks backtest showed parabolic → crashes), but the **RSI+off_high conjunction is unvalidated** and in live data never triggers. *Correction:* not "decorative" — half is validated; the OR-junction is a fallible heuristic without evidence.

**Impact:** Readers may over-weight a flag whose second branch has no measured basis.

**Direction for Fable:** Backtest the RSI+off_high branch vs forward 63d/252d drawdowns; remove or replace with a simple `above_2sd_rsi` state if IC<0.05.

---

## INTL-26 — Eurozone reflation read is oil+yield-driven with no true labor visibility *(MEDIUM · data-quality)*

**File(s):** `engine/intl_inputs.py`, `engine/intl_regime.py`, `data/intl/latest.json`

**Evidence:** EZ special-cased to use `ez_depo_rate` as policy_rate (`intl_inputs.py:~156-160`); EZ unemployment ffill'd from a 2023-01 print then NaN; EZ CPI fresh (2026-04). Latest quad = Reflation (growth≈+0.2, inflation≈+0.33), confidence 0.183 (low confidence *does* capture the degradation, but nothing surfaces *why*).

**Impact:** "Is EZ really reflating, or is this just oil+yields rising?" is unanswerable from the page; the unemployment leg is a ghost. (Overlaps INTL-11; kept distinct because the *reflation-read interpretation* is the user-facing harm.)

**Direction for Fable:** Same as INTL-11 (source live EZ unemployment; per-leg staleness flag); additionally surface "regime driven by proxies (oil/yield), no fresh labor" as an inline note when unemployment is NaN.

---

## INTL-27 — Hysteresis parameters tuned on US data, not intl return/predictive power *(MEDIUM · methodology)*

**File(s):** `config.yml`, `scripts/tune.py`, `scripts/validate.py`, `tests/test_intl_regime.py`

**Evidence:** `config.yml` `intl.engine.quad` shares `hysteresis_days=7`, `shock_override_z=0.85` uniformly across all 7 economies; `tune.py`/`validate.py` tuned these on **US** data only (whipsaw 20.4%→9.3%). No per-country intl backtest. `engine/intl_regime.py:~9-11` notes components are fixed, not per-country tuned. *Correction:* shock_override was tested on the 2020 COVID crash and did not create false reversals — lower risk than initially framed.

**Impact:** Uniform hysteresis over heterogeneous data quality (JP/KR full vs TW/IN sparse) may whipsaw thin markets or lag reversals — a live risk only if intl regime feeds signals.

**Direction for Fable:** Backtest `hysteresis_days ∈ {3,5,7,10,14}` per country vs forward 21d/63d returns; allow per-country override where thin markets need shorter holds. Expose `hysteresis_days` in `latest.json` so consumers know the regime lag.

---

## INTL-28 — Equal-weight basket construction never validated vs alternative weightings *(MEDIUM · methodology)*

**File(s):** `scripts/seed_intl_baskets.py`, `engine/baskets_intl.py`, `engine/baskets_region.py`

**Evidence:** `seed_intl_baskets.py:~203-207` fixes "Equal-weighted, monthly-rebalanced"; `baskets_intl.py` + `baskets_region.py` delegate to `engine.baskets._ew_level`. No phase-0 ever compared EW vs cap-weight, momentum-weight, quality-weight, or dividend-adjusted on the intl universe.

**Impact:** Equal-weight is an asserted prior, not a measured choice; it may under/over-perform the tradeable cap-weighted analog by a wide margin, distorting every "theme trending" read.

**Direction for Fable:** In the INTL-12 phase-0, add a weighting-scheme bake-off (EW vs CW vs momentum/quality tilt) on the intl universe and adopt the winner (or document why EW is retained for honesty/robustness).

---

## INTL-29 — intl_search closes 13 days stale; sparse (~20% coverage on last date); no refresh guard *(MEDIUM · data-quality)*

**File(s):** `data/intl_search/closes.parquet`, `collectors/intl_universe.py`, `scripts/build_baskets_intl.py`, `config.yml`

**Evidence:**
- `closes.parquet` max date 2026-06-19 (13 trading days stale vs 2026-07-02); last date with >50% coverage is 2026-06-17. June-19 has only ~20.8% (208/1000) coverage, below `config.yml` `min_coverage=0.5`.
- `collectors/intl_universe.py:~256` **persists closes even when the min_coverage check (~251-252) raises** — so sparse June-19 data was written and re-persisted via `combine_first(prev)` on subsequent runs.
- `scripts/build_baskets_intl.py` (lines 1-114) calls `compute_intl_baskets()` with **no** upstream refresh step (contrast US via `lib.store` auto-refresh; China via live china_search).

**Impact:** All live basket scores (20d momentum, correlation, breadth) run on ~2-week-old, ~20%-sparse closes. A geopolitical break in early July is invisible; the sparse tail silently corrupts breadth and momentum.

**Direction for Fable:** Add a daily intl_search refresh + coverage gate that **fails closed** (don't persist below min_coverage); validate against `members.parquet` for delisted/new names; show "as of DATE (stale)" on the page when >3 days old.

---

## INTL-30 — CANON exclusion orphans 5-7 intl baskets from any cross-market check *(MEDIUM · redundancy)*

**File(s):** `engine/narrative_crossmarket.py`, `engine/baskets_intl.py`, `site/intlbasketdata/baskets.json`

**Evidence:** `narrative_crossmarket.py:38-70` CANON includes globally-traded themes; lines ~11-15 gate out region-specific themes (banks, insurers, telecom, housing, utilities, gaming) as "domestic credit/rates/regulation don't transfer." Yet `intl_banks`/`intl_insurers`/`intl_telecom` **are** scored via `compute_theme_intel('intl')` and rendered live — so they are orphaned: scored but never cross-checked. *Correction:* it is **7 of 17** excluded, not 5; `intl_luxury` and `intl_mining` **are** in CANON (not "partially" excluded).

**Impact:** `intl_banks` trending down (ECB tightening) is never flagged as a potential leading indicator for US regional-bank stress / HIBOR spreads. The exclusion is a deliberate design choice, but its continued validity is untested given cross-market interconnectedness.

**Direction for Fable:** Audit each orphaned basket's correlation with its US/China analog (intl_banks→XLF/regional-bank ETFs; intl_telecom→US telecom momentum). If correlated and not purely domestic, add to CANON with a "macro-regime-gated / FX-adjusted" caveat; else document the low correlation and add a "show regional themes" toggle.

---

## INTL-31 — Real-yield display masked for JP/KR by stale CPI (signal gap, not bug) *(MEDIUM · data-quality)*

**File(s):** `engine/intl_inputs.py`, `engine/intl_rates.py`, `data/intl_macro/{JP,KR}_cpi_yoy.parquet`

**Evidence:** `intl_inputs.py:~196-209` gates real_yield to NULL when CPI >490d stale (correct behavior). JP CPI 2021-06, KR CPI 2023-11 → JP/KR real_yield display blank despite fresh 10y yields (JP/KR 2026-05). The gating prevents mislabeling (why severity is MEDIUM not HIGH), but the underlying feed is a genuine gap.

**Impact:** Real yield — a leading cross-asset discount-rate signal for duration-sensitive US sectors (Tech/Utilities/Financials) — is dark for two major economies, so it can never feed a US duration/rate-sector overlay.

**Direction for Fable:** Source fresh JP/KR CPI (BoJ / KOSTAT / central-bank APIs). Once current, re-enable real_yield and backtest whether fresh real-yield >2.5% forecasts 12m equity/duration relative performance. (Companion to INTL-23.)

---

## INTL-32 — Page visual hierarchy mimics actionable dashboards while text says "display-only" *(MEDIUM · ux)*

**File(s):** `templates/intl.html.j2`

**Evidence:** `templates/intl.html.j2`: KPI numbers 21px/800-weight (CSS ~96,119-127), gradient hero stage (~103-105), animated flag (~108). Scored-looking "Risk appetite 68/100" dial (~264-265) and "Capital rotating toward ex-US" verdict (~240-244). All "display-only" caveats are 11.5px muted italic placed *after* the KPIs (~280, 338, 391, 485, 545). Engine confirms intent (`intl_run.py:3`).

**Impact:** Cognitive dissonance — the eye lands on scored-looking dials, then fine print disclaims any forward edge. Ethical (not financial) risk while the suite stays display-only; becomes a real risk if these dials get promoted to signals.

**Direction for Fable:** Physically separate display from any alpha claim: add a hero banner ("Comparative international MACRO — context only; for actionable picks see intl_stocks.html"); desaturate/de-scale the scored dials; move standouts to a distinct "alpha lab" section with explicit backtest disclosure.

---

## INTL-33 — Close-only intl data cripples technical confirmation *(MEDIUM · coverage-gap)*

**File(s):** `collectors/intl_universe.py`, `data/intl_search/closes.parquet`, `engine/stock_technicals.py`, `scripts/build_intl_library.py`

**Evidence:** `collectors/intl_universe.py:~206` downloads `Close` only (`auto_adjust=True`); `closes.parquet` has no high/low/volume. `engine/stock_technicals.py:~296-322` returns None for all 15 OHLCV-only fields (ATR14, ADX/DI, squeeze, chop, NR7, donchian_pos, rel_volume, dollar_vol_20d, OBV, CMF, breakout_vol_confirmed) when H/L/V absent. `build_intl_library.py:~114` calls `snapshot(close)` and falls back to the thin snapshot. US board uses full OHLCV (`build_stock_library.py`).

**Impact:** Intl standouts have no ATR (trend strength), no ADX (direction), no volume confirmation, no vol-squeeze — half the technical alpha sources the US board uses are blind. A weak-volume/high-ATR name would be flagged risky in the US and invisible here.

**Direction for Fable:** Download H/L/V for the intl universe and recompute standouts with the full `stock_technicals.snapshot()`. For options-less markets use ATR/volume/choppiness as breadth legs. Add an "OHLCV vs close-only" data-quality flag to `intl_setups.json`.

---

## INTL-34 — Intl alpha is a cross-sectional rank with no forward backtest and no risk-management layers *(MEDIUM · no-validation)*

**File(s):** `scripts/build_intl_library.py`, `scripts/build_stock_library.py`, `engine/residual_alpha.py`

**Evidence:** `engine/residual_alpha.py:~34-36` self-describes as "a modest, regime-decayed edge — context, not a buy list." `build_intl_library.py:~267-332` produces standout rows with only signal_gate + anticipation + conviction; `build_stock_library.py:~1247-1375` adds `entry_signal`, `risk_sizing`, `gex_confirm`, `demand_chain`, `pullback_zone`. No forward-test of intl momentum on a monthly rebalance exists.

**Impact:** Intl standouts lack the institutional risk layer the US board has, and the only evidence is a t=0 cross-sectional rank. (Overlaps INTL-20 on gates and INTL-16 on validation; kept as its own ledger item because it is the *combined* "rank without confirm without forward-test" defect.)

**Direction for Fable:** Add entry/risk-sizing/confirm layers (INTL-20) **and** publish a monthly-rebalance forward test (top-20 intl names, 1-month hold vs equal-weight universe, filtered by entry/risk rules) vs a dumb 60/40 EW baseline.

---

## INTL-35 — USD performance leaderboard is descriptive-only, never actionable *(LOW · redundancy)*

**File(s):** `templates/intl.html.j2`, `engine/intl_performance.py`, `scripts/build_intl.py`

**Evidence:** `engine/intl_performance.py:~134-178` (`usd_leaderboard`) renders 7-economy 1m/3m/6m/12m/YTD USD returns with equity/FX decomposition at `intl.html.j2:~623-660` (macro mode only). Purely presentational; no downstream scoring. *Correction to a prior claim:* it is **not** redundant with `markets.html` (which shows cycle positioning, not performance) — the real issue is that this contextually rich data never feeds forward decisions.

**Impact:** Contextually valuable (honest FX-vs-equity decomposition) but never scored; page real estate could be forward-guiding.

**Direction for Fable:** Keep as an anchor but add an adjacent relative-value matrix (each 10y vs US 10y carry, real-yield spreads, FX-vol term structure) — feeds INTL-14's carry work and makes the section actionable.

---

# PART 2 — THE FEEDBACK GAP *(the centerpiece)*

> **This is the doc's reason for existing.** Every silo problem above (INTL-1, INTL-2, INTL-3, INTL-4, INTL-14, INTL-15, INTL-30) is a symptom of one architectural decision: *the intl suite was built as a read-only display vertical and was never given an export path to the signal engines that price US and China stocks.* This section names the gap precisely, explains why it exists, and lays out the opportunity map Fable should solution.

## 2.1 The current architecture, stated plainly

There are three parallel, non-communicating worlds in this repo:

1. **The intl vertical** — `collectors/intl_universe.py` + `intl_macro/*` → `engine/intl_*.py` → `scripts/build_intl*.py` → `data/intl/latest.json`, `intl_setups.json`, `baskets_intl.html`. Self-declared display-only (`intl_run.py:3`).
2. **The US stock world** — `engine/conditions.py` (US-FRED macro only) + `engine/stock_score.py` + `engine/residual_alpha.py` + `theme_scoring.compute_theme_intel("us")` → `scripts/build_stock_library.py`.
3. **The China stock world** — `scripts/build_china_library.py` importing only China-market modules; no `theme_scoring` call at all.

The **only** cross-vertical wires that exist point at BTC, not at stocks:
- `engine/global_liquidity.py` (central-bank assets, incl. BoJ `JPNASSETS`) → `btc_signals.py`.
- `engine/narrative_crossmarket.py` → BTC vector display; explicitly `DISPLAY-ONLY`, and it self-neuters on intl: "Intl has no single regime snapshot → None (never claims alignment)."

And the one wire that touches intl output feeds a *picture*: `data/intl/latest.json → build_vector.py` (the Globe hub card). **No intl datum reaches `build_stock_library.py` or `build_china_library.py`.** (Grep-verified across all seven core scorers: zero `intl_*` imports.)

So the state of the world is: **a fully-built, 7-economy, regime + rates + bonds + equity-risk + thematic-basket + per-name-alpha dataset sits one import away from the stock scorers and is used for nothing but rendering.**

## 2.2 Why the gap exists (root cause, not blame)

Three compounding reasons, all visible in the code:

1. **Display-only was a deliberate honesty posture.** The suite refuses to claim edge it hasn't validated (good discipline — see INTL-7, INTL-9, INTL-10). But "don't claim edge" got implemented as "don't export at all," which threw out the context baby with the unvalidated-signal bathwater.
2. **The validation never ran, so the door was never opened.** `narrative_crossmarket.py` literally *contains* the CANON of cross-market analog themes and admits "no reliable lead-lag" — but no one ran the lead-lag backtest (there is no `intl_*_phase0.py`), so the gate stayed shut by default (INTL-4, INTL-12, INTL-16).
3. **The data underneath is too stale/thin to trust as-is.** 25+ of ~37 macro parquets are >90d old (INTL-5, INTL-11); the universe is survivor-biased (INTL-8); closes are 13d stale and 20% sparse (INTL-29). Even a willing integrator would be feeding contaminated inputs. **This is why the feedback bridge and the data hardening must ship together** — building the pipe over a leaking reservoir just launders bad data into live trades.

## 2.3 What "good" looks like — the target architecture

A new leaf layer, `engine/intl_feed.py` (modeled on the existing leaf pattern of `global_liquidity.py` — imports nothing from the scoring core, and the scoring core imports *it*), that reads the intl outputs and emits a small, validated set of **context features** consumed by `stock_score._axis_tailwind` (US) and its China analog:

```
intl_run.py  ─┐
intl_bonds   ─┼─► engine/intl_feed.py ──► features ──► stock_score (US)
intl_stocks  ─┤                                     └─► china stock scorer
baskets_intl ─┘
```

The features are *modulators*, not standalone buys — same posture as the residual-alpha context leg — but they are **validated before they are wired**, and each carries a freshness/quality gate (INTL-5) so a stale leg contributes zero rather than noise.

## 2.4 The opportunity map — five feedback channels, ranked by expected leverage

| # | Channel | Intl source | US/China target | Mechanism (one line) | First validation |
|---|---|---|---|---|---|
| A | **Supply-chain read-through** | intl_stocks / baskets_intl semis (TSMC, Samsung, SK Hynix, MediaTek) | US semis (SMH/SOXX names), China semis | Asian fab/memory health is a physical leading indicator of US semi demand | 1-5d lead/lag IC of intl_semis vs US semi sector (PART 3 §3.1) |
| B | **Thematic lead/lag** | baskets_intl CANON themes | US/CN same-theme baskets → stock tailwind | Global theme leadership may lead the US analog by days | Rank-IC of intl theme momentum vs forward US theme beats (§3.2, INTL-4) |
| C | **Regime spillover** | intl_regime blocs (Asia, Europe) | US/China sector/beta tilt | EU goldilocks / developed-inflation divergence leads US rotation | Lagged bloc-regime vs US cyclicals returns 4-8w (§3.6, INTL-2) |
| D | **Global rate/liquidity headwind** | intl_bonds avg_10y, us_premium_bp; BoJ balance sheet | US/CN growth-tech beta, duration overlay | Rising global cost of capital + narrowing US premium = broad equity headwind / dollar direction | 63d avg_10y vs SPY/QQQ; premium vs DXY (§3.5, INTL-6/15) |
| E | **Carry / FX transmission** | intl carry ranking, BoJ softness → yen | US multinationals, EM-exposed names; forex signals | Carry unwind (yen) is a global risk-off trigger; carry tailwind supports EM | Carry vs 63d USD perf; yen-vol regime vs global drawdown (§3.3/3.4, INTL-14) |

**The single highest-conviction seed is Channel A** (supply-chain read-through). It has a *physical* mechanism (not a statistical coincidence), a clean instrument set (Asian fabs are named, liquid, and already in the intl universe), and a direct US target (SMH). It should be Fable's first solution.

## 2.5 The non-negotiable guardrails for whoever builds the bridge

1. **Validate before wiring.** No intl feature enters `stock_score` without a published per-channel IC/DSR (the phase-0 pattern already used for US). The whole point of the display-only posture was honesty — preserve it *through* the bridge.
2. **Freshness-gate every leg.** Reuse/extend INTL-5's proposed `data_age_risk`: any intl feature whose underlying series is stale beyond threshold contributes **zero**, not a ffill'd ghost. Otherwise the bridge launders INTL-5/8/11/29 into live trades.
3. **Modulator, not gate (initially).** Start intl features as continuous conviction *modifiers* (like residual alpha) with small weight; promote to hard gates only after OOS confirmation.
4. **Fix data and pipe together.** The staleness/survivorship/sparsity fixes (INTL-5, 8, 11, 29, 33) are prerequisites, not follow-ups.

---

# PART 3 — CROSS-MARKET EDGE MAP *(novel-solution seeds for Fable)*

Each subsection is a candidate feedback edge: mechanism, direction, evidence/sources, how to operationalize into a US/China leg or gate, data have vs needed, and confidence. These are hypotheses to *test*, not validated signals.

## 3.1 Asian-semi supply-chain read-through → US semis *(Channel A)*

- **Mechanism:** TSMC/Samsung/SK Hynix/MediaTek sit *upstream* of US fabless demand. Fab utilization, memory pricing, and the equity tape of Asian foundries/memory names lead US semiconductor demand physically (order-to-revenue lag), not just correlationally.
- **Direction:** Rising Asian-semi equity momentum + healthy fab tape → **boost** US semi (SMH/SOXX) conviction; deteriorating Asian-semi tape → **fade** US semi standouts even if US price is still extended.
- **Evidence / sources:** `engine/intl_stocks.py` already computes per-market residual alpha for these names; `baskets_intl` has a "Global Semis" theme (INTL-4, INTL-13); `narrative_crossmarket.py:38-70` CANON lists `semis` as a cross-market analog but never opens the gate. External corroboration should be sourced during solutioning (TSMC monthly revenue, memory spot pricing) — no external figure is asserted here.
- **Operationalize:** In `intl_feed.py`, compute a `semis_readthrough` score = f(Asian-semi residual momentum, 1-5d lead/lag IC vs US semi sector). Feed to `stock_score._axis_tailwind` for US semi names as a modulator; mirror into the China semi scorer.
- **Data have vs needed:** *Have:* Asian-semi closes + residual alpha (INTL-3). *Needed:* H/L/V for those names (INTL-33), point-in-time membership (INTL-8), TSMC monthly-revenue feed (new collector), and the lead/lag backtest.
- **Confidence:** **High** on mechanism, **medium-low** on capturability until the lead/lag IC is measured and survivorship (INTL-8) is controlled.

## 3.2 Global thematic lead/lag → US/China same-theme baskets *(Channel B)*

- **Mechanism:** For globally-traded themes (defense, robotics, autos, pharma, energy, mining, luxury, software), leadership can rotate across time zones; the intl analog may lead the US analog by days.
- **Direction:** Intl theme momentum up-tick that leads → boost the US/CN same-theme tailwind that feeds constituent stock conviction.
- **Evidence / sources:** CANON in `narrative_crossmarket.py:38-70`; intl baskets scored via `theme_scoring.compute_theme_intel("intl")` (INTL-4); the honest prior is that raw thematic momentum has rank-IC ~0 on the unbiased US universe (`scripts/thematic_rotation_phase0.py`), so **the edge, if any, is in the lead/lag, not the level.**
- **Operationalize:** For each US basket with an intl analog, measure same-day corr + 1-5d lead/lag IC on the 27y thematic phase-0 data; surface a binary/continuous "intl theme leading" modifier to `stock_score._axis_tailwind`.
- **Data have vs needed:** *Have:* intl + US basket series. *Needed:* the lead/lag phase-0 (INTL-12), plus fresh membership (INTL-13) and closes (INTL-29).
- **Confidence:** **Medium** — mechanism plausible, but the null (rank-IC ~0 on levels) is a strong prior; only lead/lag survival at txn cost would justify wiring.

## 3.3 BoJ softness → yen weakness → global carry regime *(Channel E, monetary side)*

- **Mechanism:** BoJ balance-sheet expansion / YCC caps drive yen weakness → global carry trades fund in yen → a BoJ hawkish surprise (or carry unwind) is a systemic risk-off trigger (the classic carry-unwind crash channel).
- **Direction:** Yen-weakness-from-BoJ-softness = risk-on carry tailwind (supports EM + high-beta); rapid yen strengthening / rising yen vol = **hard risk-off gate** on US/China high-beta and EM-exposed names.
- **Evidence / sources:** `global_liquidity.py` already ingests `JPNASSETS` (for BTC) but the intl desk shows *nothing* on BoJ (INTL-6). `USDJPY_X.parquet` exists in `data/intl/`. The channel is absent from the intl rates desk entirely.
- **Operationalize:** Add a BoJ balance-sheet + YCC state to the rates desk (INTL-6); compute a "yen-carry-stress" gauge (yen vol regime + BoJ direction) in `intl_feed.py`; wire as a risk-off veto to US/China high-beta conviction.
- **Data have vs needed:** *Have:* JPNASSETS, USDJPY. *Needed:* BoJ policy/YCC state (scrape), yen-vol series, and a backtest of yen-vol regime vs global equity drawdowns.
- **Confidence:** **High** on mechanism (well-documented cross-asset channel), **medium** on operational calibration.

## 3.4 Rate carry (intl 10y − US 10y) → FX & EM-exposed equity *(Channel E, rate side)*

- **Mechanism:** Positive carry (foreign 10y > US 10y) is a currency tailwind; narrowing US premium is a dollar headwind / risk-on.
- **Direction:** Widening foreign carry → currency-hedged foreign equity or the local-currency name; narrowing US premium → USD-negative, risk-on tilt for US multinationals / EM-exposed names.
- **Evidence / sources:** `intl_rates.py:97-113` computes `carry_vs_us` and `carry_ranked`; `intl_bonds.py:230-234` computes `us_premium_bp` ("the FX value/carry anchor") — both dead-ended (INTL-14, INTL-15). `forex_signals.py` uses a *separate* rates config.
- **Operationalize:** Feed `us_premium_bp` + direction into `forex_signals.carry_signal()` (a carry-flip detector) and, where the pair is untradeable (INR/KRW/TWD), into an equity conviction modifier for names exposed to that currency.
- **Data have vs needed:** *Have:* intl 10y, US 10y, us_premium_bp. *Needed:* carry-vs-forward-USD backtest (target IC>0.10); real-yield upgrade (INTL-23/31) to make carry inflation-adjusted.
- **Confidence:** **Medium-high** — carry is a first-order FX driver; the constraint is the untradeable-EM-currency mismatch, so equity-modifier use may beat FX-pair use.

## 3.5 Global cost of capital (avg_10y) + US-vs-world premium → equity beta / duration overlay *(Channel D)*

- **Mechanism:** GDP-weighted global 10y rising = higher worldwide discount rate = broad headwind for long-duration equities (growth/tech); narrowing US premium = dollar headwind / risk-on.
- **Direction:** Global 10y rising fast → **fade** US/CN growth-tech beta and lengthen the duration hedge; premium narrowing → risk-on tilt.
- **Evidence / sources:** `intl_bonds.py:202-268` computes `avg_10y` + `us_premium_bp` + EM OAS; all land in `bond_health.json` but only the US bond block is consumed downstream (INTL-15).
- **Operationalize:** Create `engine/global_rates.py` (leaf) exposing `avg_10y`, direction, `us_premium_bp`, premium direction; add `global_rates_signal()` to duration-sensitive engines; validate independence from existing curve/credit legs.
- **Data have vs needed:** *Have:* everything, already in `bond_health.json`. *Needed:* 63d-global-10y-vs-SPY/QQQ backtest + orthogonality check vs current bond legs.
- **Confidence:** **Medium-high** — the mechanism is textbook, the data is already computed; the only open question is incremental information over the existing US curve/credit legs.

## 3.6 Regime spillover — bloc regimes lead US rotation *(Channel C)*

- **Mechanism:** Europe/Asia regime shifts (EU goldilocks, developed-inflation divergence, EM growth acceleration) can lead US sector rotation because global demand/inflation impulses transmit across time zones with a lag.
- **Direction:** EU goldilocks + rising real yields → tilt US growth/rate-sensitive screening; EM growth accelerating → tilt US cyclicals/materials.
- **Evidence / sources:** `intl_regime.py` produces per-country growth/inflation scores + quads (INTL-2); currently consumed only by the Globe. **Caveat:** the regime inputs are stale/thin for exactly the economies that matter for spillover (JP/KR CPI dead — INTL-5/18), so this channel is *blocked on data* more than any other.
- **Operationalize:** In `intl_feed.py`, aggregate regimes into Asia/Europe blocs, compute relative growth/inflation momentum, emit "bloc regime" features to the US/CN sector-tilt layer — **only after** the data-hardening (INTL-5, 11, 18) restores real macro to the inputs.
- **Data have vs needed:** *Have:* the regime framework. *Needed:* fresh CPI/unemployment for JP/KR/EZ (INTL-5/11), TW/IN domestic macro (INTL-18), component-availability persistence (INTL-17), and a lagged-bloc-regime → US-cyclicals backtest.
- **Confidence:** **Low-medium** — the highest-*potential* channel (early regime detection is the intl suite's whole promise) but the lowest current data readiness. Sequence it *after* the data fixes.

---

# PART 4 — COVERAGE & DATA GAPS

## 4.1 Macro freshness (the foundation crack)

Of ~37 `data/intl_macro/*.parquet` files, **25+ are >90d stale** (worse than an earlier "54%" estimate). Load-bearing offenders:

| Series | Last obs | Approx age | In regime scoring? | Ledger item |
|---|---|---|---|---|
| JP CPI | 2021-06 | ~1,857d | Yes (drops silently) | INTL-5, INTL-18, INTL-31 |
| KR CPI | 2023-11 | ~974d | Yes (drops silently) | INTL-5, INTL-18, INTL-31 |
| AU CPI | 2025-01 (quarterly) | ~540d | Yes (lagged) | INTL-5, INTL-23 |
| EZ unemployment | 2023-01 | ~1,278d | Yes (drops → 3 legs) | INTL-11, INTL-26 |
| TW (all macro) | none | — | No domestic macro at all | INTL-18 |
| IN GDP/unemployment/3m/M2 | none | — | No — global proxies only | INTL-18 |
| JP/KR/EZ M2 | 2017 | >3,300d | No (display cruft) | INTL-5, INTL-11 |

The template discloses this in buried small text (`site/intl.html:~1461`) but never warns that two economies' quads sit on *different data foundations* (real CPI vs commodity/bond proxy) — breaking the "every economy on the same axes" premise (INTL-17).

## 4.2 Universe coverage & survivorship

- **Survivorship bias** (INTL-8): universe = current UCITS holdings; delisted names permanently absent; no point-in-time snapshots. `engine/universe_history.py` exists for US, no intl equivalent.
- **Basket membership frozen 5 years** (INTL-13): all 280 members `added=2021-06-15`, zero maintenance; missing post-2021 Asian IPOs (LG Energy Solution, SK On, Indian fintech/logistics).
- **CANON orphans** (INTL-30): 7 of 17 intl baskets scored but never cross-checked.

## 4.3 Freshness of price data

- `intl_search/closes.parquet` **13 trading days stale** and ~**20% coverage on the last date**, persisted through a coverage gate that *fails open* (INTL-29). No documented daily refresh in the intl build.

## 4.4 Total-return / adjustment

- Intl closes fetched with `auto_adjust=True` (total-return, dividend-adjusted) — consistent with the repo convention (`data/yahoo/*.parquet` close is dividend-adjusted). No defect here, but any cross-market spread vs a *price-return* series would be apples-to-oranges; flag for whoever builds carry/relative-value matrices.

## 4.5 Missing markets & instruments

- **No China in the intl comparative frame** — China is a *target* of the feedback bridge but is not one of the 7 intl-suite economies, so cross-referencing China vs its Asian peers (INTL-2) requires bridging the China stock world's own regime, not the intl suite's.
- **No BoJ/BoK balance sheet in the intl desk** (INTL-6) despite JPNASSETS being collected for BTC.
- **No implied vol** (keyless) anywhere in intl → cross-market extension grades are own-history only, incomparable (INTL-19, INTL-10).
- **No inflation-linked / breakeven series** → real-yield is lagged-CPI-based (INTL-23).

## 4.6 Missing OHLCV depth

- Intl stocks are **close-only** → 15 OHLCV technical fields are all None (INTL-33), halving the technical alpha surface vs the US board.

---

# PART 5 — PRIORITIZED ROADMAP

## 5.1 Impact × effort ranking

Impact is weighted toward the core question (does it sharpen US/China stock signals?). Effort is rough engineering size.

| Rank | Item | Ledger | Impact | Effort | Why here |
|---|---|---|---|---|---|
| 1 | **Semi supply-chain read-through** (validate → wire Asian-semi → US/CN semi tailwind) | INTL-3, §3.1 | **Very High** | Medium | Highest-conviction feedback edge; physical mechanism; instruments already in-universe |
| 2 | **`intl_feed.py` bridge + freshness gates** (the architecture for all channels) | INTL-1, INTL-2, §2.3 | **Very High** | Medium-High | Enabling layer; nothing else in Channels B-E ships without it |
| 3 | **Macro data hardening** (fresh JP/KR CPI, EZ unemployment, TW/IN domestic; per-leg `data_age_risk`) | INTL-5, INTL-11, INTL-18, INTL-31 | **High** | High | Prerequisite for regime spillover (§3.6) and any honest bridge; prevents laundering stale data |
| 4 | **Global-rates leaf** (`avg_10y`, `us_premium_bp` → duration/beta overlay) | INTL-15, §3.5 | **High** | Low | Data already computed in `bond_health.json`; cheapest high-signal wire |
| 5 | **Survivorship fix** (port `universe_history.py`; point-in-time snapshots) | INTL-8 | **High** | Medium | Every validation number is contaminated until this exists |
| 6 | **Thematic lead/lag phase-0** (open the CANON gate if edge survives) | INTL-4, INTL-12, §3.2 | Medium-High | Medium | Strong null prior (rank-IC ~0 on levels); only lead/lag survival justifies wiring |
| 7 | **BoJ/BoK transmission + yen-carry gate** | INTL-6, §3.3 | Medium-High | Medium-High | Systemic risk-off channel; needs a BoJ scrape |
| 8 | **Carry → FX/equity modifier** | INTL-14, §3.4 | Medium | Low-Medium | Data computed twice already; constrained by untradeable EM pairs |
| 9 | **Intl equity-risk + recession validation** (backtest or relabel) | INTL-9, INTL-10, INTL-25 | Medium | Medium | Honesty + optional MRS-leg promotion |
| 10 | **Intl standout hardening** (OHLCV, tiers, entry/risk gates, forward test) | INTL-7, INTL-16, INTL-20, INTL-33, INTL-34 | Medium | Medium-High | Makes intl_stocks institutionally usable and feed-worthy |
| 11 | **Basket maintenance + validation + refresh** | INTL-12, INTL-13, INTL-28, INTL-29 | Medium | Medium | Unfreezes 5-year holdings; validates or retires themes |
| 12 | **Regime methodology fixes** (smoothing, renorm persistence, per-country hysteresis) | INTL-17, INTL-22, INTL-27 | Medium | Medium | Removes false precision before regime feeds anything |
| 13 | **Dashboard UX / causal grid / correlation daily view / coherence** | INTL-19, INTL-21, INTL-24, INTL-32, INTL-35 | Low-Medium | Low-Medium | Display quality; do after the feedback work |

## 5.2 What Fable should solution first (shortlist)

1. **Ship `engine/intl_feed.py` as a leaf + validate-then-wire the semi read-through (Channel A / §3.1).** This is the single change that best answers "how does international data sharpen US/China stock signals," it has the strongest mechanism, and it forces the architecture (rank 2) into existence as a side effect. Gate every feature on freshness from day one.
2. **Wire the global-rates leaf (§3.5 / INTL-15).** Lowest-effort high-signal win — the data already sits in `bond_health.json`; it needs a leaf module and one orthogonality backtest.
3. **Harden the macro reservoir before opening the regime-spillover channel (INTL-5/11/18 → §3.6).** Regime spillover is the highest-*potential* edge but the lowest data-readiness; fixing JP/KR/EZ/TW/IN macro (and adding `data_age_risk` gating) is the prerequisite that makes it — and an honest bridge generally — safe to build.

Everything else (thematic lead/lag, BoJ carry gate, carry-FX, validation, basket maintenance, UX) sequences after these three, because each either depends on the bridge (rank 2) or on trustworthy data (rank 3).

---

# Appendix — Refuted / not-a-problem (so Fable doesn't chase them)

- **"USD leaderboard is redundant with markets.html."** *Refuted.* `markets.html` shows cycle positioning, not performance; the leaderboard is not duplicated. The real (LOW) issue is that it's descriptive-only, not redundant (INTL-35).
- **"Sparse tickers VAML.NS / 285A.T / SWIGGY.NS are delisted survivorship corpses."** *Refuted.* They are **recent IPOs** (2024-2026). Survivorship bias is real (INTL-8) but these are not its evidence — cite them as IPOs, not delistings.
- **"Stale unemployment actively degrades the EZ growth score."** *Refuted / overstated.* NaN is filtered from the axis (`intl_regime.py:80`); the growth score renormalizes over 3 legs. The real defect is **signal loss + a misleading exported value**, not score corruption (INTL-11).
- **"Weekly correlation *masks* diversification (a data flaw)."** *Refuted framing.* Weekly is a *deliberate* choice to avoid holiday zero-return noise. The real gaps are (a) no daily view for daily traders and (b) a mislabeled "daily" string in `site/intl.html:~999` (INTL-21).
- **"Bubble gauge is entirely decorative."** *Refuted.* The `parabolic`/`stretched` branch is validated (`extension.py`); only the RSI+off_high conjunction is unvalidated (INTL-25).
- **"Intl momentum was ported from US on faith (implying the US edge is solid)."** *Refuted framing.* US residual momentum **also** failed modern DSR (Sharpe≈-0.29). The real issue is a weak edge applied globally as a light context leg, honestly disclosed in code — not concealment (INTL-16).
- **"The tier badge is collected then ignored on the intl board."** *Refuted.* `blend_sorted()` **does** apply a tier-weighted cascade. The real gap is no explicit tier-split field and no UI filter (INTL-20).
- **"`global_liquidity → US` and `narrative_crossmarket → US` feedback paths exist."** *Refuted.* Both feed **BTC only** (`build_vector.py` → `data/vector`), never imported by US/China stock builders. Do not assume these are pre-existing hooks into the stock scorer.
- **"Recession composite / equity-risk gauges are an immediate live risk."** *Scoped down.* They are unvalidated (INTL-9, INTL-10) but currently isolated; the risk is **conditional on integration**. Validate *before* wiring, not because they trade today.
- **"CANON excludes 5 baskets, with luxury/mining partially excluded."** *Corrected.* It excludes **7 of 17**; luxury and mining are **in** CANON, not partial (INTL-30).
