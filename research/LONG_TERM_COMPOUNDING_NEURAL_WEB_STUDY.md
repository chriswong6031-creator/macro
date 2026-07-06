# Long-Term Compounding Signals for Neural Web

**Prepared:** 2026-07-05  
**Scope:** A gap-focused research study on whether Neural Web should investigate medium-to-long-term stock holding strategies, what signals and infrastructure would be required, what institutions and top long-term investors use, and what is net-new versus already built in this repo.  
**Not investment advice:** This is a system architecture and research roadmap, not a recommendation to buy or sell securities.

---

## 0. Executive Answer

Yes, it is worth investigating medium-to-long-term holding strategies, but only if Neural Web treats them as a different species from entry/reversal signals.

The current entry work asks:

```text
Is this name in a favorable tactical state now?
```

Long-term hold selection asks:

```text
Is this company likely to compound intrinsic value faster than expectations,
and can we identify that before the market fully prices it?
```

That is much harder. A bottom/reversal signal can win with path mechanics: washout, repair, RS improvement, forced-covering, dealer flow, sector rotation, and anti-chase location. A long-term hold signal needs business truth: durability of returns on capital, reinvestment runway, pricing power, balance sheet survivability, management capital allocation, competitive advantage, expectation drift, valuation-implied assumptions, and portfolio-level patience.

The core Neural Web upgrade should be a **Long-Term Thesis Layer**:

```text
buy-entry signal
  -> thesis admission test
  -> business-quality and reinvestment evidence
  -> expectation-drift evidence
  -> valuation-implied-expectations test
  -> ownership/sponsorship and portfolio-fit context
  -> hold/trim/watch/falsify ledger
  -> quarterly thesis refresh
```

In plain English: the buy signal gets us in the neighborhood. The long-term layer decides whether the house is worth owning.

---

## 1. Do Not Re-Suggest: Already Built or Already Chartered

This report intentionally avoids re-proposing the current Neural Web meta-layer or the recent quant-synthesis program.

Already present or documented in the repo:

- Neural Web registry, envelopes, world state, spine federation, kernel, confluence graph, constitution, cortex, hypothesis metabolism, committee view, and Ask-the-Brain in `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`.
- Entry Intelligence, durable-bottom, bottom sensors, COILED/RS repair, anti-chase, confluence tiers, and delayed-fill/staleness research in the entry and durable-bottom docs.
- Signal Commons role taxonomy, event priors, PIT tape rolling, falsifier passthrough, and half-life direction.
- Factor Intelligence as a diagnostic/de-escalation layer, with factor DNA, style regime, attribution, twin/residual concepts, and strict "not a selection engine" law.
- Ownership pressure, 13F/13D/13G context, ETF/fund-flow pressure, short-interest context, options/GEX/skew/IV spread, event calendar, crowding, analogues, falsifiers, retirement state machines, and alpha grammar/overlap map are listed as built, registered, parked, or duplicate in `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`.
- Stock fundamentals already include profitability/value/quality factors, SUE, insider flow, analyst revision blocks, archetypes, accounting-quality read, leverage ratios, dilution flags, earnings panels, forward valuation snapshots, and per-stock panels.

So the gap is not "add quality factor" or "add ownership." The gap is:

1. A **long-horizon objective function**.
2. A **business model and moat feature store**.
3. A **thesis ledger** that tracks why a name deserves to remain held.
4. A **valuation-implied-expectations engine**, not just valuation ratios.
5. A **reinvestment runway and capital allocation engine**.
6. A **moat decay and expectation-break detector**.
7. A **hold-quality evaluation harness** with 6-month, 12-month, 24-month, and 36-month labels.

---

## 2. How the Two Attached Brainstorms Were Integrated

I read both attached files:

- `/Users/chriswong/Downloads/neural_web_semi_intelligent_quant_lab_architecture.md`
- `/Users/chriswong/Downloads/neural_web_advanced_institutional_signal_architecture.md`

What I adopted:

