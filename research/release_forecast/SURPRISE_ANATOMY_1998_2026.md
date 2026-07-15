# Surprise Anatomy Catalog 1998–2026 (MRI-R38 / Track S)

Static reference table of macro-print surprise episodes where the miss was driven by
a **structural/mechanical cause** rather than by the economy behaving differently from
forecasters' models.  Used by the Track S print-integrity chip to annotate History
cards.  See §12.3 of MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md.

**Display-only.** No value from this catalog shifts any point estimate, interval, or
skew (MRI-R20 law).  Null-prints (episodes where the cause was genuinely unknowable
ex ante) are listed in a dedicated section below with honest attribution.

---

## Column key

| Column | Description |
|---|---|
| date | Reference period (YYYY-MM) or YYYY-MM-DD for event date |
| release | Economic release (NFP / CPI / Claims / etc.) |
| print_vs_exp | Direction of miss vs professional-forecaster consensus |
| cause_family | Taxonomy label (see Cause-family glossary below) |
| knowable_ex_ante | Could a diligent analyst have anticipated the distortion BEFORE the print? |
| free_signal | Observable leading indicator or data source available before the print |

### Cause-family glossary

- **STRIKE** — active major work stoppage covering NFP reference week
- **HURRICANE** — hurricane landfall near NFP reference week / CPI survey window
- **CENSUS_HIRING** — decennial census temporary government workers
- **BENCHMARK_REVISION** — annual CES benchmark + seasonal-factor revision
- **SEASONAL_ANOMALY** — seasonal-adjustment model breaks under unusual calendar or COVID baseline
- **METHODOLOGY_CHANGE** — BLS methodology or weight/table update shifts the measured level
- **COLLECTION_DISRUPTION** — government shutdown, pandemic, or system failure lowers response rates
- **COMPOSITION_SHIFT** — rapid shift in the spending/employment mix the seasonal model was not calibrated to
- **REOPEN_SURGE** — reopening-velocity spike overwhelming seasonal adjustment (COVID era)
- **HEALTH_INS_RESET** — BLS semiannual retained-earnings health-insurance update (CPI)
- **TARIFF_PASSTHROUGH** — tariff-driven import price spike feeding into measured CPI
- **ENERGY_SURGE** — rapid energy price move inflating headline CPI vs core expectations
- **BIRTH_DEATH** — net business-formation (birth-death) model bias (over/under in trend breaks)

---

## Episode catalog

### Jobless-recovery era (2001–2003)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2001-03 | NFP | MISS (−350k, much worse than exp) | SEASONAL_ANOMALY | PARTIAL | Manufacturing ISM sub-50 for months; leading indicators deteriorating |
| 2002-01 | NFP | BEAT (benchmark revision added ~100k/mo) | BENCHMARK_REVISION | YES | September preliminary benchmark estimate; published in Oct prior year |
| 2003-01 | NFP | BEAT (benchmark revision) | BENCHMARK_REVISION | YES | September preliminary benchmark estimate |

**Notes:** The 2001 recession period produced a sequence of weaker-than-expected NFP prints.
The seasonal factors had been calibrated on the 1990s expansion and systematically
underestimated the pace of job-shedding when the trend broke.  The knowable signal was
the September preliminary benchmark revision (published annually by BLS each October),
which traders with BLS literacy could read for direction.

---

### Hurricane Katrina (2005-09)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2005-09 | NFP | MASSIVE MISS (−35k vs +150k exp; hurricane-adjusted true ~+100k) | HURRICANE | YES | Katrina landfall Aug 29; NFP reference week Aug 7–13 (pre-landfall) but Sept count depressed by displacement |
| 2005-10 | NFP | BEAT (Katrina bounce: +56k vs −35k exp) | HURRICANE | YES | Historical pattern: hurricane-month miss followed by statistical rebound |
| 2005-09 | CPI | MASSIVE BEAT (energy surge: +1.2% MoM, largest since 1990) | HURRICANE + ENERGY_SURGE | YES | Katrina disrupted ~25% of US Gulf oil production; visible in spot prices pre-print |

