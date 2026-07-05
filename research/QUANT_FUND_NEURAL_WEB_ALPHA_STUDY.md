# Quant Fund Blueprint for Turning Neural Web into an Alpha Brain

**Status:** Deep research study and buildable gap map.  
**Prepared:** 2026-07-05.  
**Scope:** How quantitative funds use signals, how a quant fund would build a system like Neural Web to create alpha, and what we can build now that is not already covered by the prior institutional-bottoms report.

---

## 0. What This Report Intentionally Excludes

The prior report, `research/INSTITUTIONAL_ALPHA_NEURAL_WEB_BOTTOM_GAP_REPORT.md`, already covered:

- ownership pressure;
- 13F breadth and holder concentration;
- forced ETF/fund-flow reversal;
- short interest and borrow interpretation;
- options-surface panic and dealer positioning;
- event/dilution/refinancing fragility;
- bottom-specific quality survival;
- tradeability, stop distance, capacity, and lifecycle states.

This report does **not** repeat those. It asks a different question:

> If a quantitative fund were handed our current Neural Web, what research and signal-processing machinery would it build next so the whole organism becomes better at generating, filtering, sizing, timing, and retiring alpha?

The answer is not "one better indicator." It is a **quant research operating system** around Neural Web:

- an alpha library;
- a feature compiler;
- a signal-overlap map;
- specialist models by regime and signal family;
- confidence calibration;
- top/bottom hazard estimators;
- historical analogue memory;
- disagreement mining;
- portfolio expected-utility routing;
- automated falsifier generation;
- and strict promotion gates so the brain becomes sharper without becoming overfit.

In plain English: Neural Web already has nerves and memory. A quant fund would now give it a research lab, a probability desk, and a portfolio PM layer.

---

## 1. How Quant Funds Actually Use Signals

Quant funds usually do not bet the firm on a single signal. They build many weak, partially independent signals, then combine them under strict controls.

Important ideas from quant practice:

1. **Alpha is usually small but repeatable.**
   The edge of one signal is often weak. The business is to find many weak edges that are not the same bet.

2. **Breadth matters.**
   The fundamental law of active management frames information ratio as a function of skill, breadth, and portfolio transfer. A low-IC signal can matter if it applies across many independent bets and survives costs.

3. **Signals need an ontology.**
   A signal may be alpha, timing, sizing, veto, context, or explanation. Mixing those roles creates fake conviction.

4. **Combination is its own research problem.**
   Goldman Sachs Asset Management's signal-combination paper compares ways to mix signals and argues that preserving signal information until final portfolio construction can reduce turnover and preserve more information than prematurely mixing them into single-signal portfolios ([GSAM](https://www.gsam.com/content/dam/gsam/pdfs/institutions/en/articles/2018/Combining_Investment_Signals_in_LongShort_Strategies.pdf?rd=n&sa=n)).

