# Signal Lab Wave-2 frontier Phase-0 - 2026-07-06

## Fable audit quarantine

Fable's review found that this wave used lane-level generated metadata where
candidate-level diligence was required. The prior `advance_to_fable` labels
are therefore invalidated. This regenerated artifact restores the stricter
Wave-1-style advance bar (`score >= 10.0`) and blocks Fable dispatch until
each candidate has a corrected point-in-time source path, history claim, and
data-license status. Known concerns such as rail/truck data being attributed
to AIS, ticker-level job postings being attributed to aggregate Indeed data,
the short history of SEC cyber Item 1.05, and paid/private datasets are now
machine-readable blockers.

Wave 2 deliberately avoids the Wave-1 families already explored around
short-side pressure, EDGAR text/attention, option informed flow, insider
repair, China flows, COT, auctions, repo/SOFR, EIA inventory, and the core
equity factor zoo. The search moved to orthogonal data-generating mechanisms:
physical movement of goods and people, weather, satellite observations,
cyber operations, labor, housing, public health, legal/regulatory events,
fixed-income plumbing, private markets, grid stress, and social diffusion.

This is an admission screen, not a validation verdict. A survivor is ready
for Fable to challenge and authorize a real empirical harness. It still has
zero right to enter Signal Lab until rank-IC, HAC t-stat, BH-FDR and DSR are
measured in a pre-registered report.

## First-principles selection rules

1. The data must observe a causal or physical state before it is in prices.
2. The signal must beat an obvious baseline named in advance.
3. The data path must be point-in-time or explicitly lagged.
4. Paid-data candidates are not rejected for being paid, but they cannot be
   Fable-ready without a data contract.
5. Any family close to Wave 1 is treated as overlap and kept out of this run.

## Verdict counts

- Total candidates screened: 200
- Advance to Fable: 0
- Local Phase-0 ready: 103
- Data contract first: 4
- Watchlist/reject: 78
- Reject/hold: 15
- Strict advance score: 10.0

## Survivors by lane

| Lane | Fable | Local | Data | Watch | Reject |
|---|---|---|---|---|---|
| Agriculture and food physical supply | 0 | 9 | 1 | 0 | 0 |
| Consumer mobility and transaction activity | 0 | 7 | 0 | 0 | 3 |
| Cyber and software operational risk | 0 | 10 | 0 | 0 | 0 |
| Environment, water and resource constraints | 0 | 10 | 0 | 0 | 0 |
| Fixed-income market plumbing | 0 | 0 | 0 | 10 | 0 |
| Freight and logistics physical flow | 0 | 10 | 0 | 0 | 0 |
| Global capital flow and sovereign stress | 0 | 7 | 3 | 0 | 0 |
| Housing and real-estate high-frequency cycle | 0 | 0 | 0 | 10 | 0 |
| International real-activity alternative data | 0 | 0 | 0 | 10 | 0 |
| Knowledge, skills and technical frontier diffusion | 0 | 0 | 0 | 9 | 1 |
| Labor and human-capital traces | 0 | 10 | 0 | 0 | 0 |
| Legal, IP and product-safety filings | 0 | 10 | 0 | 0 | 0 |
| Market microstructure beyond options and shorting | 0 | 0 | 0 | 0 | 10 |
| Media, social and narrative diffusion | 0 | 0 | 0 | 10 | 0 |
| Policy, sanctions and legal/regulatory events | 0 | 10 | 0 | 0 | 0 |
| Power grid and energy-infrastructure state | 0 | 10 | 0 | 0 | 0 |
| Private markets, distress and capital formation | 0 | 0 | 0 | 10 | 0 |
| Public-health operational pressure | 0 | 0 | 0 | 10 | 0 |
| Satellite and geospatial economic traces | 0 | 0 | 0 | 9 | 1 |
| Weather and climate shocks | 0 | 10 | 0 | 0 | 0 |

## Fable-ready shortlist

| ID | Candidate | Lane | Transform | First gate | Baseline | Score |
|---|---|---|---|---|---|---|

## Local Phase-0 queue