- The "research operating system" framing: observation -> feature -> signal -> confluence -> hypothesis -> validation -> decision -> outcome -> memory.
- The insistence on signal ontology, feature stores, event streams, entity graphs, hypothesis memory, and signal independence.
- The state-vector idea, especially market/theme/ticker/portfolio/signal state vectors.
- The better institutional questions: freshness, independence, regime validity, priced-in risk, marginal buyer quality, executable edge, portfolio overlap, and falsifiers.
- The event/base-rate and good-news-failure / bad-news-resilience ideas.
- The earnings-call language delta, accounting-quality, analyst-behavior, and supply/capacity ideas as useful extensions.

What I changed:

- I narrowed the architecture to **long-term hold intelligence**, because the repo already built most of the generic Neural Web operating system.
- I replaced generic "signal OS" build items with a `Long-Term Thesis Layer`, `Compounder Feature Store`, `Business Model Ontology`, `Valuation-Implied Expectations`, and `Thesis Ledger`.
- I turned "moat" from a label into falsifiable claims. Neural Web should not say "this company has a moat"; it should track the evidence that would prove or disprove pricing power, switching cost, scale economics, network effect, or intangible advantage.
- I separated the **reason for buying** from the **reason for holding**, with different clocks and different evidence.

What I rejected or avoided:

- Rebuilding the whole signal operating system with Postgres/Kafka/Feast-style architecture. Repo law favors the existing parquet/R2/synapse/file-bus pattern unless scale forces a change.
- Fused master scores that create escalation from many unproven ingredients.
- LLM-originated signals, trades, sizing, or ranking.
- Re-proposing ownership pressure, short-interest, options panic, event calendars, analogues, crowding, and alpha grammar as missing, because they are already built, parked, or explicitly duplicate in the current repo docs.

---

## 3. Why Long-Term Holds Are a Different Signal Species

A tactical reversal can succeed if the market stops getting worse. A compounder must keep getting better.

The durable-hold candidate needs four distinct truths:

| Layer | Tactical bottom question | Long-term hold question |
|---|---|---|
| Price/path | Is the stock washed out and repairing? | Is the entry price reasonable relative to multi-year value creation? |
| Business | Can the company survive the drawdown? | Can the company reinvest at high returns for years? |
| Expectations | Is bad news priced? | Are market expectations still too low for future economics? |
| Ownership | Are forced sellers exhausted? | Is patient sponsorship building without crowding killing future returns? |
| Portfolio | Can this trade bounce? | Can we hold this through noise without hidden factor/theme duplication? |

For Neural Web, the key design rule should be:

```text
Entry signals can admit candidates.
Long-term thesis signals decide whether a candidate graduates into a hold book.
```

Do not force one score to do both jobs.

---

## 4. What Institutions and Elite Investors Use

### 4.1 Systematic Institutions

Public materials from BlackRock Systematic, Man AHL, Two Sigma, Cubist, Citadel, MSCI/Barra, and Microsoft Qlib point to a common operating model:

- Many signals, not one magic signal.
- Traditional and alternative data.
- Rigorous testing and research memory.
- Risk models and factor exposure control.
- Portfolio construction and unintended-exposure management.
- Signal decay, regime shift, and model governance.
- Data infrastructure that converts messy observations into reusable features.

Useful external anchors:

- BlackRock Systematic describes combining big data, data science, and human expertise, and says its systematic process scores thousands of securities using company fundamentals, market sentiment, macro themes, and alternative data such as search, transaction, and geolocation data. It also reports 300+ unstructured data sources and 1,000+ alpha signals as of 2025.
- Man AHL describes scientific rigor, robust technology, diverse data, hundreds of markets, thousands of daily trading signals, execution streamlining, diversification, efficiency, and risk control.
- Two Sigma publicly emphasizes financial sciences, large-scale data, rigorous inquiry, data analysis, invention, and thousands of data sources.
- Cubist says its systematic strategies are based on rigorous research and broad public data access.
- Citadel's Data Strategies Group describes alternative data, AI/ML research, noisy high-dimensional data, signal validation, and integration into systematic and discretionary strategies.
- Microsoft Qlib is useful as an open-source infrastructure benchmark: data processing, model training, backtesting, alpha seeking, risk modeling, portfolio optimization, and order execution.
- MSCI Barra is the risk-control benchmark: factor exposure, attribution, unintended bets, concentration, crowding, shocks, and regime shifts.

