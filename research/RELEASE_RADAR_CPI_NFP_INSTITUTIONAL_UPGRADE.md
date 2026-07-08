# Release Radar CPI/NFP Institutional Upgrade Research

Status: research handoff
Date: 2026-07-08
Owner surface: `site/macro.html` / `templates/dashboard.html.j2`
Engine surface: `engine/release_forecast.py`, `engine/release_components_cpi.py`, `engine/release_components_nfp.py`, `scripts/build_release_forecast.py`
Purpose: map how Release Radar works today, how institutional desks model CPI and NFP, and what infrastructure is required to turn the current display-only release radar into a forward, auditable CPI/NFP estimation ledger that can eventually classify prints as hot/cold versus consensus.

## 1. Executive Thesis

Release Radar is no longer just a calendar widget. On current `origin/main`, it is a display-only Macro Release Intelligence pipeline that:

- projects upcoming CPI headline, CPI core, NFP, claims, AHE, and AWH releases;
- stores a forward ledger and scoreboard;
- renders projection points, interval cones, benchmark strips, surprise skew, component breakdowns, confidence composition, market-implied context, quirk flags, and release-day reaction context in `macro.html`;
- keeps a hard honesty boundary: it is not an equity signal, not a sizing rule, not a Neural Web authority source, and not a consensus estimate.

The system is already directionally right. The main gap is depth. The current CPI engine is a compact public-data ridge model with a few component-aware proxy legs. The current NFP engine is a compact payroll bridge with claims, withholding, ADP-like payroll data, hours, and a display-only private/government/birth-death decomposition. That is a useful first layer, but it is not yet an institutional release-replication machine.

To reach the level the user wants, the next build should not create a parallel lab. It should deepen the existing `release_forecast` contract into:

1. a point-in-time component ledger for CPI and NFP inputs;
2. an auditable pre-release estimate history at multiple cutoffs, such as T-14, T-7, T-3, T-1, and final pre-print;
3. an official first-print outcome ledger plus later revision ledger;
4. a consensus/market-expectation layer that is explicitly sourced, timestamped, and not faked;
5. component models that explain why the headline estimate moved, not just whether it moved;
6. calibration statistics that prove whether hot/cold calls versus benchmark or consensus are genuinely useful.

The near-term objective should be "better measurement and decomposition," not "immediate trading authority." The model needs 12 to 24 real forward prints before any hot/cold skill claim is credible, and probably 36 or more before a model committee can be trusted.

## 2. What Release Radar Does Today

### 2.1 UI Surface

The user-facing Release Radar section lives in `templates/dashboard.html.j2` and is emitted into `site/macro.html`. It fetches:

`macrodata/release_forecast.json`

The UI currently renders:

- upcoming releases and reference periods;
- point projections and p10/p25/p50/p75/p90 interval cones;
- the system's benchmark set;
- surprise-skew tags such as hotter, cooler, or inline versus the internal benchmark set;
- CPI component breakdowns and confidence composition;
- NFP revision risk and decomposition where available;
- market-implied context from prediction-market snapshots when available;
- quirk flags such as CPI January weights or NFP benchmark revisions;
- scoreboard snippets from scored ledger rows.

Important honesty note: the UI copy already says the comparison set is the system's own benchmark set, not street consensus. That line matters. It prevents the page from claiming a consensus edge before a real consensus feed exists.

### 2.2 Producer and Data Contract

The nightly producer is `scripts/build_release_forecast.py`. It emits:

- `data/release_forecast/latest.json`
- `site/macrodata/release_forecast.json`
- `data/release_forecast/forward_ledger.jsonl`
- `data/release_forecast/scoreboard.json`

`scripts/build_site.py` copies the latest release-forecast artifact into the site bundle when present and fails open when missing.

The Signal Bus and Synapse contracts already register the release forecast latest artifact, site copy, ledger, and scoreboard. This means the path of least resistance is to extend this contract, not add a second release system.

### 2.3 Current CPI Model

`engine/release_forecast.py` projects CPI headline and CPI core month-over-month prints using a point-in-time public-data feature set and a simple, transparent estimator:

- ridge regression with lambda 1.0;
- z-scored features;
- expanding-window walk-forward backtest;
- minimum training observation guards;
- quantile bands from walk-forward residuals;
- COVID shock-month exclusions where specified;
- ALFRED point-in-time availability law where vintage data exists;
- non-vintaged inputs marked through provenance.

Headline CPI features include:

- CPI headline own lags;
- sticky CPI momentum;
- median CPI momentum;
- flexible CPI momentum;
- PPI momentum;
- weekly gasoline momentum;
- shelter nowcast.

Core CPI features are similar but drop gasoline and use core CPI persistence instead of headline own-lag persistence.

`engine/release_components_cpi.py` adds the current CPI V2 component logic. It maps model features into display blocks:

- energy;
- shelter;
- pipeline;
- core persistence;
- residual or other.

The shelter nowcast is already more thoughtful than a naive lag. It blends BLS shelter momentum with Zillow ZORI-style rent momentum, applies a lag, and includes a divergence guard when rent proxy momentum and official shelter momentum disagree too sharply.

Current CPI limitation: this is not yet a full CPI component-accounting model. The component display is a feature-contribution attribution from the ridge model, not a BLS-style weighted component bridge using official relative importance weights and subcomponent price estimates.

### 2.4 Current NFP Model

`engine/release_components_nfp.py` builds the NFP feature table and decomposition. The current NFP feature set includes:

- PAYEMS own lags;
- initial and continued claims around the survey week;
- Treasury withheld-tax growth;
- manufacturing aggregate weekly hours momentum;
- ADP-style private payrolls if available.

The target is the initial or first-print PAYEMS payroll change, not the fully revised "truth." That is the right target for release trading and hot/cold classification because the market reacts to the first release.

Current display-only decomposition separates:

- private trend;
- government trend;
- birth-death or residual prior;
- residual plug.

The engine also computes NFP revision risk from the gap between initial and latest PAYEMS changes over a trailing window.

Current NFP limitation: the model does not yet have a full supersector/industry bridge, response-rate stress, strike/weather/calendar flags beyond simple quirk logic, or a richer birth-death forecast tied to the BLS net birth-death process.

### 2.5 Current Ledger and Scoreboard

The current ledger is a real strength. `forward_ledger.jsonl` is append-only and includes projection rows and scored rows. The scoreboard is recomputed from scored ledger rows only, preserving the forward-only honesty rule.

Current metrics include, or are set up to include:

- MAE for own forecast;
- MAE for naive/trailing/AR/Cleveland-style benchmarks;
- p10-p90 coverage;
- p25-p75 coverage;
- skew hit rate;
- reaction context.

Current limitation: the ledger does not yet freeze a full component-input snapshot for each forecast cutoff, and it cannot yet score hot/cold versus true consensus unless a timestamped consensus source is added.

## 3. Institutional CPI Modeling: What Serious Desks Try to Replicate

### 3.1 CPI Is a Weighted Component System, Not One Time Series

The Bureau of Labor Statistics CPI process is built from item-area indexes and expenditure weights. The official calculation uses thousands of item-area combinations before rolling up to the headline indexes. BLS methodology describes 243 basic items across 32 geographic areas, or 7,776 item-area combinations. It uses Consumer Expenditure Survey weights for upper-level aggregation, and it collects or sources prices through commodity/service sampling, rent panels, and selected secondary datasets.

This has one practical implication for Release Radar:

The long-run goal cannot be a single black-box CPI model. It needs a component ledger that can answer:

- what official CPI bucket is being estimated;
- what its latest relative importance weight is;
- which public proxy is used;
- when that proxy was first available;
- whether the proxy estimates price level, price change, or only directional pressure;
- how much that component contributed to the headline and core estimate;
- how stale or unreliable that component is for the current release month.

### 3.2 CPI Institutional Desk Architecture

An institutional CPI nowcast usually has these layers:

1. Official release calendar and cutoff discipline
   - Know the CPI reference month, release date, data cutoffs, and seasonal-adjustment caveats.
   - Freeze estimates at standard checkpoints so the desk can audit forecast drift.

2. Component accounting
   - Start with the BLS relative importance table.
   - Create target groups: food, energy, core goods, shelter, core services ex shelter, medical, transport, apparel, recreation, education, communication, and other.
   - Convert component-level price-change estimates into contribution points.

3. High-frequency proxy ingestion
   - Daily/weekly gasoline and energy prices.
   - Online rent and new-lease rent indexes.
   - Used-car auctions and dealer/retail prices.
   - Airfare/hotel/travel proxies.
   - Grocery and menu-price proxies.
   - PPI and import-price pipeline data.

4. Official-method quirks
   - January CPI weights and seasonal-factor refreshes.
   - Health-insurance methodology updates.
   - Shelter rent panel lag.
   - Used-car source revisions.
   - Airfare and lodging volatility.