| ID | Candidate | Lane | Blockers | Transform | Score |
|---|---|---|---|---|---|
| W2-001 | US port anchorage queue impulse | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | anchored cargo-vessel count by port versus 3y seasonal baseline | 8.17 |
| W2-002 | AIS speed collapse by trade lane | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | median vessel speed and idle-time change on major lanes | 8.17 |
| W2-003 | Container lane rate shock | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, container spot-rate history needs a paid/licensed FBX/Drewry-style contract; NOAA AIS is not the source | Asia-US and Asia-Europe spot-rate z-score and second derivative | 8.17 |
| W2-004 | Rail intermodal diffusion | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, rail intermodal data should source to AAR, not NOAA AIS | AAR intermodal carload breadth and acceleration | 8.17 |
| W2-005 | Truck tonnage inflection | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, truck tonnage should source to BTS/ATA, not NOAA AIS | BTS/ATA truck tonnage 3m impulse and revision-aware trend | 8.17 |
| W2-006 | Air-cargo capacity squeeze | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | airport cargo movements and belly-cargo proxy by hub | 8.17 |
| W2-007 | Blank-sailing stress proxy | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | container price spike plus vessel-count drop on same lane | 8.17 |
| W2-008 | Warehouse absorption lag | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | industrial REIT/local vacancy proxy lagged to freight downturns | 8.17 |
| W2-009 | Chassis/drayage congestion proxy | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | port dwell proxy from AIS gap and inland rail handoff delay | 8.17 |
| W2-010 | Red Sea/Suez reroute distance shock | Freight and logistics physical flow | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | lane nautical-mile inflation from AIS route deviations | 8.17 |
| W2-011 | Cooling-degree demand surprise | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | population-weighted CDD anomaly by power region | 9.35 |
| W2-012 | Heating-degree demand surprise | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | population-weighted HDD anomaly by gas region | 9.35 |
| W2-013 | Drought acreage impulse | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | D1-D4 acreage change in crop and cattle states | 9.35 |
| W2-014 | ENSO transition regime | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | ONI crossing and acceleration around neutral/El Nino/La Nina | 9.35 |
| W2-015 | Hurricane economic exposure cone | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | NOAA storm-track probability times county GDP/sector exposure | 9.35 |
| W2-016 | River navigation draft stress | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | Mississippi/Ohio water-level anomaly and barge draft restrictions | 9.35 |
| W2-017 | Wildfire smoke productivity drag | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | FIRMS fires plus downwind PM2.5 population exposure | 9.35 |
| W2-018 | Snowpack water reserve shock | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | SWE percentile in hydro/ag basins | 9.35 |
| W2-019 | Geomagnetic storm risk | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | Kp spike and persistence by satellite/grid-sensitive sectors | 9.35 |
| W2-020 | Freeze-thaw construction window | Weather and climate shocks | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | extreme freeze days followed by thaw in construction-heavy regions | 9.35 |
| W2-031 | KEV vendor exposure shock | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | new CISA KEV entries mapped to public vendors and customers | 8.55 |
| W2-032 | CVE severity avalanche | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | NVD high/CVSS count acceleration by vendor/product CPE | 8.55 |
| W2-033 | Federal patch deadline wall | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | KEV due-date clustering for vendor ecosystems | 8.55 |
| W2-034 | Material cyber 8-K sequence | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, SEC cyber Item 1.05 history starts in Dec 2023, so the lane-level 5y history claim is overstated | Item 1.05 filing and amendment cadence | 8.55 |
| W2-035 | Cloud outage blast radius | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | status-page outage duration weighted by customer overlap | 8.55 |
| W2-036 | Open-source dependency shock | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | critical CVEs in dependencies used by public software stacks | 8.55 |
| W2-037 | Certificate-transparency domain churn | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | new suspicious domains targeting brand/product strings | 8.55 |
| W2-038 | Ransomware leak-site mention | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | victim leak posts mapped to tickers and suppliers | 8.55 |
| W2-039 | Software end-of-life cliff | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | EOL product dates weighted by installed-base proxies | 8.55 |
| W2-040 | Cyber insurance stress proxy | Cyber and software operational risk | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | breach frequency by NAICS crossed with insurer exposure | 8.55 |
| W2-041 | Company job-posting impulse | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, ticker-level job postings are not available from the public Indeed Hiring Lab aggregate API | ticker-mapped posting growth by function and geography | 8.65 |
| W2-042 | AI-job share acceleration | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | share of postings requiring AI/ML skills by industry | 8.65 |
| W2-043 | Remote-work reversal shock | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | remote-posting share collapse by company/sector | 8.65 |
| W2-044 | WARN layoff intensity | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | advance layoff notices by company/state normalized by workforce | 8.65 |
| W2-045 | H-1B sponsorship contraction | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | USCIS petitions by employer and NAICS versus trend | 8.65 |
| W2-046 | Wage-offer pressure | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, posted wage pressure at company/ticker level requires a paid postings vendor, not the public Indeed aggregate API | posted wage growth by occupation/sector | 8.65 |
| W2-047 | Hiring mix quality | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | engineering/sales/support posting ratios by company | 8.65 |
| W2-048 | Layoff-with-demand divergence | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | WARN spikes while job postings remain firm | 8.65 |
| W2-049 | Occupational bottleneck index | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | hard-to-fill role posting duration by sector | 8.65 |
| W2-050 | Unionization pressure watch | Labor and human-capital traces | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | NLRB election petitions and unfair-labor-practice filings by employer | 8.65 |
| W2-061 | TSA throughput surprise | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | same-weekday passenger count surprise and acceleration | 8.37 |
| W2-062 | Restaurant seated-diner impulse | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, OpenTable public seated-diner continuity requires re-check before use; do not assume current access | OpenTable YoY seated diners by city | 8.37 |
| W2-063 | Airport cancellation stress | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | FAA/airline delay and cancellation rates by hub | 8.37 |
| W2-066 | Gasoline station demand | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | EIA implied gasoline demand and regional price stress | 8.37 |
| W2-067 | App-download rank impulse | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | app-store rank change for travel/retail/fintech apps | 8.37 |
| W2-069 | Foot-traffic divergence | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | Placer-like visits versus sales expectations | 8.37 |
| W2-070 | Transit-station recovery | Consumer mobility and transaction activity | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | mobility/public transit ridership by city and office-exposed REITs | 8.37 |
| W2-071 | Crop-condition diffusion | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | good/excellent share change across corn/soy/wheat states | 9.35 |
| W2-072 | Planting-pace surprise | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | crop progress versus 5y average by state | 9.35 |
| W2-073 | Harvest-pace bottleneck | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | harvest progress lag plus wet-weather anomaly | 9.35 |
| W2-074 | Export-inspection demand shock | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | weekly export inspections versus seasonal baseline | 9.35 |
| W2-075 | Cold-storage inventory pressure | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | meat/dairy cold-storage stock build/draw | 9.35 |
| W2-076 | Livestock slaughter weight stress | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | weight/head and slaughter pace divergence | 9.35 |
| W2-077 | Fertilizer affordability spread | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | fertilizer/input price versus crop revenue proxy | 9.35 |
| W2-078 | Avian-flu protein shock | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | USDA/APHIS flock impact and egg/chicken price spread | 9.35 |
| W2-079 | Barge freight crop basis | Agriculture and food physical supply | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | river-level and barge-rate pressure around harvest | 9.35 |
| W2-091 | Federal Register comment surge | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | comment count and late-comment acceleration by rule/theme | 8.55 |
| W2-092 | OFAC sanctions exposure shock | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | new sanctioned entities mapped to issuer customers/suppliers/countries | 8.55 |
| W2-093 | Tariff docket pressure | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | USTR/Commerce tariff action by product code and issuer exposure | 8.55 |
| W2-094 | Import detention intensity | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | CBP/forced-labor detention actions by product/country | 8.55 |
| W2-095 | CPSC recall severity | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | recall count, units affected, injury flags mapped to issuer | 8.55 |
| W2-096 | NHTSA defect escalation | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | complaints/investigations/recalls by model and manufacturer | 8.55 |
| W2-097 | ITC Section 337 action | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | patent/import exclusion investigations by company and product | 8.55 |
| W2-098 | Antitrust enforcement heat | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | DOJ/FTC action and consent order pipeline by sector | 8.55 |
| W2-099 | PACER litigation burst | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | new civil filings and class-action clusters against ticker | 8.55 |
| W2-100 | Trademark application momentum | Policy, sanctions and legal/regulatory events | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | new trademark filings by brand/category and company | 8.55 |
| W2-121 | ERCOT scarcity price pulse | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | real-time price spikes and reserve margin tightness | 8.35 |
| W2-122 | PJM congestion rent shock | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | node/zone congestion and LMP spreads | 8.35 |
| W2-123 | ISO interconnection queue bottleneck | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | queue additions/withdrawals and study delays by region | 8.35 |
| W2-124 | Data-center load inflection | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | large-load interconnection and utility IRP revisions | 8.35 |
| W2-125 | Baker Hughes rig-cycle turn | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | rig count by basin and commodity type | 8.35 |
| W2-126 | Refinery utilization spread | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | utilization by PADD versus crack spread | 8.35 |
| W2-127 | LNG feedgas demand | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | terminal feedgas and utilization versus global gas spreads | 8.35 |
| W2-128 | Nuclear outage cluster | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | reactor outage MW and duration by region | 8.35 |
| W2-129 | Wind/solar capacity-factor surprise | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | renewable generation versus weather-implied baseline | 8.35 |
| W2-130 | Transmission outage stress | Power grid and energy-infrastructure state | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | reported transmission constraints/outages by ISO | 8.35 |
| W2-131 | TIC foreign Treasury demand | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | net foreign purchases by country and maturity | 8.45 |
| W2-132 | Reserve drawdown stress | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | FX reserves decline versus import cover by country | 8.45 |
| W2-133 | BIS cross-border bank credit impulse | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | cross-border claims growth by borrower country/sector | 8.45 |
| W2-134 | IMF reserve adequacy gap | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | reserve adequacy metrics and external funding need | 8.45 |
| W2-136 | Capital-control news pulse | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | policy texts imposing/removing capital restrictions | 8.45 |
| W2-137 | Remittance-flow surprise | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | remittance inflow growth versus FX and consumption proxies | 8.45 |
| W2-139 | Import-cover commodity vulnerability | Global capital flow and sovereign stress | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | commodity import bill versus reserves by country | 8.45 |
| W2-151 | Trademark launch pipeline | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | new trademark filings by company/category | 8.15 |
| W2-152 | Trademark abandonment rate | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | abandoned applications versus active portfolio | 8.15 |
| W2-153 | ITC import exclusion risk | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | Section 337 investigations by issuer/product | 8.15 |
| W2-154 | Patent-litigation defendant burst | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | PACER/IP case filings mapped to issuer | 8.15 |
| W2-155 | CPSC recall unit severity | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | recall units/injuries/remedy cost by issuer | 8.15 |
| W2-156 | NHTSA complaint acceleration | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | vehicle complaints per active fleet by model | 8.15 |
| W2-157 | FAA airworthiness directive exposure | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | airworthiness directives mapped to aerospace suppliers | 8.15 |
| W2-158 | EPA enforcement action | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, EPA enforcement action cannot be sourced to the lane's USPTO trademark data | enforcement cases and penalty size by company/facility | 8.15 |
| W2-159 | OSHA severe-injury cluster | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, OSHA severe-injury data cannot be sourced to the lane's USPTO trademark data | workplace safety incidents by employer/facility | 8.15 |
| W2-160 | CFPB complaint pressure | Legal, IP and product-safety filings | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild, CFPB complaint pressure cannot be sourced to the lane's USPTO trademark data | consumer-finance complaints by company/product | 8.15 |
| W2-171 | Reservoir-level scarcity | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | reservoir percentile by hydro/ag/municipal basin | 9.15 |
| W2-172 | River-flow industrial constraint | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | USGS flow anomaly near key industrial corridors | 9.15 |
| W2-173 | Hydropower generation surprise | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | hydro output versus snowpack and seasonality | 9.15 |
| W2-174 | Air-quality production drag | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | PM2.5/ozone exceedance days by industrial region | 9.15 |
| W2-175 | Carbon allowance regime shock | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | EUA/CCA/RGGI allowance price momentum and volatility | 9.15 |
| W2-176 | Renewable credit spread | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | REC price divergence by region | 9.15 |
| W2-177 | Water-rights legal stress | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | drought plus water-rights rulings by basin | 9.15 |
| W2-178 | Insurance climate withdrawal | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | insurer withdrawal and rate filings by state | 9.15 |
| W2-179 | Industrial pollution enforcement | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | EPA exceedance/enforcement cluster near facilities | 9.15 |
| W2-180 | Natural-disaster declaration density | Environment, water and resource constraints | below_strict_wave1_advance_bar, wave2_generated_lane_metadata_requires_candidate_source_rebuild | FEMA disasters by county and sector exposure | 9.15 |

