# Signal Lab Wave-4 source-family Phase-0 - 2026-07-06

## Why this run is different

This run incorporates both audits. Wave 2 failed because lane-level metadata
was treated as candidate-level diligence. Wave 3 failed because ten transform
templates were stamped onto each feed. Wave 4 therefore separates 500 raw
ideas from 100 independent constructs. Only the representative construct in
each source/feed family can advance; the other four rows are probe ideas for
pre-registration design and are not independent candidates.

No empirical validation is claimed. `advance_to_fable` only means the
construct has a plausible public source path, event count, tradable surface,
orthogonality to prior runs, and a named baseline worth challenging.

## Prior-run audit

- Wave 1: 60 mostly market/factor/text/flow candidates; 23 pre-Fable after Phase-0.
- Wave 2: 200 lane-generated candidates; Fable audit invalidated advance labels due source/path defects.
- Wave 3: 500 transform-grid rows; Fable audit collapsed 48 advances into four feed families.
- Wave 4 contract: 500 raw ideas, 100 independent constructs, no probe can advance.

## Verdict counts

- Raw ideas screened: 500
- Independent constructs: 100
- Probe rows blocked by design: 400
- Advance to Fable: 8
- Local Phase-0 ready: 46
- Data contract first: 0
- Reject/hold: 46
- Strict advance score: 8.5

## Construct Verdicts By Category

| Category | Fable | Local | Data | Reject |
|---|---|---|---|---|
| advertising transparency | 0 | 0 | 0 | 3 |
| air travel quality | 0 | 1 | 0 | 0 |
| autonomous vehicles | 0 | 1 | 0 | 1 |
| border operations | 0 | 1 | 0 | 0 |
| browser ecosystem | 0 | 0 | 0 | 1 |
| charging infrastructure | 0 | 0 | 0 | 1 |
| commerce ledger | 0 | 3 | 0 | 1 |
| consumer durable and firearms | 1 | 1 | 0 | 0 |
| consumer vice and state lottery | 0 | 0 | 0 | 2 |
| credit ledger | 0 | 1 | 0 | 0 |
| digital media | 0 | 0 | 0 | 1 |
| drones and robotics | 0 | 0 | 0 | 1 |
| energy completion | 0 | 1 | 0 | 0 |
| energy leasing | 0 | 0 | 0 | 2 |
| energy permits | 0 | 1 | 0 | 0 |
| energy permitting | 0 | 1 | 0 | 0 |
| energy production | 0 | 2 | 0 | 0 |
| filmed entertainment | 0 | 1 | 0 | 0 |
| food pricing | 0 | 1 | 0 | 0 |
| food supply and seafood | 0 | 1 | 0 | 0 |
| inflation microdata | 0 | 2 | 0 | 0 |
| interactive entertainment | 0 | 1 | 0 | 3 |
| live entertainment | 1 | 2 | 0 | 0 |
| macro ledger | 0 | 0 | 0 | 1 |
| minerals | 0 | 0 | 0 | 2 |
| municipal operations | 0 | 0 | 0 | 6 |
| municipal permits | 0 | 1 | 0 | 7 |
| music and culture | 0 | 0 | 0 | 2 |
| nuclear operations | 0 | 1 | 0 | 0 |
| open web corpus | 0 | 0 | 0 | 1 |
| outdoor leisure | 0 | 1 | 0 | 0 |
| payments rails | 0 | 6 | 0 | 2 |
| regulated cannabis | 0 | 0 | 0 | 4 |
| regulated gaming | 4 | 3 | 0 | 0 |
| tourism | 0 | 2 | 0 | 0 |
| tourism and gaming | 1 | 0 | 0 | 0 |
| transport fuel regulation | 0 | 1 | 0 | 0 |
| travel administration | 0 | 1 | 0 | 0 |
| travel and migration | 0 | 2 | 0 | 0 |
| urban mobility | 0 | 0 | 0 | 1 |
| vehicle demand | 1 | 0 | 0 | 0 |
| vehicle fleet | 0 | 1 | 0 | 0 |
| vehicle infrastructure | 0 | 1 | 0 | 0 |
| vehicle product cycle | 0 | 3 | 0 | 0 |
| vehicle regulation | 0 | 1 | 0 | 0 |
| web performance | 0 | 0 | 0 | 1 |
| web ranking | 0 | 1 | 0 | 0 |
| web technology | 0 | 0 | 0 | 3 |

## Fable-ready shortlist

| ID | Construct | Source | Score | Market | Mechanism | Surface | Baseline | First gate |
|---|---|---|---|---|---|---|---|---|
| W4-021 | Ticketmaster live-event supply pulse | Ticketmaster Discovery API | 8.63 | venues, promoters, hotels | future-dated event count, venue density, category mix and cancellation metadata | LYV, MSGE-like venues, hotel/casino geographies, local leisure baskets | holiday calendar, local tourism trend, artist tour cycle | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-061 | Las Vegas tourism indicator pack | LVCVA visitor statistics | 9.39 | casinos, hotels, airlines | Las Vegas visitors, occupancy, ADR, RevPAR, convention attendance and air/auto arrivals | MGM, CZR, LVS, WYNN, airlines and hotel REITs | Nevada gaming revenue, air capacity, convention calendar, SPY beta | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-076 | New Jersey iGaming and sports-betting ledger | New Jersey Division of Gaming Enforcement | 9.15 | online betting and casinos | monthly casino, internet gaming, sports wagering revenue and taxes | DKNG, FLUT, MGM, CZR, PENN and regional casino exposure | sports calendar, promo intensity if sourced, broader gambling trend | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-081 | Nevada gaming win and strip mix | Nevada Gaming Control Board monthly revenue | 9.09 | casinos and hotels | monthly gaming win by market and game type | MGM, CZR, WYNN, LVS, regional casinos and Vegas travel basket | LVCVA visitors, convention calendar, holidays, casino beta | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-086 | New York sports-wagering handle and hold | New York State Gaming Commission revenue reports | 8.98 | sportsbooks and casinos | weekly and monthly mobile sports wagering handle, gross revenue and operator share | DKNG, FLUT, MGM, CZR, PENN and sports-media baskets | sports calendar, NFL/NBA season, operator promos, NJ/PA comps | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-091 | Pennsylvania iGaming and slot/table mix | Pennsylvania Gaming Control Board revenue | 8.7 | online betting and casinos | monthly slots, tables, iGaming, VGT, sports wagering and fantasy revenue | DKNG, FLUT, MGM, CZR, PENN and regional casino exposure | sports calendar, NJ/NY comps, casino beta, seasonality | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-111 | FBI NICS firearm demand pulse | FBI NICS firearm background checks | 9.44 | firearm manufacturers and outdoor retail | monthly background checks by state and check type | SWBI, RGR, AOUT, VSTO-like outdoor/firearms exposure | political calendar, hunting season, consumer beta, inventory cycle | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |
| W4-246 | California ZEV sales share | California Energy Commission ZEV stats | 8.8 | EV OEMs, batteries, chargers | quarterly ZEV sales, shares, fuel type and geography | TSLA, legacy OEMs, battery suppliers, charging networks and utilities | tax credit calendar, gas prices, auto sales, charging availability | Representative construct only: pre-register source timestamp, event count, tradable surface, baseline, null controls, then run rank-IC/event study with HAC, BH-FDR and DSR only if the source ingest is real. |

## Local Phase-0 queue