**Source:** BLS CES release notes, September 2005; BLS CPI release September 2005.
https://www.bls.gov/news.release/archives/empsit_10072005.pdf
https://www.bls.gov/news.release/archives/cpi_10192005.pdf

---

### GM/UAW Strike (2019-10)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2019-10 | NFP | MISS (−50k from strike; headline +128k vs ~+180k exp before adjustment) | STRIKE | YES | UAW strike against GM began Sep 16, 2019; ref week Sep 6–12 (pre-strike); Oct ref week Oct 6–12 caught ~49,000 workers |
| 2019-10 | NFP (MFG sub) | MISS (manufacturing −42k, all GM-related) | STRIKE | YES | BLS work-stoppages listing updated monthly |

**Notes:** The UAW-GM strike began September 16, 2019, affecting ~49,000 workers.
The October 2019 NFP reference week (October 6–12) fell during the strike.  BLS's
monthly work-stoppages report (published with a ~1-month lag) had already flagged the
stoppage.  Professional forecasters who adjusted for the strike were close to the
"true" underlying labor market.
**Source:** BLS Employment Situation Oct 2019; BLS Work Stoppages listing.
https://www.bls.gov/news.release/archives/empsit_11012019.pdf
https://www.bls.gov/wsp/

---

### Census 2010 hiring

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2010-05 | NFP | LARGE BEAT (+431k vs +180k exp; +411k census workers) | CENSUS_HIRING | YES | Census Bureau published hiring schedule; month-by-month worker counts available |
| 2010-06 | NFP | MISS (−125k; census workers released in bulk) | CENSUS_HIRING | YES | Same schedule; census completion known |

**Notes:** The 2010 decennial census added over 450,000 temporary workers at its peak
(May 2010) and then released them rapidly in June.  The Census Bureau's own press
releases and congressional budget documents detailed the monthly hiring schedule.
Next decennial census is 2030 (next meaningful distortion window 2030).
**Source:** Census Bureau 2010 Census Employment; BLS Employment Situation releases.
https://www.census.gov/2010census/

---

### COVID shock (2020)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2020-03 | NFP | MISS (−701k vs −100k exp; survey week was Mar 8–14, pre-lockdown) | COLLECTION_DISRUPTION | PARTIAL | Ref week pre-dated most state shutdowns; Philly Fed weekly index collapsing |
| 2020-04 | NFP | MASSIVE MISS (−20,500k vs −22,000k exp; consensus range −25M to −10M) | COLLECTION_DISRUPTION + SEASONAL_ANOMALY | NO | No model could anticipate the exact shutdown depth; alt-data signals (OpenTable, TSA) available but unprecedented |
| 2020-05 | NFP | MASSIVE BEAT (+2,509k vs −7,500k consensus; classification error added) | REOPEN_SURGE + COLLECTION_DISRUPTION | NO | Consensus was −7,500k; actual was +2,509k. BLS noted a classification error (workers misclassified as "employed, absent" rather than "temporarily laid off") that, if corrected, would have lowered the reported figure by ~3M. True underlying: reopening beat but exact magnitude unknowable |
| 2020-06 | CPI | BEAT (energy surge as oil recovered; gasoline +12.3% MoM) | ENERGY_SURGE | PARTIAL | Oil futures visible; magnitude of recovery uncertain |

**May 2020 NFP detail:** The +2,509k print vs −7,500k Bloomberg consensus was the
largest positive surprise on record at that time.  BLS explicitly flagged a
misclassification error estimating ~4.9M workers as "employed, absent" who should have
been "unemployed on temporary layoff."  Correcting this would have produced a figure
closer to −2.4M but BLS did not reclassify in the published data (per their standard
methodology).  The consensus miss was driven by the unprecedented speed of the
reopening (faster than any seasonal model could anticipate) compounded by the
classification error.  Genuinely unknowable in magnitude.
**Source:** BLS Employment Situation releases; BLS note on classification.
https://www.bls.gov/news.release/archives/empsit_06052020.pdf

---