5. **A large alpha library is normal.**
   The "101 Formulaic Alphas" paper exposes a style of real quant research: many explicit, code-like formulas built from ranks, correlations, time-series transforms, price/volume relations, and decay functions. The paper reports short average holding periods and low average pairwise correlation across the formulaic alphas ([Kakushadze, 101 Formulaic Alphas](https://arxiv.org/pdf/1601.00991)).

6. **Machine learning is useful, but mostly as regularized signal combination.**
   AQR's "Can Machines Learn Finance?" emphasizes that finance is hard for ML, but ML is still useful for high-dimensional models, model selection, regularization, and surveying many model specifications, as long as economic theory and human expertise remain central ([AQR](https://www.aqr.com/-/media/AQR/Documents/Alternative-Thinking/AQR-Alternative-Thinking-2Q19-Can-Machines-Learn-Finance.pdf?sc_lang=en)).

7. **Multiple testing is a killer.**
   Deflated Sharpe Ratio work warns that large data sets and ML let researchers test millions of strategies, creating selection bias and inflated backtests unless unselected trials are accounted for ([Bailey and Lopez de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)). Harvey, Liu, and Zhu make the same point for the factor zoo: a new factor needs a much higher hurdle after hundreds of prior tests ([RFS](https://academic.oup.com/rfs/article/29/1/5/1843824)).

8. **Scale and engineering are the edge.**
   Man AHL describes systematic investing as scientific rigor, robust technology, diverse data, and hundreds of markets ([Man AHL](https://www.man.com/ahl)). BlackRock describes systematic alpha as codifying many predictive signals, using ML to generate alpha forecasts from vast signals, and combining human expertise with regime-aware models ([BlackRock AIM](https://www.blackrock.com/institutions/en-au/insights/investment-actions/augmented-investment-management)).

The quant fund translation for us:

> Neural Web should become a controlled signal laboratory whose output is not "a hot pick," but a calibrated distribution of expected edge, downside, confidence, decay, and portfolio fit.

---

## 2. Where Our Current System Already Looks Quant-Fund Grade

This matters because the next build should add missing machinery, not duplicate existing doctrine.

Already present or already chartered:

- Neural Web registry, envelopes, world state, spine federation, kernel, confluence graph, governance, cortex, hypothesis metabolism.
- Validation primitives: rank IC, incremental IC, HAC/Newey-West, BH-FDR, DSR, block bootstrap, OOS checks.
- Entry confluence and setup-species programs.
- Signal Commons role taxonomy, half-life attempt, event-prior harness, PIT-tape rolling.
- Factor Intelligence as de-escalation/conditioning, not a selection engine.
- Board-honesty audits, variable-width lane doctrine, and edge-vs-entry separation.
- Bottom/rebound sensor taxonomy and COILED/RS-repair lessons.

So the missing quant-fund layer is not "build validation." It is:

- **alpha generation at scale** under that validation;
- **feature engineering as an explicit compiler**;
- **meta-decision models** that decide take/skip/size/hold for existing signals;
- **uncertainty and confidence calibration**;
- **top/bottom hazard forecasting** as survival analysis;
- **analogue retrieval** from the Neural Web memory;
- **disagreement mining**;
- **portfolio expected-utility optimization**;
- **automatic falsifier generation**;
- **signal decommissioning and decay management**.

---

## 3. Quant Fund Version of Neural Web

A quant fund would split Neural Web into six desks.

### 3.1 Alpha Factory

Generates candidate signals from approved data using a constrained grammar. It does not ship them to production. It produces research candidates.

### 3.2 Signal Quality Lab

Measures raw IC, incremental IC, decay, turnover, cost, capacity, regime dependency, correlation to existing signals, and failure modes.

### 3.3 Meta-Decision Desk

Takes existing signals and asks: should this signal be acted on now, skipped, downsized, delayed, or routed to a different trade expression?

### 3.4 Hazard Desk

Estimates top, bottom, stop-out, trend-exhaustion, and regime-flip hazards. This is especially important for detecting tops and avoiding late buys.

### 3.5 Analogue Memory

Finds historical states similar to today's state vector and reports how those states resolved.

### 3.6 Portfolio PM Layer

Turns signal forecasts into position suggestions under active risk, correlation, capacity, drawdown, and confidence constraints.

The current Neural Web is strongest in registry, memory, and governance. These six desks turn it into a quant-fund research and trading brain.

---

## 4. Buildable Now: The Missing Quant-Fund Components

### 4.1 Alpha Grammar and Formulaic Signal Compiler

**What quant funds do:** They create a controlled language for candidate alphas. The researcher does not hand-code every one-off indicator. They define transformations and let the research engine generate families.

**Why this matters:** We have many signals, but not a formal alpha grammar that can generate, tag, and evaluate families in a uniform way.

**Build now:**

Create `engine/neuralweb/alpha_grammar.py` and `scripts/research/compile_alpha_candidates.py`.

Allowed primitives:

- cross-sectional rank;
- sector-neutral rank;
- z-score and winsorized z-score;
- time-series rank;
- rolling correlation;
- rolling covariance;
- rolling beta residual;
- delta / rate of change;
- decay-linear weighted sum;
- rolling argmax/argmin distance;
- volatility-normalized move;
- gap/reclaim transforms;
- breadth transforms;
- confluence co-fire transforms;
- lagged cross-asset transforms from already-collected ETFs/macro series.

Allowed source families:

- OHLCV panel;
- existing confluence/tier outputs;
- sector/theme/subsector states;
- macro/risk state;
- factor DNA panel;
- event-prior tables;
- Neural Web spine rows.

Forbidden:

- ad hoc formulas outside the compiler;
- same-bar fills;
- unregistered trial families;
- LLM-created formula escalation;
- new paid-data assumptions;
- formulas that cannot be PIT reconstructed.

Each candidate gets:

- `alpha_id`
- `family`
- `formula_ast`
- `source_artifacts`
- `lookback`
- `lag`
- `horizon`
- `expected_role`
- `trial_budget_family`
- `mechanism_hypothesis`
- `overlap_cluster`

**What this adds:** A quant-fund style research factory. The edge is not the first 100 formulas; the edge is that every formula is reproducible, grouped, tested, and either killed or promoted without turning the repo into a pile of one-offs.

**First candidate families:**

- `price_volume_microalpha_daily`: daily OHLCV rank/correlation/decay formulas inspired by the 101-alpha grammar, but daily and low-turnover enough for our data.
- `confluence_response_alpha`: formulas describing how price behaves after T1/T2/T3 fires.
- `regime_conditioned_pullback_alpha`: pullback/reclaim variants split by market state.
- `cross_asset_pressure_alpha`: macro/ETF lead-lag transforms into sector/name response.
- `breadth_divergence_alpha`: index/sector breadth versus price divergence for tops/bottoms.

**Promotion path:** display-only research artifacts first. No user-facing score until a family survives trial-ledger/DSR/FDR and incremental IC.

### 4.2 Alpha Correlation and Redundancy Map

**What quant funds do:** They do not just ask whether a signal works. They ask whether it is new. A weak signal with low correlation to existing signals may be more valuable than a stronger signal that duplicates the book.

**Current gap:** Neural Web has confluence and artifact graphs, but not a full **alpha redundancy map**:

- signal-to-signal forecast correlation;
- signal-to-signal realized outcome correlation;
- co-fire overlap;
- incremental IC after known signals;
- turnover overlap;
- drawdown co-failure;
- regime-specific redundancy.

**Build now:**

Create `engine/neuralweb/alpha_overlap.py`.

Outputs:

- `data/neuralweb/alpha_overlap.parquet`
- `data/neuralweb/alpha_clusters.json`
- `site/neuralwebdata/alpha_overlap.json`

Metrics:

- `forecast_corr`
- `fire_jaccard`
- `same_name_same_day_overlap`
- `outcome_corr_21d`
- `incremental_ic_after_cluster`
- `co_drawdown_rate`
- `cluster_representative`
- `net_new_info_score`

**Why it increases signal quality:** It prevents Neural Web from counting the same idea five times. It also identifies "quiet diversifiers": signals that look mediocre alone but improve the ensemble because they fire in different states.

**Mastermind use:** When a stock has five bullish signals, the brain should know whether that is five independent witnesses or one repeated witness wearing five badges.

### 4.3 Meta-Label Router for Take / Skip / Size

**What quant funds do:** They often start with a primary signal and then train a secondary model to decide whether to act on it. The primary model says "opportunity"; the meta-model says "take this one."

This is related to meta-labeling and triple-barrier style labeling. The relevant lesson is not to blindly predict returns. It is to label real trade outcomes using profit, loss, and time barriers, then learn which signal fires deserve action. Public descriptions of triple-barrier/meta-labeling emphasize that fixed-horizon labels can be weak because they ignore volatility and path, while barrier labels model realistic trade outcomes ([mlfinpy docs](https://mlfinpy.readthedocs.io/en/latest/Labelling.html)).

**Current status:** Entry Intelligence has local meta-label plans. The new gap is a **Neural Web-wide router** that works across all signal families once enough spine rows exist.

**Build now as shadow:**

Create `engine/neuralweb/meta_router.py`.

Inputs:

- primary signal role;
- signal age;
- confluence count;
- regime state;
- factor DNA;
- alpha cluster;
- volatility regime;
- liquidity/ADV from existing data;
- prior family reliability;
- recent family decay;
- disagreement state;
- analog outcome distribution.

Outputs:

- `take_probability`
- `skip_probability`
- `downsize_probability`
- `expected_mae_bucket`
- `expected_time_to_resolution`
- `model_confidence`
- `top_falsifier`

Labels:

- triple-barrier or race labels already close to our existing stop-out/liftoff framework:
  - target first;
  - stop first;
  - neither by time barrier;
  - dead money;
  - retest hold;
  - trend continuation;
  - top failure.

Validation:

- purged and embargoed folds;
- chronological walk-forward;
- same-computable subset;
- no training on unresolved labels;
- compare to simple rule baseline;
- calibrate with Brier/reliability curves.

**Important constraint:** The router cannot create a buy signal. It only filters, sizes, or delays already-emitted signals.

### 4.4 Specialist Mixture-of-Experts by Regime

**What quant funds do:** They avoid one universal model when relationships change by regime. A mean-reversion edge, breakout edge, and defensive drawdown signal can all be real but work in different states.

**Current gap:** Neural Web has regime state and kernel clocks, but a quant fund would explicitly train **specialist models**:

- risk-on continuation specialist;
- risk-off bounce specialist;
- bear-market bottom specialist;
- late-cycle top specialist;
- high-vol crash specialist;
- low-vol grind specialist;
- China reversal specialist;
- US large-cap quality specialist;
- thematic bubble/exhaustion specialist.

**Build now:**

Create `engine/neuralweb/specialists.py`.

Each specialist is a small rule/model bundle:

- eligible regime states;
- eligible signal families;
- minimum sample floor;
- local features;
- local baseline;
- local calibration;
- current authority state.

Outputs:

- `data/neuralweb/specialist_scores.parquet`
- `data/neuralweb/specialist_registry.json`

**Why it increases accuracy:** It stops averaging across incompatible worlds. A signal that is mediocre globally may be useful in one specialist cell.

**Do not do:** Do not let the specialist ensemble override the kernel before the kernel authority clocks mature. Run in shadow and publish disagreement.

### 4.5 Probability Calibration and Confidence Surface

**What quant funds do:** A forecast is not useful unless it is calibrated. A 70% label should hit around 70%, or the model is lying.

**Current gap:** The repo has Wilson bounds and track records in pieces, but not one decision-facing **confidence surface** across signal families.

**Build now:**

Create `engine/neuralweb/confidence_surface.py`.

For each signal family x regime x horizon:

- `base_rate`
- `hit_rate`
- `calibrated_probability`
- `wilson_low`
- `brier_score`
- `expected_calibration_error`
- `sample_n`
- `effective_n`
- `staleness`
- `confidence_class`

Decision outputs:

- `high_confidence`: enough n, calibrated, stable;
- `medium_confidence`: useful but wide CI;
- `low_confidence`: direction plausible, uncertainty high;
- `uncalibrated`: display only;
- `decayed`: historical edge no longer reliable.

**Why this matters for the user's stated goal:** More certainty is not created by stronger language. It is created by knowing which cells have enough evidence and which are still noise.

**Display idea:** Every recommendation should show:

> "This signal family has n=184 comparable fires in this regime, 21d hit 58%, Wilson low 52%, Brier improving versus base by 0.03. Confidence: medium."

That is the difference between a dashboard and a trading brain.

### 4.6 Top and Bottom Hazard Models

**What quant funds do:** They model not just direction but transition risk: the chance a trend ends, the chance a bottom holds, the chance a rally fails, or the chance a regime flips.

**Current gap:** The repo has many bottom/top descriptors and some hazard artifacts, but not a unified **survival/hazard desk** that every signal can query.

**Build now:**

Create `engine/neuralweb/hazard.py`.

Hazards:

- `bottom_failure_hazard`: chance the recent low fails within N days.
- `bottom_confirmation_hazard`: chance low survives and trend turns.
- `top_failure_hazard`: chance a high fails and starts drawdown.
- `trend_exhaustion_hazard`: chance continuation signal is late.
- `regime_flip_hazard`: chance macro/risk state changes in the next N days.
- `signal_decay_hazard`: chance an old signal is no longer actionable.

Features:

- signal age;
- confluence tier;
- distance from high/low;
- realized volatility regime;
- breadth divergence;
- sector/thematic concentration;
- factor DNA;
- recent MAE/MFE path;
- analog distribution;
- macro/risk state.

Labels:

- top: failed breakout, drawdown > X ATR, breadth divergence resolves down;
- bottom: low held, low failed, retest held, dead money;
- trend: continuation, exhaustion, reversal.

Models:

- Cox-style proportional hazard if data supports it;
- discrete-time logistic hazard by day bucket;
- nonparametric Kaplan-Meier tables first;
- no black box until tables are stable.

**Why it matters:** It lets Neural Web say:

- "This is a good stock, but the late-entry hazard is high."
- "This bottom has not confirmed, but failure hazard is falling."
- "This top risk is rising because breadth and price are diverging."

That is a mastermind brain function.

### 4.7 Historical Analogue Retrieval

**What quant funds do:** They compare today's state to historical states. Not as a mystical "this looks like 2009" narrative, but as a nearest-neighbor distribution with honest sample count.

**Current gap:** Neural Web has a spine index and many artifacts, but no generalized analogue engine for stock/sector/macro state vectors.

**Build now:**

Create `engine/neuralweb/analogues.py`.

State vector examples:

- market regime;
- sector state;
- confluence tier;
- signal age;
- factor DNA;
- volatility state;
- breadth state;
- distance to low/high;
- RS repair state;
- event-prior state;
- risk state.

Outputs:

- nearest historical episodes;
- median/quantile forward return;
- stop-out rate;
- low-held rate;
- top-failure rate;
- feature match explanation;
- sample quality flag.

Artifacts:

- `data/neuralweb/analogues.parquet`
- `site/neuralwebdata/analogues.json`

**Use cases:**

- bottom candidate: "20 closest historical states; 13 held the low, median 21d +3.2%, worst MAE -6.1%."
- top candidate: "Closest late-cycle breadth divergence states failed 60% within 30d."
- stock quality: "This signal combination historically worked only in high-dispersion regimes; current dispersion is neutral."

**Guardrail:** analogue results are context, not a forecast, until their retrieval method is pre-registered and graded.

### 4.8 Disagreement Mining

**What quant funds do:** They do not only reward agreement. They study when disagreement itself contains information. Sometimes a signal conflict is a warning; sometimes it is the edge.

**Current status:** Confluence graph and contradiction detection exist. Signal Commons has a committee-dissent study that was underpowered. The missing build is a systematic **disagreement mining harness**.

**Build now:**

Create `scripts/research/disagreement_mining.py`.

Question families:

- When technical timing is bullish but risk regime is bearish, which side wins?
- When sector leadership is bullish but single-name alpha is weak, what happens?
- When bottom confluence fires against factor DNA headwind, is MAE worse?
- When cortex/LLM caution disagrees with deterministic signals, is caution valuable?
- When Oracle/sector rotation and stock selection disagree, does the name or group dominate?
- When short-term and weekly timeframes disagree, is it a bounce-only setup?

Outputs:

- pair_id;
- conflict_type;
- n;
- base rate;
- conflict outcome lift;
- sign stability;
- regime split;
- recommendation: ignore / display warning / de-escalate / study more.

**Why it matters:** A mastermind brain should know not just what confirms, but what kind of disagreement historically mattered.

### 4.9 Signal Decay and Act-Late Replay

**What quant funds do:** They measure how long a signal stays alive. They also measure what happens if execution is late.

**Current status:** Signal Commons W2 measured holding-horizon half-lives and printed an honest null because no family passed the gate. But staleness half-life was explicitly left unmeasured because replay telemetry had uniform fill offset.

**Build now:**

Create delayed-fill replay variants:

- act at t+1;
- act at t+2;
- act at t+3;
- act at t+5;
- act after retest;
- act after confirmation;
- act after pullback.

For each signal family:

- edge at each delay;
- MAE at each delay;
- stop-out at each delay;
- signal value half-life;
- chase threshold.

Artifacts:

- `data/neuralweb/signal_delay_replay.parquet`
- `data/neuralweb/signal_staleness.json`

**Why it matters:** It answers practical trading questions:

- "Did I miss this?"
- "Is it still buyable?"
- "Should I wait for a pullback?"
- "Is this a top because the signal is stale?"

This directly increases accuracy and user trust.

### 4.10 Breadth Manufacturing Through Signal Diversity

**What quant funds do:** They increase breadth by adding independent bets, not by listing more tickers from the same cluster.

**Current gap:** The repo has effective-bets/correlation ideas, but not a **breadth budget** that tells the signal brain how many independent decisions it truly has.

**Build now:**

Create `engine/neuralweb/breadth_budget.py`.

Metrics:

- number of fired signals;
- number of independent alpha clusters;
- effective names after correlation;
- effective sector/theme bets;
- effective horizons;
- effective mechanisms;
- transfer coefficient from signal intent to portfolio holdings.

Output:

- `breadth_available`
- `breadth_used`
- `cluster_overuse`
- `new_bet_score`
- `duplicate_bet_score`

**Use:** A new candidate should be rewarded for adding an independent bet, not for being the 14th expression of the same AI/semis/rates/China beta.

**Mastermind language:** "This pick is good, but it adds 0.08 effective bets because the book already owns the same cluster."

### 4.11 Alpha Decay Monitor and Retirement Engine

**What quant funds do:** They expect edges to decay. They monitor live IC, hit rate, drawdown, turnover, crowding, and regime dependence. They retire signals.

**Current gap:** The repo has promotion/authority machinery, but needs an explicit **retirement engine** for alpha families.

**Build now:**

Create `engine/neuralweb/retirement.py`.

Retirement triggers:

- rolling IC sign flip;
- live hit rate below Wilson lower bound;
- Brier worse than base;
- outcome variance exploding;
- costs consuming edge;
- co-drawdown with another stronger cluster;
- sample stale;
- family superseded by lower-turnover equivalent.

States:

- active;
- probation;
- de-escalation-only;
- display-only;
- retired;
- revisit-on-regime.

**Why it matters:** A quant fund brain is not just good at adding signals. It is ruthless about killing them.

### 4.12 Expected-Utility Portfolio Router

**What quant funds do:** Signals do not become trades directly. They become expected return distributions, risk distributions, costs, and constraints. The portfolio layer decides.

**Current gap:** We have sizing and risk layers, but not one Neural Web expected-utility router that combines signal confidence, downside, correlation, and costs.

**Build now in shadow:**

Create `engine/neuralweb/utility_router.py`.

Inputs:

- calibrated probability;
- expected excess return quantiles;
- expected MAE;
- stop-out probability;
- confidence class;
- cost estimate;
- capacity;
- alpha cluster;
- current book exposure;
- signal age/staleness.

Outputs:

- `action_class`: ignore / watch / paper / small / normal / reduce / exit;
- `size_cap_bps`;
- `why_not_bigger`;
- `dominant_constraint`;
- `expected_utility_score`;
- `confidence_adjusted_edge`.

Core formula concept:

`expected_utility = expected_edge - lambda_drawdown * expected_mae - cost - crowding_penalty - uncertainty_penalty`

Do not surface as a buy score at first. Use it to explain why the brain would size one similar-looking setup smaller than another.

### 4.13 Top-Detection Desk

**What quant funds do:** They put as much work into avoiding late-cycle entries and detecting tops as finding bottoms. Tops are often about **distribution, exhaustion, crowding, breadth divergence, factor reversal, and failed continuation**.

**Build now:**

Create `engine/neuralweb/top_desk.py`.

Top setup families:

- `breadth_price_divergence`: price makes high, breadth does not;
- `rs_leader_exhaustion`: leader makes price high but RS momentum rolls over;
- `failed_breakout`: new high reverses below breakout level;
- `late_confluence_stale`: bullish signal fires far from low and late in move;
- `vol_expansion_after_grind`: volatility expands after low-vol uptrend;
- `factor_leader_rotation`: stock/theme leader loses factor support;
- `cluster_euphoria`: many names in one theme extended together;
- `downside_asymmetry`: upside remaining small versus stop/MAE risk.

Labels:

- 21d drawdown > X ATR;
- failed breakout;
- underperformance versus sector;
- top held for N days;
- reversal to 50d/200d.

Outputs:

- `top_hazard`
- `late_entry_warning`
- `distribution_flag`
- `hold_downgrade`
- `avoid_new_entry`

**Important:** This should be a risk/entry-veto desk first, not a short-selling engine.

### 4.14 Signal Explanation and Falsifier Generator

**What quant funds do:** Good PMs ask, "What would prove this signal wrong?" Neural Web should do that mechanically.

**Current gap:** qledger and cortex have falsifier concepts, but every user-facing trade candidate should carry a falsifier set.

**Build now:**

Create `engine/neuralweb/falsifiers.py`.

For each candidate:

- thesis;
- expected path;
- invalidation price or state;
- time window;
- data update that would cancel;
- conflicting signal that matters;
- event that dominates;
- evidence still missing.

Examples:

- Bottom thesis falsified if price closes below washout low before +5% liftoff.
- Top hazard falsified if breadth confirms new high within 5 sessions.
- High-quality stock thesis falsified if factor residual turns negative and earnings event fails.
- Regime signal falsified if risk state flips and specialist loses authority.

**Why it matters:** It makes the brain self-critical, not just confident.

### 4.15 Research Queue Ranker

**What quant funds do:** They rank research ideas by expected value. Most ideas do not deserve compute time.

**Build now:**

Create `engine/neuralweb/research_queue.py`.

Score candidate research ideas by:

- expected sample size;
- novelty versus alpha clusters;
- implementation cost;
- data availability;
- mechanism plausibility;
- potential user impact;
- probability of surviving validation;
- whether it unlocks multiple downstream desks.

Outputs:

- `next_best_experiment`
- `blocked_by_data`
- `too_sparse`
- `duplicate_of_existing`
- `high_ev_build_now`

**This makes cortex useful:** The AI layer can propose and prioritize experiments, but the deterministic queue decides whether the idea is worth a trial budget.

---

## 5. What This Adds to Bottoms, Tops, and Stock Selection

### 5.1 Better Bottom Detection

The quant-fund additions improve bottoms by asking:

- Is this bottom similar to historical bottoms that held?
- Is the signal stale?
- Does the current regime specialist trust this family?
- Is the signal redundant with other bottom signals or independent?
- Is the setup a bounce-only state or a durable-low state?
- Does a meta-router recommend take, skip, or wait?
- What is the calibrated probability and Wilson lower bound?
- What falsifies the bottom thesis?

This adds certainty by narrowing the set of bottoms we act on.

### 5.2 Better Top Detection

The additions improve top detection by adding:

- breadth-price divergence;
- stale bullish signal detection;
- late-entry hazard;
- failed-breakout hazard;
- cluster euphoria;
- factor leader exhaustion;
- regime flip hazard;
- analogue comparisons to prior tops.

This is largely not in the prior institutional-bottoms report.

### 5.3 Better High-Quality Stock Selection

A quant fund would not simply ask "is this a quality stock?" It would ask:

- Does this stock have residual edge after known factors?
- Is it in a factor DNA class where current signals historically work?
- Is it a new independent bet?
- Is it supported by a specialist model?
- Is the expected utility positive after cost, MAE, and uncertainty?
- Is the signal still fresh?
- Are similar historical states favorable?

This creates a better high-quality trading list than a static quality/factor rank.

### 5.4 General Alpha Generation

The report's biggest alpha opportunity is the alpha grammar plus overlap map:

- generate many small candidates;
- cluster them;
- kill duplicates;
- measure net-new information;
- calibrate by regime/horizon;
- route through utility;
- retire decayed signals.

That is how Neural Web becomes a compounding research platform instead of a collection of clever dashboards.

---

## 6. Build Priority

### Wave Q1: Alpha Factory Foundation

1. `alpha_grammar.py`
2. `compile_alpha_candidates.py`
3. candidate registry with formula AST and trial family
4. first daily OHLCV/confluence formula families

**Why first:** It creates the research pipeline. Everything else needs candidate signals with reproducible identities.

### Wave Q2: Redundancy and Breadth

1. `alpha_overlap.py`
2. `alpha_clusters.json`
3. `breadth_budget.py`
4. committee/admin display of independent witnesses versus duplicates

**Why second:** It stops double-counting and tells us which signals are actually additive.

### Wave Q3: Confidence and Delay

1. `confidence_surface.py`
2. `signal_delay_replay.parquet`
3. calibration curves per family/regime/horizon
4. signal staleness cards

**Why third:** It turns signal quality into calibrated confidence and answers "is it too late?"

### Wave Q4: Meta-Router and Hazard Desk

1. `meta_router.py`
2. `hazard.py`
3. top/bottom hazard labels
4. shadow take/skip/size outputs

**Why fourth:** Once calibration and overlap exist, the router can learn real take/skip behavior without overcounting.

### Wave Q5: Analogue Memory and Disagreement Mining

1. `analogues.py`
2. `disagreement_mining.py`
3. similar-state distributions
4. conflict family scorecards

**Why fifth:** This is the "mastermind" layer users will feel. It gives the brain case memory and adversarial judgment.

### Wave Q6: Utility Router and Retirement Engine

1. `utility_router.py`
2. `retirement.py`
3. expected-utility shadow book
4. signal retirement dashboard

**Why sixth:** This converts research intelligence into portfolio intelligence and keeps the organism from accumulating stale parts.

---

## 7. Concrete Data We Already Have

The buildable-now case is strong because we already have:

- daily OHLCV across baskets/universes;
- benchmark ETFs and macro series;
- sector/theme/subsector maps;
- confluence tiers and entry signals;
- Neural Web spine rows;
- regime/risk state;
- factor intelligence coordinates;
- event-prior harnesses;
- signal archive/track records;
- qledger-style claims;
- cortex hypothesis metabolism;
- validation primitives;
- admin/committee surfaces.

The next layer is mostly **computation and organization**, not procurement.

---

## 8. What Not to Build

Do not build:

- a universal black-box stock picker;
- a single Neural Web "master alpha score";
- a hand-weighted confidence number;
- an LLM-originated alpha;
- a giant formula sweep without trial-budget logging;
- a top/bottom model trained on overlapping labels without purging;
- a portfolio optimizer before forecasts are calibrated;
- a signal-combination model that ignores costs and correlation;
- a dashboard that shows five duplicate confirmations as five independent facts.

Quant funds are aggressive, but the good ones are not casual. The machine should be curious, but the ledger should be merciless.

---

## 9. Final Thesis

If a quantitative fund built Neural Web, it would make the system more powerful in three ways:

1. **More breadth:** an alpha grammar generates many candidate signals across names, sectors, horizons, regimes, and signal roles.

2. **More precision:** confidence surfaces, meta-routing, hazard models, staleness replay, and analogue memory decide which signals deserve action.

3. **More portfolio intelligence:** overlap maps, breadth budgets, expected-utility routing, and retirement rules prevent duplicate bets and stale edges from masquerading as conviction.

The final product should not say:

> "NVDA is a 91 buy."

It should say:

> "NVDA has three bullish witnesses, but two are the same alpha cluster. The independent evidence is one timing signal and one factor-DNA specialist. In this regime, comparable states have a 57% 21d hit rate with wide uncertainty. Signal is t+3 and decay replay says half the edge is gone. Top hazard is medium because breadth divergence is rising. Expected utility is positive only at small size."

That is a Neural Web worthy of the name: not a louder signal board, but a self-aware quant brain that knows what it knows, what it does not know, when it is late, when it is double-counting, and when the trade no longer deserves capital.

---

## Sources Consulted

- Kakushadze: [101 Formulaic Alphas](https://arxiv.org/pdf/1601.00991)
- Goldman Sachs Asset Management: [How to Combine Investment Signals in Long/Short Strategies](https://www.gsam.com/content/dam/gsam/pdfs/institutions/en/articles/2018/Combining_Investment_Signals_in_LongShort_Strategies.pdf?rd=n&sa=n)
- Bailey and Lopez de Prado: [The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- Man Group: [Man AHL](https://www.man.com/ahl)
- AQR: [Can Machines Learn Finance?](https://www.aqr.com/-/media/AQR/Documents/Alternative-Thinking/AQR-Alternative-Thinking-2Q19-Can-Machines-Learn-Finance.pdf?sc_lang=en)
- BlackRock: [Augmented Investment Management](https://www.blackrock.com/institutions/en-au/insights/investment-actions/augmented-investment-management)
- BlackRock: [Alpha Reimagined](https://www.blackrock.com/institutions/en-global/institutional-insights/thought-leadership/alpha-reimagined)
- CFA Institute Research Foundation: [The Current State of Quantitative Equity Investing](https://rpc.cfainstitute.org/sites/default/files/-/media/documents/book/rf-lit-review/2018/becker-rf-lit-review-2018.pdf)
- Harvey, Liu, Zhu: [... and the Cross-Section of Expected Returns](https://academic.oup.com/rfs/article/29/1/5/1843824)
- mlfinpy documentation: [Labeling and Triple-Barrier Method](https://mlfinpy.readthedocs.io/en/latest/Labelling.html)