| ID | Construct | Source | Score | Blockers | Mechanism | Surface |
|---|---|---|---|---|---|---|
| W4-006 | Steam store release and ranking metadata | Steam Store API / Steam Web API | 6.69 | tradable_surface | new release cadence, app tags, review count, and store visibility | game publishers, GPU vendors and PC hardware baskets |
| W4-026 | Ticketmaster venue utilization map | Ticketmaster Discovery API | 8.1 | below_strict_wave4_bar | venue-level event density and classification mix | public venue owners, local hotel REITs, casino and restaurant exposure |
| W4-031 | Broadway weekly gross and attendance pressure | The Broadway League grosses | 8.0 | tradable_surface | show-level weekly grosses, attendance and average ticket price | NYC tourism proxies, venue operators, media licensing exposure |
| W4-036 | Domestic box-office release impulse | The Numbers box office data | 7.34 | tradable_surface | daily and weekend box office by title and distributor | DIS, CMCSA, WBD, SONY/NTDOY comps and cinema chains |
| W4-056 | National Park visitation demand | NPS Visitor Use Statistics | 8.13 | tradable_surface | monthly visitation by park unit and region | outdoor retailers, RV makers, regional hotels and fuel demand |
| W4-066 | Hawaii visitor-expenditure pulse | Hawaii Tourism Data Warehouse | 7.98 | tradable_surface | monthly visitor arrivals, source markets, air seats and expenditures | airlines, hotel REITs, travel platforms and Hawaii-exposed businesses |
| W4-071 | Florida visitor estimate pulse | VISIT FLORIDA research | 6.88 | sufficient_observations, tradable_surface | quarterly visitors by origin and travel mode | theme parks, airlines, hotel REITs and Florida leisure exposure |
| W4-096 | Commercial gaming state-tax impulse | American Gaming Association revenue tracker | 7.19 | tradable_surface | state-level regulated gaming revenue and tax contribution | casino operators, sportsbooks and local tax-sensitive regions |
| W4-116 | ATF firearm production and import cycle | ATF firearms commerce statistics | 6.5 | sufficient_observations, tradable_surface | annual firearms production, imports, exports and license statistics | firearm manufacturers and outdoor retail |
| W4-121 | Nonimmigrant visa issuance travel pulse | State Department NIV statistics | 7.49 | tradable_surface | monthly nonimmigrant visa issuances by class and post | international airlines, hotels, universities and staffing-sensitive themes |
| W4-126 | Immigrant visa issuance family/workflow pressure | State Department immigrant visa statistics | 6.93 | tradable_surface | monthly immigrant visa issuance by post and category | airlines, remittance, labor-supply and regional consumer themes |
| W4-141 | Fedwire large-value payment stress | Fedwire volume and value statistics | 7.18 | not_prior_wave_family, tradable_surface | monthly transfer count, value and average value | money-center banks, payment processors and market-stress overlays |
| W4-146 | FedACH commercial ACH usage | Federal Reserve commercial ACH statistics | 7.52 | tradable_surface | quarterly commercial ACH volume and value | payment processors, banks, payroll providers and B2B commerce themes |
| W4-156 | FedNow participant breadth | FedNow participants list | 7.84 | tradable_surface | live participating FIs, settlement agents and certified service providers | banks, core processors and payment infrastructure vendors |
| W4-161 | RTP network participant breadth | TCH RTP participating FIs | 7.93 | tradable_surface | current RTP-enabled institutions and routing reach | core processors, banks and payment vendors |
| W4-171 | Nacha ACH network same-day mix | Nacha ACH statistics | 6.79 | sufficient_observations, tradable_surface | ACH and Same Day ACH volume/value by quarter | payment processors, banks and payroll providers |
| W4-176 | Federal Reserve check-service decay | FRB check services volume/value | 6.32 | tradable_surface | check-service volume and value by period | bank operations, payment processors and legacy-check exposure |
| W4-181 | Census retail sales category surprise | Census Monthly Retail Trade | 6.96 | not_prior_wave_family | monthly retail sales by NAICS category | retailers, restaurants, autos, e-commerce and consumer ETFs |
| W4-191 | Wholesale inventory-sales pressure | Census Monthly Wholesale Trade | 7.54 | not_prior_wave_family, tradable_surface | merchant wholesaler sales, inventories and inventory/sales ratios | industrial distributors, retailers, manufacturers and working-capital themes |
| W4-196 | Manufacturers orders and backlog stress | Census M3 manufacturers shipments/inventories/orders | 7.07 | not_prior_wave_family, tradable_surface | new orders, shipments, inventories and unfilled orders by industry | industrials, machinery, aerospace, electronics and materials |
| W4-201 | BLS CPI average-price pressure | BLS Public Data API | 6.47 | not_prior_wave_family, tradable_surface | average price and CPI component changes by item | retail, food, fuel, consumer staples and discretionary margins |
| W4-206 | BLS PPI industry input squeeze | BLS Public Data API | 6.86 | not_prior_wave_family, tradable_surface | producer-price indexes by industry and commodity | industry margin baskets and pass-through themes |
| W4-216 | Federal Reserve consumer-credit mix | Federal Reserve Consumer Credit G.19 | 7.37 | not_prior_wave_family, tradable_surface | revolving and nonrevolving consumer credit growth | credit-card lenders, auto lenders and consumer finance themes |
| W4-221 | NHTSA vPIC model-introduction cadence | NHTSA vPIC API | 8.15 | below_strict_wave4_bar | manufacturer-submitted makes, models, body classes and VIN decoding metadata | auto OEMs, suppliers, insurers and EV/ICE product-cycle baskets |
| W4-226 | EPA fuel-economy product mix | FuelEconomy.gov data | 8.15 | tradable_surface | model-year MPG, MPGe, fuel type and annual fuel-cost estimates | auto OEMs, EV suppliers, fuel demand and regulatory-credit themes |
| W4-231 | EPA certification test intensity | EPA cars used for fuel-economy testing | 8.01 | tradable_surface | vehicle test records used in fuel economy certification | auto OEMs, powertrain suppliers and emissions-control themes |
| W4-241 | California AV collision incident pressure | California DMV AV collision reports | 7.05 | tradable_surface | reported AV collisions and narratives | AV developers, insurers and autonomy suppliers |
| W4-256 | Alternative fuel station deployment | DOE AFDC Station Locator API | 7.37 | not_prior_wave_family | station openings, fuel type, network and access fields | charging/fuel networks, EV/hydrogen suppliers and fleet operators |
| W4-261 | FHWA vehicle registration mix | FHWA Highway Statistics | 6.29 | sufficient_observations, tradable_surface | state vehicle registrations by vehicle class | auto OEMs, insurers, fuel demand and parts retailers |
| W4-266 | DOT air consumer complaint pressure | DOT Air Travel Consumer Reports | 6.85 | not_prior_wave_family, tradable_surface | consumer complaints, mishandled baggage, cancellations and service quality | airlines, travel platforms and airport-exposed regions |
| W4-276 | CARB executive-order certification cadence | CARB executive orders | 7.47 | tradable_surface | vehicle and engine certification executive orders | auto OEMs, powertrain suppliers and emissions-control vendors |
| W4-281 | LCFS credit-transfer price pressure | CARB LCFS credit reports | 7.59 | not_prior_wave_family | LCFS credit transfers, prices and volumes | renewable diesel, refiners, biofuel producers and EV-charging credit generators |
| W4-316 | Tranco domain-rank adoption | Tranco top-sites ranking | 7.18 | tradable_surface | research-oriented top-site rank list and rank persistence | web-platform companies, ad-tech and CDN exposure |
| W4-346 | NYC DOB construction permit pulse | NYC DOB permit issuance | 6.55 | not_prior_wave_family, tradable_surface | issued construction permits by borough, job type and owner | NYC construction suppliers, REITs and local banks |
| W4-411 | Texas drilling permit master | Texas Railroad Commission data downloads | 8.98 | not_prior_wave_family | Texas drilling permit applications, issue dates, well type and geography | Permian E&Ps, oilfield services, sand/water logistics and midstream |
| W4-416 | Texas oil and gas production reports | Texas RRC production queries | 8.02 | not_prior_wave_family | monthly production by lease, district and operator | Texas E&Ps, midstream and oilfield services |
| W4-421 | FracFocus completion and fluid-intensity signal | FracFocus data download | 8.49 | not_prior_wave_family | fracturing disclosures, chemicals, water volume and operator/well metadata | oilfield services, proppant, chemicals, water handling and E&Ps |
| W4-426 | North Dakota Bakken production report | ND Monthly Production Reports | 6.8 | not_prior_wave_family, tradable_surface | monthly oil/gas production reports and well data | Bakken E&Ps, midstream and oilfield services |
| W4-441 | NRC nuclear event notification pressure | NRC event reports | 7.43 | not_prior_wave_family, tradable_surface | reactor and materials event notifications | nuclear utilities, uranium, nuclear services and grid reliability themes |
| W4-446 | DOE LNG export authorization queue | DOE LNG export authorizations | 6.83 | not_prior_wave_family, tradable_surface | export authorizations, orders, project status and destination authorization | LNG developers, gas producers, pipelines and equipment suppliers |
| W4-451 | NOAA fisheries landings revenue | NOAA commercial fisheries landings | 6.66 | not_prior_wave_family, tradable_surface | commercial fishery landings volume and value by species/region | seafood suppliers, restaurants, grocers and regional economies |
| W4-466 | USDA AMS wholesale food market news | USDA Market News | 6.87 | not_prior_wave_family, tradable_surface | wholesale market reports by commodity and region | grocers, restaurants, protein processors and food-service margins |
| W4-481 | Ohio casino and racino revenue ledger | Ohio Casino Control Commission revenue reports | 7.59 | below_strict_wave4_bar | monthly casino and racino revenue by property/category | regional casino operators and Midwest leisure exposure |
| W4-486 | Maryland casino gaming revenue ledger | Maryland Lottery and Gaming revenue reports | 7.36 | tradable_surface | monthly casino revenue by property and game type | regional casino operators and Mid-Atlantic leisure exposure |
| W4-491 | CBP border wait-time congestion | CBP Border Wait Times API | 7.13 | not_prior_wave_family, tradable_surface | border crossing wait time by port, lane type and vehicle class | border-region retailers, auto supply chains and logistics context |
| W4-496 | Passport issuance workload pulse | State Department passport statistics | 7.02 | tradable_surface | passport demand, issuance and processing workload statistics | international airlines, travel agencies and leisure demand themes |