5. Model committee
   - A component bridge estimate.
   - A statistical time-series estimate.
   - A mixed-frequency nowcast.
   - A market-implied or consensus prior.
   - A human override ledger only if the institution permits it, with reason codes.

6. Scoring
   - Score versus first print and latest revised value separately.
   - Score headline, core, supercore, and key components separately.
   - Score directional hot/cold versus consensus separately from MAE.

### 3.3 CPI Component Research Map

| CPI block | Official concept | Institutional proxy set | Current Release Radar status | Needed build |
| --- | --- | --- | --- | --- |
| Headline all-items | Weighted aggregate of all CPI categories | Full component bridge plus top-down statistical model | Top-down ridge model exists | Add component-weight accounting and contribution ledger |
| Core CPI | All items less food and energy | Core component bridge, sticky/median CPI, wages, services demand | Top-down ridge model exists | Add core-services, core-goods, and shelter bridge |
| Energy gasoline | Motor fuel and gasoline indexes | Weekly retail gasoline, RBOB, crude, EIA, AAA where licensed/allowed | `GASREGW` style feature exists | Convert into monthly CPI gasoline component contribution |
| Energy utilities | Electricity and utility gas service | EIA electricity/gas prices, utility tariff changes, weather degree days | Mostly absent | Add utility proxy series and weather-normalized layer |
| Food at home | Grocery categories | PPI food, USDA commodity data, scanner/online grocery if available | Mostly absent | Public proxy bridge first; paid/scanner data later only if licensed |
| Food away from home | Restaurant/menu prices | Wages, food input costs, reservation/restaurant data, online menus | Mostly absent | Simple wage/input pass-through model |
| Shelter rent | Rent of primary residence | BLS rent lag, ZORI, Apartment List, CoreLogic, Redfin, vacancy proxies | Shelter nowcast exists | Expand to rent/OER split and contribution math |
| Shelter OER | Owners' equivalent rent | OER shares, lease-renewal lag, rent panel lag model, home price lag as weak context | Blended shelter proxy only | Add OER-specific lag and weight treatment |
| Used vehicles | Used cars and trucks | Manheim, Black Book, JD Power, auction prices, dealer inventory | Absent | Add public Manheim-like lane if license permits; otherwise keep absent |
| New vehicles | New cars/trucks | Incentives, inventory, ATP, production, dealer margins | Absent | Add optional public proxy; do not fake precision |
| Airfares | Passenger fares | Airfare scrapes, jet fuel, TSA volumes, route mix | Absent | Add volatile component flag and public proxy experiment |
| Lodging | Hotels/motels | STR/ADR if licensed, public hotel occupancy/ADR proxies, travel demand | Absent | Add only if source is reliable and timestamped |
| Medical care services | Medical professional/hospital services | PPI health services, wage costs, administered-price calendars | Mostly absent | Add slow-moving services bridge |
| Health insurance | Retained earnings method | BLS methodology calendar, NAIC/insurer margin context | Quirk flag exists | Add explicit health-insurance update module |
| Apparel | Apparel prices | Import prices, online prices, retail discounts | Absent | Low-priority volatile core-goods proxy |
| Core services ex shelter | Services inflation excluding shelter | AHE/ECI, wages, ISM services prices, NFIB comp plans | Partly through sticky/median CPI | Build supercore target and wage/pass-through layer |
| Pipeline goods | Goods cost pressure | PPI, import prices, supplier delivery, shipping | PPI momentum exists | Decompose by goods block and lag structure |

### 3.4 CPI Algorithms Worth Building

Release Radar should use multiple model families, but only after the input ledger exists. Recommended sequence:

1. Component bridge model
   - Estimate each major CPI component's MoM change.
   - Multiply by current BLS relative importance.
   - Sum into headline, core, and supercore contributions.
   - This is the most explainable institutional baseline.

2. Top-down statistical model
   - Keep the current ridge model as the transparent baseline.
   - Add elastic net only if it improves out-of-sample stability.
   - Do not over-optimize monthly CPI with too many features.

3. Mixed-frequency model
   - Use MIDAS-style or state-space logic for daily/weekly proxies such as gasoline, rents, job postings, and withholding.
   - Preserve point-in-time cutoffs: a T-7 forecast must not see T-1 data.

4. Dynamic factor model
   - Extract common inflation pressure from sticky CPI, median CPI, PPI, import prices, wages, and services surveys.
   - Useful for core/supercore, less useful for gasoline-heavy headline noise.

