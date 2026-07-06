# Long-Term Thesis Signal Research For Fable

**Prepared:** 2026-07-06  
**Audience:** Fable / Macro Dashboard long-hold program adjudication  
**Status:** research paper and implementation proposal, not a ratified pre-registration  
**Relationship to current program:** companion to `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`, `research/long_hold/OBJECTIVE.md`, `research/long_hold/W1_KILLTEST_RESULTS.md`, and `research/long_hold/WASHOUT_TIMEFRAME_HYPOTHESIS.md`  
**Non-advice:** this is system design and research architecture, not investment advice.

---

## 0. Executive Thesis

The Long-Term Thesis framework should begin from the strongest externally validated long-horizon equity signals, but it should not turn them into a fused "compounder score." The correct architecture is a staged admission and maintenance system:

```text
tactical or washout entry candidate
  -> externally validated quality / value / capital discipline evidence
  -> business repair and expectation-drift evidence
  -> sponsorship and ownership evidence
  -> valuation-implied-expectations check
  -> falsifier-clean thesis watch
  -> active thesis only after earned authority
```

The main design rule:

```text
Entry signals find the door.
Long-term thesis signals decide whether there is a business worth following through the door.
```

The current repo already has a ratified long-hold program, a horizon firewall, long-hold labels, a deferred W1 missed-hold kill-test, display-only compounder features, clocks, and moat falsifiers. The next research layer should not rebuild those. It should add a disciplined external-factor foundation and a first-principles research queue that can eventually feed the existing long-hold machinery.

My strongest recommendation:

1. Build a **Long-Term Thesis Feature Store** that begins with externally validated factors: profitability, quality, conservative investment, accrual quality, value, momentum, low-risk/safety, net issuance, buybacks, insider sponsorship, PEAD/SUE, analyst revisions, and expected growth.
2. Replicate each family locally on point-in-time data before using it in any thesis admission surface.
3. Treat technical washout, including the operator's 2W/1M MACD or StochRSI idea, as an **entry-state / candidate-sourcing family**, not proof of long-hold quality.
4. Use nontechnical signals to answer the true hold question: "Is the business repairing or compounding faster than expectations, and is the market still pricing it like a damaged asset?"
5. Keep all new families display-only / research-only until G1-Retest or a separate ratified long-hold gauntlet clears effective-n, survivorship, and program-wide FDR.

---

## 1. Current Repo Boundary

This paper assumes the following current state:

- The Long-Hold Thesis Layer is chartered, but W3/W4 selection surfaces remain locked.
- W1's fundamental missed-hold test was **deferred**, not killed and not validated. The honest OOS window had too few compounder clusters. Piotroski F and quality-like fields look promising in biased or sensitivity cells, but they have no behavioral authority.
- W2 display-only additions exist or are registered: compounder feature columns, entry/thesis clocks, moat falsifier sensors, and great-company-trap context.
- The durable-bottom / COILED program is an entry-quality program, not a long-hold admission program.
- `WASHOUT_TIMEFRAME_HYPOTHESIS.md` records the operator's 2W/1M washout idea as a possible technical long-hold feature family, but it is not currently lockable/runnable on honest monthly data without governance and sample-size resolution.

Therefore this paper proposes:

```text
not a new live signal
not a replacement for OBJECTIVE.md
not a committee surface
not a master score
```

It is a research map for what to add, what to test, and what Fable should adjudicate next.

---

## 2. External Signal Families With Institutional Or Academic Validation

This section intentionally starts with signals already validated by institutions, index providers, or major academic/quant literature. "Validated externally" does **not** mean validated for our universe, our labels, our horizons, or our entry-conditioned population. It means the family is strong enough to justify local replication.

### 2.1 Quality Minus Junk / Broad Quality Composite

**External anchor:** AQR's Quality Minus Junk research and live data library. AQR defines quality around profitability, growth, safety, and payout; QMJ goes long high-quality stocks and short low-quality stocks. AQR reports significant historical risk-adjusted returns in the U.S. and 23 other countries and updates the factor monthly. Source: [AQR QMJ dataset](https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly).

**Methodology:** create a composite of:

- Profitability: gross profits/assets, ROA, ROE, operating profitability, FCF margin.
- Growth: stable revenue/earnings/gross profit growth.
- Safety: low leverage, low earnings volatility, lower beta, lower distress risk.
- Payout/capital discipline: buybacks, dividends, low issuance, shareholder yield.

Typical process:

```text
compute raw descriptors
-> winsorize outliers
-> standardize cross-sectionally
-> combine into quality score
-> sort by quality, often size-neutralized
-> test long high-quality / short low-quality spreads
```

**Long-thesis use:** first candidate for our "business worth owning" foundation. Not sufficient alone because quality can be overpriced, crowded, or deteriorating.

**Repo implementation:** create `quality_compounder_core`:

- `gross_profit_to_assets_z`
- `roa_z`
- `roe_z`
- `fcf_margin_z`
- `revenue_growth_stability_z`
- `earnings_volatility_inv_z`
- `net_debt_to_ebitda_inv_z`
- `shareholder_yield_z`
- `quality_price_spread` = quality rank minus valuation rank