## Data-contract queue

| ID | Candidate | Lane | Data path | Blockers | Score |
|---|---|---|---|---|---|
| W2-080 | WASDE surprise map | Agriculture and food physical supply | USDA NASS QuickStats; build PIT panel for wasde surprise map. | data_path, pit_plan | 6.55 |
| W2-135 | Sovereign CDS spread shock | Global capital flow and sovereign stress | Treasury International Capital; build PIT panel for sovereign cds spread shock. | data_path, pit_plan | 5.65 |
| W2-138 | Dollar funding squeeze abroad | Global capital flow and sovereign stress | Treasury International Capital; build PIT panel for dollar funding squeeze abroad. | data_path, pit_plan | 5.65 |
| W2-140 | Local-currency bond outflow | Global capital flow and sovereign stress | Treasury International Capital; build PIT panel for local-currency bond outflow. | data_path, pit_plan | 5.65 |

## Watch/reject queue

| ID | Candidate | Lane | Verdict | Blockers | Score |
|---|---|---|---|---|---|
| W2-021 | Night-lights industrial belt nowcast | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-022 | Refinery flaring anomaly | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-023 | Mine activity thermal pulse | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-025 | Construction-site activity | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-026 | Power-plant plume proxy | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-027 | Port container-stack area | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-028 | Agricultural greenness divergence | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-029 | Conflict/economic-darkening shock | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-030 | Fishing-fleet light displacement | Satellite and geospatial economic traces | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-051 | Price-cut breadth impulse | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-052 | Pending-sales rate shock | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-053 | New-listing drought | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-054 | Rent-growth inflection | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-055 | Mortgage purchase-app thrust | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-056 | Refi-cashout proxy | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-057 | Builder cancellation stress | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-058 | Affordability spread | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-059 | Rental vacancy squeeze | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-060 | Home-insurance shock | Housing and real-estate high-frequency cycle | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.93 |
| W2-081 | Flu intensity consumer drag | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-082 | Wastewater virus acceleration | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-083 | FDA adverse-event cluster | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-084 | Device adverse-event surge | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-085 | CMS reimbursement draft shock | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-086 | Hospital occupancy stress | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-087 | Drug shortage substitution | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-088 | Clinical enrollment slippage | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-089 | PubMed publication velocity | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-090 | Opioid/overdose regional alert | Public-health operational pressure | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.73 |
| W2-101 | TRACE turnover stress | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild, per-trade TRACE-style liquidity work needs a licensed/verified data path, not a generic fixed-income page | 7.75 |
| W2-102 | Corporate bond price dispersion | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-103 | Primary issuance window | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild, primary issuance concession/deal-quality fields are generally paid-data, not available from SIFMA summary statistics | 7.75 |
| W2-104 | CMDI impulse | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-105 | Muni distress spillover | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-106 | ABS issuance freeze | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-107 | Treasury market depth proxy | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-108 | TIPS liquidity wedge | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-109 | Dealer balance-sheet quarter-end | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-110 | Fallen-angel pipeline | Fixed-income market plumbing | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.75 |
| W2-111 | VC funding drought | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-112 | Down-round frequency | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-113 | Startup layoff breadth | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-114 | Venture debt stress | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-115 | SPAC redemption pressure | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-116 | IPO S-1 filing quality | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-117 | Secondary-market mark shock | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild, private secondary-market marks are paid/vendor data | 6.93 |
| W2-118 | Chapter 11 supplier exposure | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-119 | Private-credit BDC discount | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-120 | Commercial real-estate loan maturity wall | Private markets, distress and capital formation | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 6.93 |
| W2-141 | GDELT entity-tone shock | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-142 | Reddit attention persistence | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-143 | StockTwits disagreement index | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-144 | Podcast transcript theme velocity | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-145 | YouTube product-review sentiment | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-146 | App-review rating drift | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-147 | Search-trend brand divergence | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-148 | Meme-to-fundamental split | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-149 | Narrative crowding decay | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-150 | Local-news incident cluster | Media, social and narrative diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-161 | arXiv topic acceleration | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-162 | Model-benchmark leap | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-163 | StackOverflow question decay | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-164 | Developer skill-mismatch | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-165 | University enrollment mix | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-167 | Conference paper acceptance cluster | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-168 | Standards-body activity | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-169 | Scientific retraction cluster | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-170 | Dataset/benchmark usage decay | Knowledge, skills and technical frontier diffusion | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.25 |
| W2-181 | EM night-lights nowcast | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild, night-lights nowcast should source to VIIRS/NASA night-lights data, not the lane's MODIS NDVI source | 7.05 |
| W2-182 | Port-call export nowcast | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild, port-call export nowcast should source to AIS/port data, not the lane's MODIS NDVI source | 7.05 |
| W2-183 | Customs data surprise | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-184 | Food-price stress basket | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-185 | Electricity consumption proxy | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild, electricity consumption proxy should source to grid/load data or night-lights data, not MODIS NDVI | 7.05 |
| W2-186 | Local policy liquidity ops | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-187 | Local ETF premium/discount | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-188 | Export-control exposure | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-189 | Tourism arrival nowcast | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-190 | Remittance destination impulse | International real-activity alternative data | watchlist_or_reject | weak_admission_score, wave2_generated_lane_metadata_requires_candidate_source_rebuild | 7.05 |
| W2-024 | Retail parking-lot occupancy | Satellite and geospatial economic traces | reject_or_hold | data_path, pit_plan | 5.55 |
| W2-064 | Hotel occupancy nowcast | Consumer mobility and transaction activity | reject_or_hold | data_path, pit_plan | 5.07 |
| W2-065 | Theme-park wait-time proxy | Consumer mobility and transaction activity | reject_or_hold | data_path, pit_plan | 5.07 |
| W2-068 | Credit-card spend pulse | Consumer mobility and transaction activity | reject_or_hold | data_path, pit_plan | 5.07 |
| W2-166 | Open-course enrollment surge | Knowledge, skills and technical frontier diffusion | reject_or_hold | data_path, pit_plan | 3.95 |
| W2-191 | Odd-lot share imbalance | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-192 | Closing-auction imbalance | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-193 | Opening-gap absorption | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-194 | Intraday liquidity drought | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-195 | Realized correlation shock | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-196 | ETF premium-discount stress | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-197 | Index futures cash-basis wedge | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-198 | Treasury fails-to-deliver stress | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-199 | Exchange outage / halt density | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |
| W2-200 | Volume-at-price vacuum | Market microstructure beyond options and shorting | reject_or_hold | data_path, pit_plan | 5.43 |