5. Bayesian hierarchical component model
   - Shrink noisy small components toward group-level priors.
   - Let high-weight components such as shelter dominate only when the proxy is fresh enough.

6. Quantile/conformal uncertainty layer
   - Forecast the distribution, not only the point.
   - Score p10-p90 coverage, p25-p75 coverage, and calibration by component block.

7. Model committee after maturity
   - Only build after enough forward prints exist.
   - Suggested minimum: 18 scored CPI releases for dashboard display of committee performance, 36 for any serious claim.

## 4. Institutional NFP Modeling: What Serious Desks Try to Replicate

### 4.1 NFP Is a First-Print Survey Estimate

NFP is not direct payroll truth. BLS describes the Employment Situation as using two surveys:

- the household survey, with roughly 60,000 eligible households;
- the establishment survey, with about 119,000 businesses and government agencies covering roughly 622,000 worksites.

The establishment survey reference period is the pay period that includes the 12th day of the month. That detail matters for every high-frequency proxy. A payroll processor series or claims series is more useful when it is aligned to the survey week, not simply averaged over the calendar month.

The CES also uses a net birth-death model because the sample cannot immediately capture business births and deaths. This creates a recurring residual bucket that is not well explained by claims alone.

### 4.2 NFP Institutional Desk Architecture

An institutional payrolls nowcast usually has these layers:

1. Survey-week labor stress
   - Initial claims and continued claims around the survey week.
   - Holiday distortions and state-processing anomalies.
   - Weather, strikes, and school-calendar effects.

2. Private payroll processors
   - ADP and other payroll data where available.
   - Homebase/time-clock data where licensed or public enough.
   - Industry and firm-size split if available.

3. Wage/income flow
   - Treasury withheld taxes as a high-frequency nominal labor-income proxy.
   - Hours and earnings to separate jobs from pay-rate effects.

4. Labor demand
   - Indeed job postings, JOLTS openings, hiring plans, NFIB, ISM employment.
   - This is often more useful for trend than for the exact monthly print.

5. Industry bridge
   - Private services, goods-producing, construction, manufacturing, government, education/health, leisure/hospitality, temp help, retail.
   - This matters because payroll misses often come from one or two sectors.

6. Birth-death and benchmark residual
   - Explicit residual prior by month and business-cycle regime.
   - Track revisions and benchmark drift separately from first-print accuracy.

7. Consensus and whisper layer
   - Consensus should be a real feed or source with first-seen timestamp.
   - Without that, Release Radar should say "benchmark," not "consensus."

### 4.3 NFP Input Research Map

| NFP block | Official concept | Institutional proxy set | Current Release Radar status | Needed build |
| --- | --- | --- | --- | --- |
| Headline PAYEMS | CES total nonfarm first-print payroll change | Industry bridge plus top-down labor factor | Top-down ridge exists | Add supersector/industry contribution bridge |
| Private payrolls | Private-sector employment | ADP, payroll processors, withholding, job postings | ADP-style feature exists if file present | Reconcile local ADP series id and add coverage diagnostics |
| Government payrolls | Federal/state/local payrolls | Education calendar, census hiring, state/local budgets | Simple government trend component exists | Add school-calendar and census/government event flags |
| Claims stress | Separations proxy | Initial claims, continued claims, insured unemployment | Survey-week claims features exist | Add claims anomaly/stale state flags and holiday adjustment confidence |
| Labor income | Wage and hours flow | Treasury withholding, AHE, AWH | Withheld tax and AWHMAN exist | Add nominal-income decomposition and hours/earnings cross-check |
| Labor demand | Hiring appetite | Indeed postings, JOLTS, NFIB, ISM employment | Some series exist in repo, not fully bridged | Add demand factor and lead/lag tests |
| Birth-death | Net firm creation/destruction residual | BLS net birth-death table, QCEW history, calendar-month priors | Residual prior display exists | Build explicit birth-death source table and prior backtest |
| Revisions | First-print to later-print drift | Response rates, benchmark revisions, sector diffusion, historical revision patterns | Revision-risk display exists | Add first/second/final vintage tracking and revision model |
| Strikes/weather | Temporary survey-week disruptions | BLS strike data, NOAA weather, shutdowns, disasters | Quirk flags partial | Add event flags with no model authority until tested |
| Household labor | Unemployment, labor force, flows | CPS, CHURN-like flow nowcast, claims, job-finding rates | Mostly absent | Context-only unemployment risk lane |

