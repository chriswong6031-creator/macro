# Economic Release Replication Machine

> **ADJUDICATED 2026-07-07 (Fable).** This external handoff arrived the same day the
> MRI program shipped (PRs #1822/#1825/#1828 + C/D) and is ~75-80% duplicate of it.
> Verdict + delta build ("Package F") recorded in
> `research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md` §9. Do not build from this
> doc directly; it is preserved as the docket source. Its "consensus" framing is
> superseded by MRI-R5 (benchmark_set honesty), and its market-reaction trading
> layer is constrained by MRI-R1/R3 (descriptive playbook only).

**Status:** deep research + buildable architecture. Doc-only handoff.
**Scope:** CPI, NFP first, then PCE, PPI, retail sales, ISM, GDP advance, jobless claims, FOMC-path-sensitive prints.
**Operating principle:** model the *government release*, not the abstract economy; grade every frozen pre-release estimate against the first release, later revisions, consensus surprise, and market reaction.

---

## 0. Executive Answer

Yes, we can build a serious version of the institutional CPI/NFP modeling stack, but it should not be framed as a single clever AI predictor. The viable machine is a release-replication system:

1. **Replicate the release mechanics.** CPI is a weighted basket of component price changes. NFP is a stratified establishment-survey estimate plus imputation plus net birth-death modeling. We should model the exact release target and its quirks.
2. **Nowcast only the components with live evidence.** Gasoline, used vehicles, airfares, shelter, jobless claims, job postings, tax withholding, payroll proxies, weather/strike flags, and market-implied event pricing carry more signal than a generic macro model.
3. **Use a committee, not one model.** Component bridge equations, dynamic-factor/ragged-edge models, Bayesian shrinkage, and release-microstructure rules should compete and ensemble under a forward ledger.
4. **Freeze pre-release snapshots.** A model that is not timestamped before release is theater. Every estimate must be written to an append-only ledger with `asof`, `release_id`, available-input hash, prediction distribution, and later realized outcome.
5. **Separate three scores.** The machine should be graded on (a) release-number accuracy, (b) surprise-vs-consensus accuracy, and (c) market-reaction usefulness. These are not the same problem.

The realistic target is not "always nail CPI/NFP." It is:

| Release | Public/free v1 target | Paid-data institutional target | Best use |
|---|---:|---:|---|
| Headline CPI MoM | within +/-0.08-0.12 pp on normal months | +/-0.04-0.08 pp | Fed/rates risk, event preparation |
| Core CPI MoM | +/-0.10-0.15 pp | +/-0.06-0.10 pp | Inflation persistence, rate repricing |
| NFP headline | +/-60k-90k jobs | +/-40k-70k jobs | labor-risk skew, not single-print certainty |
| Unemployment rate | +/-0.1-0.2 pp | +/-0.1 pp | Fed reaction function |
| Average hourly earnings MoM | +/-0.1 pp | +/-0.05-0.1 pp | wage inflation pulse |

These are ambitious but not mystical. Public evidence says high-quality inflation nowcasts can outperform surveys, while NFP remains intrinsically noisier because the first release is itself a sampled, imputed, later-revised estimate.

---

## 1. How Serious Institutions Do This

### 1.1 The common architecture

The sophisticated shops are not simply asking analysts for estimates. They usually combine five layers:

| Layer | What they collect | Method |
|---|---|---|
| Official-release skeleton | BLS/BEA/Census/Fed/Treasury release definitions, seasonal factors, weights, reference weeks, revisions | deterministic release calendar + component accounting |
| High-frequency hard proxies | gasoline, oil, used-car auctions, rents, jobless claims, Treasury withholding, card/scanner/online prices, payroll processor data | bridge equations, mixed-frequency nowcasts, MIDAS, dynamic-factor models |
| Alternative microdata | web-scraped prices, job postings, HR profiles, payroll/time-clock systems, rent listings, freight/airline/hotel/retail feeds | cleaning, de-duplication, panel construction, sector/geography mapping |
| Survey/market priors | analyst consensus, Polymarket/market-implied probabilities, rates/futures reaction functions | prior blending + surprise calibration |
| Outcome ledger | first-release error, revised-release error, surprise direction, rates/equity/FX reaction | append-only grading, calibration, model retirement |

The "ingenious" part is usually not the model class. It is the data engineering and target discipline: knowing exactly which component of a release can move, which input is already known, which input is lagged, and which residual is unmodelable.

### 1.2 CPI modeling

The official CPI is large but not unknowable. BLS says CPI price data are collected through commodities/services and rent surveys, with roughly 100,000 commodity/service prices and about 8,000 rental housing quotes each month; weights come from Consumer Expenditure survey data and are updated annually. The CPI design page also notes price collection from about 80,000 goods/services across 75 urban areas, about 6,000 housing units, and about 23,000 retail establishments. Sources: [BLS CPI design](https://www.bls.gov/opub/hom/cpi/design.htm), [BLS CPI data sources](https://www.bls.gov/opub/hom/cpi/data.htm).

Institutional CPI nowcasting breaks the basket into:

| CPI block | Predictability | Data used by serious models |
|---|---|---|
| Energy/gasoline | high | daily oil, wholesale/retail gasoline, EIA/AAA/gas station data |
| Food at home | medium | grocery scanner/web prices, commodity pass-through, BLS food series persistence |
| Shelter/OER/rent | medium but slow | BLS rent method, Zillow/CoreLogic/Apartment List/new-tenant rents, lag models |
| Used cars | medium | Manheim/auction values, retail inventory, depreciation/quality controls |
| Airfares | medium/noisy | web-fare samples, jet fuel, route/trip-month specs |
| Goods ex food/energy | medium | online prices, import prices, retailer discounting, supply-chain pressure |
| Services ex shelter | low-medium | wage/ECI, health insurance methodology, local services persistence |

The Cleveland Fed inflation nowcast is the clean public benchmark. It uses a small mixed-frequency set including daily oil prices, weekly gasoline prices, and monthly CPI/PCE readings. Its own real-time assessment found headline inflation nowcasts historically beat alternative statistical models and professional survey nowcasts, while core nowcasts are harder and less statistically dominant. Sources: [Cleveland Fed nowcast page](https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting), [Cleveland Fed real-time assessment](https://www.clevelandfed.org/publications/economic-commentary/2023/ec-202306-real-time-assessment-inflation-nowcasting-cleveland-fed).

The private-data edge is microprice coverage. The Billion Prices Project reached 5 million online prices per day by 2010 and showed online price indexes often co-move with official CPIs, while also warning that online prices under-cover services and some offline retail categories. State Street PriceStats now markets daily inflation and PPP indicators built from millions of prices across 1,500+ retailer websites and 27 countries. Sources: [Cavallo and Rigobon, JEP 2016](https://www.aeaweb.org/articles?id=10.1257%2Fjep.30.2.151), [State Street PriceStats](https://www.statestreet.com/us/en/solutions/data-intelligence/pricestats).

Shelter is where first-principles modeling matters. Market rents lead CPI shelter, but CPI shelter is a stock-of-housing-service index, not a new-lease index. Richmond Fed/KC Fed summaries show Zillow/New Tenant/CoreLogic rent measures lead official rent/OER by months to roughly a year. A 2025 NBER working paper decomposes the lag into lease terms, renewal smoothing, and the CPI six-month measurement construction. Sources: [Richmond Fed rent lead table](https://www.richmondfed.org/research/national_economy/macro_minute/2023/mm_04_04_23), [Kansas City Fed rent comparison](https://www.kansascityfed.org/research/economic-bulletin/comparing-measures-of-rental-prices-can-inform-monetary-policy/), [Ball and Koh NBER 2025](https://www.nber.org/system/files/working_papers/w34113/w34113.pdf).

### 1.3 NFP modeling

NFP is much harder than CPI because the first release is a survey estimate, not a complete count. BLS CES currently samples about 119,000 businesses/government agencies covering roughly 622,000 worksites and about 26% of nonfarm payroll employment. Annual benchmarking aligns CES to QCEW UI records. A net birth-death model fills the new-business/closed-business gap; BLS describes an imputation component plus an ARIMA model based on QCEW-derived residuals over the prior five years. Sources: [CES benchmark technical notes](https://www.bls.gov/web/empsit/cestn.htm), [CES net birth-death model](https://www.bls.gov/web/empsit/cesbd.htm).

Serious NFP modeling splits the problem:

| NFP subproblem | Signal families |
|---|---|
| Establishment-job count | ADP/payroll processors, job postings, jobless claims, tax withholding, Homebase/time-clock activity |
| Industry mix | job postings and payroll data by NAICS/SOC, strike/weather/education/government calendars |
| Birth-death residual | business formation, QCEW lag structure, seasonal residuals, small-business proxies |
| Reference-week distortion | weather, strikes, holiday timing, school/government calendar, pay-period alignment |
| Unemployment rate | CPS job flows, claims, online job search, CHURN-like flow model |
| Average hourly earnings | payroll processors, posted wages, sector mix, hours worked |

ADP-style microdata is powerful but imperfect. A Federal Reserve paper using ADP establishment-level payroll microdata notes ADP covers about half a million business establishments and roughly one fifth of US private employment, with weekly/biweekly timeliness and coverage outside the CES reference week. But ADP's own report is not designed as a one-for-one BLS forecast, and method differences can matter. Source: [Federal Reserve FEDS 2018-005](https://www.federalreserve.gov/econres/feds/files/2018005pap.pdf).

High-frequency public/free proxies can still help. Treasury withholding is a rich wage/income flow because large firms remit withheld taxes shortly after payroll and Treasury reports the totals quickly. Indeed job postings are daily, seasonally adjusted, and available on FRED, with national, occupation, and geography series. Sources: [Tax Tracking on withholding](https://taxtracking.com/), [FRED Indeed release](https://fred.stlouisfed.org/release?rid=476).

Private job-posting vendors are the closest public window into hedge-fund-style NFP modeling. LinkUp says its company-website job openings data beat Reuters consensus 65% of the time over a two-year sample, with a 68k average first-release error versus 75k for consensus; this is a vendor slide deck, so it should be treated as suggestive, not independent proof. Revelio's public labor statistics use job postings and public employment records, and its methodology emphasizes de-duplicated postings from career pages, boards, aggregators, and staffing firms. Sources: [LinkUp NFP forecasting deck](https://link-up.files.svdcdn.com/production/documents/Research/NFP_forecasting_using_Jobs_data.pdf?dm=1756927516), [Revelio RPLS methodology note](https://www.reveliolabs.com/news/macro/introducing-revelio-public-labor-statistics-rpls/).

The official/public research direction is also moving toward blended flow models. Chicago Fed's 2025 CHURN model blends monthly BLS job-flow statistics, traditional indicators, and private high-frequency indicators into a weekly unemployment-rate nowcast. Source: [Chicago Fed CHURN](https://www.chicagofed.org/publications/chicago-fed-letter/2025/506).

### 1.4 GDP and other releases

GDPNow/NY Fed nowcasts are the template for "release-replication" beyond CPI/NFP. Atlanta Fed GDPNow relates source data to GDP subcomponents with bridge equations, factor models, and BVARs, then aggregates subcomponents into GDP; missing monthly source data are forecast with econometric methods. The New York Fed Staff Nowcast is a dynamic factor model for weekly GDP tracking. Sources: [Atlanta Fed GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow), [NY Fed Staff Nowcast 2.0](https://www.newyorkfed.org/medialibrary/media/research/blog/2023/NYFed-Staff-Nowcast_technical-paper).

The lesson: each release should have a component accounting identity, a ragged-edge input matrix, and a tracked nowcast path that updates as source data arrive.

---

## 2. What "Success" Really Looks Like

### 2.1 CPI success

Public evidence supports useful CPI nowcasting:

- Cleveland Fed reports its headline CPI/PCE nowcasts historically outperformed MIDAS/DFM alternatives and survey benchmarks; core inflation was more competitive and less statistically dominant.
- Online-price indexes work best for goods/categories with strong online representation; they are weaker for services and offline/local categories.
- Shelter can be forecast structurally better than a pure AR model if the model respects stock-vs-new-lease mechanics.

The highest attainable public/free edge is likely **headline CPI direction and rough magnitude**, not perfect core CPI decimals. A paid microprice stack can improve goods coverage materially, but services and methodology changes remain hard.

### 2.2 NFP success

NFP success should be measured with humility:

- A 50k error can be excellent in one month and useless in another if consensus was already close.
- BLS first release can later revise by 50k-150k+ in unusual periods; modeling "truth" can beat first release but lose on market day.
- ADP/payroll/job-posting data are not the CES survey. They measure overlapping but not identical concepts.

The right target is **probabilistic surprise bands**:

```text
NFP release forecast:
  median +95k
  60% interval [+35k, +155k]
  90% interval [-40k, +240k]
  consensus +125k
  surprise skew: downside
  model confidence: medium-low
```

Then grade: Did the release land in the interval? Did the model beat consensus? Was the surprise direction right? Did rates/FX/equities react as the release-surprise function expected?

### 2.3 Market-use success

For trading and risk, the release number is only one layer. The actionable machine needs:

- **Surprise vs consensus**, not just level.
- **Policy relevance**, e.g. CPI services/wages/UR matter more near Fed turning points.
- **Positioning/event-risk context**, e.g. a CPI miss after rates already priced hot inflation is different from a miss into dovish positioning.
- **Reaction function**, e.g. rates may care more about core services ex shelter than headline gasoline.

This means the output should not say "CPI will be 0.23." It should say:

```text
Core CPI release-risk distribution:
  model: +0.27 MoM, consensus +0.30
  downside surprise probability: 58%
  hot-tail probability >= +0.40: 16%
  primary uncertainty: core services residual, airfare, medical services
  likely market sensitivity: high because front-end rates pricing is compressed
```

---

## 3. What We Already Have In This Repo

The repo is closer than it looks. Existing machinery:

| Asset | Current state |
|---|---|
| FRED collector + keyless fallback | `collectors/fred.py`; broad `config.yml` series inventory |
| ALFRED vintage support | `data/fred_vintage/vintages.parquet`; configured initial-release matrix for PAYEMS, CPI, PCE, PPI, etc. |
| CPI/PCE/PPI/ECI actual releases | configured under `fred.series.inflation_releases`; parquets exist for `CPIAUCSL`, `CPILFESL`, `PCEPI`, `PCEPILFE`, `PPIFIS`, `PPIFES`, `ECI*` |
| High-frequency labor nowcast | `research/REAL_ACTIVITY_NOWCAST.md`; claims, Indeed, Treasury withholding, SF Fed news sentiment |
| Rate/inflation transmission | `research/RATE_INFLATION_TRANSMISSION.md`; actual inflation prints + display-only calibration |
| Event calendar | `engine/event_calendar.py`; config already covers official release dates/manual rows |
| Prediction-market collector | `collectors/prediction_markets.py`; already targets FOMC/jobs-style event odds |
| Trial/forward ledgers | `data/trial_ledger.jsonl`, multiple forward logs, Oracle/Cycle grading discipline |
| PIT doctrine | `research/cycle_masterplan/S2_PIT.md`, `D5_PREDICTION.md`, ALFRED comments in `config.yml` |

The gap is not basic data plumbing. The gap is a dedicated release-target table, component-level replication logic, and a forward-graded pre-release ledger.

---

## 4. Proposed Machine

### 4.1 Program name

**Macro Release Lab**.

It should be an infrastructure program, not a page-only feature. It emits release nowcasts into the signal bus and later feeds dashboard/Oracle/Neural Web context.

### 4.2 Output artifacts

```text
data/release_lab/calendar.parquet
data/release_lab/releases.parquet
data/release_lab/input_snapshots/<release_id>.json
data/release_lab/predictions.jsonl
data/release_lab/outcomes.jsonl
data/release_lab/grades.parquet
data/release_lab/models/<target>.json
site/releasedata/release_lab.json
```

### 4.3 Core schema

`predictions.jsonl`, one frozen row per model snapshot:

```json
{
  "schema": 1,
  "prediction_id": "cpi_2026-06:first:2026-07-14T20:00Z:v1",
  "release_id": "CPI:2026-06:first",
  "target": "core_cpi_mom_sa",
  "asof": "2026-07-14T20:00:00Z",
  "release_time": "2026-07-15T12:30:00Z",
  "horizon_hours": 16.5,
  "model": "component_ensemble_v1",
  "prediction": 0.27,
  "interval_60": [0.19, 0.34],
  "interval_90": [0.08, 0.45],
  "consensus": 0.30,
  "surprise_distribution": {"p_hot": 0.31, "p_cold": 0.58, "p_inline": 0.11},
  "components": [
    {"name": "shelter", "contrib_pp": 0.14, "confidence": "medium"},
    {"name": "used_cars", "contrib_pp": -0.02, "confidence": "low"}
  ],
  "inputs_hash": "sha256:...",
  "data_vintage": "available_at_asof",
  "status": "frozen_pre_release"
}
```

`outcomes.jsonl`:

```json
{
  "release_id": "CPI:2026-06:first",
  "released_at": "2026-07-15T12:30:00Z",
  "actual_first": 0.29,
  "actual_latest": 0.29,
  "consensus": 0.30,
  "market_reaction": {
    "ust2y_30m_bp": -4.1,
    "spx_30m_pct": 0.42,
    "dxy_30m_pct": -0.18
  }
}
```

### 4.4 Model committee

Each target gets at least four model families. They are frozen separately and ensembled only after enough history:

| Family | CPI use | NFP use |
|---|---|---|
| Persistence/seasonal baseline | prior month, same-month seasonal, component AR | rolling average, seasonal residual, birth-death prior |
| Component bridge | gasoline/oil, shelter lag, used cars, airfare, food | claims, tax withholding, Indeed, ADP-like/free proxies |
| Ragged-edge factor | mixed-frequency inflation pressure | labor/common activity factor |
| Event/residual rules | methodology changes, unusual weather, strikes, health insurance resets | strikes, weather, government/education, reference week |
| Market/consensus prior | analyst consensus + event odds | analyst consensus + Polymarket/jobs odds |

Initial ensemble rule should be conservative:

```text
forecast = 0.35 * component_bridge
         + 0.25 * persistence
         + 0.20 * ragged_edge_factor
         + 0.15 * consensus_prior
         + 0.05 * event_residual
```

Weights must not be optimized until there are enough frozen pre-release observations. Before that, print them as pre-registered heuristics.

---

## 5. CPI Build Plan

### 5.1 Free/public data we can use now

| CPI component | Public/free proxy | Repo status |
|---|---|---|
| Headline/core actuals | FRED/ALFRED CPIAUCSL, CPILFESL | exists/configured |
| PCE/core PCE | FRED/ALFRED PCEPI, PCEPILFE | exists/configured |
| Gasoline | FRED gasoline CPI, WTI, EIA gas/retail proxy | partial; add explicit gas proxy collector if needed |
| Used vehicles | BLS CPI used cars, public Manheim monthly/midmonth if accessible | add collector |
| Shelter | BLS shelter/rent/OER, Zillow ZORI if accessible, FRED Case-Shiller, NTRR if public | partial |
| Airfares | BLS airfare CPI, BLS methodology, optional scrape later | add if useful |
| Food | BLS food CPI, commodity proxy, online grocery if feasible | partial |
| Sticky/flex/median | Atlanta/Cleveland FRED series | exists/configured |
| Expectations/market | breakevens, Cleveland expected inflation, UMich | exists/configured |

### 5.2 Component logic

**Headline CPI MoM**

```text
headline_mom =
  w_core_ex_shelter * core_ex_shelter_nowcast
  + w_shelter * shelter_nowcast
  + w_energy * energy_nowcast
  + w_food * food_nowcast
  + residual_seasonal
```

**Core CPI MoM**

```text
core_mom =
  w_shelter * shelter_nowcast
  + w_core_goods * goods_nowcast
  + w_core_services_ex_shelter * services_nowcast
  + residual_methodology
```

**Shelter model**

Use a stock-adjustment model, not a simple lag:

```text
new_lease_market_rent[t] -> renewal_adjustment[t+k] -> CPI rent six-month quote index
```

Parameters:

- lease reset distribution: 12-month dominant, smoothed
- continuing-tenant pass-through < 1
- CPI six-month rent comparison smoothing
- shrink to BLS shelter momentum when private rent proxy diverges

This is exactly where a simple AI model would get fooled by the "Zillow already fell, why is CPI shelter still hot?" trap.

### 5.3 CPI accuracy gate

For each print:

| Target | Grade |
|---|---|
| headline CPI MoM | MAE, RMSE, interval coverage, hit vs consensus |
| core CPI MoM | same |
| component contributions | signed component error |
| surprise | sign and magnitude of actual minus consensus |
| market reaction | does surprise bucket explain UST2Y/SPX/DXY move better than consensus alone? |

Promotion rule:

```text
display-only until >= 18 frozen CPI prints
decision/context badge only if:
  MAE improves on consensus by >= 10%
  interval_60 coverage in [50%, 75%]
  no split-half sign failure in surprise direction
```

---

## 6. NFP Build Plan

### 6.1 Public/free data we can use now

| Signal | Source | Repo status |
|---|---|---|
| PAYEMS first/later releases | ALFRED/FRED | configured |
| Initial claims / 4wk / continued claims | FRED | exists/configured |
| Indeed postings/new postings | FRED | exists/configured; private-use caution |
| Treasury withheld income/FICA taxes | FiscalData API | collector exists |
| AHE/hours | BLS/FRED CES series to add | partial |
| JOLTS openings/quits | FRED | add |
| Challenger layoffs | public but licensing/source check needed | deferred |
| ADP headline | public release scrape/API if permitted | optional |
| Homebase | public report, not clean API | optional/manual |
| Weather/strikes | NOAA/GDELT/BLS notes | deferred |
| Prediction markets | Polymarket collector | exists |

### 6.2 NFP component model

Targets:

- total nonfarm payrolls change
- private payrolls change
- unemployment rate
- average hourly earnings MoM
- average weekly hours
- revisions risk

The headline model should explicitly decompose:

```text
NFP_change =
  private_payroll_trend
  + government_payroll_trend
  + birth_death_residual
  + reference_week_adjustment
  + industry_mix_adjustment
  + seasonal_residual
```

**Private payroll trend**

Use a dynamic regression/factor model on:

- claims level/change and four-week average
- continued claims
- Indeed total/new postings, plus sector postings if allowed
- Treasury withholding growth, workday adjusted
- prior PAYEMS momentum and revision pattern
- consumer/business activity proxies already in repo

**Birth-death residual**

Do not try to exactly copy BLS ARIMA at first. Start with:

- month-of-year birth-death prior from published CES birth-death tables
- small-business formation proxy if free/public
- residual correction learned only from initial-release-vs-benchmark history
- uncertainty widened at turning points

**Reference-week adjustment**

Flags:

- strikes/labor actions
- severe weather during survey week
- federal/government education calendar
- holiday/pay-period anomalies

This can be mostly rule-based until data accrues.

### 6.3 NFP accuracy gate

NFP has too much noise for a hard point-estimate boast. Grade as:

| Grade | Meaning |
|---|---|
| MAE vs first release | did we beat consensus/ADP/simple prior? |
| Surprise sign | did actual-consensus sign match? |
| Interval coverage | did realized value land in stated distribution? |
| Revisions direction | did first-release-to-later revision risk match? |
| Market reaction | did surprise bucket explain UST2Y/DXY/SPX move? |

Promotion rule:

```text
display-only until >= 24 frozen NFP prints
context badge only if:
  MAE beats consensus by >= 8% OR surprise sign hit-rate >= 58%
  interval calibration acceptable
  no two-year holdout failure
```

NFP should never become a hard trade signal by itself. It can become an event-risk skew and Fed-reaction input.

---

## 7. Do We Need A Forward Ledger?

Yes. Without it this entire project should not be trusted.

The ledger is the product. The model is replaceable.

### 7.1 Ledger rules

- Every prediction is written before release.
- Keep the first frozen prediction for each `asof` bucket; never overwrite.
- Store input availability and hashes.
- Grade against first release and latest revised release separately.
- Grade consensus-relative surprise separately.
- Record market reaction windows separately.
- Require minimum sample sizes before using badges like "beats consensus."
- Print nulls and failures.

### 7.2 Maturity schedule

| Release | Prints/year | Minimum useful ledger |
|---|---:|---:|
| CPI | 12 | 18-24 prints |
| NFP | 12 | 24-36 prints |
| Jobless claims | 52 | 52-104 prints |
| ISM | 12 | 24 prints |
| Retail sales | 12 | 24 prints |
| GDP advance | 4 | 12+ prints, slow |

The first useful releases for rapid learning are weekly jobless claims and weekly/daily labor proxies. CPI/NFP need patience.

---

## 8. Novel Solution Ideas Worth Building

### 8.1 "Release twin" simulator

Build a miniature release engine for each major report:

- CPI twin: component weights + contribution bridge + uncertainty.
- NFP twin: CES-like decomposition + birth-death/residual + reference-week distortions.
- GDP twin: GDPNow-like component bridge.

The twin outputs not only a number but a component-level explanation and uncertainty source.

### 8.2 "Known-knowns vs unknown residual"

Before every release, split the forecast:

```text
Known by public market:
  gasoline, oil, prior inflation, claims, published source data

Hard proxy:
  rents, used cars, postings, withholding

Residual:
  services, methodology quirks, survey noise, birth-death
```

Then confidence comes from how much of the release weight is in known/observable components. This prevents false confidence.

### 8.3 Consensus-relative model, not just release model

Markets trade surprise. We need a second model:

```text
surprise = release_model - consensus_model
```

Consensus itself is noisy and late. Track consensus drift and model whether consensus has already incorporated the same public inputs. A model that predicts CPI but simply matches consensus is less useful than one that identifies where consensus is stale.

### 8.4 Market reaction function

Estimate conditional reaction:

```text
UST2Y move ~ CPI_core_surprise + labor_surprise + Fed_regime + positioning + vol_regime
```

Do not use this to predict every release reaction. Use it to classify whether an upcoming release is worth caring about.

### 8.5 Prediction-market arbitrage input

Use Polymarket/event odds as one prior, not an authority:

- `p_hot_cpi`, `p_jobs_above`, `p_fed_cut`
- compare market-implied release distribution to model distribution
- flag divergence, but grade it

The repo already has a prediction-market collector; the missing piece is a stable release target ontology.

### 8.6 Residual anomaly detector

After enough history, identify release categories where models systematically miss:

- BLS methodology reset months
- health insurance CPI annual reset
- school/government payroll calendar distortions
- strikes/weather
- rent model lag breakdown

These should feed a "residual warning" chip, not an overfit correction.

---

## 9. Implementation Plan

### Phase 0: Registry + ledger, no fancy model

Files:

```text
engine/release_lab/
  __init__.py
  calendar.py
  registry.py
  ledger.py
  grade.py
  consensus.py
scripts/release_lab_snapshot.py
scripts/release_lab_grade.py
research/ECONOMIC_RELEASE_REPLICATION_MACHINE.md
```

Deliver:

- release target registry for CPI/NFP
- freeze daily pre-release snapshots
- simple baselines: persistence, rolling seasonal, consensus prior if available
- grade first release/latest release/market reaction

### Phase 1: CPI component bridge

Add:

- CPI component weight table
- gasoline/energy bridge
- shelter lag model
- used-car bridge if public Manheim/midmonth source can be used
- core services persistence
- output to `site/releasedata/release_lab.json`

### Phase 2: NFP labor bridge

Add:

- claims/Indeed/withholding model
- government/private split
- birth-death prior table
- reference-week event flags
- NFP distribution output

### Phase 3: Release page + dashboard integration

Page should show:

- next major releases
- model vs consensus
- confidence bands
- component uncertainty
- track record card
- market reaction sensitivity

No hero hype. This is an operator desk.

### Phase 4: Model committee and promotion

Only after enough ledger rows:

- model-family leaderboard
- ensemble weights learned with rolling-origin CV
- retire broken components
- badge models by target and horizon

---

## 10. Guardrails

- **No scored trading signal until ledger maturity.** Display/context first.
- **First-release and revised-truth are separate.** Markets trade first release; economists may care about revised truth.
- **No LLM-originated numbers.** LLMs can summarize and identify event caveats, but cannot create estimates.
- **No post-release edits to predictions.** Ever.
- **No single-number output without interval.**
- **No authority/promotion language before the gate.**
- **Paid-data claims stay segregated.** If we later add PriceStats/LinkUp/Revelio/ADP/Truflation/etc., keep them behind source tags and licensing gates.

---

## 11. Build Verdict

Build it, but build it in this order:

1. **Ledger first.** Freeze/grade predictions before making the model clever.
2. **CPI component bridge first.** Highest public-data feasibility; fastest path to useful event-risk context.
3. **NFP bridge second.** Valuable, but inherently noisier and more dependent on private payroll/job-posting data.
4. **Market-reaction layer third.** This turns good estimates into useful risk decisions.
5. **Only then add paid data or advanced ML.**

The system can become genuinely useful without proprietary data. Proprietary data would improve coverage and reduce error, especially for goods prices and labor microdata, but the house edge is the discipline: component replication, PIT input snapshots, forward ledger grading, and honest uncertainty.

The best version of this is not an "economic prophet." It is a calibrated release radar that says, before the number drops: what the number is likely to be, which component is most uncertain, whether consensus is stale, what kind of surprise matters for the Fed, and whether the model has earned trust on this exact target.