Translation for us:

```text
Neural Web does not need to copy their scale.
It needs to copy their operating discipline and choose a narrower moat:
structured long-horizon company truth + thesis memory + expectation-drift detection.
```

### 4.2 Top Long-Term Investors

Elite long-term investors ask a different set of questions than short-horizon quant desks:

- Buffett/AQR "Buffett's Alpha": cheap, safe, high-quality stocks, patience, and survival through large drawdowns.
- Fundsmith: buy and hold, high-quality businesses, intangible assets hard to replicate, no leverage dependency, growth potential, and avoidance of "greater fool" buying.
- Nick Sleep/Nomad style: scale economics shared, customer reciprocity, self-reinforcing advantages, and business-model flywheels that are hard to see in simple margin screens.
- Quality/moat research from S&P and Morgan Stanley: sustained ROIC, sustained gross margins, high market share, and the difficulty of maintaining value creation because high returns attract competition.
- Academic factor work: profitability and investment from Fama-French, gross profitability from Novy-Marx, QMJ quality from AQR, PEAD/SUE, analyst revisions, accruals/accounting quality, and conservative investment.

Translation for Neural Web:

```text
The long-term signal is not "high ROIC."
It is "high ROIC that persists, reinvests, is not overpaid for, and is not being competed away."
```

---

## 5. The Missing Signal Families

### 5.1 Compounder Admission Test

Purpose: decide whether a normal buy-entry signal is eligible for long-term thesis tracking.

Inputs:

- Entry state from existing bottom/entry/confluence machinery.
- Fundamental survival from existing leverage/accounting/dilution fields.
- Liquidity/capacity and event fragility from existing systems.
- Existing factor DNA and style regime.
- Initial expectation drift: SUE, analyst revision, guidance/event response.

Output:

```text
not_eligible
watch_for_thesis
thesis_candidate
temporary_trade_only
```

This must not rank the board. It only opens a thesis file for candidates with enough evidence to study over longer horizons.

### 5.2 Persistence of High Returns on Capital

Already partially covered by factor quality/profitability. Missing is persistence, not level.

New features:

- `roic_5y_median`
- `roic_5y_stability`
- `roic_vs_wacc_spread_proxy`
- `incremental_roic_3y`
- `gross_margin_5y_stability`
- `gross_profit_to_assets_trend`
- `cash_roic_proxy`
- `roic_decay_rate`
- `competition_reversion_risk`

Why it matters: high returns attract capital. The edge is finding names where returns stay high despite competition.

Implementation note: start with EDGAR statements and existing fundamentals. Use proxies where true invested capital is incomplete, but stamp coverage and caveats. Financials need a separate taxonomy.

### 5.3 Reinvestment Runway

A company compounds only if it can reinvest at attractive returns.

Signals:

- `reinvestment_rate`: capex + R&D + acquisition spend + working-capital investment versus owner earnings.
- `incremental_revenue_per_reinvestment_dollar`.
- `organic_growth_quality`: revenue growth not driven by share issuance or serial acquisitions.
- `asset_light_scaling`: revenue growth faster than tangible capital growth.
- `market_share_delta`: company revenue growth versus industry/peer growth.
- `runway_saturation`: growth slowing as the company matures.
- `unit_economics_improving`: gross margin and sales efficiency improving while revenue grows.

Current system has fundamental snapshots and some growth/archetype fields. It does not yet model the **reinvestment machine**.

### 5.4 Moat and Business-Model Flywheel

This is the hardest and most interesting layer.

Signals:

- Pricing power: gross margin level, stability, and expansion during input-cost pressure.
- Switching costs: low churn proxies, recurring revenue, deferred revenue/RPO/backlog, installed-base service revenue.
- Network effects: user/customer ecosystem growth, platform take-rate stability, third-party developer/supplier/customer graph where available.
- Scale economies shared: revenue per employee, fulfillment/opex leverage, gross margin deliberately low but asset turnover and customer value improving.
- Brand/intangible strength: advertising/R&D efficiency, intangible investment persistence, brand demand proxies where available.
- Competitive gap: market share gains while margins hold, or lower price with equal/better returns on capital.
- Moat decay: margin compression, share loss, CAC/revenue deterioration, R&D productivity decline, customer concentration risk, rising capital intensity.