### 4.4 NFP Algorithms Worth Building

1. Industry bridge
   - Forecast supersector changes and sum to total NFP.
   - Score each supersector against first-print CES initial estimates.
   - Keep residual as a visible component, not hidden error.

2. Survey-week mixed-frequency model
   - Align claims, ADP, withholding, and job postings to the pay period including the 12th.
   - Create T-14/T-7/T-3/T-1 forecasts so accuracy can be scored by information date.

3. Birth-death residual model
   - Use BLS published net birth-death values and QCEW benchmark history where available.
   - Estimate month-of-year and cycle-regime priors.
   - Treat it as a residual with a confidence band, not a hard correction.

4. Revision-risk model
   - Predict not just the first print, but the likely direction and size of first-to-latest revisions.
   - Useful for "market may fade this print later" context, but not for release-day hot/cold.

5. Labor factor model
   - Combine claims, postings, JOLTS, ADP, withholding, hours, and payroll trend into a latent labor-momentum factor.
   - Use this as a benchmark to the industry bridge, not a replacement.

6. Quantile and calibration layer
   - For NFP, interval quality matters more than false precision.
   - Score directional hot/cold hit rate versus benchmark and consensus separately.

## 5. Hot/Cold Versus Consensus: The Missing Contract

Release Radar can already say hotter/cooler versus its own benchmark set. It cannot honestly say hotter/cooler versus street consensus until a consensus data lane exists.

Minimum consensus contract:

```json
{
  "release_id": "cpi_headline:2026-06",
  "target": "cpi_headline_mom_sa",
  "source": "licensed_or_public_source_name",
  "source_kind": "street_consensus|prediction_market|survey|manual_research",
  "value": 0.23,
  "unit": "percent_mom",
  "first_seen_utc": "2026-07-13T14:00:00Z",
  "last_seen_utc": "2026-07-14T11:59:00Z",
  "asof_cutoff_utc": "2026-07-14T12:00:00Z",
  "license": "approved_for_internal_modeling_or_display",
  "confidence": "source_metadata_only"
}
```

Rules:

- Do not scrape or imply Bloomberg/Reuters consensus unless licensed.
- Do not label prediction-market implied values as consensus.
- Store consensus snapshots separately from model inputs so the model can be scored against consensus without necessarily training on consensus.
- A hot/cold call should be stored before the release, frozen, and scored after the release.
- Score hot/cold versus:
  - internal benchmark median;
  - market-implied if available;
  - real street consensus if available;
  - optional whisper estimate if explicitly sourced.

Recommended hot/cold metrics:

- directional hit rate;
- Brier score if using probabilities;
- expected calibration error;
- average surprise captured in basis points or payroll thousands;
- false-hot and false-cold rates;
- hit rate by release type, era, and volatility regime;
- market-reaction usefulness, tracked separately from macro accuracy.

## 6. Forward Ledger V3: Required Structure

The current ledger is the right foundation. It needs richer rows, not a new file family.

Recommended row families:

1. `projection`
   - Frozen estimate for a target and cutoff.
   - Includes point, bands, components, input snapshot hash, benchmark set, quirk flags, and source coverage.

2. `input_snapshot`
   - Full manifest of feature values known at that cutoff.
   - Stores first-seen timestamps, source vintage, stale flags, and transformation notes.

3. `consensus_snapshot`
   - Street consensus or market-implied value with source metadata.
   - Must not be fabricated from internal benchmarks.

4. `actual_first_print`
   - Official initial release value and timestamp.
   - Target for release-day scoring.

5. `actual_revision`
   - Later official revised values.
   - Target for revision-risk scoring.

6. `reaction`
   - Market move windows around release, such as 2y/10y yields, dollar, equity futures, breakevens.
   - Context only.

7. `score`
   - MAE, direction, calibration, interval coverage, hot/cold classification result.

Suggested projection schema:

```json
{
  "row_type": "projection",
  "schema": "release_forecast_ledger.v3",
  "prediction_id": "cpi_headline:2026-06:T-1:2026-07-13T21:00:00Z",
  "release_id": "cpi_headline:2026-06",
  "target": "cpi_headline_mom_sa",
  "cutoff_label": "T-1",
  "asof_utc": "2026-07-13T21:00:00Z",
  "release_date": "2026-07-14",
  "point": 0.23,
  "unit": "percent_mom",
  "interval": {"p10": 0.09, "p25": 0.16, "p50": 0.23, "p75": 0.31, "p90": 0.39},
  "components": [
    {"block": "shelter", "contribution": 0.14, "confidence": 0.66},
    {"block": "energy", "contribution": -0.03, "confidence": 0.82}
  ],
  "benchmarks": {
    "naive_prior": 0.20,
    "trailing_3m": 0.18,
    "ar_model": 0.21,
    "cleveland_nowcast": 0.25,
    "market_implied": 0.24,
    "street_consensus": null
  },
  "hot_cold": {
    "versus_internal_benchmark": "hotter",
    "versus_market_implied": "inline",
    "versus_street_consensus": "unavailable"
  },
  "source_coverage": {
    "weight_coverage": 0.91,
    "fresh_proxy_coverage": 0.63,
    "non_vintaged_share": 0.22
  },
  "input_snapshot_hash": "sha256:...",
  "display_only": true,
  "authority": "none"
}
```

## 7. Infrastructure Required

### 7.1 New or Expanded Data Artifacts

All paths should stay under the existing `release_forecast` family.

| Artifact | Purpose |
| --- | --- |
| `data/release_forecast/component_weights/cpi_relative_importance.parquet` | Official CPI relative-importance weights by release vintage and category |
| `data/release_forecast/component_map/cpi_component_map.yml` | Mapping from BLS item categories to Release Radar blocks |
| `data/release_forecast/component_inputs/*.parquet` | Public proxy inputs for energy, food, shelter, vehicles, airfares, medical, services |
| `data/release_forecast/input_snapshots/*.json` | Frozen feature manifests for each prediction cutoff |
| `data/release_forecast/consensus_snapshots.jsonl` | Real consensus or expectation snapshots with source/license metadata |
| `data/release_forecast/forward_ledger.jsonl` | Expanded append-only ledger; keep current file |
| `data/release_forecast/scoreboard.json` | Expanded scoreboard with calibration and hot/cold metrics |
| `site/macrodata/release_forecast.json` | Compact public display payload |

### 7.2 Engine Modules

Recommended additions:

| Module | Responsibility |
| --- | --- |
| `engine/release_component_weights.py` | Load BLS CPI weights and map them to model blocks |
| `engine/release_cpi_bridge.py` | Component contribution model for headline/core/supercore CPI |
| `engine/release_nfp_industry_bridge.py` | Supersector/industry NFP bridge and component decomposition |
| `engine/release_input_snapshots.py` | Freeze source values, first-seen timestamps, hashes, stale flags |
| `engine/release_consensus.py` | Load allowed consensus/market-expectation snapshots |
| `engine/release_calibration.py` | Directional, interval, Brier, and coverage scoring |

Existing modules should stay in place:

- `engine/release_forecast.py` remains the top-level forecast API.
- `engine/release_components_cpi.py` can be evolved or wrapped by the component bridge.
- `engine/release_components_nfp.py` can be evolved or wrapped by the industry bridge.
- `engine/release_market_context.py` remains display/context only.
- `engine/release_quirks.py` remains metadata only unless a preregistered model later proves value.

### 7.3 Tests and Gates

Required test classes before any display upgrade:

- point-in-time availability tests for all new inputs;
- no lookahead tests for CPI weights, BLS component releases, and consensus snapshots;
- weight-sum tests for CPI component aggregation;
- component contribution reconciliation tests;
- stale-source and missing-source rendering tests;
- ledger idempotence tests;
- cutoff tests for T-14/T-7/T-3/T-1 forecasts;
- no-authority tests ensuring output remains display-only;
- ADP scale and series-id tests;
- scoreboard tests verifying only forward-scored rows enter live track records.

### 7.4 Data Quality Flags

Every prediction should carry:

- `fresh_proxy_coverage`: share of weighted component model backed by fresh current-month data;
- `weight_coverage`: share of CPI relative importance mapped to components;
- `vintaged_share`: share of model inputs with proper ALFRED or equivalent first-seen availability;
- `non_vintaged_share`: share requiring explicit caveat;
- `source_stale_flags`: named stale or missing inputs;
- `quirk_flags`: official release mechanics such as January CPI weights or NFP benchmark revisions;
- `model_maturity`: number of forward-scored releases by target.

This lets the UI tell the user when the model is data-rich versus extrapolating from priors.

## 8. Proposed Build Roadmap

### Phase 0: Hardening and Contracts, 1 to 2 weeks

Goal: make the existing Release Radar more auditable without changing its forecast authority.