## Data-contract queue

| ID | Construct | Source | Score | Blockers |
|---|---|---|---|---|

## Rejected construct representatives

| ID | Construct | Source | Score | Blockers |
|---|---|---|---|---|
| W4-001 | Steam current-player concurrency | Valve Steam Web API | 5.41 | sufficient_observations |
| W4-011 | Twitch live-stream demand by game | Twitch API | 5.72 | not_prior_wave_family, tradable_surface |
| W4-016 | Twitch VOD retention by game | Twitch Get Videos API | 5.34 | not_prior_wave_family, tradable_surface |
| W4-041 | YouTube channel velocity for official brands | YouTube Data API | 5.49 | not_prior_wave_family, tradable_surface |
| W4-046 | Spotify artist popularity drift | Spotify Web API | 5.85 | tradable_surface |
| W4-051 | Spotify chart-rank diffusion | Spotify Charts | 3.18 | tradable_surface, license_clear_enough |
| W4-101 | Colorado cannabis sales and tax cycle | Colorado marijuana sales reports | 6.04 | not_prior_wave_family, tradable_surface |
| W4-106 | Colorado cannabis tax receipt stress | Colorado marijuana tax reports | 5.59 | not_prior_wave_family, tradable_surface |
| W4-131 | Texas lottery sales discretionary-stress pulse | Texas Lottery financial information | 4.3 | not_prior_wave_family, tradable_surface |
| W4-136 | Massachusetts lottery revenue pulse | Massachusetts Lottery financial reports | 4.15 | not_prior_wave_family, tradable_surface |
| W4-151 | FedNow real-time-payment adoption | FedNow volume and value statistics | 4.67 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-166 | RTP network volume/value growth | The Clearing House RTP reports | 4.72 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-186 | Census quarterly services demand | Census Quarterly Services Survey | 5.72 | not_prior_wave_family, tradable_surface |
| W4-211 | BEA consumer income and outlay revision | BEA API | 5.27 | not_prior_wave_family, tradable_surface |
| W4-236 | California AV disengagement progress | California DMV AV reports | 4.54 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-251 | California EV charger deployment | CEC ZEV infrastructure data | 5.5 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-271 | FAA drone registration and waiver activity | FAA UAS data | 5.06 | tradable_surface |
| W4-286 | Meta Ad Library commercial/political intensity | Meta Ad Library API | 5.47 | not_prior_wave_family, tradable_surface |
| W4-291 | Google Ads Transparency advertiser activity | Google Ads Transparency Center | 2.23 | not_prior_wave_family, tradable_surface, license_clear_enough |
| W4-296 | FCC political-ad file contract flow | FCC Public Inspection Files | 4.84 | tradable_surface |
| W4-301 | Chrome UX origin performance drift | Chrome UX Report BigQuery | 5.89 | tradable_surface |
| W4-306 | HTTP Archive technology adoption | HTTP Archive BigQuery | 5.88 | tradable_surface |
| W4-311 | Common Crawl brand-web corpus drift | Common Crawl | 3.72 | not_prior_wave_family, tradable_surface |
| W4-321 | Chrome Web Store extension install pressure | Chrome Web Store | 2.18 | not_prior_wave_family, tradable_surface, license_clear_enough |
| W4-326 | BuiltWith technology install share | BuiltWith Trends | 2.93 | not_prior_wave_family, usable_source_path, pit_plan, license_clear_enough |
| W4-331 | Wappalyzer technology adoption | Wappalyzer datasets | 2.78 | not_prior_wave_family, usable_source_path, pit_plan, license_clear_enough |
| W4-336 | NYC 311 neighborhood service stress | NYC 311 Open Data | 4.77 | not_prior_wave_family, tradable_surface |
| W4-341 | NYC restaurant inspection pressure | NYC restaurant inspection results | 5.08 | not_prior_wave_family, tradable_surface |
| W4-351 | NYC film-permit production pulse | NYC film permits | 6.18 | tradable_surface |
| W4-356 | NYC TLC trip revenue pressure | NYC TLC trip records | 5.52 | not_prior_wave_family, tradable_surface |
| W4-361 | Chicago 311 municipal stress | Chicago Data Portal service requests | 4.55 | not_prior_wave_family, tradable_surface |
| W4-366 | Chicago building permit mix | Chicago building permits | 5.43 | not_prior_wave_family, tradable_surface |
| W4-371 | San Francisco 311 service stress | SF Open Data 311 cases | 4.55 | not_prior_wave_family, tradable_surface |
| W4-376 | San Francisco building permit pressure | SF building permits | 5.35 | not_prior_wave_family, tradable_surface |
| W4-381 | Los Angeles permit valuation pulse | LA Open Data building permits | 5.35 | not_prior_wave_family, tradable_surface |
| W4-386 | DC 311 public-space stress | Open Data DC 311 | 4.55 | not_prior_wave_family, tradable_surface |
| W4-391 | Seattle permit and land-use pressure | Seattle Open Data permits | 5.35 | not_prior_wave_family, tradable_surface |
| W4-396 | Austin building permit momentum | Austin Open Data permits | 5.35 | not_prior_wave_family, tradable_surface |
| W4-401 | Boston 311 neighborhood stress | Analyze Boston 311 | 4.55 | not_prior_wave_family, tradable_surface |
| W4-406 | Toronto building-permit pulse | Toronto Open Data | 5.42 | not_prior_wave_family, tradable_surface |
| W4-431 | BOEM offshore lease-sale bid intensity | BOEM lease sales | 4.65 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-436 | BLM onshore oil/gas lease-sale demand | BLM oil and gas lease sales | 6.15 | not_prior_wave_family, tradable_surface |
| W4-456 | USGS mineral commodity production pressure | USGS mineral commodity summaries | 5.56 | sufficient_observations, tradable_surface |
| W4-461 | USGS mineral resource deposit map | USGS Mineral Resources Data System | 3.25 | sufficient_observations, tradable_surface |
| W4-471 | Illinois cannabis sales channel mix | Illinois cannabis sales figures | 5.34 | not_prior_wave_family, tradable_surface |
| W4-476 | Michigan cannabis market maturity | Michigan CRA statistical reports | 5.42 | not_prior_wave_family, tradable_surface |

## Probe rows

Probe rows were screened, but every one is blocked from advancement because
it is a within-construct pre-registration probe, not an independent signal.