Novel Neural Web idea:

```text
Do not label a moat directly.
Build "moat falsifier sensors."
```

Example:

```text
Thesis: pricing power.
Falsifiers: gross margin falls despite revenue growth; price increases fail to protect margin;
receivables stretch; inventory builds; competitor revenue accelerates faster.
```

The system should learn which moat claims survive, not pretend to know the moat on day one.

### 5.5 Expectation Drift and Revision Ladder

This is likely the highest-ROI bridge between tactical entry and long-term holds.

Signals:

- SUE and PEAD context already exists.
- Analyst revision delta exists, but revenue-revision direction and per-analyst accuracy are currently data-blocked/paid-data watchlist.
- Guidance language delta from 8-Ks and earnings releases.
- Beat-and-raise versus beat-and-fade memory.
- Earnings call KPI extraction: bookings, RPO, backlog, same-store sales, churn, net retention, pricing, volumes, unit shipments, capex plans.
- Negative-expectation resilience: bad news but stock rises, estimate floor forms.
- Good-news failure: beat but stock fades, expectations too high.

New infrastructure:

```text
expectation_ledger:
  ticker
  as_of
  fiscal_period
  actual_growth
  consensus_growth_proxy
  revision_delta
  guidance_delta
  price_reaction
  next_revision_30d
  next_revision_90d
  evidence_source
```

The long-term hold edge often comes when business evidence improves before consensus has caught up.

### 5.6 Valuation-Implied Expectations

Static valuation ratios are not enough. A long-term hold engine needs to ask:

```text
What growth, margin, and reinvestment assumptions are already priced?
```

Signals:

- Reverse DCF / reverse owner-earnings model.
- Implied revenue CAGR from current EV/sales and margin assumptions.
- Implied terminal margin versus historical/peer range.
- FCF yield plus reinvestment runway.
- PEG-like growth-adjusted valuation, but sector- and margin-aware.
- Quality-at-a-reasonable-price spread: quality percentile minus valuation percentile.
- Valuation support near entry: is the tactical buy merely cheap because fundamentals are breaking, or cheap versus conservative forward value?

Output should be a "what must be true" block, not a price target.

Example:

```text
Market-implied case: 12% revenue CAGR, 24% terminal EBIT margin, reinvestment rate 35%.
Neural Web evidence: current demand and margins support 10-13% CAGR, but reinvestment efficiency is falling.
Verdict: thesis watch, not high-conviction hold.
```

### 5.7 Capital Allocation and Management Quality

Top long-term investors care about how management redeploys cash.

Signals:

- Buybacks done below/above intrinsic-value proxy.
- Share count reduction versus SBC dilution.
- M&A frequency and post-deal ROIC/revenue/margin performance.
- Debt issuance used for productive investment versus buybacks at high valuation.
- Dividend/buyback consistency without starving reinvestment.
- Founder/operator ownership and insider open-market buying already partly available, but should be interpreted as capital-allocation context.
- Governance red flags: serial dilution, aggressive adjusted EBITDA, recurring restructuring, acquisition accounting, high SBC without offsetting repurchases.

New concept:

```text
capital_allocation_delta:
  did management's last 3 capital decisions increase per-share value?
```

This is more durable than one quarter's EPS beat.

### 5.8 Company-Specific KPI and Unit-Economics Memory

Institutions and fundamental PMs know each company by its actual operating KPIs. Neural Web mostly knows tickers through generalized signal families.

Build:

```text
kpi_registry:
  ticker
  sector
  kpi_name
  direction_good
  source_pattern
  extraction_source
  unit
  cadence
  evidence_quality
```

Examples:

- Semis: backlog, book-to-bill, utilization, gross margin, customer capex.
- Software: ARR, NRR, billings, RPO, seat growth, churn, sales efficiency, SBC.
- Retail: comps, traffic, ticket, inventory, shrink, gross margin.
- Industrials: orders, backlog, pricing/cost spread, book-to-bill.
- Banks: deposit beta, NIM, credit losses, CET1.
- Biotech: trial stage, cash runway, dilution risk.