### Reopening misses (2021)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2021-04 | NFP | MISS (+266k vs +978k consensus) | SEASONAL_ANOMALY + COLLECTION_DISRUPTION | PARTIAL | Enhanced unemployment benefits reduced labor supply; ADP (+742k) was itself misleading |
| 2021-04 | CPI | BEAT (+0.8% MoM core; used-car prices +10.0%) | COMPOSITION_SHIFT | PARTIAL | Manheim used-car index visible ~4 weeks prior; showed +8-10% in March |
| 2021-06 | CPI | BEAT (used cars +10.5%; CPI shelter catching up) | COMPOSITION_SHIFT | PARTIAL | Manheim index; apartment-list data visible |

**April 2021 NFP detail:** The +266k vs +978k consensus miss was driven by pandemic-
era seasonal-factor distortions (pre-pandemic April typically sees large seasonal
hiring that was absent), enhanced UI limiting labor supply, and ongoing COVID-related
disruptions.  ADP's +742k was itself a misleading pre-release signal.
**Used-cars 2021 (CPI):** The Manheim Used Vehicle Value Index (published ~4 weeks
before CPI) showed double-digit gains throughout spring 2021.  Analysts tracking
Manheim had a directional signal; the exact passthrough to CPI was uncertain because
rental-car company fleet rebuilding (post-pandemic disposal) created a composition
effect not normally present.  The knowable signal was imprecise.
**Source:** BLS CPI and Employment Situation; Manheim Analytics.
https://www.bls.gov/news.release/archives/empsit_05072021.pdf
https://www.bls.gov/news.release/archives/cpi_05122021.pdf

---

### 2022-06 CPI shock

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2022-06 | CPI | LARGE BEAT (+1.3% MoM headline vs +1.1% exp; +9.1% YoY, 40y high) | ENERGY_SURGE + COMPOSITION_SHIFT | PARTIAL | Gasoline prices visible (averaging $4.99/gal in June); shelter acceleration visible in private survey data (Apartment List, Zillow) |

**Notes:** The June 2022 CPI print came in at +9.1% YoY, above the +8.8% consensus.
Gasoline prices (+11.2% MoM) were the primary driver and were entirely observable
before the print.  Shelter, which lagged private survey data by ~12 months, was a
secondary driver not fully anticipated.  A forecaster who correctly estimated gasoline
passthrough would still have underestimated shelter.
**Source:** BLS CPI June 2022 release; EIA weekly gasoline prices.
https://www.bls.gov/news.release/archives/cpi_07132022.pdf

---

### 2022-09 CPI shock

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2022-09 | CPI | BEAT (+0.4% MoM core vs +0.3% exp; shelter +0.7%) | COMPOSITION_SHIFT | PARTIAL | Shelter still accelerating; Cleveland Fed nowcast +0.47% core MoM (publicly available day before) |

**Notes:** The September 2022 CPI was particularly surprising because energy prices
had fallen (correctly anticipated) but core came in hotter than expected.  Shelter
(rent equivalent) continued to accelerate well above expectations.  The Cleveland Fed
Inflation Nowcast, available the day before the release, had estimated core MoM at
+0.47%, roughly consistent with the actual print.  This was a knowable-directional
signal available in real time.
**Source:** BLS CPI September 2022; Cleveland Fed Inflation Nowcast.
https://www.bls.gov/news.release/archives/cpi_10132022.pdf
https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting

---

### CPI health-insurance resets (2022-10 and 2023-01)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2022-10 | CPI | MISS (core +0.3% MoM vs +0.5% exp; health insurance −4.0%) | HEALTH_INS_RESET | YES | BLS announced the methodology change in October 2022 MLR article; first landing was October print |
| 2023-01 | CPI | MISS (health insurance weighing on core) | HEALTH_INS_RESET | YES | BLS cadence is April and October prints; first April landing was April 2023 |