## Full 200-candidate docket

| ID | Candidate | Lane | Market | Data | PIT | Years | Verdict | Lane source | Source audit |
|---|---|---|---|---|---|---|---|---|---|
| W2-001 | US port anchorage queue impulse | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-002 | AIS speed collapse by trade lane | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-003 | Container lane rate shock | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild, container spot-rate history needs a paid/licensed FBX/Drewry-style contract; NOAA AIS is not the source |
| W2-004 | Rail intermodal diffusion | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild, rail intermodal data should source to AAR, not NOAA AIS |
| W2-005 | Truck tonnage inflection | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild, truck tonnage should source to BTS/ATA, not NOAA AIS |
| W2-006 | Air-cargo capacity squeeze | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-007 | Blank-sailing stress proxy | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-008 | Warehouse absorption lag | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-009 | Chassis/drayage congestion proxy | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-010 | Red Sea/Suez reroute distance shock | Freight and logistics physical flow | Transport / industrials | free_new | release_lag | 7 | local_phase0_ready | NOAA MarineCadastre AIS | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-011 | Cooling-degree demand surprise | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-012 | Heating-degree demand surprise | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-013 | Drought acreage impulse | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-014 | ENSO transition regime | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-015 | Hurricane economic exposure cone | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-016 | River navigation draft stress | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-017 | Wildfire smoke productivity drag | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-018 | Snowpack water reserve shock | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-019 | Geomagnetic storm risk | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-020 | Freeze-thaw construction window | Weather and climate shocks | Commodities / sectors | free_new | release_lag | 20 | local_phase0_ready | NOAA Climate Data Online | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-021 | Night-lights industrial belt nowcast | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-022 | Refinery flaring anomaly | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-023 | Mine activity thermal pulse | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-024 | Retail parking-lot occupancy | Satellite and geospatial economic traces | Global sectors | paid | paid_unknown | 10 | reject_or_hold | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-025 | Construction-site activity | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-026 | Power-plant plume proxy | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-027 | Port container-stack area | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-028 | Agricultural greenness divergence | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-029 | Conflict/economic-darkening shock | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-030 | Fishing-fleet light displacement | Satellite and geospatial economic traces | Global sectors | external_heavy | lagged | 10 | watchlist_or_reject | NASA FIRMS active fire | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-031 | KEV vendor exposure shock | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-032 | CVE severity avalanche | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-033 | Federal patch deadline wall | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-034 | Material cyber 8-K sequence | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild, SEC cyber Item 1.05 history starts in Dec 2023, so the lane-level 5y history claim is overstated |
| W2-035 | Cloud outage blast radius | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-036 | Open-source dependency shock | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-037 | Certificate-transparency domain churn | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-038 | Ransomware leak-site mention | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-039 | Software end-of-life cliff | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-040 | Cyber insurance stress proxy | Cyber and software operational risk | Software / infrastructure | free_new | clean | 5 | local_phase0_ready | CISA KEV catalog | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-041 | Company job-posting impulse | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild, ticker-level job postings are not available from the public Indeed Hiring Lab aggregate API |
| W2-042 | AI-job share acceleration | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-043 | Remote-work reversal shock | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-044 | WARN layoff intensity | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-045 | H-1B sponsorship contraction | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-046 | Wage-offer pressure | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild, posted wage pressure at company/ticker level requires a paid postings vendor, not the public Indeed aggregate API |
| W2-047 | Hiring mix quality | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-048 | Layoff-with-demand divergence | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-049 | Occupational bottleneck index | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-050 | Unionization pressure watch | Labor and human-capital traces | US equities / macro | free_new | lagged | 5 | local_phase0_ready | Indeed Hiring Lab API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-051 | Price-cut breadth impulse | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-052 | Pending-sales rate shock | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-053 | New-listing drought | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-054 | Rent-growth inflection | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-055 | Mortgage purchase-app thrust | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-056 | Refi-cashout proxy | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-057 | Builder cancellation stress | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-058 | Affordability spread | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-059 | Rental vacancy squeeze | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-060 | Home-insurance shock | Housing and real-estate high-frequency cycle | Housing / consumer | free_new | lagged | 8 | watchlist_or_reject | Redfin downloadable housing data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-061 | TSA throughput surprise | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-062 | Restaurant seated-diner impulse | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild, OpenTable public seated-diner continuity requires re-check before use; do not assume current access |
| W2-063 | Airport cancellation stress | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-064 | Hotel occupancy nowcast | Consumer mobility and transaction activity | Consumer / travel | paid | paid_unknown | 7 | reject_or_hold | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-065 | Theme-park wait-time proxy | Consumer mobility and transaction activity | Consumer / travel | paid | paid_unknown | 7 | reject_or_hold | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-066 | Gasoline station demand | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-067 | App-download rank impulse | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-068 | Credit-card spend pulse | Consumer mobility and transaction activity | Consumer / travel | paid | paid_unknown | 7 | reject_or_hold | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-069 | Foot-traffic divergence | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-070 | Transit-station recovery | Consumer mobility and transaction activity | Consumer / travel | free_new | clean | 7 | local_phase0_ready | TSA checkpoint volumes | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-071 | Crop-condition diffusion | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-072 | Planting-pace surprise | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-073 | Harvest-pace bottleneck | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-074 | Export-inspection demand shock | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-075 | Cold-storage inventory pressure | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-076 | Livestock slaughter weight stress | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-077 | Fertilizer affordability spread | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-078 | Avian-flu protein shock | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-079 | Barge freight crop basis | Agriculture and food physical supply | Agriculture / food | free_new | release_lag | 20 | local_phase0_ready | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-080 | WASDE surprise map | Agriculture and food physical supply | Agriculture / food | paid | paid_unknown | 20 | data_contract_first | USDA NASS QuickStats | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-081 | Flu intensity consumer drag | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-082 | Wastewater virus acceleration | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-083 | FDA adverse-event cluster | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-084 | Device adverse-event surge | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-085 | CMS reimbursement draft shock | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-086 | Hospital occupancy stress | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-087 | Drug shortage substitution | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-088 | Clinical enrollment slippage | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-089 | PubMed publication velocity | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-090 | Opioid/overdose regional alert | Public-health operational pressure | Healthcare / consumer | free_new | lagged | 8 | watchlist_or_reject | openFDA APIs | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-091 | Federal Register comment surge | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-092 | OFAC sanctions exposure shock | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-093 | Tariff docket pressure | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-094 | Import detention intensity | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-095 | CPSC recall severity | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-096 | NHTSA defect escalation | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-097 | ITC Section 337 action | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-098 | Antitrust enforcement heat | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-099 | PACER litigation burst | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-100 | Trademark application momentum | Policy, sanctions and legal/regulatory events | Policy-exposed equities | ready | clean | 10 | local_phase0_ready | Federal Register API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-101 | TRACE turnover stress | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild, per-trade TRACE-style liquidity work needs a licensed/verified data path, not a generic fixed-income page |
| W2-102 | Corporate bond price dispersion | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-103 | Primary issuance window | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild, primary issuance concession/deal-quality fields are generally paid-data, not available from SIFMA summary statistics |
| W2-104 | CMDI impulse | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-105 | Muni distress spillover | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-106 | ABS issuance freeze | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-107 | Treasury market depth proxy | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-108 | TIPS liquidity wedge | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-109 | Dealer balance-sheet quarter-end | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-110 | Fallen-angel pipeline | Fixed-income market plumbing | Credit / rates | external_heavy | lagged | 10 | watchlist_or_reject | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-111 | VC funding drought | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-112 | Down-round frequency | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-113 | Startup layoff breadth | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-114 | Venture debt stress | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-115 | SPAC redemption pressure | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-116 | IPO S-1 filing quality | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-117 | Secondary-market mark shock | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild, private secondary-market marks are paid/vendor data |
| W2-118 | Chapter 11 supplier exposure | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-119 | Private-credit BDC discount | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-120 | Commercial real-estate loan maturity wall | Private markets, distress and capital formation | Private/public crossover | external_heavy | lagged | 8 | watchlist_or_reject | FRED/ALFRED macro data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-121 | ERCOT scarcity price pulse | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-122 | PJM congestion rent shock | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-123 | ISO interconnection queue bottleneck | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-124 | Data-center load inflection | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-125 | Baker Hughes rig-cycle turn | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-126 | Refinery utilization spread | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-127 | LNG feedgas demand | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-128 | Nuclear outage cluster | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-129 | Wind/solar capacity-factor surprise | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-130 | Transmission outage stress | Power grid and energy-infrastructure state | Utilities / energy / industrials | free_new | release_lag | 10 | local_phase0_ready | EIA electricity data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-131 | TIC foreign Treasury demand | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-132 | Reserve drawdown stress | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-133 | BIS cross-border bank credit impulse | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-134 | IMF reserve adequacy gap | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-135 | Sovereign CDS spread shock | Global capital flow and sovereign stress | FX / global macro | paid | paid_unknown | 20 | data_contract_first | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-136 | Capital-control news pulse | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-137 | Remittance-flow surprise | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-138 | Dollar funding squeeze abroad | Global capital flow and sovereign stress | FX / global macro | paid | paid_unknown | 20 | data_contract_first | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-139 | Import-cover commodity vulnerability | Global capital flow and sovereign stress | FX / global macro | free_new | release_lag | 20 | local_phase0_ready | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-140 | Local-currency bond outflow | Global capital flow and sovereign stress | FX / global macro | paid | paid_unknown | 20 | data_contract_first | Treasury International Capital | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-141 | GDELT entity-tone shock | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-142 | Reddit attention persistence | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-143 | StockTwits disagreement index | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-144 | Podcast transcript theme velocity | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-145 | YouTube product-review sentiment | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-146 | App-review rating drift | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-147 | Search-trend brand divergence | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-148 | Meme-to-fundamental split | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-149 | Narrative crowding decay | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-150 | Local-news incident cluster | Media, social and narrative diffusion | US equities / themes | free_new | clean | 10 | watchlist_or_reject | GDELT project | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-151 | Trademark launch pipeline | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-152 | Trademark abandonment rate | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-153 | ITC import exclusion risk | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-154 | Patent-litigation defendant burst | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-155 | CPSC recall unit severity | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-156 | NHTSA complaint acceleration | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-157 | FAA airworthiness directive exposure | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-158 | EPA enforcement action | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild, EPA enforcement action cannot be sourced to the lane's USPTO trademark data |
| W2-159 | OSHA severe-injury cluster | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild, OSHA severe-injury data cannot be sourced to the lane's USPTO trademark data |
| W2-160 | CFPB complaint pressure | Legal, IP and product-safety filings | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO trademark data | wave2_generated_lane_metadata_requires_candidate_source_rebuild, CFPB complaint pressure cannot be sourced to the lane's USPTO trademark data |
| W2-161 | arXiv topic acceleration | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-162 | Model-benchmark leap | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-163 | StackOverflow question decay | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-164 | Developer skill-mismatch | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-165 | University enrollment mix | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-166 | Open-course enrollment surge | Knowledge, skills and technical frontier diffusion | Technology / education | paid | paid_unknown | 10 | reject_or_hold | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-167 | Conference paper acceptance cluster | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-168 | Standards-body activity | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-169 | Scientific retraction cluster | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-170 | Dataset/benchmark usage decay | Knowledge, skills and technical frontier diffusion | Technology / education | free_new | clean | 10 | watchlist_or_reject | arXiv API | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-171 | Reservoir-level scarcity | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-172 | River-flow industrial constraint | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-173 | Hydropower generation surprise | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-174 | Air-quality production drag | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-175 | Carbon allowance regime shock | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-176 | Renewable credit spread | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-177 | Water-rights legal stress | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-178 | Insurance climate withdrawal | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-179 | Industrial pollution enforcement | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-180 | Natural-disaster declaration density | Environment, water and resource constraints | Utilities / commodities / industrials | free_new | clean | 20 | local_phase0_ready | USGS water data | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-181 | EM night-lights nowcast | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild, night-lights nowcast should source to VIIRS/NASA night-lights data, not the lane's MODIS NDVI source |
| W2-182 | Port-call export nowcast | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild, port-call export nowcast should source to AIS/port data, not the lane's MODIS NDVI source |
| W2-183 | Customs data surprise | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-184 | Food-price stress basket | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-185 | Electricity consumption proxy | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild, electricity consumption proxy should source to grid/load data or night-lights data, not MODIS NDVI |
| W2-186 | Local policy liquidity ops | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-187 | Local ETF premium/discount | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-188 | Export-control exposure | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-189 | Tourism arrival nowcast | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-190 | Remittance destination impulse | International real-activity alternative data | International / EM | external_heavy | lagged | 10 | watchlist_or_reject | NASA MODIS NDVI | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-191 | Odd-lot share imbalance | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-192 | Closing-auction imbalance | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-193 | Opening-gap absorption | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-194 | Intraday liquidity drought | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-195 | Realized correlation shock | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-196 | ETF premium-discount stress | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-197 | Index futures cash-basis wedge | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-198 | Treasury fails-to-deliver stress | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-199 | Exchange outage / halt density | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |
| W2-200 | Volume-at-price vacuum | Market microstructure beyond options and shorting | US equities / ETFs | paid | paid_unknown | 8 | reject_or_hold | FINRA fixed income / TRACE | wave2_generated_lane_metadata_requires_candidate_source_rebuild |