| ID | Construct | Probe | Verdict | Raw idea |
|---|---|---|---|---|
| W4-002 | Steam current-player concurrency | exposure_map | construct_probe_only | Map ATVI successor comps, EA, TTWO, NTDOY, SONY and platform/vendor baskets to liquid public exposures and predefine zero-exposure controls |
| W4-003 | Steam current-player concurrency | release_lag_test | construct_probe_only | Measure publication lag and revision risk in current concurrent players by Steam app id before any return test |
| W4-004 | Steam current-player concurrency | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-005 | Steam current-player concurrency | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: game release calendar, Twitch attention, Steam sale calendar, publisher beta |
| W4-007 | Steam store release and ranking metadata | exposure_map | construct_probe_only | Map game publishers, GPU vendors and PC hardware baskets to liquid public exposures and predefine zero-exposure controls |
| W4-008 | Steam store release and ranking metadata | release_lag_test | construct_probe_only | Measure publication lag and revision risk in new release cadence, app tags, review count, and store visibility before any return test |
| W4-009 | Steam store release and ranking metadata | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-010 | Steam store release and ranking metadata | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: Steam player counts, release seasonality, publisher announcements |
| W4-012 | Twitch live-stream demand by game | exposure_map | construct_probe_only | Map public game publishers, creator-platform and ad-tech baskets to liquid public exposures and predefine zero-exposure controls |
| W4-013 | Twitch live-stream demand by game | release_lag_test | construct_probe_only | Measure publication lag and revision risk in live channels and viewer attention by game/category before any return test |
| W4-014 | Twitch live-stream demand by game | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-015 | Twitch live-stream demand by game | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: Steam players, release calendar, esports schedule, broad tech beta |
| W4-017 | Twitch VOD retention by game | exposure_map | construct_probe_only | Map public game publishers and creator-platform baskets to liquid public exposures and predefine zero-exposure controls |
| W4-018 | Twitch VOD retention by game | release_lag_test | construct_probe_only | Measure publication lag and revision risk in VOD volume and post-live retention by broadcaster/game before any return test |
| W4-019 | Twitch VOD retention by game | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-020 | Twitch VOD retention by game | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: live streams, publisher release calendar, esports schedule |
| W4-022 | Ticketmaster live-event supply pulse | exposure_map | construct_probe_only | Map LYV, MSGE-like venues, hotel/casino geographies, local leisure baskets to liquid public exposures and predefine zero-exposure controls |
| W4-023 | Ticketmaster live-event supply pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in future-dated event count, venue density, category mix and cancellation metadata before any return test |
| W4-024 | Ticketmaster live-event supply pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-025 | Ticketmaster live-event supply pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: holiday calendar, local tourism trend, artist tour cycle |
| W4-027 | Ticketmaster venue utilization map | exposure_map | construct_probe_only | Map public venue owners, local hotel REITs, casino and restaurant exposure to liquid public exposures and predefine zero-exposure controls |
| W4-028 | Ticketmaster venue utilization map | release_lag_test | construct_probe_only | Measure publication lag and revision risk in venue-level event density and classification mix before any return test |
| W4-029 | Ticketmaster venue utilization map | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-030 | Ticketmaster venue utilization map | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: Ticketmaster event supply, local hotel occupancy, venue capacity |
| W4-032 | Broadway weekly gross and attendance pressure | exposure_map | construct_probe_only | Map NYC tourism proxies, venue operators, media licensing exposure to liquid public exposures and predefine zero-exposure controls |
| W4-033 | Broadway weekly gross and attendance pressure | release_lag_test | construct_probe_only | Measure publication lag and revision risk in show-level weekly grosses, attendance and average ticket price before any return test |
| W4-034 | Broadway weekly gross and attendance pressure | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-035 | Broadway weekly gross and attendance pressure | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: seasonality, holidays, tourism, opening/closing calendar |
| W4-037 | Domestic box-office release impulse | exposure_map | construct_probe_only | Map DIS, CMCSA, WBD, SONY/NTDOY comps and cinema chains to liquid public exposures and predefine zero-exposure controls |
| W4-038 | Domestic box-office release impulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in daily and weekend box office by title and distributor before any return test |
| W4-039 | Domestic box-office release impulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-040 | Domestic box-office release impulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: release budget, seasonality, franchise history, reviews if licensed |
| W4-042 | YouTube channel velocity for official brands | exposure_map | construct_probe_only | Map public brands with official channels and launch/event calendars to liquid public exposures and predefine zero-exposure controls |
| W4-043 | YouTube channel velocity for official brands | release_lag_test | construct_probe_only | Measure publication lag and revision risk in official-channel uploads, views, comments and subscriber changes before any return test |
| W4-044 | YouTube channel velocity for official brands | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-045 | YouTube channel velocity for official brands | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: search trend, paid ads, release calendar, price momentum |
| W4-047 | Spotify artist popularity drift | exposure_map | construct_probe_only | Map music labels, live events and ad-supported audio platforms to liquid public exposures and predefine zero-exposure controls |
| W4-048 | Spotify artist popularity drift | release_lag_test | construct_probe_only | Measure publication lag and revision risk in artist popularity, playlist presence and track metadata before any return test |
| W4-049 | Spotify artist popularity drift | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-050 | Spotify artist popularity drift | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: tour calendar, Ticketmaster supply, social attention |
| W4-052 | Spotify chart-rank diffusion | exposure_map | construct_probe_only | Map music labels, live-event promoters and consumer attention baskets to liquid public exposures and predefine zero-exposure controls |
| W4-053 | Spotify chart-rank diffusion | release_lag_test | construct_probe_only | Measure publication lag and revision risk in top-track and viral chart rank changes by market before any return test |
| W4-054 | Spotify chart-rank diffusion | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-055 | Spotify chart-rank diffusion | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: Spotify artist popularity, tour calendar, release day effects |
| W4-057 | National Park visitation demand | exposure_map | construct_probe_only | Map outdoor retailers, RV makers, regional hotels and fuel demand to liquid public exposures and predefine zero-exposure controls |
| W4-058 | National Park visitation demand | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly visitation by park unit and region before any return test |
| W4-059 | National Park visitation demand | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-060 | National Park visitation demand | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: weather, school calendar, gas prices, park closures |
| W4-062 | Las Vegas tourism indicator pack | exposure_map | construct_probe_only | Map MGM, CZR, LVS, WYNN, airlines and hotel REITs to liquid public exposures and predefine zero-exposure controls |
| W4-063 | Las Vegas tourism indicator pack | release_lag_test | construct_probe_only | Measure publication lag and revision risk in Las Vegas visitors, occupancy, ADR, RevPAR, convention attendance and air/auto arrivals before any return test |
| W4-064 | Las Vegas tourism indicator pack | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-065 | Las Vegas tourism indicator pack | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: Nevada gaming revenue, air capacity, convention calendar, SPY beta |
| W4-067 | Hawaii visitor-expenditure pulse | exposure_map | construct_probe_only | Map airlines, hotel REITs, travel platforms and Hawaii-exposed businesses to liquid public exposures and predefine zero-exposure controls |
| W4-068 | Hawaii visitor-expenditure pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly visitor arrivals, source markets, air seats and expenditures before any return test |
| W4-069 | Hawaii visitor-expenditure pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-070 | Hawaii visitor-expenditure pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: air seats, FX, fuel, weather/disaster closures |
| W4-072 | Florida visitor estimate pulse | exposure_map | construct_probe_only | Map theme parks, airlines, hotel REITs and Florida leisure exposure to liquid public exposures and predefine zero-exposure controls |
| W4-073 | Florida visitor estimate pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in quarterly visitors by origin and travel mode before any return test |
| W4-074 | Florida visitor estimate pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-075 | Florida visitor estimate pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: theme-park calendar, air capacity, hurricane season, consumer beta |
| W4-077 | New Jersey iGaming and sports-betting ledger | exposure_map | construct_probe_only | Map DKNG, FLUT, MGM, CZR, PENN and regional casino exposure to liquid public exposures and predefine zero-exposure controls |
| W4-078 | New Jersey iGaming and sports-betting ledger | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly casino, internet gaming, sports wagering revenue and taxes before any return test |
| W4-079 | New Jersey iGaming and sports-betting ledger | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-080 | New Jersey iGaming and sports-betting ledger | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: sports calendar, promo intensity if sourced, broader gambling trend |
| W4-082 | Nevada gaming win and strip mix | exposure_map | construct_probe_only | Map MGM, CZR, WYNN, LVS, regional casinos and Vegas travel basket to liquid public exposures and predefine zero-exposure controls |
| W4-083 | Nevada gaming win and strip mix | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly gaming win by market and game type before any return test |
| W4-084 | Nevada gaming win and strip mix | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-085 | Nevada gaming win and strip mix | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: LVCVA visitors, convention calendar, holidays, casino beta |
| W4-087 | New York sports-wagering handle and hold | exposure_map | construct_probe_only | Map DKNG, FLUT, MGM, CZR, PENN and sports-media baskets to liquid public exposures and predefine zero-exposure controls |
| W4-088 | New York sports-wagering handle and hold | release_lag_test | construct_probe_only | Measure publication lag and revision risk in weekly and monthly mobile sports wagering handle, gross revenue and operator share before any return test |
| W4-089 | New York sports-wagering handle and hold | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-090 | New York sports-wagering handle and hold | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: sports calendar, NFL/NBA season, operator promos, NJ/PA comps |
| W4-092 | Pennsylvania iGaming and slot/table mix | exposure_map | construct_probe_only | Map DKNG, FLUT, MGM, CZR, PENN and regional casino exposure to liquid public exposures and predefine zero-exposure controls |
| W4-093 | Pennsylvania iGaming and slot/table mix | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly slots, tables, iGaming, VGT, sports wagering and fantasy revenue before any return test |
| W4-094 | Pennsylvania iGaming and slot/table mix | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-095 | Pennsylvania iGaming and slot/table mix | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: sports calendar, NJ/NY comps, casino beta, seasonality |
| W4-097 | Commercial gaming state-tax impulse | exposure_map | construct_probe_only | Map casino operators, sportsbooks and local tax-sensitive regions to liquid public exposures and predefine zero-exposure controls |
| W4-098 | Commercial gaming state-tax impulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in state-level regulated gaming revenue and tax contribution before any return test |
| W4-099 | Commercial gaming state-tax impulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-100 | Commercial gaming state-tax impulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: state gaming reports, sports calendar, macro consumption |
| W4-102 | Colorado cannabis sales and tax cycle | exposure_map | construct_probe_only | Map cannabis operators, hydroponics suppliers and state-tax-sensitive themes to liquid public exposures and predefine zero-exposure controls |
| W4-103 | Colorado cannabis sales and tax cycle | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly medical and retail marijuana sales by county before any return test |
| W4-104 | Colorado cannabis sales and tax cycle | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-105 | Colorado cannabis sales and tax cycle | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: state legalization comps, price reports, seasonality |
| W4-107 | Colorado cannabis tax receipt stress | exposure_map | construct_probe_only | Map cannabis operators and state fiscal themes to liquid public exposures and predefine zero-exposure controls |
| W4-108 | Colorado cannabis tax receipt stress | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly marijuana tax and fee revenue by county before any return test |
| W4-109 | Colorado cannabis tax receipt stress | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-110 | Colorado cannabis tax receipt stress | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: Colorado cannabis sales, tax-rate changes, local tourism |
| W4-112 | FBI NICS firearm demand pulse | exposure_map | construct_probe_only | Map SWBI, RGR, AOUT, VSTO-like outdoor/firearms exposure to liquid public exposures and predefine zero-exposure controls |
| W4-113 | FBI NICS firearm demand pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly background checks by state and check type before any return test |
| W4-114 | FBI NICS firearm demand pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-115 | FBI NICS firearm demand pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: political calendar, hunting season, consumer beta, inventory cycle |
| W4-117 | ATF firearm production and import cycle | exposure_map | construct_probe_only | Map firearm manufacturers and outdoor retail to liquid public exposures and predefine zero-exposure controls |
| W4-118 | ATF firearm production and import cycle | release_lag_test | construct_probe_only | Measure publication lag and revision risk in annual firearms production, imports, exports and license statistics before any return test |
| W4-119 | ATF firearm production and import cycle | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-120 | ATF firearm production and import cycle | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: NICS checks, political calendar, inventory cycle |
| W4-122 | Nonimmigrant visa issuance travel pulse | exposure_map | construct_probe_only | Map international airlines, hotels, universities and staffing-sensitive themes to liquid public exposures and predefine zero-exposure controls |
| W4-123 | Nonimmigrant visa issuance travel pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly nonimmigrant visa issuances by class and post before any return test |
| W4-124 | Nonimmigrant visa issuance travel pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-125 | Nonimmigrant visa issuance travel pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: FX, policy changes, air capacity, tourism data |
| W4-127 | Immigrant visa issuance family/workflow pressure | exposure_map | construct_probe_only | Map airlines, remittance, labor-supply and regional consumer themes to liquid public exposures and predefine zero-exposure controls |
| W4-128 | Immigrant visa issuance family/workflow pressure | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly immigrant visa issuance by post and category before any return test |
| W4-129 | Immigrant visa issuance family/workflow pressure | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-130 | Immigrant visa issuance family/workflow pressure | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: policy changes, consular backlogs, labor data |
| W4-132 | Texas lottery sales discretionary-stress pulse | exposure_map | construct_probe_only | Map consumer stress proxies, Texas regional retail and state fiscal themes to liquid public exposures and predefine zero-exposure controls |
| W4-133 | Texas lottery sales discretionary-stress pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in lottery sales and transfers to state funds before any return test |
| W4-134 | Texas lottery sales discretionary-stress pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-135 | Texas lottery sales discretionary-stress pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: jackpot size, income, gasoline prices, seasonality |
| W4-137 | Massachusetts lottery revenue pulse | exposure_map | construct_probe_only | Map state fiscal and low-income consumer stress themes to liquid public exposures and predefine zero-exposure controls |
| W4-138 | Massachusetts lottery revenue pulse | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly sales, prizes and net profit by game family before any return test |
| W4-139 | Massachusetts lottery revenue pulse | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-140 | Massachusetts lottery revenue pulse | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: jackpot size, income, seasonality |
| W4-142 | Fedwire large-value payment stress | exposure_map | construct_probe_only | Map money-center banks, payment processors and market-stress overlays to liquid public exposures and predefine zero-exposure controls |
| W4-143 | Fedwire large-value payment stress | release_lag_test | construct_probe_only | Measure publication lag and revision risk in monthly transfer count, value and average value before any return test |
| W4-144 | Fedwire large-value payment stress | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-145 | Fedwire large-value payment stress | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: market volatility, quarter-end, rates, banking stress |
| W4-147 | FedACH commercial ACH usage | exposure_map | construct_probe_only | Map payment processors, banks, payroll providers and B2B commerce themes to liquid public exposures and predefine zero-exposure controls |
| W4-148 | FedACH commercial ACH usage | release_lag_test | construct_probe_only | Measure publication lag and revision risk in quarterly commercial ACH volume and value before any return test |
| W4-149 | FedACH commercial ACH usage | negative_control | construct_probe_only | Run the same feature against unrelated peers to catch broad beta leakage |
| W4-150 | FedACH commercial ACH usage | failure_probe | construct_probe_only | Attempt to kill the idea with baseline controls: retail sales, payrolls, Fedwire, GDP |