This turns Neural Web from "stock chart plus factors" into "business model observer."

### 5.9 Theme-to-Company Causality Graph

Oracle and theme/sector systems are already strong. The missing long-term question is:

```text
Which company actually converts the theme into cash flow?
```

Signals:

- Theme demand driver -> customer capex -> supplier revenue.
- Direct beneficiary versus derivative beneficiary.
- Revenue exposure to theme.
- Margin sensitivity to theme.
- Lag time from theme event to company fundamentals.
- Substitution risk: is the company a bottleneck, commodity supplier, or replaceable participant?
- Theme saturation: when narrative momentum is strong but incremental fundamental evidence is slowing.

Output:

```text
theme_cashflow_transmission:
  direct
  delayed
  derivative
  crowded
  narrative_only
```

This is a cleaner use of Neural Web than simply boosting every AI/semis name when the theme is hot.

### 5.10 Thesis Ledger and Hold Maintenance

This is the most important infrastructure gap.

Every long-term candidate needs a machine-readable thesis:

```yaml
thesis_id: lth_NVDA_2026Q3_001
ticker: NVDA
admitted_from: entry_signal_id
as_of: 2026-07-05
thesis_type: quality_compounder | turnaround_compounder | reinvestment_runway | mispriced_growth | special_situation_to_hold
horizon: 12m | 24m | 36m
core_claims:
  - revenue growth remains above peer median
  - gross margin does not structurally erode
  - reinvestment efficiency remains positive
  - expectations still rising after entry
falsifiers:
  - two-quarter gross margin compression not explained by mix
  - revenue guide-down without valuation reset
  - share count dilution > threshold
  - factor/theme crowding unwind with no idiosyncratic repair
milestones:
  - next earnings
  - next 10-Q
  - next analyst revision window
  - next thesis review date
status: watch | active_thesis | challenged | falsified | graduated
```

This lets Neural Web answer:

- Why do we still own it?
- What would change our mind?
- Is the reason for holding different from the reason for buying?
- Has the thesis improved, decayed, or merely survived?
- Are we confusing price confirmation with thesis confirmation?

---

## 6. Infrastructure We Need

### 6.1 Long-Horizon Outcome Store

Current entry/backtest horizons are mostly short and medium term. The long-hold system needs:

- 126d, 252d, 504d, and 756d forward returns.
- Max drawdown, time under water, recovery time, and stop-out path.
- Benchmark-relative and sector-relative returns.
- Fundamental-forward outcomes: revenue growth, margin change, revision change, share count change, ROIC change, bankruptcy/dilution.
- Thesis outcome labels:
  - `compounder`: price up and fundamentals improved.
  - `multiple_expansion_only`: price up but business evidence did not improve.
  - `cheap_trap`: valuation looked attractive but fundamentals worsened.
  - `quality_but_overpriced`: business held up but returns disappointed.
  - `tactical_only`: short bounce worked, long thesis failed.
  - `missed_hold`: entry looked tactical but became durable.

This is the scoreboard. Without it, every long-term discussion will become narrative.

### 6.2 Point-in-Time Fundamental Feature Store

Current EDGAR/factor infrastructure is a strong base. Long-term research needs an explicit PIT company feature store:

```text
data/company_features/pit_company_features.parquet
```

Keys:

```text
ticker, fiscal_period, filing_date, first_seen, as_of, feature_name,
raw_value, normalized_value, coverage, source, version
```

Feature groups:

- Profitability and margins.
- ROIC/incremental ROIC proxies.
- Reinvestment and asset growth.
- FCF conversion and accruals.
- Share count, SBC, buybacks, dilution.
- Debt, interest coverage, refinancing wall.
- Growth quality.
- KPI extraction.
- Business-model classification.
- Intangible-adjusted capital.

### 6.3 Business Model Ontology

Neural Web needs business-model classes distinct from factor DNA.

Examples:

- `asset_light_recurring`
- `scale_economics_shared`
- `network_effect_platform`
- `mission_critical_supplier`
- `commodity_price_taker`
- `cyclical_operating_leverage`
- `regulated_balance_sheet`
- `binary_event_biotech`
- `rollup_acquirer`
- `financial_engineering`
- `mature_cash_returner`
- `broken_growth`