**Notes:** In October 2022, BLS switched the health-insurance CPI component from a
direct-price method to a retained-earnings method, updated semiannually.  The first
update (October 2022 CPI) caused a large step-down in the health-insurance CPI
component that was announced in advance in an MLR article but not widely incorporated
by forecasters.  Subsequent updates (April and October each year since) are now
knowable ex ante because the BLS schedule is published.
The January 2023 print was softer than expected in part because of residual carry-
through from the health-insurance reset.
**Source:** BLS Monthly Labor Review, October 2022.
https://www.bls.gov/opub/mlr/2023/article/incorporating-new-estimates-into-the-cpi.htm

---

### NFP 2023-01 benchmark revision (+517k)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2023-01 | NFP (benchmark revision) | UPWARD REVISION (+517k to prior 12 months) | BENCHMARK_REVISION | YES (direction) | September 2022 BLS preliminary benchmark estimate: +462k; published October 2022 |

**Notes:** The January 2023 NFP release (published February 3, 2023) included the
annual CES benchmark revision.  BLS had published a preliminary estimate of +462k in
October 2022 (the September preliminary benchmark), alerting forecasters to the
direction and rough magnitude.  The final revision of +517k was close to the
preliminary estimate.  The benchmark revision itself is always knowable in direction
(and rough magnitude) from the October preliminary.  The seasonal re-estimation in
the same release can add additional variance.
**Source:** BLS Employment Situation January 2023 (released Feb 2023); BLS benchmark revision preliminary, Oct 2022.
https://www.bls.gov/ces/publications/benchmark.htm

---

### Hurricanes + Boeing strike (2024-10)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2024-10 | NFP | MISS (+12k vs +113k exp; hurricane/strike impact ~100k) | HURRICANE + STRIKE | YES | Hurricanes Helene (Sep 26 landfall) + Milton (Oct 9 landfall); Boeing IAM strike Sep 13 → 33,000 workers |
| 2024-10 | NFP (manufacturing) | MISS (−46k; Boeing) | STRIKE | YES | IAM-Boeing strike began Sep 13, 2024; reference week Oct 6–12 squarely during strike |

**Notes:** The October 2024 NFP reference week (October 6–12) was affected by two
simultaneous distortions: Hurricane Helene (September 26 landfall) displaced workers
in the Southeast, and Hurricane Milton made landfall October 9.  Additionally, the
Boeing IAM strike (33,000 machinists) began September 13 and was ongoing through the
reference week.  BLS estimated the combined weather and strike impact at
approximately 100,000 jobs.  Both distortions were observable before the print: NOAA
issued official track data, and the Boeing strike was publicly announced.  The
headline +12k print was among the weakest in the post-pandemic period, with November
showing a large rebound (+227k).
**Source:** BLS Employment Situation October 2024 (released Nov 1, 2024); NOAA NHC.
https://www.bls.gov/news.release/archives/empsit_11012024.pdf
https://www.nhc.noaa.gov/

---

### 2025 shutdown-delayed prints

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2025-01 | Multiple (JOLTS, retail sales, trade) | DELAYED/PARTIAL | COLLECTION_DISRUPTION | YES | Continuing resolution / lapse watch; OMB guidance published |
| 2025-Q1 | NFP (federal workers) | MISS direction (federal layoffs) | COLLECTION_DISRUPTION | PARTIAL | DOGE reduction-in-force announcements visible before BLS survey |

**Notes:** The 2025 appropriations gap and associated DOGE-driven federal workforce
reductions created disruptions to BLS data collection (reduced response rates) and
delayed publication of some statistical series.  The CPI publication scheduled for
October 2025 was cancelled outright (unprecedented since the 1995-96 government
shutdown).  Federal employment counts in 2025 were affected by the timing of when
OMB classified separations vs. when BLS counted them in CES.
This is an ongoing situation; episodes will be updated as data is finalized.
**Source:** BLS press releases; OMB guidance memos (public).

---

### 2025-10 CPI cancellation

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2025-10 | CPI | CANCELLED (not published on scheduled date) | COLLECTION_DISRUPTION | YES (event), NO (timing) | Government funding lapse was observable; exact date of cancellation was not |

**Notes:** The October 2025 CPI release was cancelled or indefinitely delayed due to
the government shutdown / appropriations gap.  This is the first outright CPI
cancellation since the 1995–96 Clinton-era shutdown.  Markets had to price CPI
expectations without an official print.  Subsequent prints carried residual
uncertainty about seasonal adjustment and carry-forward effects.