Only the first 120 probe rows are shown here to keep the memo readable; the
JSON artifact contains all 500 rows.

## Full construct representatives

| ID | Construct | Category | Source | Data | PIT | Years | N | Verdict | Score | Blockers |
|---|---|---|---|---|---|---|---|---|---|---|
| W4-001 | Steam current-player concurrency | interactive entertainment | Valve Steam Web API | partial | clean | 0 | 0 | reject_or_hold | 5.41 | sufficient_observations |
| W4-006 | Steam store release and ranking metadata | interactive entertainment | Steam Store API / Steam Web API | partial | clean | 8 | 96 | local_phase0_ready | 6.69 | tradable_surface |
| W4-011 | Twitch live-stream demand by game | interactive entertainment | Twitch API | partial | clean | 5 | 260 | reject_or_hold | 5.72 | not_prior_wave_family, tradable_surface |
| W4-016 | Twitch VOD retention by game | interactive entertainment | Twitch Get Videos API | partial | clean | 5 | 260 | reject_or_hold | 5.34 | not_prior_wave_family, tradable_surface |
| W4-021 | Ticketmaster live-event supply pulse | live entertainment | Ticketmaster Discovery API | free_new | clean | 7 | 365 | advance_to_fable | 8.63 |  |
| W4-026 | Ticketmaster venue utilization map | live entertainment | Ticketmaster Discovery API | free_new | clean | 7 | 365 | local_phase0_ready | 8.1 | below_strict_wave4_bar |
| W4-031 | Broadway weekly gross and attendance pressure | live entertainment | The Broadway League grosses | free_new | release_lag | 25 | 1200 | local_phase0_ready | 8.0 | tradable_surface |
| W4-036 | Domestic box-office release impulse | filmed entertainment | The Numbers box office data | external_heavy | clean | 20 | 1000 | local_phase0_ready | 7.34 | tradable_surface |
| W4-041 | YouTube channel velocity for official brands | digital media | YouTube Data API | partial | clean | 5 | 260 | reject_or_hold | 5.49 | not_prior_wave_family, tradable_surface |
| W4-046 | Spotify artist popularity drift | music and culture | Spotify Web API | partial | clean | 5 | 260 | reject_or_hold | 5.85 | tradable_surface |
| W4-051 | Spotify chart-rank diffusion | music and culture | Spotify Charts | partial | manual_download | 5 | 260 | reject_or_hold | 3.18 | tradable_surface, license_clear_enough |
| W4-056 | National Park visitation demand | outdoor leisure | NPS Visitor Use Statistics | free_new | release_lag | 40 | 480 | local_phase0_ready | 8.13 | tradable_surface |
| W4-061 | Las Vegas tourism indicator pack | tourism and gaming | LVCVA visitor statistics | free_new | release_lag | 20 | 240 | advance_to_fable | 9.39 |  |
| W4-066 | Hawaii visitor-expenditure pulse | tourism | Hawaii Tourism Data Warehouse | free_new | release_lag | 20 | 240 | local_phase0_ready | 7.98 | tradable_surface |
| W4-071 | Florida visitor estimate pulse | tourism | VISIT FLORIDA research | free_new | release_lag | 10 | 40 | local_phase0_ready | 6.88 | sufficient_observations, tradable_surface |
| W4-076 | New Jersey iGaming and sports-betting ledger | regulated gaming | New Jersey Division of Gaming Enforcement | free_new | release_lag | 12 | 144 | advance_to_fable | 9.15 |  |
| W4-081 | Nevada gaming win and strip mix | regulated gaming | Nevada Gaming Control Board monthly revenue | free_new | release_lag | 20 | 240 | advance_to_fable | 9.09 |  |
| W4-086 | New York sports-wagering handle and hold | regulated gaming | New York State Gaming Commission revenue reports | free_new | release_lag | 4 | 200 | advance_to_fable | 8.98 |  |
| W4-091 | Pennsylvania iGaming and slot/table mix | regulated gaming | Pennsylvania Gaming Control Board revenue | free_new | release_lag | 8 | 96 | advance_to_fable | 8.7 |  |
| W4-096 | Commercial gaming state-tax impulse | regulated gaming | American Gaming Association revenue tracker | free_new | release_lag | 7 | 84 | local_phase0_ready | 7.19 | tradable_surface |
| W4-101 | Colorado cannabis sales and tax cycle | regulated cannabis | Colorado marijuana sales reports | free_new | release_lag | 12 | 144 | reject_or_hold | 6.04 | not_prior_wave_family, tradable_surface |
| W4-106 | Colorado cannabis tax receipt stress | regulated cannabis | Colorado marijuana tax reports | free_new | release_lag | 12 | 144 | reject_or_hold | 5.59 | not_prior_wave_family, tradable_surface |
| W4-111 | FBI NICS firearm demand pulse | consumer durable and firearms | FBI NICS firearm background checks | free_new | release_lag | 25 | 300 | advance_to_fable | 9.44 |  |
| W4-116 | ATF firearm production and import cycle | consumer durable and firearms | ATF firearms commerce statistics | free_new | release_lag | 25 | 25 | local_phase0_ready | 6.5 | sufficient_observations, tradable_surface |
| W4-121 | Nonimmigrant visa issuance travel pulse | travel and migration | State Department NIV statistics | free_new | release_lag | 10 | 120 | local_phase0_ready | 7.49 | tradable_surface |
| W4-126 | Immigrant visa issuance family/workflow pressure | travel and migration | State Department immigrant visa statistics | free_new | release_lag | 10 | 120 | local_phase0_ready | 6.93 | tradable_surface |
| W4-131 | Texas lottery sales discretionary-stress pulse | consumer vice and state lottery | Texas Lottery financial information | free_new | release_lag | 10 | 120 | reject_or_hold | 4.3 | not_prior_wave_family, tradable_surface |
| W4-136 | Massachusetts lottery revenue pulse | consumer vice and state lottery | Massachusetts Lottery financial reports | free_new | release_lag | 10 | 120 | reject_or_hold | 4.15 | not_prior_wave_family, tradable_surface |
| W4-141 | Fedwire large-value payment stress | payments rails | Fedwire volume and value statistics | ready | release_lag | 20 | 240 | local_phase0_ready | 7.18 | not_prior_wave_family, tradable_surface |
| W4-146 | FedACH commercial ACH usage | payments rails | Federal Reserve commercial ACH statistics | ready | release_lag | 20 | 80 | local_phase0_ready | 7.52 | tradable_surface |
| W4-151 | FedNow real-time-payment adoption | payments rails | FedNow volume and value statistics | free_new | release_lag | 3 | 12 | reject_or_hold | 4.67 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-156 | FedNow participant breadth | payments rails | FedNow participants list | free_new | clean | 3 | 156 | local_phase0_ready | 7.84 | tradable_surface |
| W4-161 | RTP network participant breadth | payments rails | TCH RTP participating FIs | free_new | clean | 7 | 365 | local_phase0_ready | 7.93 | tradable_surface |
| W4-166 | RTP network volume/value growth | payments rails | The Clearing House RTP reports | free_new | release_lag | 7 | 28 | reject_or_hold | 4.72 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-171 | Nacha ACH network same-day mix | payments rails | Nacha ACH statistics | free_new | release_lag | 10 | 40 | local_phase0_ready | 6.79 | sufficient_observations, tradable_surface |
| W4-176 | Federal Reserve check-service decay | payments rails | FRB check services volume/value | ready | release_lag | 20 | 240 | local_phase0_ready | 6.32 | tradable_surface |
| W4-181 | Census retail sales category surprise | commerce ledger | Census Monthly Retail Trade | ready | release_lag | 30 | 360 | local_phase0_ready | 6.96 | not_prior_wave_family |
| W4-186 | Census quarterly services demand | commerce ledger | Census Quarterly Services Survey | ready | release_lag | 20 | 80 | reject_or_hold | 5.72 | not_prior_wave_family, tradable_surface |
| W4-191 | Wholesale inventory-sales pressure | commerce ledger | Census Monthly Wholesale Trade | ready | release_lag | 30 | 360 | local_phase0_ready | 7.54 | not_prior_wave_family, tradable_surface |
| W4-196 | Manufacturers orders and backlog stress | commerce ledger | Census M3 manufacturers shipments/inventories/orders | ready | release_lag | 30 | 360 | local_phase0_ready | 7.07 | not_prior_wave_family, tradable_surface |
| W4-201 | BLS CPI average-price pressure | inflation microdata | BLS Public Data API | ready | release_lag | 30 | 360 | local_phase0_ready | 6.47 | not_prior_wave_family, tradable_surface |
| W4-206 | BLS PPI industry input squeeze | inflation microdata | BLS Public Data API | ready | release_lag | 30 | 360 | local_phase0_ready | 6.86 | not_prior_wave_family, tradable_surface |
| W4-211 | BEA consumer income and outlay revision | macro ledger | BEA API | ready | release_lag | 30 | 360 | reject_or_hold | 5.27 | not_prior_wave_family, tradable_surface |
| W4-216 | Federal Reserve consumer-credit mix | credit ledger | Federal Reserve Consumer Credit G.19 | ready | release_lag | 30 | 360 | local_phase0_ready | 7.37 | not_prior_wave_family, tradable_surface |
| W4-221 | NHTSA vPIC model-introduction cadence | vehicle product cycle | NHTSA vPIC API | free_new | clean | 10 | 120 | local_phase0_ready | 8.15 | below_strict_wave4_bar |
| W4-226 | EPA fuel-economy product mix | vehicle product cycle | FuelEconomy.gov data | free_new | release_lag | 30 | 360 | local_phase0_ready | 8.15 | tradable_surface |
| W4-231 | EPA certification test intensity | vehicle product cycle | EPA cars used for fuel-economy testing | free_new | release_lag | 20 | 240 | local_phase0_ready | 8.01 | tradable_surface |
| W4-236 | California AV disengagement progress | autonomous vehicles | California DMV AV reports | free_new | release_lag | 10 | 10 | reject_or_hold | 4.54 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-241 | California AV collision incident pressure | autonomous vehicles | California DMV AV collision reports | free_new | lagged | 10 | 120 | local_phase0_ready | 7.05 | tradable_surface |
| W4-246 | California ZEV sales share | vehicle demand | California Energy Commission ZEV stats | free_new | release_lag | 12 | 48 | advance_to_fable | 8.8 |  |
| W4-251 | California EV charger deployment | charging infrastructure | CEC ZEV infrastructure data | free_new | release_lag | 8 | 32 | reject_or_hold | 5.5 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-256 | Alternative fuel station deployment | vehicle infrastructure | DOE AFDC Station Locator API | free_new | clean | 10 | 365 | local_phase0_ready | 7.37 | not_prior_wave_family |
| W4-261 | FHWA vehicle registration mix | vehicle fleet | FHWA Highway Statistics | free_new | release_lag | 25 | 25 | local_phase0_ready | 6.29 | sufficient_observations, tradable_surface |
| W4-266 | DOT air consumer complaint pressure | air travel quality | DOT Air Travel Consumer Reports | free_new | release_lag | 20 | 240 | local_phase0_ready | 6.85 | not_prior_wave_family, tradable_surface |
| W4-271 | FAA drone registration and waiver activity | drones and robotics | FAA UAS data | partial | release_lag | 8 | 96 | reject_or_hold | 5.06 | tradable_surface |
| W4-276 | CARB executive-order certification cadence | vehicle regulation | CARB executive orders | free_new | lagged | 15 | 180 | local_phase0_ready | 7.47 | tradable_surface |
| W4-281 | LCFS credit-transfer price pressure | transport fuel regulation | CARB LCFS credit reports | free_new | release_lag | 10 | 120 | local_phase0_ready | 7.59 | not_prior_wave_family |
| W4-286 | Meta Ad Library commercial/political intensity | advertising transparency | Meta Ad Library API | partial | clean | 7 | 365 | reject_or_hold | 5.47 | not_prior_wave_family, tradable_surface |
| W4-291 | Google Ads Transparency advertiser activity | advertising transparency | Google Ads Transparency Center | external_heavy | manual_download | 3 | 156 | reject_or_hold | 2.23 | not_prior_wave_family, tradable_surface, license_clear_enough |
| W4-296 | FCC political-ad file contract flow | advertising transparency | FCC Public Inspection Files | external_heavy | lagged | 10 | 120 | reject_or_hold | 4.84 | tradable_surface |
| W4-301 | Chrome UX origin performance drift | web performance | Chrome UX Report BigQuery | external_heavy | release_lag | 6 | 72 | reject_or_hold | 5.89 | tradable_surface |
| W4-306 | HTTP Archive technology adoption | web technology | HTTP Archive BigQuery | external_heavy | release_lag | 10 | 120 | reject_or_hold | 5.88 | tradable_surface |
| W4-311 | Common Crawl brand-web corpus drift | open web corpus | Common Crawl | external_heavy | lagged | 10 | 120 | reject_or_hold | 3.72 | not_prior_wave_family, tradable_surface |
| W4-316 | Tranco domain-rank adoption | web ranking | Tranco top-sites ranking | free_new | clean | 5 | 260 | local_phase0_ready | 7.18 | tradable_surface |
| W4-321 | Chrome Web Store extension install pressure | browser ecosystem | Chrome Web Store | external_heavy | manual_download | 5 | 260 | reject_or_hold | 2.18 | not_prior_wave_family, tradable_surface, license_clear_enough |
| W4-326 | BuiltWith technology install share | web technology | BuiltWith Trends | paid | paid_unknown | 10 | 120 | reject_or_hold | 2.93 | not_prior_wave_family, usable_source_path, pit_plan, license_clear_enough |
| W4-331 | Wappalyzer technology adoption | web technology | Wappalyzer datasets | paid | paid_unknown | 10 | 120 | reject_or_hold | 2.78 | not_prior_wave_family, usable_source_path, pit_plan, license_clear_enough |
| W4-336 | NYC 311 neighborhood service stress | municipal operations | NYC 311 Open Data | free_new | clean | 6 | 2000 | reject_or_hold | 4.77 | not_prior_wave_family, tradable_surface |
| W4-341 | NYC restaurant inspection pressure | municipal operations | NYC restaurant inspection results | free_new | clean | 10 | 1200 | reject_or_hold | 5.08 | not_prior_wave_family, tradable_surface |
| W4-346 | NYC DOB construction permit pulse | municipal permits | NYC DOB permit issuance | free_new | clean | 10 | 1200 | local_phase0_ready | 6.55 | not_prior_wave_family, tradable_surface |
| W4-351 | NYC film-permit production pulse | municipal permits | NYC film permits | free_new | clean | 10 | 120 | reject_or_hold | 6.18 | tradable_surface |
| W4-356 | NYC TLC trip revenue pressure | urban mobility | NYC TLC trip records | free_new | clean | 10 | 1200 | reject_or_hold | 5.52 | not_prior_wave_family, tradable_surface |
| W4-361 | Chicago 311 municipal stress | municipal operations | Chicago Data Portal service requests | free_new | clean | 6 | 1200 | reject_or_hold | 4.55 | not_prior_wave_family, tradable_surface |
| W4-366 | Chicago building permit mix | municipal permits | Chicago building permits | free_new | clean | 10 | 1200 | reject_or_hold | 5.43 | not_prior_wave_family, tradable_surface |
| W4-371 | San Francisco 311 service stress | municipal operations | SF Open Data 311 cases | free_new | clean | 6 | 1200 | reject_or_hold | 4.55 | not_prior_wave_family, tradable_surface |
| W4-376 | San Francisco building permit pressure | municipal permits | SF building permits | free_new | clean | 10 | 1200 | reject_or_hold | 5.35 | not_prior_wave_family, tradable_surface |
| W4-381 | Los Angeles permit valuation pulse | municipal permits | LA Open Data building permits | free_new | clean | 10 | 1200 | reject_or_hold | 5.35 | not_prior_wave_family, tradable_surface |
| W4-386 | DC 311 public-space stress | municipal operations | Open Data DC 311 | free_new | clean | 6 | 1200 | reject_or_hold | 4.55 | not_prior_wave_family, tradable_surface |
| W4-391 | Seattle permit and land-use pressure | municipal permits | Seattle Open Data permits | free_new | clean | 10 | 1200 | reject_or_hold | 5.35 | not_prior_wave_family, tradable_surface |
| W4-396 | Austin building permit momentum | municipal permits | Austin Open Data permits | free_new | clean | 10 | 1200 | reject_or_hold | 5.35 | not_prior_wave_family, tradable_surface |
| W4-401 | Boston 311 neighborhood stress | municipal operations | Analyze Boston 311 | free_new | clean | 6 | 1200 | reject_or_hold | 4.55 | not_prior_wave_family, tradable_surface |
| W4-406 | Toronto building-permit pulse | municipal permits | Toronto Open Data | free_new | clean | 10 | 1200 | reject_or_hold | 5.42 | not_prior_wave_family, tradable_surface |
| W4-411 | Texas drilling permit master | energy permitting | Texas Railroad Commission data downloads | free_new | release_lag | 40 | 480 | local_phase0_ready | 8.98 | not_prior_wave_family |
| W4-416 | Texas oil and gas production reports | energy production | Texas RRC production queries | free_new | release_lag | 40 | 480 | local_phase0_ready | 8.02 | not_prior_wave_family |
| W4-421 | FracFocus completion and fluid-intensity signal | energy completion | FracFocus data download | free_new | lagged | 12 | 500 | local_phase0_ready | 8.49 | not_prior_wave_family |
| W4-426 | North Dakota Bakken production report | energy production | ND Monthly Production Reports | free_new | release_lag | 20 | 240 | local_phase0_ready | 6.8 | not_prior_wave_family, tradable_surface |
| W4-431 | BOEM offshore lease-sale bid intensity | energy leasing | BOEM lease sales | free_new | event | 20 | 15 | reject_or_hold | 4.65 | not_prior_wave_family, sufficient_observations, tradable_surface |
| W4-436 | BLM onshore oil/gas lease-sale demand | energy leasing | BLM oil and gas lease sales | free_new | event | 15 | 60 | reject_or_hold | 6.15 | not_prior_wave_family, tradable_surface |
| W4-441 | NRC nuclear event notification pressure | nuclear operations | NRC event reports | free_new | clean | 20 | 1000 | local_phase0_ready | 7.43 | not_prior_wave_family, tradable_surface |
| W4-446 | DOE LNG export authorization queue | energy permits | DOE LNG export authorizations | free_new | release_lag | 15 | 120 | local_phase0_ready | 6.83 | not_prior_wave_family, tradable_surface |
| W4-451 | NOAA fisheries landings revenue | food supply and seafood | NOAA commercial fisheries landings | free_new | release_lag | 20 | 240 | local_phase0_ready | 6.66 | not_prior_wave_family, tradable_surface |
| W4-456 | USGS mineral commodity production pressure | minerals | USGS mineral commodity summaries | free_new | release_lag | 30 | 30 | reject_or_hold | 5.56 | sufficient_observations, tradable_surface |
| W4-461 | USGS mineral resource deposit map | minerals | USGS Mineral Resources Data System | free_new | static | 30 | 1 | reject_or_hold | 3.25 | sufficient_observations, tradable_surface |
| W4-466 | USDA AMS wholesale food market news | food pricing | USDA Market News | free_new | release_lag | 20 | 1000 | local_phase0_ready | 6.87 | not_prior_wave_family, tradable_surface |
| W4-471 | Illinois cannabis sales channel mix | regulated cannabis | Illinois cannabis sales figures | free_new | release_lag | 6 | 72 | reject_or_hold | 5.34 | not_prior_wave_family, tradable_surface |
| W4-476 | Michigan cannabis market maturity | regulated cannabis | Michigan CRA statistical reports | free_new | release_lag | 5 | 60 | reject_or_hold | 5.42 | not_prior_wave_family, tradable_surface |
| W4-481 | Ohio casino and racino revenue ledger | regulated gaming | Ohio Casino Control Commission revenue reports | free_new | release_lag | 10 | 120 | local_phase0_ready | 7.59 | below_strict_wave4_bar |
| W4-486 | Maryland casino gaming revenue ledger | regulated gaming | Maryland Lottery and Gaming revenue reports | free_new | release_lag | 10 | 120 | local_phase0_ready | 7.36 | tradable_surface |
| W4-491 | CBP border wait-time congestion | border operations | CBP Border Wait Times API | free_new | clean | 8 | 2000 | local_phase0_ready | 7.13 | not_prior_wave_family, tradable_surface |
| W4-496 | Passport issuance workload pulse | travel administration | State Department passport statistics | free_new | release_lag | 10 | 120 | local_phase0_ready | 7.02 | tradable_surface |