## Source anchors

These are the original lane-level anchors retained for audit provenance,
not candidate-cleared source paths. Rows with `quality_flags` require
candidate-level source replacement before any empirical harness.

- NOAA MarineCadastre AIS: https://coast.noaa.gov/digitalcoast/tools/ais.html
- NOAA Climate Data Online: https://www.ncei.noaa.gov/cdo-web/
- NASA FIRMS active fire: https://firms.modaps.eosdis.nasa.gov/
- CISA KEV catalog: https://www.cisa.gov/resources-tools/resources/kev-catalog
- Indeed Hiring Lab API: https://docs.indeed.com/hiring-lab-api/
- Redfin downloadable housing data: https://www.redfin.com/news/data-center/
- TSA checkpoint volumes: https://www.tsa.gov/travel/passenger-volumes
- USDA NASS QuickStats: https://www.nass.usda.gov/developer/index.php
- openFDA APIs: https://open.fda.gov/apis/
- Federal Register API: https://www.federalregister.gov/developers/documentation/api/v1
- FINRA fixed income / TRACE: https://www.finra.org/finra-data/fixed-income
- FRED/ALFRED macro data: https://fred.stlouisfed.org/docs/api/fred/
- EIA electricity data: https://www.eia.gov/opendata/
- Treasury International Capital: https://home.treasury.gov/data/treasury-international-capital-tic-system
- GDELT project: https://www.gdeltproject.org/
- USPTO trademark data: https://www.uspto.gov/learning-and-resources/electronic-data-products/trademark-data-products
- arXiv API: https://info.arxiv.org/help/api/index.html
- USGS water data: https://waterdata.usgs.gov/nwis
- NASA MODIS NDVI: https://modis.gsfc.nasa.gov/data/dataprod/mod13.php