---

### 2025 tariff pass-through

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2025-Q2 | CPI (goods) | BEAT (import prices rising; goods deflation reversed) | TARIFF_PASSTHROUGH | PARTIAL | Tariff schedules published (Executive Orders, CBP); import price index available monthly |
| 2025-Q3 | CPI (core goods) | BEAT (auto/appliance prices) | TARIFF_PASSTHROUGH | PARTIAL | Import price index; producer price survey |

**Notes:** The 2025 tariff rounds (administered via Executive Orders and Section 232/
301 actions) passed through to consumer prices with approximately a 3–6 month lag.
The tariff schedules were publicly available (CBP tariff codes), and import price
indices (published monthly by BLS) showed the early signal.  However, the magnitude
of domestic passthrough and retailer margin absorption was uncertain.  Most
forecasters initially underestimated passthrough speed.
**Source:** BLS Import Price Index; CBP tariff database.
https://www.bls.gov/mxp/

---

### 2026 energy surge

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2026-Q1 | CPI headline | BEAT (energy component) | ENERGY_SURGE | PARTIAL | WTI futures strip visible; EIA weekly data available |
| 2026-Q2 | CPI headline | BEAT (persistent energy) | ENERGY_SURGE | PARTIAL | EIA weekly gasoline / WTI; NOAA weather-season demand forecasts |

**Notes:** Elevated energy prices in 2026 (driven by supply constraints and geopolitical
premium) caused a series of above-expectation headline CPI prints.  Core CPI was less
affected.  The weekly EIA petroleum supply / price data provides a real-time directional
signal for the energy component (available ~10 days before CPI).

---

### 2026 energy deflation (cold print)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2026-06 | CPI headline | MISS (−0.4% MoM vs −0.1% consensus; largest gasoline drag since 2022; first negative headline since 2020) | ENERGY_COLLAPSE | PARTIAL | EIA weekly gasoline (5 weeks published, ~10d lead) showed sharp June drop; WTI strip; Cleveland nowcast −0.06 vs model +0.08 |

**Notes:** ENERGY_COLLAPSE is the inverse of ENERGY_SURGE — a sharp gasoline drawdown
pulls headline below expectations. Same free signal (EIA weekly retail gasoline / WTI,
~10 days ahead of CPI), opposite direction. The June-2026 print was the first cold print
of this family in the catalog. Two honest caveats on knowability: (1) the energy
*direction* was signalled ex ante, but the −0.4 *magnitude* was a tail — it breached even
the energy-aware `mf_energy` shadow's p10 of −0.356; (2) roughly 0.26pp of the miss was
ex-energy core-side disinflation (core services ex-shelter + core goods) that the
`cpi_bridge` lag-1 persistence blocks could not see and no free instrument flagged — see
`research/release_forecast/FIELD_GUIDE_BRIDGE_FORWARD_PROXIES.md`. So the family is tagged
PARTIAL, not YES: the energy leg was knowable, the core-side leg was not.
**Source:** BLS CPI June-2026 release.
https://www.bls.gov/news.release/archives/cpi_07142026.htm

---

### 5-week survey gaps

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| Multiple | NFP | Systematic variance (higher or lower) | SEASONAL_ANOMALY | YES | Pure calendar computation (see engine/release_quirks.py:_nfp_five_week_gap) |

**Notes:** When the gap between consecutive NFP reference weeks (week containing the
12th) is 5 weeks instead of the typical 4 weeks, the seasonal adjustment performs
differently: there is simply more calendar time in which economic activity can shift,
and the model's implicit assumption of 4-week spacing is violated.  This is a pure
deterministic calendar fact, fully knowable before any data is released.  Known
5-week gap months include January 2025, August 2023 (ref: see _nfp_five_week_gap
function in engine/release_quirks.py).
**Source:** BLS CES methodology, reference-week definition.
https://www.bls.gov/ces/documentation/ces_methodology.htm

---

### Birth-death model bias (2007–2009)