## Source anchors

- Valve Steam Web API: https://partner.steamgames.com/doc/webapi/isteamuserstats
- Steam Store API / Steam Web API: https://developer.valvesoftware.com/wiki/Steam_Web_API
- Twitch API: https://dev.twitch.tv/docs/api/reference
- Twitch Get Videos API: https://dev.twitch.tv/docs/api/videos
- Ticketmaster Discovery API: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
- The Broadway League grosses: https://www.broadwayleague.com/research/grosses-broadway-nyc/
- The Numbers box office data: https://www.the-numbers.com/market/
- YouTube Data API: https://developers.google.com/youtube/v3
- Spotify Web API: https://developer.spotify.com/documentation/web-api
- Spotify Charts: https://charts.spotify.com/charts/overview/global
- NPS Visitor Use Statistics: https://irma.nps.gov/Stats/
- LVCVA visitor statistics: https://www.lvcva.com/research/visitor-statistics/
- Hawaii Tourism Data Warehouse: https://dbedt.hawaii.gov/economic/tourism-datawarehouse/
- VISIT FLORIDA research: https://www.visitflorida.org/research
- New Jersey Division of Gaming Enforcement: https://www.nj.gov/oag/ge/financialandstatisticalinformation.html
- Nevada Gaming Control Board monthly revenue: https://www.gaming.nv.gov/about-us/gaming-revenue-information-gri/
- New York State Gaming Commission revenue reports: https://gaming.ny.gov/revenue-reports
- Pennsylvania Gaming Control Board revenue: https://gamingcontrolboard.pa.gov/news-and-transparency/revenue
- American Gaming Association revenue tracker: https://www.americangaming.org/resources/commercial-gaming-revenue-tracker/
- Colorado marijuana sales reports: https://cdor.colorado.gov/data-and-reports/marijuana-data/marijuana-sales-reports
- Colorado marijuana tax reports: https://cdor.colorado.gov/data-and-reports/marijuana-data/marijuana-tax-reports
- FBI NICS firearm background checks: https://www.fbi.gov/file-repository/nics_firearm_checks_-_month_year_by_state.pdf/view
- ATF firearms commerce statistics: https://www.atf.gov/resource-center/data-statistics
- State Department NIV statistics: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/nonimmigrant-visa-statistics/monthly-nonimmigrant-visa-issuances.html
- State Department immigrant visa statistics: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/immigrant-visa-statistics.html
- Texas Lottery financial information: https://www.texaslottery.com/export/sites/lottery/About_Us/Financial_Information/
- Massachusetts Lottery financial reports: https://www.masslottery.com/about/financial-reports
- Fedwire volume and value statistics: https://www.frbservices.org/resources/financial-services/wires/volume-value-stats
- Federal Reserve commercial ACH statistics: https://www.federalreserve.gov/paymentsystems/fedach_quarterlycomm.htm
- FedNow volume and value statistics: https://www.frbservices.org/resources/financial-services/fednow/volume-value-stats
- FedNow participants list: https://www.frbservices.org/financial-services/fednow/organizations
- TCH RTP participating FIs: https://www.theclearinghouse.org/payment-systems/rtp/RTP-Participating-Financial-Institutions
- The Clearing House RTP reports: https://www.theclearinghouse.org/payment-systems/rtp
- Nacha ACH statistics: https://www.nacha.org/taxonomy/term/336
- FRB check services volume/value: https://www.frbservices.org/resources/financial-services/check/volume-value-stats
- Census Monthly Retail Trade: https://www.census.gov/retail/index.html
- Census Quarterly Services Survey: https://www.census.gov/services/index.html
- Census Monthly Wholesale Trade: https://www.census.gov/wholesale/index.html
- Census M3 manufacturers shipments/inventories/orders: https://www.census.gov/manufacturing/m3/
- BLS Public Data API: https://www.bls.gov/developers/api_signature_v2.htm
- BEA API: https://apps.bea.gov/API/signup/
- Federal Reserve Consumer Credit G.19: https://www.federalreserve.gov/releases/g19/
- NHTSA vPIC API: https://vpic.nhtsa.dot.gov/api/
- FuelEconomy.gov data: https://www.fueleconomy.gov/feg/download.shtml
- EPA cars used for fuel-economy testing: https://www.epa.gov/compliance-and-fuel-economy-data/data-cars-used-testing-fuel-economy
- California DMV AV reports: https://www.dmv.ca.gov/portal/vehicle-industry-services/autonomous-vehicles/
- California Energy Commission ZEV stats: https://www.energy.ca.gov/data-reports/energy-almanac/zero-emission-vehicle-and-infrastructure-statistics-collection/new-zev
- CEC ZEV infrastructure data: https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data
- DOE AFDC Station Locator API: https://developer.nrel.gov/docs/transportation/alt-fuel-stations-v1/
- FHWA Highway Statistics: https://www.fhwa.dot.gov/policyinformation/statistics.cfm
- DOT Air Travel Consumer Reports: https://www.transportation.gov/airconsumer/air-travel-consumer-reports
- FAA UAS data: https://www.faa.gov/uas
- CARB executive orders: https://ww2.arb.ca.gov/resources/documents/executive-orders
- CARB LCFS credit reports: https://ww2.arb.ca.gov/resources/documents/low-carbon-fuel-standard-credit-transfer-activity-reports
- Meta Ad Library API: https://www.facebook.com/ads/library/api/
- Google Ads Transparency Center: https://adstransparency.google.com/
- FCC Public Inspection Files: https://publicfiles.fcc.gov/
- Chrome UX Report BigQuery: https://developer.chrome.com/docs/crux/guides/bigquery
- HTTP Archive BigQuery: https://httparchive.org/faq
- Common Crawl: https://commoncrawl.org/
- Tranco top-sites ranking: https://tranco-list.eu/
- Chrome Web Store: https://chromewebstore.google.com/
- BuiltWith Trends: https://trends.builtwith.com/
- Wappalyzer datasets: https://www.wappalyzer.com/technologies/
- NYC 311 Open Data: https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9
- NYC restaurant inspection results: https://data.cityofnewyork.us/Health/DOHMH-New-York-City-Restaurant-Inspection-Results/43nn-pn8j
- NYC DOB permit issuance: https://data.cityofnewyork.us/Housing-Development/DOB-Permit-Issuance/ipu4-2q9a
- NYC film permits: https://data.cityofnewyork.us/City-Government/Film-Permits/tg4x-b46p
- NYC TLC trip records: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- Chicago Data Portal service requests: https://data.cityofchicago.org/
- SF Open Data 311 cases: https://data.sfgov.org/
- LA Open Data building permits: https://data.lacity.org/
- Open Data DC 311: https://opendata.dc.gov/
- Seattle Open Data permits: https://data.seattle.gov/
- Austin Open Data permits: https://data.austintexas.gov/
- Analyze Boston 311: https://data.boston.gov/
- Toronto Open Data: https://open.toronto.ca/
- Texas Railroad Commission data downloads: https://www.rrc.texas.gov/resource-center/research/data-sets-available-for-download/
- Texas RRC production queries: https://www.rrc.texas.gov/resource-center/research/research-queries/
- FracFocus data download: https://fracfocus.org/data-download
- ND Monthly Production Reports: https://www.dmr.nd.gov/oilgas/mprindex.asp
- BOEM lease sales: https://www.boem.gov/oil-gas-energy/lease-sales
- BLM oil and gas lease sales: https://www.blm.gov/programs/energy-and-minerals/oil-and-gas/leasing/regional-lease-sales
- NRC event reports: https://www.nrc.gov/reading-rm/doc-collections/event-status/event/
- DOE LNG export authorizations: https://www.energy.gov/fecm/listings/lng-reports
- NOAA commercial fisheries landings: https://www.fisheries.noaa.gov/foss/f?p=215:200:10320894814095:::::
- USGS mineral commodity summaries: https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries
- USGS Mineral Resources Data System: https://mrdata.usgs.gov/mrds/
- USDA Market News: https://www.ams.usda.gov/market-news
- Illinois cannabis sales figures: https://idfpr.illinois.gov/profs/adultusecan.html
- Michigan CRA statistical reports: https://www.michigan.gov/cra/resources/cannabis-regulatory-agency-statistical-reports
- Ohio Casino Control Commission revenue reports: https://casinocontrol.ohio.gov/About/MonthlyRevenueReports
- Maryland Lottery and Gaming revenue reports: https://www.mdgaming.com/financial-reports/
- CBP Border Wait Times API: https://bwt.cbp.gov/
- State Department passport statistics: https://travel.state.gov/content/travel/en/about-us/reports-and-statistics.html