Build:

- confirm the ADP local-series contract. `config.yml` references `ADPMNUSNERSA`, while `engine/release_components_nfp.py` currently reads `ADPNFRPRIVSA.parquet`; reconcile or document the alias;
- add a release-input coverage report to the nightly producer;
- add ledger cutoff labels even if only the final pre-print forecast is populated at first;
- add `input_snapshot_hash` and source coverage fields;
- write `research/release_forecast/PREREG_V3_CPI_COMPONENTS.md`;
- write `research/release_forecast/PREREG_NFP_INDUSTRY_BRIDGE_V2.md`;
- add tests that prevent any new field from being used as a scoring or sizing signal.

Success definition:

- no change in public authority;
- more complete provenance;
- clear missing-input flags;
- the current UI continues to render.

### Phase 1: CPI Component Ledger, 2 to 4 weeks

Goal: convert CPI from feature attribution to component accounting.

Build:

- BLS relative-importance collector;
- CPI component taxonomy and mapping file;
- official component target lake for all major CPI blocks;
- contribution calculator for headline, core, and supercore;
- initial public proxy matrix for energy, shelter, food, vehicles, airfares, medical, services, and goods;
- component-level backtest using only point-in-time-available data where possible.

Success definition:

- every headline/core estimate can show weighted component contributions;
- the ledger records which components were model-driven, proxy-driven, stale, or prior-driven;
- component sums reconcile to headline/core targets.

### Phase 2: CPI Institutional Nowcast V3, 4 to 8 weeks

Goal: create a shadow component nowcast that competes against the current top-down ridge.

Build:

- component bridge model;
- mixed-frequency energy/shelter/vehicle modules;
- core-services wage/pass-through module;
- model comparison report versus current ridge, naive, trailing, AR, and Cleveland-style benchmark;
- expanded interval calibration;
- UI display only after preregistered backtest passes.

Success definition:

- V3 is better or more explainable than V2 in walk-forward tests;
- it does not hide missing data behind false precision;
- Release Radar can explain which components drove the forecast revision since the prior cutoff.

### Phase 3: NFP Industry Bridge, 4 to 8 weeks

Goal: move NFP from top-down payroll bridge to industry contribution model.

Build:

- CES supersector first-print target lake;
- private/government/industry contribution model;
- claims, withholding, ADP, Indeed, JOLTS, hours, and earnings alignment by survey week;
- birth-death source table and prior;
- strike/weather/calendar event flags;
- revision-risk score by sector if feasible.

Success definition:

- NFP estimate has visible private, government, industry, birth-death, and residual components;
- first-print accuracy is scored separately from later revision accuracy;
- the model can explain why payrolls look strong/weak before release day.

### Phase 4: Consensus and Hot/Cold Skill, after 12 to 24 forward prints

Goal: start measuring whether Release Radar can beat or complement consensus.

Build:

- licensed or approved consensus snapshot source;
- hot/cold probability layer versus consensus;
- Brier/calibration reports;
- dashboard track record by target and cutoff;
- abstention rule when confidence or source coverage is too low.

Success definition:

- every hot/cold claim has a frozen pre-release row;
- hit rate and calibration are visible;
- the system can abstain;
- no hot/cold claim is made where consensus was unavailable.

### Phase 5: Model Committee, after 36 or more forward prints

Goal: consider a blended model only after enough live evidence exists.

Build:

- champion/challenger model registry;
- fixed-weight committee first, adaptive weights only after sufficient evidence;
- model retirement rules;
- era and volatility-regime diagnostics.

Success definition:

- committee improves accuracy or calibration out of sample;
- component explanations remain readable;
- no model receives trading authority by implication.

## 9. UI Upgrade Ideas for `macro.html`

Keep UI changes compact and mobile-safe. The current page is already dense.

Recommended additions after the data exists:

- "What changed since last snapshot" line for each release.
- Component contribution waterfall for CPI headline/core.
- Source coverage chip: fresh, partial, stale, or prior-heavy.
- Consensus availability chip: unavailable, market-implied only, or street consensus.
- Accuracy mini-table by target: CPI headline, CPI core, NFP, AHE, AWH.
- Cutoff selector: final, T-1, T-3, T-7, T-14.
- Abstention display when source coverage is too low.

Avoid:

- long explanatory prose inside the panel;
- fake precision;
- claims that "market expects" unless the source is truly a market or consensus source;
- adding another dashboard card that repeats the same projection.

## 10. Already Covered / Do Not Rebuild