Each class gets different features and falsifiers. A bank, SaaS company, semiconductor equipment supplier, retailer, and biotech cannot share one long-term model.

### 6.4 Company Text and KPI Extraction Pipeline

Start with free and already available sources:

- 10-K / 10-Q MD&A.
- 8-K earnings releases.
- Investor presentations if already cached or manually supplied.
- Press releases.
- Existing news/briefing infrastructure.

Later paid-data unlocks:

- Earnings call transcripts.
- Segment estimates.
- Better consensus revenue/EPS revisions.
- Per-analyst revision history.
- Expert/channel data.

Use LLMs only to extract structured facts into strict schemas, never to originate signals.

### 6.5 Thesis Review Scheduler

Every active thesis should schedule reviews:

- After earnings.
- After 10-Q/10-K filing.
- After guidance/revision change.
- After large price drawdown or multiple expansion.
- After factor/theme crowding change.
- Every quarter even if nothing happens.

Output:

```text
thesis_delta:
  improved
  intact
  challenged
  falsified
  insufficient_new_evidence
```

### 6.6 Hold Book Risk and Overlap View

The repo already has factor/reflexivity pieces. Long-term hold needs a book-level view:

- Effective number of independent theses.
- Hidden theme overlap.
- Hidden factor overlap.
- Earnings calendar clustering.
- Same customer/supplier exposure.
- Same macro driver exposure.
- Same valuation-duration exposure.
- Thesis crowding: many names requiring the same macro story.

This is not for sizing at first. It is to stop "five different stocks, one thesis" accidents.

---

## 7. Novel Neural Web Sparks

### 7.1 The "Reason for Buying" Must Decay Separately From the "Reason for Holding"

The entry reason often expires quickly. The hold reason should not.

Add two clocks:

```text
entry_clock: days since tactical signal, half-life from existing staleness/entry work
thesis_clock: days since last fundamental confirmation
```

A position can have:

- Entry expired, thesis improving -> continue studying/holding.
- Entry strong, thesis weak -> tactical only.
- Entry weak, thesis strong -> wait for better location.
- Both weak -> remove.

### 7.2 Anti-PEG: Growth Is Good Only If Reinvestment Efficiency Holds

Classic growth screens overpay for revenue growth. Neural Web should compute:

```text
growth_quality = revenue_growth * f(incremental_margin, reinvestment_efficiency, dilution, FCF_conversion)
```

Then compare it with valuation-implied growth. This catches the difference between:

- a real compounder;
- a growth company buying revenue with dilution/SBC;
- a cyclical peak pretending to be secular growth.

### 7.3 Moat Falsifier Library

Instead of "this company has a moat," define claims and falsifiers:

| Moat claim | Evidence | Falsifier |
|---|---|---|
| Pricing power | Stable/high gross margin, pass-through during cost pressure | margin compression despite revenue growth |
| Switching cost | recurring revenue, retention/RPO, service revenue | churn/discounting/sales efficiency deterioration |
| Scale economics shared | revenue per asset/employee improves while customer value improves | cost advantage stops widening; prices rise without volume response |
| Network effect | usage/customer growth strengthens unit economics | growth slows while cost to acquire rises |
| Intangible brand/IP | high/stable gross margin, low capital intensity, innovation output | R&D productivity falls; competitor products catch up |

This converts fundamental investing into measurable, falsifiable Neural Web objects.

### 7.4 "Market-Implied Thesis" Cards

Every long-term candidate should get a small reverse-DCF style card:

```text
Current price implies:
- revenue CAGR: X
- terminal EBIT margin: Y
- reinvestment rate: Z
- years of high return period: N

Evidence today supports:
- revenue evidence: improving / flat / deteriorating
- margin evidence: improving / flat / deteriorating
- reinvestment evidence: high / uncertain / poor
- expectation drift: positive / neutral / negative
```

This avoids generic "cheap/expensive" labels.

### 7.5 Missed-Hold Classifier

Some tactical trades become great long-term holds. Neural Web should study missed compounders:

```text
Events where:
  entry system fired
  short-term target was hit
  but stock kept compounding for 12-36 months
```

Then ask what was visible at entry:

- ROIC persistence?
- revision drift?
- ownership broadening?
- margin stability?
- theme cash-flow transmission?
- valuation-implied expectations too low?

This is likely the most direct path from your existing entry work into long-term hold alpha.

### 7.6 Thesis Aging and Great-Company Trap Detector

Long-term investors often lose money by holding a great business after expectations become impossible.

Signals:

- Valuation-implied growth rises faster than evidence.
- Estimate revisions slow while price keeps rising.
- Margin and ROIC stay high but stop improving.
- Sponsorship/crowding becomes one-sided.
- Insider selling rises while buybacks occur at elevated multiples.
- Narrative velocity rises while KPI evidence slows.

Output:

```text
thesis_intact_but_price_demanding
```

This is different from "sell." It tells the brain the margin of safety has eroded.

---

## 8. Build Plan

### Phase 1: Long-Term Objective and Labels

Build:

- `research/long_hold/OBJECTIVE.md`
- `scripts/research/long_hold_label_panel.py`
- `data/research/long_hold_labels.parquet` (local/off-render first)

Labels:

- `fwd_ret_126d`, `fwd_ret_252d`, `fwd_ret_504d`, `fwd_ret_756d`
- `max_dd_252d`, `time_underwater_252d`
- `sector_rel_ret_252d`
- `fundamental_delta_next_4q`
- `revision_delta_next_90d`
- `compounder_label`
- `cheap_trap_label`
- `tactical_only_label`
- `missed_hold_label`

No site output.

### Phase 2: Compounder Feature Store v1

Build:

- `engine/neuralweb/long_hold_features.py`
- `data/company_features/pit_company_features.parquet`

Features:

- ROIC proxy persistence.
- Gross margin stability.
- FCF conversion.
- Reinvestment rate.
- Incremental revenue per reinvestment dollar.
- Share count/SBC/dilution.
- Net debt and interest coverage.
- Revenue/margin/FCF trend.
- Existing SUE and analyst revision join.
- Existing ownership/beneficial-ownership context join.

### Phase 3: Business Model Ontology v1

Build:

- `research/long_hold/BUSINESS_MODEL_ONTOLOGY.md`
- `engine/neuralweb/business_model.py`

Output:

- Business-model class.
- Applicable KPI list.
- Default falsifier set.
- Coverage flag.

Keep deterministic and transparent. Avoid LLM classification until the schema is stable.

### Phase 4: Thesis Ledger

Build:

- `engine/neuralweb/long_thesis.py`
- `data/neuralweb/long_thesis_registry.jsonl`
- `data/neuralweb/long_thesis_reviews.jsonl`

Rules:

- Thesis creation requires an existing deterministic signal, event, or admitted candidate.
- LLM can draft summary text only from structured evidence.
- Every thesis needs claims, falsifiers, review cadence, and horizon.
- No thesis can rank or size until a future governance promotion.

### Phase 5: Valuation-Implied Expectations v1

Build:

- `engine/neuralweb/implied_expectations.py`

Start simple:

- EV/sales, EV/EBIT, P/FCF where available.
- Reverse growth/margin assumptions using conservative templates by business-model class.
- No price targets.
- Output "what must be true."

### Phase 6: Missed-Hold Study

Build:

- `scripts/research/missed_hold_study.py`

Question:

```text
When our existing entry/bottom/confluence systems fired, which winners should have been held,
and what long-term evidence existed at the original signal date?
```

This directly bridges the current edge into the next one.

### Phase 7: Committee Surface

Only after Phases 1-6 produce useful artifacts:

- Add a Committee "Long Thesis" tab.
- Show thesis status, claims, falsifiers, latest evidence delta, and market-implied thesis.
- Display-only. No action language.

---

## 9. Paid Data: What Would Actually Move the Needle

The repo memory says the user chose to skip paid purchases on 2026-07-05, so this is not a buy recommendation. It is a priority map if that decision changes.

Highest value:

1. Earnings call transcripts: KPI extraction, language delta, management tone, customer/capex clues.
2. Consensus revenue/EPS revisions with point-in-time history: expectation drift.
3. Segment fundamentals / KPI database: business-model truth.
4. Supply-chain/customer exposure data: theme cash-flow propagation.
5. Web traffic / transaction / app / geolocation data: demand nowcasts for consumer/software/retail.
6. Short/borrow history: squeeze and informed-short context, but less central to long holds.

The most valuable paid-data theme is **expectation drift**, not more price data.

---

## 10. Recommendation

The highest-ROI path is not to build a universal "long-term stock score." That would violate the house's anti-megascore lessons and likely overfit.

Build a **Long-Term Thesis Layer** that starts as research-only and display-only:

```text
1. Label missed holds from existing entry signals.
2. Build PIT compounder features.
3. Add business-model classes and moat falsifiers.
4. Create thesis ledgers with claims, falsifiers, and quarterly reviews.
5. Add implied-expectation cards.
6. Let the kernel/hypothesis machinery learn which thesis evidence predicts 12-36m outcomes.
```

The edge is not "find high-quality stocks." Everyone can screen for those.

The edge is:

```text
find the moment when a good entry, improving business evidence,
underpriced expectations, and a durable thesis all become true at once,
then keep checking whether the thesis remains true after the entry signal expires.
```

That is how Neural Web graduates from entry intelligence to ownership intelligence.

---

## 11. Repo Sources Consulted

- `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
- `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
- `research/QUANT_FUND_NEURAL_WEB_ALPHA_STUDY.md`
- `research/INSTITUTIONAL_ALPHA_NEURAL_WEB_BOTTOM_GAP_REPORT.md`
- `research/SIGNAL_COMMONS_MASTERPLAN_BY_FABLE.md`
- `research/FACTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- `research/STOCK_FUNDAMENTALS_PLAN.md`
- `research/STOCK_CONVICTION_V2.md`
- `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md`
- `engine/stock_fundamentals.py`
- `engine/equity_factors.py`
- `engine/analyst_revisions.py`
- `engine/neuralweb/bottom_sensors.py`
- `engine/neuralweb/alpha_grammar.py`
- `engine/neuralweb/alpha_overlap.py`
- `engine/neuralweb/research_queue.py`
- `engine/beneficial_ownership.py`
- `engine/crowding.py`

## 12. External Sources Used

- [BlackRock Systematic Investing](https://www.blackrock.com/us/individual/investment-ideas/systematic-investing)
- [Man AHL](https://www.man.com/ahl)
- [Two Sigma](https://www.twosigma.com/)
- [Point72 Cubist](https://point72.com/cubist/)
- [Citadel Data Strategies Group role description](https://www.citadel.com/careers/details/quantitative-researcher-data-strategies-group/)
- [Microsoft Qlib](https://github.com/microsoft/qlib)
- [MSCI Barra Equity Factor Models](https://www.msci.com/data-and-analytics/factor-investing/equity-factor-models)
- [AQR Quality Minus Junk dataset](https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly)
- [AQR Can Machines Learn Finance?](https://www.aqr.com/Insights/Research/Journal-Article/Can-Machines-Learn-Finance)
- [Fama and French, A Five-Factor Asset Pricing Model](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2287202)
- [Novy-Marx, The Other Side of Value](https://mysimon.rochester.edu/novy-marx/research/OSoV.pdf)
- [NBER Buffett's Alpha](https://www.nber.org/papers/w19681)
- [S&P Dow Jones Indices, A Systematic Approach for Identifying Companies with Economic Moats](https://www.spglobal.com/spdji/en/documents/research/research-a-systematic-approach-for-identifying-companies-with-economic-moats.pdf)
- [Morgan Stanley, Measuring the Moat](https://www.morganstanley.com/im/publication/insights/articles/article_measuringthemoat.pdf)
- [Fundsmith Owner's Manual](https://www.fundsmith.co.uk/media/ykbfhfvu/owners-manual.pdf)
- [Quartr summary of Nick Sleep / Nomad's Costco thesis](https://quartr.com/insights/investment-strategy/investing-mastery-with-nick-sleep-nomad-s-costco-investment)