**Research test:** among tactical winners, does the composite separate `compounder` from `tactical_only` at 252d after sector-relative benchmarking?

### 2.2 MSCI Quality

**External anchor:** MSCI Quality Indexes methodology uses Return on Equity, Debt to Equity, and Earnings Variability. Source: [MSCI Quality methodology](https://www.msci.com/index/methodology/latest/Quality).

**Methodology:** compute winsorized z-scores for:

- Higher ROE is better.
- Lower debt-to-equity is better.
- Lower earnings variability is better.

Then average the available z-scores.

**Long-thesis use:** clean institutional baseline for "quality that survives." It is simpler than QMJ and easier to replicate.

**Repo implementation:** `msci_quality_proxy`:

- `roe_ttm_z`
- `debt_to_equity_inv_z`
- `earnings_variability_5y_inv_z`
- `coverage_n`
- `sector_neutral_rank`

**Research test:** compare raw cross-sectional rank vs sector-neutral rank; test both. Quality often clusters by sector, and a sector-neutral version may better identify within-industry survivors.

### 2.3 S&P Quality

**External anchor:** S&P Quality Indices select on Return on Equity, Accruals Ratio, and Financial Leverage Ratio, with semiannual rebalancing and z-score construction. Source: [S&P Quality Indices Methodology](https://www.spindices.com/documents/methodologies/methodology-sp-quality-indices.pdf).

**Methodology:** combine:

- ROE: high preferred.
- Accruals ratio: low preferred.
- Financial leverage: low preferred.

**Why it matters:** S&P explicitly includes accruals. This is important because long-term thesis traps often look profitable through accounting, but not through cash conversion.

**Repo implementation:** `sp_quality_proxy`:

- `roe_z`
- `accruals_ratio_inv_z`
- `financial_leverage_inv_z`
- `sp_quality_z`

**Research test:** compare S&P-style quality against QMJ-style quality. If both agree, candidate is "institutionally quality-confirmed." If QMJ likes a name but S&P quality rejects it due to accruals/leverage, the name should be "quality-fragile."

### 2.4 Fama-French Five-Factor Profitability And Investment

**External anchor:** Fama-French five factors include operating profitability (RMW: robust minus weak) and investment (CMA: conservative minus aggressive). The Ken French data library publishes factor construction details and current factor returns. Source: [Ken French 5-factor description](https://mba.tuck.dartmouth.edu/pages/faculty/Ken.french/Data_Library/f-f_5_factors_2x3.html).

**Methodology:** form portfolios on:

- Operating profitability.
- Investment intensity / asset growth.
- Value and size.

RMW captures robust profitability. CMA captures conservative investment versus aggressive investment.

**Long-thesis use:** a company with high profitability and conservative investment is a cleaner long-term candidate than a company buying growth through asset expansion.

**Repo implementation:** `ff5_proxy`:

- `operating_profitability_z`
- `asset_growth_inv_z`
- `investment_conservatism_z`
- `ff_rmw_cma_combo`

**Research test:** does `RMW high AND CMA high` separate durable holders from tactical-only bounces? Does aggressive investment become good only when expected growth also rises?

### 2.5 Gross Profitability

**External anchor:** Novy-Marx's gross profitability premium finds gross profits-to-assets has strong return-predictive power and complements value. Source: [Journal of Financial Economics abstract](https://ideas.repec.org/a/eee/jfinec/v108y2013i1p1-28.html).

**Methodology:** use:

```text
gross_profitability = (revenue - cost_of_goods_sold) / total_assets
```

Then rank cross-sectionally, often in combination with value.

**Long-thesis use:** gross profitability is closer to business model strength than bottom-line earnings, which can be distorted by investment, taxes, and accounting choices.

**Repo implementation:** `gross_profitability_core`:

- `gross_profit_to_assets`
- `gross_profit_to_assets_5y_median`
- `gross_profit_to_assets_stability`
- `gross_profit_to_assets_vs_sector`

**Research test:** separate gross-profitability level from gross-profitability persistence. Long-term thesis needs persistence, not just a one-year high reading.

### 2.6 Piotroski F-Score

**External anchor:** Piotroski's F-score uses accounting signals to separate winners from losers among high book-to-market stocks. Source: [Piotroski paper PDF](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf).

**Methodology:** nine binary accounting signals:

- Profitability: positive ROA, positive operating cash flow, ROA improvement, cash flow greater than net income.
- Leverage/liquidity: lower leverage, higher current ratio, no equity issuance.
- Operating efficiency: gross margin improvement, asset turnover improvement.

**Long-thesis use:** ideal for "washed-out but not broken" candidates. A cheap or washed-out name with high F-score has evidence of survival and repair.

**Repo implementation:** strengthen existing W1 usage:

- Restore coverage for interest coverage, operating income, and missing feature inputs.
- Add per-component F-score breakdown.
- Add `f_score_delta_1y`.
- Add `f_score_floor_clean`: no equity issuance, positive CFO, no leverage worsening.

**Research test:** current W1 evidence points the right way but is deferred. Keep it as the first retest-critical family, not a live admission rule.

### 2.7 Accruals And Cash-Flow Quality

**External anchor:** Sloan's accrual anomaly finds accruals negatively predict future returns; S&P also uses accruals in its Quality methodology. Source: [ScienceDirect summary of accrual anomaly literature](https://www.sciencedirect.com/science/article/abs/pii/S0304405X08002006).

**Methodology:** estimate the non-cash component of earnings. Lower accruals are better; cash-backed earnings are higher quality.

Potential definitions:

```text
balance_sheet_accruals = change in net operating assets / average total assets
cash_conversion = operating_cash_flow / net_income
fcf_conversion = free_cash_flow / net_income
```

**Long-thesis use:** protects against "quality illusion" and cheap traps.

**Repo implementation:** `earnings_quality_block`:

- `accruals_ratio`
- `cash_conversion`
- `fcf_conversion`
- `receivables_growth_minus_revenue_growth`
- `inventory_growth_minus_revenue_growth`

**Research test:** whether accrual quality is more useful as an admission positive or as a falsifier / veto.

### 2.8 Conservative Investment / Asset Growth

**External anchor:** Fama-French CMA and Cooper-Gulen-Schill asset growth literature find aggressive asset growth is often associated with weaker future returns. Source: [Asset Growth and the Cross-Section of Stock Returns](https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1609-1651.html).

**Methodology:** measure growth in total assets, capex, working capital, and external financing.

**Long-thesis use:** distinguishes "reinvestment machine" from "empire-building." Some aggressive investment is good when ROIC is high and expected growth is rising; otherwise it is dangerous.

**Repo implementation:** `investment_quality_block`:

- `asset_growth_yoy`
- `capex_to_assets`
- `capex_growth_minus_revenue_growth`
- `reinvestment_rate`
- `incremental_revenue_per_reinvestment_dollar`
- `incremental_gross_profit_per_reinvestment_dollar`

**Research test:** interaction, not raw cutoff:

```text
high investment is good only if incremental profitability and expected growth are rising
```

### 2.9 Net Share Issuance / Dilution

**External anchor:** Pontiff and Woodgate find share issuance has strong cross-sectional ability to predict returns; broader issuance literature links equity issuance and future underperformance. Source: [Share Issuance and Cross-Sectional Returns](https://ideas.repec.org/a/bla/jfinan/v63y2008i2p921-945.html).

**Methodology:** measure change in shares outstanding, net issuance, and financing mix.

**Long-thesis use:** one of the cleanest trap detectors. A washed-out company funding itself with dilution is usually not a durable long-hold unless the dilution directly finances a high-return inflection.

**Repo implementation:** `dilution_discipline_block`:

- `shares_growth_yoy`
- `shares_growth_3y`
- `sbc_to_revenue`
- `buyback_offset_ratio`
- `net_issuance_z`
- `dilution_trap_flag`

**Research test:** dilution should be mostly a negative/falsifier, not a positive signal.

### 2.10 Buybacks And Shareholder Yield

**External anchor:** open-market repurchase literature finds long-run abnormal returns after repurchase announcements in some settings, often interpreted as management signaling undervaluation. Source: [Buybacks around the world / Peyer-Vermaelen discussion](https://www.shareholderforum.com/wag/Library/20140800_Manconi-Peyer-Vermaelen.pdf).

**Methodology:** measure repurchase authorization, actual share count reduction, buyback yield, valuation context, and prior return.

**Long-thesis use:** buybacks matter only if real, value-accretive, and not financed by dangerous leverage.

**Repo implementation:** `capital_return_quality`:

- `buyback_yield`
- `net_buyback_yield_after_sbc`
- `buyback_below_normalized_valuation`
- `debt_funded_buyback_flag`
- `share_count_reduction_confirmed`

**Research test:** buyback signal should require:

```text
drawdown or valuation compression
AND real share count reduction
AND leverage not worsening materially
```

### 2.11 Momentum And Relative Strength

**External anchor:** Jegadeesh and Titman document that buying past winners and selling past losers generated significant returns over intermediate horizons. Source: [Jegadeesh-Titman PDF](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf).

**Methodology:** rank 3-12 month past returns, often skipping the most recent month, rebalance monthly.

**Long-thesis use:** not "buy extended winners." For our framework, momentum should be a repair signal:

- A washed-out stock stops underperforming.
- Stock/sector RS turns before absolute price fully recovers.
- Sector leadership confirms the business theme.

**Repo implementation:** `rs_repair_block`:

- `stock_spy_rs_slope_50d`
- `stock_sector_rs_slope_50d`
- `rs_drawdown_repair`
- `downside_capture_repair`
- `upside_capture_repair`

**Research test:** compare raw momentum vs post-washout RS repair. The long-hold framework probably wants the second.

### 2.12 Low Volatility / Betting Against Beta / Safety

**External anchor:** Frazzini and Pedersen's BAB literature and AQR BAB factor data support a low-beta / leverage-constrained investor mechanism. Source: [AQR BAB dataset](https://www.aqr.com/Insights/Datasets/Betting-Against-Beta-Equity-Factors-Monthly).

**Methodology:** estimate beta and volatility, long low-beta assets, short high-beta assets, leverage-adjusted in institutional implementations.

**Long-thesis use:** safety is not enough to find compounders, but it improves survival and holdability. A long-term thesis candidate should survive noise.

**Repo implementation:** `holdability_safety_block`:

- `beta_252d`
- `downside_beta_252d`
- `idiosyncratic_vol`
- `max_drawdown_252d`
- `funding_sensitivity`
- `credit_beta`

**Research test:** safety should be tested as a drawdown/time-underwater reducer, not only as return predictor.

### 2.13 PEAD / SUE

**External anchor:** post-earnings-announcement drift describes delayed drift in the direction of earnings surprise. Source: [open-access PEAD review](https://www.sciencedirect.com/science/article/pii/S2214635020303750).

**Methodology:** compute standardized unexpected earnings:

```text
SUE = (actual earnings - expected earnings) / historical surprise volatility
```

Then test drift after earnings announcements.

**Long-thesis use:** expectation drift is probably the highest-value bridge from tactical entry to long-hold. A bottom with positive SUE or improving post-earnings drift may be a business inflection rather than a pure bounce.

**Repo implementation:** `expectation_drift_block`:

- `sue_latest`
- `sue_streak`
- `post_earnings_drift_20d`
- `beat_and_hold_flag`
- `bad_news_absorption_flag`
- `next_revision_30d`

**Research test:** PEAD may be stronger on shorter horizons than 252d. Test as an intermediate thesis confirmation clock, not only an entry feature.

### 2.14 Analyst Revisions And Recommendation Context

**External anchor:** analyst recommendation and forecast revision literature finds recommendations add value conditionally and are entangled with quantitative characteristics. Source: [Jegadeesh, Kim, Krische, Lee paper page](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=291241).

**Methodology:** track earnings/revenue estimate revisions, recommendation changes, dispersion, and analyst quality.

**Long-thesis use:** revisions are not pure truth. They are expectation-state measurements. The best signal is not "analysts like it"; it is "expectations have stopped falling while price no longer responds badly."

**Repo implementation:** `revision_ladder`:

- `eps_revision_30d`
- `revenue_revision_30d`
- `revision_breadth`
- `revision_dispersion`
- `recommendation_delta`
- `revision_inflection_flag`

**Research test:** revisions should interact with valuation and price reaction:

```text
positive revisions after washout = confirmation
negative revisions with price resilience = expectation floor
positive revisions with price fade = crowded/overpriced warning
```

### 2.15 Insider Buying

**External anchor:** Lakonishok and Lee document insider trades and find insider purchases are more informative than insider sales, especially in smaller firms. Source: [NBER PDF](https://www.nber.org/system/files/working_papers/w6656/w6656.pdf).

**Methodology:** aggregate Form 4 open-market purchases/sales by officer/director, dollar value, cluster count, role, and recency.

**Long-thesis use:** insider buying near a washout is a high-quality sponsorship signal if it is open-market, clustered, and not token-sized.

**Repo implementation:** `insider_sponsorship_block`:

- `insider_net_buy_usd_90d`
- `insider_buyers_count_90d`
- `officer_buy_flag`
- `cluster_buy_flag`
- `first_buy_after_drawdown_flag`
- `sale_pressure_flag`

**Research test:** insider buying should be conditioned on distress and valuation:

```text
post-washout insider cluster + no dilution + no solvency stress
```

### 2.16 Institutional And Systematic Process Lessons

**BlackRock Systematic:** BlackRock describes using data and technology to evaluate thousands of securities, combining accounting measures with alternative data such as search, transaction activity, and geolocation. Source: [BlackRock systematic investing](https://www.blackrock.com/us/individual/investment-ideas/systematic-investing).

**Man AHL:** Man AHL describes scientific rigor, robust technology, diverse data, and hundreds of global markets. Source: [Man AHL](https://www.man.com/ahl).

**Translation for us:** the lesson is not "copy every alt-data feed." It is:

```text
many weak signals
standardized feature store
pre-registered tests
clear role taxonomy
risk/factor attribution
ongoing retirement/falsification
```

The Macro Dashboard version should stay file-bus/parquet native, not become a new database monolith.

---

## 3. What Needs To Be Added To The Long-Term Thesis Layer

### 3.1 Long-Term Thesis Feature Store

Add a research artifact:

```text
data/research/long_thesis_features.parquet
```

Suggested schema:

```text
ticker
asof_date
feature_family
feature_name
raw_value
sector_z
market_z
coverage
source
known_date
version
survivorship_biased
```

The feature store should initially include:

- `quality_qmj_proxy`
- `quality_msci_proxy`
- `quality_sp_proxy`
- `gross_profitability`
- `piotroski_f_components`
- `accrual_quality`
- `investment_quality`
- `net_share_issuance`
- `capital_return_quality`
- `sue_pead`
- `revision_ladder`
- `insider_sponsorship`
- `rs_repair`
- `holdability_safety`
- `valuation_implied_expectations`

### 3.2 Expectation Ledger

The current long-hold work needs a structured way to measure whether expectations are moving in our favor.

```text
data/research/expectation_ledger.parquet
```

Fields:

```text
ticker
event_date
event_type
actual_metric
expected_metric
surprise_z
price_reaction_1d
price_reaction_5d
revision_30d
revision_90d
bad_news_absorbed
good_news_failed
evidence_source
known_date
```

Core idea:

```text
business inflection + expectation underreaction = thesis fuel
```

### 3.3 Capital Allocation Ledger

Long-term compounding requires per-share value creation.

```text
data/research/capital_allocation_ledger.parquet
```

Track:

- Buybacks authorized and actually completed.
- Share count change.
- SBC dilution.
- Debt-funded repurchases.
- M&A spend and subsequent margin/revenue effect.
- Capex/R&D/reinvestment versus incremental gross profit.

Output:

```text
capital_allocation_delta = accretive | neutral | dilutive | unavailable
```

### 3.4 Business Model Ontology

The same long-hold rules cannot apply to a bank, SaaS company, semicap equipment company, biotech, retailer, and utility.

Add deterministic business-model classes:

- `asset_light_recurring`
- `network_effect_platform`
- `mission_critical_supplier`
- `cyclical_operating_leverage`
- `regulated_balance_sheet`
- `commodity_price_taker`
- `rollup_acquirer`
- `binary_event_biotech`
- `mature_cash_returner`
- `broken_growth`

This can start with GICS plus financial-shape heuristics. No LLM classification should originate the class.

### 3.5 KPI Registry

Long-term investors own businesses, not factor rows. The missing layer is company-specific KPI memory.

```text
data/research/kpi_registry.yml
```

Examples:

- Software: ARR, NRR, RPO, billings, churn, sales efficiency.
- Semis: book-to-bill, backlog, utilization, customer capex.
- Industrials: orders, backlog, pricing/cost spread.
- Retail: comps, inventory, traffic, ticket, shrink.
- Banks: NIM, deposit beta, credit losses, CET1.
- Biotech: trial stage, cash runway, dilution risk.

Start with EDGAR/8-K extraction where possible. Paid transcript features remain deferred.

### 3.6 Valuation-Implied Expectations Engine

Static value ratios are not enough. Add a "what must be true" block:

```text
market_implied_revenue_cagr
market_implied_terminal_margin
market_implied_reinvestment_rate
quality_adjusted_value_spread
growth_expectation_gap
```

The output should not be a price target. It should say:

```text
current price requires X growth and Y margin
current evidence supports / does not support that
```

### 3.7 Sponsorship And Ownership Layer

Add an ownership support layer that remains display/shadow until validated.

Potential sources:

- Insider Form 4.
- 13F smart-money adds, with 45-day lag caveat.
- Buyback execution.
- Short interest reset.
- ETF/fund-flow pressure release.

Output:

```text
sponsorship_state = none | insider | buyback | institutional | multi_support
```

No single sponsorship signal should admit a thesis by itself.

---

## 4. Proposed Long-Term Thesis Admission Funnel

This is the target system. It should not become behavioral until Fable ratifies the needed gates.

### Stage A: Candidate Source

A name can enter the long-thesis research queue from:

- Existing tactical entry / confluence signal.
- COILED / COILED-FIRE state.
- Future washout-timeframe family if admitted and runnable.
- Fundamental quality dislocation screen.
- Sponsorship event after large drawdown.
- Expectation inflection after a prolonged selloff.

### Stage B: Minimum Survival Gate

The name is not thesis-eligible if:

- severe dilution is ongoing,
- solvency is deteriorating,
- interest coverage is missing or weak where required,
- cash flow is persistently negative without financing runway,
- accounting-quality flags are severe,
- moat falsifiers are firing in multiple dimensions.

Initial positive tests:

```text
Piotroski F >= 6 or improving
cash flow positive or improving
no aggressive share issuance
leverage not worsening
no major accrual/receivables/inventory warning
```

### Stage C: Quality And Reinvestment

Score only as display:

```text
QMJ proxy
MSCI quality proxy
S&P quality proxy
gross profitability persistence
ROIC / incremental ROIC proxy
asset-light scaling
reinvestment efficiency
```

Key distinction:

```text
high ROIC without reinvestment runway = good company, maybe not compounder
high reinvestment without ROIC = empire-building trap
high ROIC + reinvestment + expectation gap = thesis candidate
```

### Stage D: Expectation Drift

Evidence that expectations are too low:

- Positive SUE.
- Bad news stops making new lows.
- Estimate cuts slow.
- Revisions turn up.
- Beat-and-raise after washout.
- Good news holds instead of fading.

This stage is likely the best bridge between bottom signal and long-term thesis.

### Stage E: Sponsorship

Evidence that better owners are taking the other side:

- Cluster insider buying.
- Real buyback execution below normalized valuation.
- 13F adds by quality institutions.
- Short interest stops rising or begins covering.
- Sector/subsector sponsorship turns up.

### Stage F: Valuation-Implied Expectations

Question:

```text
is the repaired business already priced?
```

Pass examples:

- Quality high, valuation low versus history and peers.
- Growth implied by EV/sales is below plausible KPI trajectory.
- Margin implied by price is below normalized margin and moat falsifiers are clean.

Fail examples:

- Great company, but implied growth requires heroic assumptions.
- Multiple already expanded while fundamentals only stabilized.
- Crowding high and revisions no longer improving.

### Stage G: Thesis State

Possible display states:

```text
not_eligible
watch_for_thesis
thesis_candidate_shadow
active_thesis_shadow
challenged
falsified
```

Until Fable ratifies W3/W4, the system should stop at `thesis_candidate_shadow`.

---

## 5. First-Principles Novel Signal Families To Research

This section goes beyond externally validated factors. These are hypotheses to test, not claims.

### 5.1 Washed-Out But Not Broken

**Mechanism:** price is damaged by forced selling, style unwind, sector drawdown, or temporary disappointment, but the business still has intact economics.

**Signal:**

```text
2W/1M washout or COILED candidate
AND no moat-falsifier fire
AND no dilution trap
AND cash conversion intact
AND sector cohort washout present
```

**Expected edge:** better long-hold survival than raw technical bottoms.

**Data needed:** price/technicals, EDGAR statements, moat falsifiers, share count, sector cohort state.

### 5.2 Repair Before Reprice

**Mechanism:** fundamentals turn before valuation multiple recovers.

**Signal:**

```text
gross margin or revenue stabilizes
AND revisions stop falling
AND EV/sales or P/FCF remains in low historical percentile
AND price still below long-term moving average or prior breakdown level
```

**Expected edge:** long-hold candidates with asymmetric upside.

### 5.3 Bad-News Absorption

**Mechanism:** when the market stops punishing bad news, expectations may already be washed out.

**Signal:**

```text
negative earnings/revision/news event
AND stock does not make a new 63d low
AND stock outperforms sector over next 5d
```

**Expected edge:** identifies expectation floors.

### 5.4 Good-News Hold

**Mechanism:** genuine thesis repair appears when good news is not faded.

**Signal:**

```text
positive SUE or guidance
AND 1d gap or rally
AND closes above event VWAP / gap midpoint after 5-10d
AND revisions continue improving
```

**Expected edge:** differentiates real business inflection from one-day short cover.

### 5.5 Downside Beta Collapse

**Mechanism:** ownership changes when a stock stops participating in sector downside but still participates in upside.

**Signal:**

```text
downside beta to sector falls over 60d
AND upside capture rises
AND relative strength slope turns positive
```

**Expected edge:** early sponsorship/accumulation proxy.

### 5.6 Sponsorship Stack

**Mechanism:** multiple marginal buyers with different motivations create durable support.

**Signal:**

```text
insider buy
OR real buyback
OR 13F quality-owner add
OR short-interest reset
```

Upgrade only when at least two independent legs fire within a post-washout window.

### 5.7 Capital Allocation Inflection

**Mechanism:** a company moves from value destruction to per-share value creation.

**Signal:**

```text
share count stops rising
AND buybacks begin or SBC is offset
AND capex/R&D productivity improves
AND leverage does not worsen
```

**Expected edge:** especially useful in software, industrials, cyclicals, and post-bubble growth names.

### 5.8 Competitive Capacity Withdrawal

**Mechanism:** industry supply exits, allowing survivors to recover margin.

**Signal:**

```text
sector drawdown severe
AND weaker peers cut capex / exit capacity / restructure
AND candidate balance sheet survives
AND pricing or gross margin stops falling
```

**Expected edge:** durable bottoms in cyclicals and commodity-adjacent industries.

### 5.9 Theme-To-Cashflow Conversion

**Mechanism:** narratives become investable only when company KPIs convert the theme into revenue, margin, backlog, or cash flow.

**Signal:**

```text
theme momentum high or recovering
AND company-specific KPI improves
AND revenue exposure to theme is direct
AND valuation-implied growth not excessive
```

**Expected edge:** separates real beneficiaries from narrative-only stocks.

### 5.10 KPI Inflection By Business Model

**Mechanism:** each business model has a different truth variable.

Examples:

- Software: RPO/billings/NRR improves while sales efficiency stabilizes.
- Semicap: book-to-bill/backlog turns before revenue.
- Retail: inventory clears before comps recover.
- Banks: deposit beta/NIM/credit losses stabilize before earnings.
- Industrials: orders/backlog bottom before margins.

**Signal:** business-model-specific KPI derivative turns positive after price washout.

### 5.11 Duration Arbitrage

**Mechanism:** near-term earnings are depressed, but long-term value drivers improve.

**Signal:**

```text
next-quarter EPS revisions negative
BUT long-duration KPI improving
AND price no longer reacts badly
AND balance sheet supports waiting
```

**Expected edge:** this is a true long-hold signal, not a tactical bounce signal.

### 5.12 Quality Detox

**Mechanism:** a high-quality company was over-owned and de-rated; after crowding clears, the same quality becomes attractive again.

**Signal:**

```text
quality high
AND crowding / valuation premium compressed
AND moat falsifiers clean
AND RS repair begins
```

**Expected edge:** avoids buying quality at the wrong price.

### 5.13 Founder / Operator Recoupling

**Mechanism:** owner-operators buying after a large drawdown can mark real confidence, especially if capital allocation is improving.

**Signal:**

```text
founder/operator open-market purchase
AND drawdown > threshold
AND no solvency/dilution stress
AND business KPI stable or improving
```

**Expected edge:** best in smaller/mid-cap names; less useful for mega-caps with token purchases.

### 5.14 Sector Denominator Collapse

**Mechanism:** a company's absolute growth may look mediocre, but peers are collapsing faster. That can indicate share gain.

**Signal:**

```text
company revenue growth >= 0 or improving
AND sector median revenue growth falling
AND margins not sacrificed
AND RS repair vs sector
```

**Expected edge:** identifies survivors in sector washouts.

### 5.15 Thesis Contradiction Detector

**Mechanism:** many "long-term winners" are only multiple expansion.

**Signal:**

```text
price up strongly after entry
BUT revenue/margin/ROIC/revisions do not improve
```

Output:

```text
multiple_expansion_only
```

**Expected use:** prevents the system from mislabeling a lucky rerating as a thesis success.

---

## 6. Research Methodology For Fable

### 6.1 Data Discipline

Every feature must carry:

- point-in-time known date,
- source,
- coverage,
- survivorship stamp,
- family id,
- version,
- horizon role.

No feature can be admitted without a coverage table.

### 6.2 Outcome Labels

Use existing long-hold labels as the primary ruler:

- `compounder`
- `multiple_expansion_only`
- `sector_laggard_winner`
- `cheap_trap`
- `tactical_only`
- `missed_hold` as derived contrast.

Also add richer thesis diagnostics:

- 252d and 504d total return.
- Sector-relative return.
- Fundamental-forward improvement.
- Max drawdown after entry.
- Time underwater.
- Valuation multiple change versus fundamental change.

### 6.3 Testing Structure

For each family:

```text
register feature list
register expected signs
define coverage/drop rules
freeze transformation
compute PIT features
test against labels
run name x regime clustered inference
apply program-wide FDR
print nulls
```

### 6.4 Comparisons To Run

For every feature family:

1. Raw market-rank version.
2. Sector-neutral version.
3. Entry-conditioned version: only existing tactical fires.
4. Universe washout version: all stocks in severe drawdown, independent of entry stack.
5. Interaction with technical bottom state.
6. Interaction with valuation.
7. Interaction with sponsorship.

### 6.5 Metrics

Primary:

- separation of `compounder` vs `tactical_only`;
- 252d sector-relative return;
- hit rate of top tercile vs bottom tercile;
- cheap-trap avoidance;
- time-underwater reduction.

Secondary:

- 126d repair;
- 504d caveated read;
- max drawdown;
- multiple-expansion-only rate.

### 6.6 Promotion Logic

Suggested authority ladder:

```text
research_only
-> display_shadow
-> thesis_candidate_shadow
-> committee_context
-> behavioral only after separate ratification
```

No signal from this paper should skip directly to board ranking or push surfaces.

---

## 7. Prioritized Build Plan

### Wave LT-0: External Factor Replication Pack

Build a single script:

```text
scripts/research/long_thesis_feature_pack.py
```

Outputs:

```text
data/research/long_thesis_features.parquet
data/research/long_thesis_features_manifest.json
research/long_hold/LT_FEATURE_PACK_REPORT.md
```

Families:

- QMJ proxy.
- MSCI quality proxy.
- S&P quality proxy.
- FF5 RMW/CMA proxy.
- Gross profitability.
- Piotroski components.
- Accrual quality.
- Asset growth / investment quality.
- Net issuance.
- Shareholder yield.
- SUE/PEAD.
- Insider sponsorship.
- RS repair.

### Wave LT-1: Local Replication Study

Goal: prove which externally validated families work on our data and labels.

Output:

```text
research/long_hold/LT_EXTERNAL_FACTOR_REPLICATION.md
```

Must include:

- coverage;
- PIT audit;
- family-by-family result;
- nulls;
- multiple-testing correction;
- biased vs honest cohort separation.

### Wave LT-2: Admission Funnel Shadow Prototype

Build a display-only candidate funnel:

```text
not_eligible
watch_for_thesis
thesis_candidate_shadow
```

This is not W3/W4 activation. It is a research artifact to inspect how many names would pass.

### Wave LT-3: Expectation And Sponsorship Lanes

Add:

- `expectation_ledger`;
- `capital_allocation_ledger`;
- `insider_sponsorship_block`;
- `buyback_execution_block`;
- `revision_ladder`.

### Wave LT-4: First-Principles Hypothesis Pack

Register a finite roster of novel families:

- washed-out but not broken;
- repair before reprice;
- bad-news absorption;
- good-news hold;
- downside beta collapse;
- quality detox;
- KPI inflection;
- sponsorship stack;
- capital allocation inflection;
- theme-to-cashflow conversion.

### Wave LT-5: Fable Adjudication

Fable decides:

- which families join the G1-Retest roster;
- how to apply program-wide FDR across W1 fundamental, washout-timeframe, and new families;
- whether any family can be tested on a broader washout universe rather than only entry fires;
- what sample-size gates are needed for thesis-candidate display.

---

## 8. Recommended First Starting Set

If we only start with the highest-signal, lowest-regret families, use this order:

1. **Piotroski F-score and components** - already central to W1 and promising, but coverage needs repair.
2. **S&P quality proxy** - ROE + accruals + leverage is clean, institutional, and implementable.
3. **QMJ proxy** - broader quality/safety/payout/growth model.
4. **Gross profitability persistence** - simple, powerful, business-model grounded.
5. **Net share issuance / dilution** - likely best cheap-trap veto.
6. **Accrual and cash-conversion quality** - protects against accounting traps.
7. **Investment quality / asset growth** - separates reinvestment from empire building.
8. **SUE / PEAD / bad-news absorption** - best expectation-drift bridge.
9. **RS repair after washout** - technical confirmation without pretending price is thesis.
10. **Insider buying and buyback execution** - sponsorship overlay, not standalone alpha.
11. **Valuation-implied expectations** - prevents buying great companies at solved prices.
12. **Moat falsifier clean state** - thesis maintenance and de-escalation.

This starting set is enough to build a serious first long-thesis research database without paid data.

---

## 9. Specific Recommendations To Fable

### R1. Ratify An External-Factor Replication Wave

The long-hold program needs an externally validated baseline before novel ideas proliferate. Ratify a finite `long_hold.external_foundation` roster and attach it to program-wide FDR.

### R2. Keep Technical Washout In A Separate Family

The operator's 2W/1M washout idea is worth preserving, but it should stay in `long_hold.washout_tf` or an adjacent technical family. It should not be mixed into the fundamental family.

### R3. Require A "No Broken Business" Gate For Technical Bottoms

Any long-term thesis candidate sourced from COILED or washout should require:

```text
no severe dilution
no severe accrual warning
no solvency deterioration
no multi-sensor moat-falsifier fire
```

This is a safety gate, not alpha.

### R4. Make Expectation Drift The First Novel Research Priority

The most likely missing edge is not another quality ratio. It is:

```text
business repair + expectation underreaction
```

Prioritize SUE, revisions, bad-news absorption, good-news hold, and event VWAP behavior.

### R5. Build Falsifiers Before Admission Authority

A long-hold system that can only add conviction is dangerous. Every thesis candidate needs falsifiers:

- margin compression despite revenue growth;
- receivables stretch;
- inventory build;
- capital intensity rising;
- dilution;
- revision deterioration;
- good-news failure;
- valuation solved.

### R6. Keep The First Output As A Research Database

The immediate product should be:

```text
per-name long-thesis feature profile
```

not:

```text
buy this for long term
```

### R7. Do Not Let Survivor-Only Results Promote

Any pre-2021 survivor-only positive result in deep washout, quality, or sponsorship families should be treated as direction-finding only. Dead companies are exactly where cheap traps live.

---

## 10. Final Model

The best Long-Term Thesis framework is a **multi-evidence thesis candidate engine**:

```text
Technical candidate:
  washed out, repairing, not chased

Business survival:
  cash flow, leverage, dilution, accounting quality

Business quality:
  profitability, gross profitability, ROIC proxy, margin stability

Reinvestment:
  incremental returns, asset growth discipline, runway

Expectations:
  SUE, revisions, price reaction, bad-news absorption

Sponsorship:
  insiders, buybacks, patient owners, short reset

Valuation:
  implied growth/margins versus evidence

Falsifiers:
  moat decay, capital intensity, working capital stress, good-news failure
```

The strongest possible beginning is not novel. It is to replicate the institutional foundations honestly, then use first-principles signals to find the interaction they miss:

```text
quality + repair + expectations + sponsorship + price dislocation
```

That is the long-term thesis sweet spot.

---

## 11. Source Map

External anchors used for this paper:

- AQR, Quality Minus Junk dataset and methodology summary: https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly
- AQR, Betting Against Beta dataset: https://www.aqr.com/Insights/Datasets/Betting-Against-Beta-Equity-Factors-Monthly
- BlackRock, systematic investing overview: https://www.blackrock.com/us/individual/investment-ideas/systematic-investing
- Man AHL overview: https://www.man.com/ahl
- Ken French Data Library, Fama-French 5 factors: https://mba.tuck.dartmouth.edu/pages/faculty/Ken.french/Data_Library/f-f_5_factors_2x3.html
- MSCI Quality methodology: https://www.msci.com/index/methodology/latest/Quality
- S&P Quality Indices methodology: https://www.spindices.com/documents/methodologies/methodology-sp-quality-indices.pdf
- Piotroski F-score paper: https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf
- Novy-Marx gross profitability reference: https://ideas.repec.org/a/eee/jfinec/v108y2013i1p1-28.html
- Hou, Mo, Xue, Zhang q5 expected growth reference: https://ideas.repec.org/a/oup/revfin/v25y2021i1p1-41..html
- Sloan/accrual anomaly literature summary: https://www.sciencedirect.com/science/article/abs/pii/S0304405X08002006
- Asset growth anomaly reference: https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1609-1651.html
- Pontiff-Woodgate share issuance reference: https://ideas.repec.org/a/bla/jfinan/v63y2008i2p921-945.html
- Jegadeesh-Titman momentum paper PDF: https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
- PEAD review: https://www.sciencedirect.com/science/article/pii/S2214635020303750
- Analyst recommendations / revisions reference: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=291241
- Insider trading reference: https://www.nber.org/system/files/working_papers/w6656/w6656.pdf
- Buyback literature reference: https://www.shareholderforum.com/wag/Library/20140800_Manconi-Peyer-Vermaelen.pdf