| date | release | print_vs_exp | cause_family | knowable_ex_ante | free_signal |
|---|---|---|---|---|---|
| 2007-Q4–2009-Q1 | NFP | SYSTEMATIC UPWARD BIAS (birth-death model over-added; benchmark revised −1.2M over this period) | BIRTH_DEATH | PARTIAL | September preliminary benchmark: −824k preliminary for 2009 (published Oct 2009) |
| 2008-Q4 | NFP | MISS (real-time understated job losses; truth revealed in 2009 revision) | BIRTH_DEATH | PARTIAL | BED (Business Employment Dynamics) showed unusual establishment-closure rates |

**Notes:** During the 2007–2009 recession, the BLS birth-death model (which adds
estimated net jobs from new business formation minus closures) systematically over-
added jobs because it extrapolated pre-recession formation rates into the downturn.
The total overestimate was approximately −1.2M jobs over the 12-month period ending
March 2009, revealed in the January 2010 benchmark revision.  The September 2009
preliminary estimate (−824k) was published in October 2009, providing a directional
signal that real-time NFP had overstated payroll strength.  Business Employment
Dynamics (BED) data also showed unusual establishment-closure rates.
**Source:** BLS benchmark revision January 2010; BLS BED.
https://www.bls.gov/ces/publications/benchmark.htm
https://www.bls.gov/bdm/

---

## Genuinely unknowable episodes (honest nulls)

These episodes involved structural causes but the cause magnitude was not knowable
ex ante from public information.  We display them for historical completeness but do
NOT draw ex-ante signal inference from them.

| date | release | miss | why_unknowable |
|---|---|---|---|
| 2020-04 | NFP | −20.5M; consensus range −25M to −10M | Pandemic lockdown depth had no historical precedent; no model had training data for simultaneous nationwide closure |
| 2020-05 | NFP | +2.5M vs −7.5M consensus | Reopening velocity was genuinely unprecedented; BLS classification error compounded the uncertainty |
| 2021-04 | NFP | +266k vs +978k exp | Post-pandemic labor supply response was unmeasurable in real time; enhanced-UI elasticity was not identified |
| 2025 (federal) | NFP | Federal component timing | DOGE RIF timing vs BLS survey-week cut depended on internal agency implementation that was not publicly disclosed |
| 2008-Q4 | NFP (real-time) | Ongoing recession depth | Birth-death bias directionally flagged by BED but exact magnitude only knowable at benchmark revision |

---

## Track S engine flag map

Each episode family maps to a flag in `engine/release_quirks.py`:

| cause_family | engine_flag | active |
|---|---|---|
| STRIKE | active_strike | When BLS work-stoppages listing shows stoppage ≥25k workers overlapping NFP ref week |
| BENCHMARK_REVISION | nfp_preliminary_benchmark | Each January NFP; additionally flagged when Sept preliminary >|100k| |
| COLLECTION_DISRUPTION (shutdown) | government_shutdown | Seeded YAML calendar; flag when active |
| CENSUS_HIRING | census_hiring | Decennial calendar; currently inactive (next 2030) |
| HURRICANE | hurricane_landfall | YAML-seeded NOAA events; live NHC collector is comeback scope |
| BIRTH_DEATH | — | Descriptive note only; no deterministic signal (comeback C-11 Philly-Fed early-benchmark) |

---

## Data provenance

- BLS Employment Situation releases: https://www.bls.gov/news.release/empsit.toc.htm
- BLS CPI releases: https://www.bls.gov/news.release/cpi.toc.htm
- BLS Work Stoppages: https://www.bls.gov/wsp/
- BLS CES Benchmark revisions: https://www.bls.gov/ces/publications/benchmark.htm
- NOAA NHC: https://www.nhc.noaa.gov/
- Cleveland Fed Inflation Nowcast: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
- BLS Import Price Index: https://www.bls.gov/mxp/
- Census Bureau 2010 Census employment: https://www.census.gov/2010census/

*Generated 2026-07-10 as Track S lane output (MRI-R38). Static reference; update via PR when new episodes arise.*