These are hard boundaries from the existing Macro Release Intelligence masterplan and repo contracts:

- Do not create `engine/release_lab` or `data/release_lab`. The adopted system is `release_forecast`.
- Do not use LLMs to originate CPI or NFP forecasts.
- Do not let Release Radar influence equity scoring, entries, sizing, event-risk dampeners, or Neural Web authority.
- Do not claim consensus without a real timestamped consensus source.
- Do not fuse prediction-market data into the model math unless a future preregistration explicitly allows it. It is context only today.
- Do not restart the claims model attempt without program-level adjudication. Claims is benchmark-only because prior tests failed.
- Do not duplicate the active over/under-expectation work in PR #1889. Treat it as in-flight and build around its final contract after merge.
- Do not present backtest rows as live track record. The live scoreboard must remain forward-only.

## 11. Open Questions for Fable / Next Implementer

1. Which consensus source is legally usable for display and/or internal scoring?
2. Should CPI component weights be pulled directly from BLS tables every release cycle, or manually versioned until a collector is stable?
3. Is public Manheim/vehicle data licensed enough for model input, or should used vehicles remain prior-driven until a compliant source exists?
4. Should CPI supercore be a first-class target in Release Radar V3?
5. Should NFP industry bridge start with broad supersectors only, or go deeper into detailed CES industries?
6. What is the minimum source-coverage threshold below which the UI should abstain from hot/cold labels?
7. Should consensus be used only for scoring hot/cold, or also as an input to the point forecast after enough evidence exists?
8. Should market reaction scoring focus on 2y yields, 10y yields, Fed funds futures, DXY, equities, breakevens, or a compact bundle?

## 12. Source Notes Used for This Research

Official and public sources consulted for the institutional design:

- BLS CPI calculation methodology: https://www.bls.gov/opub/hom/cpi/calculation.htm
- BLS CPI item aggregation methodology: https://www.bls.gov/opub/hom/cpi/calculation.htm#item-aggregation
- BLS CPI shelter factsheet: https://www.bls.gov/cpi/factsheets/owners-equivalent-rent-and-rent.htm
- BLS CPI current relative-importance/release table example: https://www.bls.gov/news.release/cpi.t01.htm
- Cleveland Fed inflation nowcasting description: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
- BLS Employment Situation technical note: https://www.bls.gov/news.release/empsit.tn.htm
- BLS CES net birth-death model notes: https://www.bls.gov/web/empsit/cesbd.htm
- BLS CES benchmark and seasonal-adjustment technical notes: https://www.bls.gov/web/empsit/cesbmart.htm
- ADP National Employment Report description: https://adpemploymentreport.com/
- Indeed Hiring Lab job postings index / FRED notes: https://fred.stlouisfed.org/series/IHLIDXUS
- U.S. Treasury Daily Treasury Statement overview: https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance
- Chicago Fed CHURN description: https://www.chicagofed.org/research/data/churn

Repo-native sources reviewed:

- `research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md`
- `research/ECONOMIC_RELEASE_REPLICATION_MACHINE.md`
- `research/DO_NOT_REBUILD.md`
- `research/release_forecast/PREREG_V1.md`
- `research/release_forecast/PREREG_V2.md`
- `research/release_forecast/PREREG_NFP_DECOMP_V1.md`
- `research/release_forecast/CLAIMS_BACKTEST.md`
- `engine/release_forecast.py`
- `engine/release_components_cpi.py`
- `engine/release_components_nfp.py`
- `engine/release_market_context.py`
- `engine/release_quirks.py`
- `scripts/build_release_forecast.py`
- `templates/dashboard.html.j2`

## 13. One-Screen Fable Brief

Release Radar already has the right skeleton: point-in-time ridge projections, component display, market context, quirk flags, forward ledger, and scoreboard. The next leap is not a new model name. It is a deeper evidence ledger.

Build CPI V3 as component accounting first:

- official weights;
- component map;
- proxy freshness;
- contribution math;
- source coverage;
- interval calibration.

Build NFP V2 as an industry bridge:

- supersector targets;
- survey-week alignment;
- ADP/claims/withholding/postings/hours inputs;
- birth-death residual;
- revision risk.

Add consensus only when legally/source-valid. Until then, keep saying "benchmark," not "consensus."

The strongest near-term upgrade is a frozen input snapshot and component ledger. That gives every future forecast a receipt, lets the model explain itself, and creates the data required to know whether hot/cold prediction skill is real.
