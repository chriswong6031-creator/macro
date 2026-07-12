# Falsifier Field Book — for Fable

**As of:** 2026-07-12  
**Program:** Neural Web long-hold lobe, field-guide phase for the amended A1/A2/A6 contracts  
**Status:** historical evidence collection; calibration prior, not a backtest or promotion claim  
**Decision use:** operator review support only  
**Not investment advice.**

---

## Executive read

This book asks a narrow question: if the proposed long-hold falsifier contract had existed at the time, what would it have seen in public filings, when would it have seen it, and how often would the same shape have been survivable? It uses four purposively selected cases for each of six hold archetypes—two genuine thesis breaks and two false alarms—so that normal cyclicality and repair receive equal weight. The 50/50 construction is deliberate stress testing, not an estimate that half of all challenges become breaks.

The unit of evidence is the public filing or release date. Later restatements, hindsight about an effective date, and price behavior do not move the clock backward. Price appears only in each setup to establish that a position trader could plausibly have owned the name after a meaningful run; it never supplies a business-break verdict.

## Binding boundary from the adjudication

This field book follows [Long-Hold Lobe Brainstorm — Adjudication](LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md), especially LHB-R2, R3, R4, and R10:

- The A1 packet has a business-evidence axis and an expectation-burden axis. The campaign/tape axis is struck. This study contains no support-loss, drawdown, valuation-target, or price-based break rule.
- The replay vocabulary is `not_observed | no_break_observed | challenged | broken | unverifiable`. Two consecutive filed periods of the **same named deterioration** may produce `challenged`; they may not auto-produce `broken`.
- Auto-`broken` is reserved for a filed terminal event that the ticker contract named in advance: Item 1.03 bankruptcy/receivership, a filed primary-endpoint failure, or a named material-agreement termination that ends the registered thesis. Other 8-K events—including Items 2.04, 3.01, 4.02, and 5.02—open review and cap at `challenged` unless a separate legal terminal event arrives.
- Missing or stale evidence is `unverifiable`, never evidence that the thesis is intact.
- No implied-growth, “what must be true,” target-price, or valuation-required-return computation appears here. Those remain locked.
- Acquisition, spin-off, accounting-standard, denominator-sign, and uncorroborated greater-than-20% share-count discontinuities are refusal conditions for per-share bridges, not negative evidence.

## Reading rules and calculations

### Point-in-time clock

`date` means the SEC filing date or the date a company/agency first released the cited fact publicly. If an 8-K filed later recites an earlier effective date, the table uses the filing date. Accession numbers are shown without dashes in EDGAR archive URLs but are written with dashes in the source label where useful.

### Two-filing replay

For each case, the replay freezes one named observable and asks when two adjacent public filings first showed deterioration in the same direction. Different weak facts do not vote together. For example, one quarter of gross-margin compression followed by one quarter of inventory growth is **not** double confirmation.

For a true break, lead time is measured from the second confirming filing to the first public date on which the core hold thesis was clearly invalidated or legally terminated. For a false alarm, resolution time is measured from the challenge to the first filing that reversed the named deterioration or otherwise demonstrated operating recovery. A negative lead means the rule arrived late. “One filing” is discussed case by case rather than assumed superior.

### Observable conventions

- **Gross-margin change YoY:** filed gross margin minus the comparable prior-year period.
- **Receivables/revenue spread:** YoY receivables growth minus YoY revenue growth. A positive spread means collections expanded faster than sales.
- **Inventory/revenue spread:** YoY inventory growth minus YoY revenue growth.
- **Capex/revenue:** filed capital expenditure divided by filed revenue; scope changes are flagged.
- **FCF/share:** `(cash from operations - capital expenditures) / diluted weighted-average shares`, using only comparable filed periods. This is a field-book reconstruction, not a company-defined non-GAAP measure.
- **Backlog/RPO/deferred revenue:** used only when the issuer filed a comparable definition. Contract value, bookings, billings, and RPO are not silently treated as synonyms.
- **Cash runway:** cash and marketable securities divided by the most recent comparable quarterly operating cash burn. A negative or acquisition-distorted burn is shown as `unverifiable` rather than forced into a runway estimate.
- **Peer-relative read:** descriptive only. It asks whether the cited deterioration was visibly company-specific or broadly shared by a relevant industry cohort using contemporaneous primary disclosures. This hand-collected book does not pretend to be the future PIT peer engine.

### Honest-verdict vocabulary

- `VISIBLE_IN_FILINGS_WITH_LEAD`: two-filed-period evidence challenged the thesis before the defined break date.
- `VISIBLE_ONLY_COINCIDENT`: the decisive filing or release disclosed the break when it happened, without useful prior double-confirmation lead.
- `NOT_VISIBLE_IN_FUNDAMENTALS`: the holding error was driven by price, valuation, or narrative and the filed business evidence did not reveal it in time.
- `FALSE_ALARM_CORRECTLY_SURVIVABLE`: the deterioration was real, but the two-filing rule and/or peer/context check could keep it at review while subsequent filings showed repair.

## Case register

The register is a navigation summary; the load-bearing citation for every date is in the corresponding case timeline below.

| ID | Issuer / case window | Outcome arm | Size at onset | Two-filing challenge | Break or recovery anchor | Honest verdict |
|---|---|---|---|---|---|---|
| QC-TB-1 | Under Armour, 2016–17 | True break | Large | 2016-11-02 | 2017-01-31 operating reset | `VISIBLE_IN_FILINGS_WITH_LEAD` — 90d |
| QC-TB-2 | V.F. Corp., 2022–23 | True break | Large | 2022-11-02 | 2023-02-07 dividend-quality reset | `VISIBLE_IN_FILINGS_WITH_LEAD` — 97d |
| QC-FA-1 | Texas Roadhouse, 2022–24 | False alarm | **Mid** | 2022-07-28 | 2024-02-15 first recovery; 2024-05-02 confirmed | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| QC-FA-2 | Ulta Beauty, 2019–21 | False alarm | Large | 2019-08-29 | 2021-05-27 first clean recovery; 2021-08-25 confirmed | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| OO-TB-1 | 2U, 2021–24 | True break | **Mid** | 2024-03-06 | 2024-07-25 Item 1.03 | `VISIBLE_IN_FILINGS_WITH_LEAD` — 141d |
| OO-TB-2 | Stitch Fix, 2021–23 | True break | **Mid** | 2022-06-09 | 2023-01-05 strategy/governance reversal | `VISIBLE_IN_FILINGS_WITH_LEAD` — 210d |
| OO-FA-1 | Amazon, 2021–24 | False alarm | Mega | 2023-02-03 | 2023-10-26 first FCF recovery; 2024-02-02 confirmed | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| OO-FA-2 | FedEx, 2022–24 | False alarm | Large | 2022-12-20 | 2023-09-20 first margin recovery; 2023-12-19 confirmed | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| TR-TB-1 | Hertz, 2019–20 | True break | Small | No pre-break double confirmation | 2020-05-22 public Chapter 11; 2020-05-26 Item 1.03 | `VISIBLE_ONLY_COINCIDENT` |
| TR-TB-2 | Party City, 2021–23 | True break | Small | 2022-08-08 | 2023-01-17 public Chapter 11; 2023-01-18 Item 1.03 | `VISIBLE_IN_FILINGS_WITH_LEAD` — 162d |
| TR-FA-1 | Carvana, 2022–24 | False alarm | Large | `unverifiable` (ADESA scope); no valid challenge clock | 2024-02-22 first full-year post-ADESA operating evidence | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| TR-FA-2 | Teva, 2018–24 | False alarm | Large | 2018-11-01 | 2024-02-12 operating recovery with continued deleveraging | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| CP-TB-1 | Fastly, 2020–22 | True break | **Mid** | 2021-08-06 | 2022-03-01 annual confirmation | `VISIBLE_IN_FILINGS_WITH_LEAD` — 207d |
| CP-TB-2 | Twilio, 2021–23 | True break | Large | 2022-11-04, coincident | 2022-11-04 platform-economics break | `VISIBLE_ONLY_COINCIDENT` |
| CP-FA-1 | Autodesk, 2016–18 | False alarm | Large | 2016-08-30 | 2018-08-30 like-basis recovery | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| CP-FA-2 | Okta, 2021–24 | False alarm | Large | `unverifiable` (Auth0 scope); no valid challenge clock | 2024-03-01 two-print clean comparable evidence | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| CL-TB-1 | FibroGen, 2020–21 | True break | **Mid** | No pre-outcome double confirmation | 2021-08-11 CRL requiring another study | `VISIBLE_ONLY_COINCIDENT` |
| CL-TB-2 | Allakos, 2021 | True break | **Mid** | No pre-outcome double confirmation | 2021-12-22 filed endpoint failure | `VISIBLE_ONLY_COINCIDENT` |
| CL-FA-1 | Axsome, 2021–22 | False alarm | **Mid** | 2021-11-08 | 2022-08-19 approval | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| CL-FA-2 | Immunomedics, 2019–20 | False alarm | **Mid** | 2019-02-25 | 2020-04-22 approval | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| CY-TB-1 | Arch Coal, 2014–16 | True break | Small | 2015-07-31 | 2016-01-11 Item 1.03 | `VISIBLE_IN_FILINGS_WITH_LEAD` — 164d |
| CY-TB-2 | U.S. Silica, 2018–20 | True break | **Mid** | 2019-02-19, coincident | 2019-02-19 structural impairment disclosure | `VISIBLE_ONLY_COINCIDENT` |
| CY-FA-1 | Micron, 2018–20 | False alarm | Large | 2019-06-26 | 2020-09-29 operating recovery | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |
| CY-FA-2 | Freeport-McMoRan, 2014–17 | False alarm | Large | 2015-08-10 | 2017-10-25 two-print operating recovery | `FALSE_ALARM_CORRECTLY_SURVIVABLE` |

### Sample-construction audit

- **Balance:** 24 issuers, exactly 12 true breaks and 12 false alarms; two of each per archetype.
- **Era and breadth:** evidence windows run from 2014 through 2024 across apparel, restaurants, specialty retail, education software, ecommerce, parcel/freight, rental cars, party goods, auto retail, pharmaceuticals, edge cloud, communications software, design software, identity, biotechnology, coal, frac sand, memory, and copper.
- **Size:** 9 of 24 cases, or **37.5%**, were in the $2–10 billion mid-cap band on the nearest contemporaneous 10-K public-float disclosure. Three more were small-caps. This clears the one-third mid-cap requirement without treating tiny speculative names as substitutes.
- **Macro concentration:** Hertz is the only true-break case classified as primarily an abrupt macro shock. Other cyclical cases contain macro exposure by archetype, but the defined break mechanism is issuer leverage, stranded capacity, or operating deterioration rather than the macro move alone.
- **Selection warning:** requiring a verifiable filing record necessarily excludes some narrative/tape-only holding errors. The register therefore cannot estimate the population share of `NOT_VISIBLE_IN_FUNDAMENTALS` cases.

---

## Quality compounder

All dates below are filing dates, or the same-day public-release date for a furnished 8-K exhibit. The replay admits only information filed by that date. Calculations use the displayed filing values; differences from company-presented percentages can reflect rounding. “Challenged” is an evidence state, not a forced sale, and none of the quality-compounder cases meets the narrow legal-terminal rule.

### QC-TB-1 — Under Armour (2016–17): growth remained visible while gross-margin quality broke

#### Setup

Under Armour entered 2016 looking like an unusually clean founder-led brand compounder: rapid category expansion, more than 20% revenue growth, and a long record of market-share gains. Its 2016 Form 10-K performance graph shows that a hypothetical $100 invested at the end of 2011 had become $449.19 at the end of 2015 before retreating to $313.38 at the end of 2016. That price history is setup only; it does not enter the filing replay.

**Size band (filed): large-cap** — the nearest 10-K reported Class A and C public floats totaling approximately **$14.23 billion** at June 30, 2016 ([2016 Form 10-K, filed February 23, 2017, accession 0001336917-17-000017](https://www.sec.gov/Archives/edgar/data/1336917/000133691717000017/0001336917-17-000017-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2016-08-03 | [Q2 2016 Form 10-Q, accession 0001336917-16-000099](https://www.sec.gov/Archives/edgar/data/1336917/000133691716000099/0001336917-16-000099-index.html) | Quarterly revenue was $956.280 million versus $751.911 million, up **27.2%**. Gross profit was $477.647 million versus $379.053 million. Derived gross margin was **49.95% versus 50.41%, down 46 bp**. | First filing in which gross margin contracted year over year despite strong revenue growth. |
| 2016-11-02 | [Q3 2016 Form 10-Q, accession 0001336917-16-000113](https://www.sec.gov/Archives/edgar/data/1336917/000133691716000113/0001336917-16-000113-index.html) | Revenue was $1.421908 billion versus $1.165357 billion, up **22.0%**. Gross profit was $698.624 million versus $587.160 million. Derived gross margin was **49.13% versus 50.38%, down 125 bp**. | Second consecutive filing with the same observable. The contract changes from `no_break_observed` to **challenged** on this date. |
| 2017-01-31 | [Q4/FY 2016 Form 8-K, accession 0001336917-17-000007](https://www.sec.gov/Archives/edgar/data/1336917/000133691717000007/0001336917-17-000007-index.html) | Q4 revenue still rose **11.7%**, but gross margin fell to **44.8% from 48.0%**, a 320-bp decline, and operating income fell 6.1%. Management guided 2017 revenue to only 11%–12% growth and operating income to approximately $320 million versus $420 million in 2016, about **24% lower**. | The quality-growth thesis becomes clearly wrong: the margin deterioration is now accompanied by a material operating-profit reset. |

#### Contract replay

**Named observable:** year-over-year gross-margin change while revenue remains positive. The calculation is gross profit divided by revenue for each current and comparison quarter. The first filing produced a negative reading of 46 bp; the second produced a negative reading of 125 bp. Because the same observable deteriorated in two consecutive filings, the no-look-ahead contract first changed state on **November 2, 2016**.

The “clearly wrong” endpoint is **January 31, 2017**, when a third and much larger margin decline arrived with a roughly 24% operating-income guide-down. The filing-only signal therefore led the hard reset by **90 calendar days**. It did not satisfy a legal terminal condition: no Item 1.03 was filed and no explicit terminal agreement or endpoint was disclosed, so the proper state remained **challenged**, not broken.

**One-filing versus two-filing counterfactual:** acting on the August 3 print would have bought 91 additional calendar days. That apparent advantage is not free. A 46-bp margin decline during 27% revenue growth could plausibly have been mix, launch, or freight noise. Waiting for the same metric to worsen to a 125-bp decline retained 90 days of lead and materially improved specificity. Here the two-print rule was useful, not fatal.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD — 90 days.** The filings did not predict the exact January reset, but the archetype-native quality sensor had already failed twice. Revenue growth alone would have hidden the break; gross-margin persistence exposed it.

### QC-TB-2 — V.F. Corporation (2022–23): inventory outran demand before the dividend-quality reset

#### Setup

V.F. Corporation entered fiscal 2023 as a diversified brand compounder built around franchises such as Vans and The North Face, with a long dividend record and a reputation for disciplined brand stewardship. Its 2022 10-K performance graph put a hypothetical $100 investment at $176.14 in April 2021 and $129.00 in April 2022, versus the April 2016 base. Again, that history only establishes why a long-duration quality owner might have been reluctant to declare a break.

**Size band (filed): large-cap** — the nearest 10-K reported non-affiliate public float of approximately **$21.03 billion** at October 2, 2021 ([FY2022 Form 10-K, filed May 26, 2022, accession 0000103379-22-000006](https://www.sec.gov/Archives/edgar/data/103379/000010337922000006/0000103379-22-000006-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2022-08-05 | [Q1 FY2023 Form 10-Q, accession 0000103379-22-000013](https://www.sec.gov/Archives/edgar/data/103379/000010337922000013/0000103379-22-000013-index.html) | Inventory was $2.341395 billion versus $1.216818 billion, up **92.4%**. Quarterly revenue was $2.261595 billion versus $2.194557 billion, up **3.1%**. The inventory-growth less revenue-growth spread was therefore about **+89.4 percentage points**. | First filing with an extreme inventory build relative to demand. |
| 2022-11-02 | [Q2 FY2023 Form 10-Q, accession 0000103379-22-000016](https://www.sec.gov/Archives/edgar/data/103379/000010337922000016/0000103379-22-000016-index.html) | Inventory was $2.749894 billion versus $1.464714 billion, up **87.7%**, while quarterly revenue fell 3.7% to $3.080600 billion. The spread widened to about **+91.4 points**. Six-month operating cash flow was negative $913.957 million versus negative $171.137 million, and the filing recorded a $229.044 million goodwill impairment. | Second consecutive filing with the same inventory-versus-demand failure; contract becomes **challenged**. Cash conversion and impairment provide independent corroboration. |
| 2023-02-07 | [Q3 FY2023 Form 8-K, accession 0001157523-23-000196](https://www.sec.gov/Archives/edgar/data/103379/000115752323000196/0001157523-23-000196-index.html) | Revenue fell 3%; Vans revenue fell 13%. The board cut the quarterly dividend to **$0.30 from $0.51**, a 41% reduction, and management explicitly framed the action as strengthening the financial position. | Clearly-wrong endpoint for a dividend-quality compounder. |
| 2023-10-30 | [Q2 FY2024 Form 8-K, accession 0001157523-23-001573](https://www.sec.gov/Archives/edgar/data/103379/000115752323001573/0001157523-23-001573-index.html) | The company cut the dividend again, to **$0.09 from $0.30**, withdrew its FY2024 revenue and earnings outlook, reduced free-cash-flow guidance to about $600 million from $900 million, and reported Vans revenue down 21%. | Later confirmation that the February reset was not a one-quarter aberration. |

#### Contract replay

**Named observable:** year-over-year inventory growth materially in excess of year-over-year revenue growth. The transparent calculation is `(current inventory / prior-year inventory - 1) - (current-quarter revenue / prior-year current-quarter revenue - 1)`. It read approximately +89.4 points on August 5 and +91.4 points on November 2. The contract therefore changed to **challenged on November 2, 2022**. The large cash-flow deterioration and impairment were not needed to trigger the rule, but they made this a multi-sensor challenge rather than an inventory-only guess.

The “clearly wrong” endpoint is the **February 7, 2023 dividend cut**. For an archetype whose quality claim included dividend durability, the 41% cut made the earlier working thesis untenable even before the second cut. The filing signal led that endpoint by **97 days**. Neither dividend cut is a legal terminal event under the field-book rule, so the correct state remains challenged rather than broken.

**One-filing versus two-filing counterfactual:** the August 5 filing would have provided another 89 days of lead. But retailers and apparel companies were still normalizing supply chains, and one inventory spike could have reflected receipt timing. The November filing showed inventory still up almost 88% while revenue was declining, plus a large operating-cash outflow and impairment. The second-print requirement discarded some lead but dramatically improved the evidentiary quality.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD — 97 days.** The dividend cut itself was not inferable in amount, but a persistent inventory/demand mismatch and collapsing cash conversion were visible before the board acknowledged the balance-sheet constraint.

### QC-FA-1 — Texas Roadhouse (2022–24): a real margin challenge that unit economics survived

#### Setup

Texas Roadhouse fit the quality-compounder archetype through sustained unit growth, strong restaurant-level economics, and a shareholder-return record that made temporary cost pressure easy to overinterpret. Its 2021 10-K performance graph shows a hypothetical $100 invested at the end of 2016 at **$180.83** by year-end 2021. The case asks whether two margin-compression filings required an exit, not whether the pressure was imaginary.

**Size band (filed): mid-cap** — the nearest 10-K reported non-affiliate public float of approximately **$6.58 billion** at June 29, 2021 ([2021 Form 10-K, filed February 25, 2022, accession 0001558370-22-002141](https://www.sec.gov/Archives/edgar/data/1289460/000155837022002141/0001558370-22-002141-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2022-05-05 | [Q1 2022 Form 8-K, accession 0001104659-22-056438](https://www.sec.gov/Archives/edgar/data/1289460/000110465922056438/0001104659-22-056438-index.html) | Revenue increased 23.3%. Restaurant margin fell to **16.4% from 18.6%**, a decline of approximately 213 bp on unrounded filed values. Yet restaurant-margin dollars still increased **9.2%**. | First filing with year-over-year restaurant-margin-rate compression despite sales growth. |
| 2022-07-28 | [Q2 2022 Form 8-K, accession 0001104659-22-083654](https://www.sec.gov/Archives/edgar/data/1289460/000110465922083654/0001104659-22-083654-index.html) | Restaurant margin was **16.6%**, down 116 bp year over year, while restaurant-margin dollars rose **6.6%**. Commodity inflation was 11.8%. | Second consecutive filing with the same rate compression; contract becomes **challenged**. Margin dollars and positive comparable sales remain counter-evidence. |
| 2023-02-16 | [Q4/FY2022 Form 8-K, accession 0001104659-23-022796](https://www.sec.gov/Archives/edgar/data/1289460/000110465923022796/0001104659-23-022796-index.html) | FY2022 restaurant margin was **15.7% versus 16.9%**, down 118 bp. Revenue grew 15.9% and restaurant-margin dollars grew 7.9%. | Challenge persists, but the dollar economics still expand; no second independent sensor breaks. |
| 2024-02-15 | [Q4/FY2023 Form 8-K, accession 0001558370-24-001236](https://www.sec.gov/Archives/edgar/data/1289460/000155837024001236/0001558370-24-001236-index.html) | Q4 restaurant margin rose to **15.3% from 14.5%**, up 75 bp. Restaurant sales rose 15.4% and restaurant-margin dollars rose 21.4%. | First same-metric recovery filing, **567 days** after challenge. |
| 2024-05-02 | [Q1 2024 Form 8-K, accession 0001558370-24-006538](https://www.sec.gov/Archives/edgar/data/1289460/000155837024006538/0001558370-24-006538-index.html) | Restaurant margin rose to **17.4% from 15.9%**, up 148 bp on filed unrounded values; restaurant-margin dollars rose 23.0%, and company comparable sales rose 8.4%. | Second consecutive recovery filing; de-escalation is confirmed **644 days** after challenge. |

#### Contract replay

**Named observable:** year-over-year change in company-defined restaurant margin as a percentage of restaurant and other sales. The May 5 and July 28 filings both showed compression, so a strict replay changes to **challenged on July 28, 2022**. This was a valid challenge: the rate deterioration lasted through FY2022. It was not, however, a two-sensor break. At both trigger filings, restaurant-margin dollars grew, comparable sales remained positive, and management identified exceptional commodity inflation rather than deteriorating guest demand.

The first recovery on the same observable was filed **February 15, 2024**, 567 days after challenge. The next filing repeated the improvement on **May 2, 2024**, making the symmetric two-print recovery clock **644 days**, or roughly seven quarterly reporting intervals after the trigger.

**One-filing versus two-filing counterfactual:** a one-print rule would have challenged the thesis on May 5, 2022, one quarter earlier. That would have treated a 213-bp margin-rate decline as sufficient even though restaurant-margin dollars rose 9.2% and revenue rose 23.3%. The second print proved the inflation squeeze was persistent, so the two-print rule correctly generated a challenge. The false alarm would have come from escalating that challenge into “broken” while the counter-sensors stayed healthy—not from observing nothing.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE — first recovery after 567 days; two-print confirmation after 644 days.** The filing contract usefully forced scrutiny, but the expanding margin-dollar pool and continued demand distinguished cyclical cost pressure from franchise impairment.

### QC-FA-2 — Ulta Beauty (2019–21): comp deceleration without a concurrent margin break

#### Setup

Ulta entered 2019 as a large specialty-retail compounder whose store rollout, loyalty ecosystem, and category leadership had produced years of high comparable-sales growth. Its FY2019 10-K performance graph shows a hypothetical $100 investment at the end of January 2015 at **$203.05** by February 1, 2020. Growth did slow; the question is whether the filing record supported declaring the economic engine broken.

**Size band (filed): large-cap** — the nearest 10-K reported non-affiliate public float of approximately **$14.37 billion** at August 2, 2019 ([FY2019 Form 10-K, filed March 27, 2020, accession 0001558370-20-003272](https://www.sec.gov/Archives/edgar/data/1403568/000155837020003272/0001558370-20-003272-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2019-05-30 | [Q1 FY2019 Form 10-Q, accession 0001558370-19-005390](https://www.sec.gov/Archives/edgar/data/1403568/000155837019005390/0001558370-19-005390-index.html) | Comparable sales rose **7.0% versus 8.1%** in the prior-year quarter. Net sales still rose 12.9% to $1.743029 billion. Derived gross margin was **37.00% versus 36.32%, up about 68 bp**. | First filing in which the comparable-sales growth rate was below the prior-year rate. Gross margin moved the other way. |
| 2019-08-29 | [Q2 FY2019 Form 10-Q, accession 0001558370-19-008397](https://www.sec.gov/Archives/edgar/data/1403568/000155837019008397/0001558370-19-008397-index.html) | Comparable sales rose **6.2% versus 6.5%** in the prior-year quarter. Net sales still rose 12.0% to $1.666607 billion. Derived gross margin was **36.36% versus 35.98%, up about 38 bp**. | Second consecutive filing with comp-growth deceleration; contract becomes **challenged**. Revenue growth and gross margin remain positive counter-sensors. |
| 2021-05-27 | [Q1 FY2021 Form 8-K, accession 0001558370-21-007799](https://www.sec.gov/Archives/edgar/data/1403568/000155837021007799/0001558370-21-007799-index.html) | To avoid a distorted closed-store comparison, the company supplied a 2019 baseline: net sales were **$1.9385 billion versus $1.7430 billion in Q1 FY2019**, up 11.2%; comparable sales were 7.0% versus 2019; gross margin was **38.9% versus 37.0%**. | First clean post-shock recovery print on both demand and margin, **637 days** after challenge. |
| 2021-08-25 | [Q2 FY2021 Form 8-K, accession 0001558370-21-012063](https://www.sec.gov/Archives/edgar/data/1403568/000155837021012063/0001558370-21-012063-index.html) | Comparable sales were **13.1% above Q2 FY2019**; gross margin reached **40.6%**, versus 26.8% in the shutdown-affected 2020 quarter. | Second recovery print; demand was above the pre-shock base and margin had recovered, **727 days** after challenge. |

#### Contract replay

**Named observable:** reported comparable-sales growth rate below the comparable growth rate in the corresponding prior-year quarter. This is an **archetype-specific store-compounder demand sensor outside A2’s current gross-margin pilot**; the replay tests whether it deserves future inclusion and does not imply that A2 already ingests comparable sales. The May and August filings both met it, so the time-machine replay changes to **challenged on August 29, 2019**. The adopted A2 gross-margin leg would **not** have fired: gross margin expanded by about 68 bp and 38 bp in the two trigger filings.

The challenge did not deserve “broken.” The very filings that triggered it reported double-digit net-sales growth and year-over-year gross-margin expansion. That disagreement between the demand-rate sensor and the economics sensor was knowable contemporaneously. The pandemic then made 2020 comparisons unusable for a clean contract adjudication; rather than pretend otherwise, the recovery clock waits for company-furnished 2019 comparisons. Q1 FY2021 supplied the first clean recovery **637 days** after challenge, and Q2 confirmed it at **727 days**.

**One-filing versus two-filing counterfactual:** a one-print trigger on May 30, 2019 would have acted on 7.0% comps, 12.9% revenue growth, and a 68-bp gross-margin expansion. That is precisely the kind of high-quality-but-slower print that the consecutive-filing rule is meant to survive. Even after the second print, the absence of an independent margin or cash-conversion failure argued for challenge and monitoring, not a broken label.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE — first clean recovery after 637 days; confirmed after 727 days.** The slowdown was visible, but the filings also contained the evidence needed to keep a deceleration alert from becoming a false terminal call.

## Owner-operator / allocator

These cases test whether capital allocation still compounds per-share owner value. The named observables are intentionally reproducible from filed cash-flow, share-count, repurchase, and governance data. A management change or restructuring charge can challenge an owner-operator thesis, but the legal state becomes automatically “broken” only when the company files Item 1.03 or discloses an explicit terminal agreement or endpoint.

### OO-TB-1 — 2U (2021–24): acquisition financing and persistent per-share cash deficits before Chapter 11

#### Setup

2U was a founder-led education-technology allocator whose long-duration university relationships and acquisition program asked shareholders to underwrite years of reinvestment. The June 2021 agreement to buy edX assets for $800 million was therefore not merely an operating event; it was a concentrated capital-allocation decision financed in part with expensive secured debt. This replay gives management the benefit of an integration period and asks when filed per-share economics stopped supporting that trust.

**Size band (filed): mid-cap** — the nearest 10-K reported non-affiliate public float of approximately **$2.17 billion** at June 30, 2021 ([2021 Form 10-K, filed March 1, 2022, accession 0001459417-22-000004](https://www.sec.gov/Archives/edgar/data/1459417/000145941722000004/0001459417-22-000004-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2021-06-29 | [Form 8-K, accession 0001193125-21-202610](https://www.sec.gov/Archives/edgar/data/1459417/000119312521202610/0001193125-21-202610-index.html) | 2U agreed to pay **$800 million** for the edX assets. It simultaneously entered a **$475 million** term facility bearing adjusted Eurodollar plus 5.75%, secured by substantially all tangible and intangible assets; the acquisition had no financing contingency. | Capital-allocation burden established, but no falsifier fires merely because an acquisition is large. |
| 2022-03-01 | [2021 Form 10-K, accession 0001459417-22-000004](https://www.sec.gov/Archives/edgar/data/1459417/000145941722000004/0001459417-22-000004-index.html) | Operating cash flow was negative $18.074 million and purchases of property and equipment were $9.788 million, producing narrow free cash flow of **negative $27.862 million**. Diluted weighted-average shares rose to 74.580 million from 67.143 million, up **11.1%**. Derived FCF per diluted share was **negative $0.37**. | `unverifiable` for the two-period trigger: edX closed during the comparison year, so the acquisition-scope refusal overrides what would otherwise look like a first hit. |
| 2023-02-21 | [2022 Form 10-K, accession 0001459417-23-000004](https://www.sec.gov/Archives/edgar/data/1459417/000145941723000004/0001459417-23-000004-index.html) | Operating cash flow was $10.927 million and property-and-equipment purchases were $11.755 million, leaving narrow FCF of **negative $0.828 million**, or about **negative $0.01 per diluted share**. Diluted weighted-average shares rose 3.7% to 77.328 million. Revenue grew only 1.8%, and the filing recorded $78.991 million of goodwill impairments. | First acquisition-clean annual observation with negative FCF per share and a higher diluted share count. |
| 2024-03-06 | [2023 Form 10-K, accession 0001459417-24-000011](https://www.sec.gov/Archives/edgar/data/1459417/000145941724000011/twou-20231231.htm) | Operating cash use was **$3.431 million** and property-and-equipment purchases were $6.021 million, producing narrow FCF of **negative $9.452 million**, or about **negative $0.12 per diluted share**. Diluted weighted-average shares rose 4.6% to 80.891 million from 77.328 million. | Second acquisition-clean annual observation in the same state; contract becomes **challenged**. |
| 2024-07-25 | [Form 8-K, Items 1.03 and 2.04, accession 0001193125-24-184277](https://www.sec.gov/Archives/edgar/data/1459417/000119312524184277/0001193125-24-184277-index.html) | 2U and subsidiaries filed voluntary Chapter 11 cases. The filing said bankruptcy accelerated approximately $380.0 million under the 2025 notes, approximately **$147.0 million** under the 2030 notes, and approximately $414.3 million under the first-lien credit agreement. The contemplated reorganized company would be private. | Filed Item 1.03 activates the field book’s legal auto-terminal rule: state becomes **broken**. |

#### Contract replay

**Named observable:** negative narrow free cash flow per diluted share while the diluted weighted-average share count increases year over year. Narrow FCF is `operating cash flow - purchases of property and equipment`; FCF per share divides that result by filed diluted weighted-average shares. The calculation deliberately excludes acquisition spending and separately capitalized technology or content outlays, making the negative reading conservative rather than exaggerated.

The 2021 filing-year comparison is refused because edX closed during that year. The first clean post-acquisition observation appears in the February 21, 2023 filing and repeats in the March 6, 2024 filing. The strict contract therefore changes to **challenged on March 6, 2024**. The 2022 FCF deficit was small, which is an important caveat, but the same per-share state worsened in the next full post-acquisition year. The hard endpoint is **July 25, 2024**, when Item 1.03 made the legal status automatically **broken**. The filing signal led bankruptcy by **141 days**.

**One-filing versus two-filing counterfactual:** after enforcing the acquisition refusal, a one-print rule would have triggered on February 21, 2023, adding **379 days** of lead. The refused 2021 acquisition year cannot start either clock. Requiring two clean post-acquisition annual observations sacrificed lead but preserved the contract's denominator discipline and still left 141 days before Chapter 11.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD — 141 days to filed Item 1.03.** The acquisition-year comparison was not admissible; two clean post-acquisition negative per-share cash outcomes amid dilution were. The later bankruptcy supplies the rare unambiguous legal endpoint.

### OO-TB-2 — Stitch Fix (2021–23): buybacks failed to offset dilution as the Freestyle allocation unraveled

#### Setup

Stitch Fix entered fiscal 2022 as a founder-controlled personalization platform shifting capital and attention toward Freestyle, its direct-shopping expansion. Its 2021 10-K performance graph shows a hypothetical $100 invested at the November 2017 IPO at **$355.91** by July 31, 2021. Founder Katrina Lake had handed the chief-executive role to Elizabeth Spaulding in 2021, so the case tests both capital allocation and delegated operating stewardship.

**Size band (filed): mid-cap** — the nearest 10-K reported Class A and B public floats totaling approximately **$6.21 billion** at January 30, 2021 ([FY2021 Form 10-K, filed September 27, 2021, accession 0001576942-21-000121](https://www.sec.gov/Archives/edgar/data/1576942/000157694221000121/0001576942-21-000121-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2021-09-27 | [FY2021 Form 10-K, accession 0001576942-21-000121](https://www.sec.gov/Archives/edgar/data/1576942/000157694221000121/0001576942-21-000121-index.html) | Operating cash flow was negative $15.675 million; property-and-equipment purchases were $35.256 million; stock compensation was $100.696 million. Diluted weighted-average shares rose 3.5% to 105.975 million. | Early allocation strain, but not a contract print because the later repurchase program had not begun. |
| 2022-03-09 | [Q2 FY2022 Form 10-Q, accession 0001576942-22-000015](https://www.sec.gov/Archives/edgar/data/1576942/000157694222000015/0001576942-22-000015-index.html) | For the first six months, repurchases were $9.996 million and stock compensation was $64.713 million. Diluted weighted-average shares were **108.777 million versus 104.840 million**, up 3.8%. Q2 revenue rose 2.5% and gross margin expanded 214 bp, so the business sensor was still ambiguous. | First post-buyback filing in which repurchases failed to prevent year-over-year dilution. |
| 2022-06-09 | [Q3 FY2022 Form 10-Q, accession 0001576942-22-000041](https://www.sec.gov/Archives/edgar/data/1576942/000157694222000041/0001576942-22-000041-index.html) | Nine-month repurchases were $30.042 million and stock compensation was $96.305 million. Diluted weighted-average shares were **108.771 million versus 105.458 million**, up 3.1%. Q3 revenue fell 8.0%; derived gross margin fell to **42.62% from 46.00%**, down 338 bp. | Second consecutive filing with ineffective anti-dilution execution; contract becomes **challenged**. Demand and margin now corroborate it. |
| 2022-09-21 | [FY2022 Form 10-K, accession 0001576942-22-000077](https://www.sec.gov/Archives/edgar/data/1576942/000157694222000077/0001576942-22-000077-index.html) | FY repurchases remained $30.042 million against $128.485 million of stock compensation; diluted shares were 108.763 million versus 105.975 million. Derived Q4 revenue was **$481.903 million versus $571.159 million**, down 15.6%, and derived Q4 gross margin was **39.98% versus 46.48%**, down 650 bp. | Allocation and operating deterioration persist. Q4 values are transparently calculated as filed FY totals less filed nine-month totals. |
| 2023-01-05 | [Form 8-K, Items 2.05 and 5.02, accession 0001193125-23-002459](https://www.sec.gov/Archives/edgar/data/1576942/000119312523002459/0001193125-23-002459-index.html) | The company eliminated about **20% of salaried positions**, approximately 6% of the overall workforce. CEO Elizabeth Spaulding stepped down, and founder Katrina Lake returned as interim CEO. | Clearly-wrong endpoint for the delegated Freestyle allocation: a large retrenchment and CEO reversal. It is not a legal terminal event. |

#### Contract replay

**Named observable:** year-over-year diluted weighted-average share count remains higher after buybacks begin. The repurchase and stock-compensation dollars are context, not mathematically interchangeable quantities; the filed share count is the deciding measure. It rose 3.8% in the first post-authorization filing and 3.1% in the next. The contract therefore changes to **challenged on June 9, 2022**. The second filing also supplied an independent operating corroboration—falling revenue and 338 bp of gross-margin compression—that the first filing lacked.

The hard business endpoint is **January 5, 2023**. Eliminating one-fifth of salaried roles and reversing the CEO appointment demonstrated that the delegated strategy had not met its burden. The challenge led that endpoint by **210 days**. Because the company did not file Item 1.03 or disclose a terminal transaction, the legal state remains **challenged**, not broken.

**One-filing versus two-filing counterfactual:** a one-print rule would have challenged on March 9, adding 92 days of lead. At that time Q2 revenue was still positive and gross margin had expanded by 214 bp. The June filing made the allocation signal much more decision-useful by adding demand and margin failures. In this case the two-print gate prevented a premature thesis call without losing the material part of the lead.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD — 210 days.** Buybacks that coexist with rising share counts are not automatically fatal, but here the repeated per-share failure gained independent operating confirmation before the governance reversal.

### OO-FA-1 — Amazon (2021–24): two negative FCF years that capacity normalization reversed

#### Setup

Amazon’s 2021–24 transition combined a founder-to-successor handoff with exceptional fulfillment, transportation, and technology-infrastructure investment. Andy Jassy became CEO in July 2021 while Jeff Bezos remained executive chair. A filing-only allocator contract therefore had to distinguish a genuine per-share cash warning from a deliberate capacity cycle that the balance sheet could survive.

**Size band (filed): mega-cap** — the nearest 10-K reported non-affiliate public float of approximately **$1.507 trillion** at June 30, 2021 ([2021 Form 10-K, filed February 4, 2022, accession 0001018724-22-000005](https://www.sec.gov/Archives/edgar/data/1018724/000101872422000005/0001018724-22-000005-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2022-02-04 | [2021 Form 10-K, accession 0001018724-22-000005](https://www.sec.gov/Archives/edgar/data/1018724/000101872422000005/0001018724-22-000005-index.html) | Net sales rose 21.7% to $469.822 billion. Operating cash flow was $46.327 billion and purchases of property and equipment net of proceeds and incentives were $55.396 billion, producing company-defined FCF of **negative $9.069 billion**, versus positive $31.020 billion. Cash capex was **11.79% of sales**. | First annual filing with negative company-defined FCF. |
| 2023-02-03 | [2022 Form 10-K, accession 0001018724-23-000004](https://www.sec.gov/Archives/edgar/data/1018724/000101872423000004/0001018724-23-000004-index.html) | Net sales rose 9.4% to $513.983 billion. Operating cash flow was $46.752 billion and net cash capex was $58.321 billion, leaving FCF of **negative $11.569 billion**; cash capex was **11.35% of sales**. A broader company measure that treats equipment finance leases as cash-like improved to negative $12.786 billion from negative $14.340 billion. | Second consecutive negative-FCF filing; contract becomes **challenged**, but the alternative measure and continued sales growth are counter-evidence. |
| 2023-10-26 | [Q3 2023 Form 8-K, accession 0001018724-23-000016](https://www.sec.gov/Archives/edgar/data/1018724/000101872423000016/0001018724-23-000016-index.html) | Trailing-12-month operating cash flow rose to $71.7 billion. TTM FCF turned **positive $21.4 billion** from negative $19.7 billion, while TTM cash capex declined to $50.220 billion from $59.351 billion. | First same-metric recovery, **265 days** after challenge. |
| 2024-02-02 | [2023 Form 10-K, accession 0001018724-24-000008](https://www.sec.gov/Archives/edgar/data/1018724/000101872424000008/0001018724-24-000008-index.html) | Operating cash flow was $84.946 billion and net cash capex was $48.133 billion, producing full-year FCF of **positive $36.813 billion**. | Annual recovery confirmation, **364 days** after challenge. |

#### Contract replay

**Named observable:** company-defined annual FCF below zero, where FCF equals operating cash flow less purchases of property and equipment net of proceeds and incentives. It appeared in the February 4, 2022 filing and repeated on February 3, 2023, so the strict contract changes to **challenged on February 3, 2023**.

**Per-share bridge refused:** Amazon completed a 20-for-1 stock split in 2022. Although later filings restated historical share data, the field-book denominator guard refuses an FCF-per-share bridge when a corporate action changes the apparent share count by far more than 20%. No unverified continuity assumption is smuggled into this case.

At the challenge date, survival evidence was already present: sales remained positive, the cash-capex ratio had stopped rising, the equipment-finance-adjusted FCF measure improved, and there was no liquidity or legal-terminal filing. The same FCF metric turned positive on **October 26, 2023**, 265 days later, and the full-year filing confirmed it after **364 days**.

**One-filing versus two-filing counterfactual:** a one-print rule would have challenged a year earlier, but it would have treated one exceptional fulfillment-and-AWS capacity build as proof of allocator failure. The second annual negative print made scrutiny warranted. The disciplined response was still “challenged,” not “broken,” because the filing record showed identifiable capacity investment and ample financial survival capacity.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE — first recovery after 265 days; annual confirmation after 364 days.** The two-print FCF sensor did its job by demanding proof. The error would have been converting that challenge into a terminal judgment despite improving counter-sensors.

### OO-FA-2 — FedEx (2022–24): founder succession met a two-quarter margin shock, then recovered

#### Setup

FedEx paired a founder succession with a global freight and parcel slowdown. That combination is exactly where an owner-operator contract can overreact: a new CEO inherits a weakening demand backdrop, and ordinary cyclicality can be mistaken for failed stewardship. The contemporaneous governance facts also mattered—Raj Subramaniam was a long-tenured internal successor, while founder Fred Smith remained full-time executive chairman.

**Size band (filed): large-cap** — the nearest 10-K reported non-affiliate public float of approximately **$56.4 billion** at November 30, 2021 ([FY2022 Form 10-K, filed July 18, 2022, accession 0000950170-22-012762](https://www.sec.gov/Archives/edgar/data/1048911/000095017022012762/0000950170-22-012762-index.html)).

#### Dated evidence timeline

| Filing/public date | Primary source | What a contemporaneous reader could see | Contract observable |
|---|---|---|---|
| 2022-03-28 | [Form 8-K, Item 5.02, accession 0001193125-22-086689](https://www.sec.gov/Archives/edgar/data/1048911/000119312522086689/0001193125-22-086689-index.html) | Fred Smith would step down as CEO on May 31 but remain full-time executive chairman. Raj Subramaniam, an employee since 1991 and then president/COO, would become CEO. | Governance warning logged; an orderly internal succession is not itself a fracture or terminal event. |
| 2022-09-22 | [Q1 FY2023 Form 10-Q, accession 0000950170-22-018769](https://www.sec.gov/Archives/edgar/data/1048911/000095017022018769/0000950170-22-018769-index.html) | Revenue was $23.242 billion versus $22.003 billion, up 5.6%, but operating income fell to $1.191 billion from $1.398 billion. Derived operating margin was **5.12% versus 6.35%, down 123 bp**. | First post-transition filing with year-over-year operating-margin compression. |
| 2022-12-20 | [Q2 FY2023 Form 10-Q, accession 0000950170-22-026825](https://www.sec.gov/Archives/edgar/data/1048911/000095017022026825/0000950170-22-026825-index.html) | Revenue fell 2.8% to $22.814 billion and operating income fell to $1.176 billion from $1.597 billion. Derived margin was **5.15% versus 6.80%, down 165 bp**. Yet six-month operating cash flow was $3.125 billion, the company had repurchased $1.5 billion of shares, and diluted shares fell to 259 million from 270 million. | Second consecutive margin-compression filing; contract becomes **challenged**. Cash flow and per-share execution remain counter-evidence. |
| 2023-09-20 | [Q1 FY2024 Form 10-Q, accession 0000950170-23-048994](https://www.sec.gov/Archives/edgar/data/1048911/000095017023048994/0000950170-23-048994-index.html) | Revenue was $21.681 billion and operating income was $1.485 billion. Derived margin was **6.85% versus 5.12%, up 173 bp**. | First same-metric recovery, **274 days** after challenge. |
| 2023-12-19 | [Q2 FY2024 Form 10-Q, accession 0000950170-23-071495](https://www.sec.gov/Archives/edgar/data/1048911/000095017023071495/0000950170-23-071495-index.html) | Revenue was $22.165 billion and operating income was $1.276 billion. Derived margin was **5.76% versus 5.15%, up 61 bp**. | Second consecutive recovery filing; de-escalation confirmed **364 days** after challenge. |
| 2024-06-25 | [Q4/FY2024 Form 8-K, accession 0000950170-24-077290](https://www.sec.gov/Archives/edgar/data/1048911/000095017024077290/0000950170-24-077290-index.html) | FY2024 GAAP operating margin was **6.3% versus 5.4%** even though revenue fell to $87.7 billion from $90.2 billion. Capital expenditures fell to $5.176 billion from $6.174 billion. | Full-year confirmation that the margin recovery survived softer revenue. |

#### Contract replay

**Named observable:** year-over-year change in consolidated GAAP operating margin after the CEO transition. It fell by 123 bp and then 165 bp in consecutive quarterly filings. The no-look-ahead contract therefore changes to **challenged on December 20, 2022**. Item 5.02 made succession a context flag; it did not independently falsify the thesis.

The first recovery on the same observable was filed **September 20, 2023**, 274 days later. A second consecutive margin expansion arrived **December 19, 2023**, exactly **364 days** after challenge, and FY2024 later confirmed the restoration. At the trigger date, an investor could already distinguish this case from a terminal allocation failure: the successor was internal and deeply tenured, the founder remained executive chair, operating cash flow was positive, and buybacks had reduced the diluted share count.

**One-filing versus two-filing counterfactual:** a one-print rule would have challenged on September 22, one reporting interval earlier, immediately after the CEO handoff and during an abrupt demand shock. Waiting for December established persistence while preserving nine months of lead to the first recovery. The two-print rule was appropriately conservative; the false alarm would have been treating a valid cyclical challenge as a broken owner-operator contract.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE — first recovery after 274 days; two-print confirmation after 364 days.** The filed margin damage was real, but cash generation, share-count reduction, succession continuity, and later same-metric recovery supported survival rather than forced abandonment.

## Turnaround / distressed rerating

### TR-TB-1 — Hertz Global Holdings (2019–2020 true break)

#### Setup

Hertz was a leveraged turnaround: holders were underwriting better fleet utilization, pricing, vehicle residuals, and cash generation after a long operating reset. The shares had roughly doubled from their 2017 trough into 2019 (setup-only tape context), while the company entered the break window as a **small-cap** by its nearest filed public-float observation: $897 million at June 28, 2019 ([2019 10-K, filed 2020-02-25](https://www.sec.gov/Archives/edgar/data/1657853/000165785320000007/hghthc201910-k.htm)). The operating thesis had looked unusually credible immediately before the shock: Hertz later described ten consecutive quarters of year-over-year revenue growth and nine of Adjusted Corporate EBITDA improvement. COVID-19 was the one primarily macro-driven case in this archetype; the case asks whether quarterly fundamentals could have warned before the legally terminal filing.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2019-11-05 | [10-Q, Acc. 0001657853-19-000146](https://www.sec.gov/Archives/edgar/data/1657853/000165785319000146/hghthcq32019form10-q.htm) | Q3 revenue was $2.836 billion versus $2.758 billion, **+2.8% YoY**. Nine-month CFO was $2.233 billion versus $2.017 billion, **+10.7%**. | `self_funding_transition`: improving; no deterioration registered. |
| 2020-02-25 | [10-K, Acc. 0001657853-20-000007](https://www.sec.gov/Archives/edgar/data/1657853/000165785320000007/hghthc201910-k.htm) | FY2019 revenue was $9.779 billion versus $9.504 billion, **+2.9%**; CFO was $2.900 billion versus $2.556 billion, **+13.5%**. Cash did fall to $865 million from $1.127 billion, but the same-period operating-flow observable was still improving. | `self_funding_transition`: no two-period stall; `cash_liquidity`: one adverse balance observation only. |
| 2020-03-26 | [8-K, Items 7.01/9.01, Acc. 0001657853-20-000030](https://www.sec.gov/Archives/edgar/data/1657853/000165785320000030/a8-kcovidx19.htm), [filed release](https://www.sec.gov/Archives/edgar/data/1657853/000165785320000030/covid-19pressreleasev4.htm) | Hertz said January–February global revenue had risen 6%, but March brought rapidly declining airline travel, cancellations, forward bookings, and employee furloughs. It disclosed about $1.0 billion of liquidity and warned that available liquidity depended on the duration and magnitude of the slowdown and used-car values. | Event-driven `liquidity_shock`: first warning and review evidence only; not the same periodic observable, not double confirmation, and not terminal. |
| 2020-05-11 | [10-Q, Acc. 0001657853-20-000049](https://www.sec.gov/Archives/edgar/data/1657853/000165785320000049/hghthcq12020form10-q.htm) | Q1 revenue was $1.923 billion versus $2.107 billion, **-8.7% YoY**; CFO was $449 million versus $514 million, **-12.6%**. The filing disclosed missed vehicle-lease payments, waivers, about $1.0 billion of unrestricted cash, and management's conclusion that substantial doubt existed about continuing as a going concern. | `self_funding_transition` and `solvency_deterioration`: first adverse periodic hit; strong review evidence, but the two-period contract has not yet earned `challenged`. |
| 2020-05-22 | [Company public release (later filed as Exhibit 99.1)](https://www.sec.gov/Archives/edgar/data/1657853/000110465920065674/tm2020858d1_ex99-1.htm) | Hertz publicly announced that it and certain U.S./Canadian subsidiaries had filed voluntary Chapter 11 petitions. This is the earliest cited public date on which the common-equity turnaround was clearly wrong. | Public terminal information: retrospective wrong date, but not yet the contract's legally enumerated **filed Item 1.03** hard stop. |
| 2020-05-26 | [8-K, Items 1.03/2.04 (plus 1.01/5.02/7.01/9.01), Acc. 0001104659-20-065674](https://www.sec.gov/Archives/edgar/data/1657853/000110465920065674/tm2020858d1_8k.htm) | Hertz filed that it and named U.S./Canadian subsidiaries had commenced Chapter 11 cases; the filing also routed resulting acceleration/defaults under Item 2.04. The public date here is the **8-K filing date**, not the earlier petition date. | `8-K Item 1.03`: the first legally valid automatic `broken` event. |

#### Contract replay

The same named periodic observable—`self_funding/solvency deterioration`—had only one adverse filed quarter (2020-05-11) before the company's 2020-05-22 Chapter 11 announcement. A strict two-consecutive-period rule therefore had **no challenged date before the clearly wrong 2020-05-22 public-release date: 0 days of lead**. A one-filing rule would have challenged on 2020-05-11, 11 days earlier, and was modestly more useful in this singular case; machine status still could not become automatic `broken` until the filed Item 1.03 on 2020-05-26, four days after the market already had the company announcement.

#### Honest verdict

**VISIBLE_ONLY_COINCIDENT — 0 days under the required two-filing rule.** The 2020-05-11 going-concern/default disclosure was genuine one-filing evidence 11 days before the 2020-05-22 company announcement, but the required replay had no pre-break double confirmation. The legally decisive Item 1.03 then followed on 2020-05-26, so the hard-stop bus necessarily lagged the public wrong date by four days.

### TR-TB-2 — Party City Holdco (2021–2023 true break)

#### Setup

Party City was a post-pandemic distressed rerating built on store normalization, better vertical sourcing, and conversion of a heavily leveraged retailer back to durable positive cash generation. The shares had risen roughly thirtyfold from the 2020 panic low into 2021 (setup-only tape context), and the nearest 10-K placed the company in the **small-cap** band with $1.037 billion of public float at June 30, 2021 ([2021 10-K, filed 2022-02-28](https://www.sec.gov/Archives/edgar/data/1592058/000095017022002280/prty-20211231.htm)). The thesis did not fail merely because freight and helium costs rose; it failed when repeated gross-margin loss, inventory accumulation, and renewed cash burn met a thin liquidity cushion. Unlike Hertz, this was not classified as primarily macro-driven: the filed evidence showed company-specific leverage, inventory, and liquidity transmission.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2022-05-09 | [10-Q, Acc. 0000950170-22-008474](https://www.sec.gov/Archives/edgar/data/1592058/000095017022008474/prty-20220331.htm) | Q1 revenue rose **1.4%** ($432.976 million / $426.807 million - 1), but gross margin fell to **31.87% from 35.68%, -3.81 pp YoY**. Inventory rose **20.8% YoY** to $517.459 million. CFO less capex was **-$135.445 million** (-$116.825 million - $18.620 million), versus **-$70.995 million** a year earlier. | `gross-margin compression YoY`: first hit; `inventory build` and `cash burn`: corroborating first-period stress. |
| 2022-08-08 | [10-Q, Acc. 0000950170-22-015233](https://www.sec.gov/Archives/edgar/data/1592058/000095017022015233/prty-20220630.htm) | Q2 revenue fell **1.5% YoY**; gross margin fell to **33.74% from 40.54%, -6.79 pp**. Inventory rose **58.8% YoY** to $676.731 million. Six-month CFO less capex was **-$150.227 million** versus **-$26.675 million**. | Second consecutive `gross-margin deterioration`; repeated `inventory build` and `cash burn`. Contract becomes `challenged`. |
| 2022-11-08 | [10-Q, Acc. 0000950170-22-023330](https://www.sec.gov/Archives/edgar/data/1592058/000095017022023330/prty-20220930.htm) | Q3 revenue fell **1.6% YoY** and gross margin fell to **31.55% from 36.01%, -4.45 pp**. Inventory was $745.697 million, **+43.4% YoY**. Nine-month CFO less capex was **-$362.386 million** versus **-$122.762 million**; quarter-end liquidity was disclosed as only $121.5 million. | Third margin hit; worsening `inventory build`, `cash burn`, and `solvency/liquidity`. Challenge strengthens, but still cannot auto-break. |
| 2023-01-17 | [Company public release (later filed as Exhibit 99.2)](https://www.sec.gov/Archives/edgar/data/1592058/000119312523009847/d643228dex992.htm) | Party City publicly announced that it and certain domestic subsidiaries had filed voluntary Chapter 11 petitions. This is the earliest cited public date on which the common-equity turnaround was clearly wrong. | Public terminal information: retrospective wrong date; still not the machine's filed Item 1.03 hard stop. |
| 2023-01-18 | [8-K, Items 1.03/2.04 (plus 1.01/5.02/7.01/8.01/9.01), Acc. 0001193125-23-009847](https://www.sec.gov/Archives/edgar/data/1592058/000119312523009847/d643228d8k.htm) | Party City filed that it and subsidiaries had commenced Chapter 11 cases and that the filings accelerated obligations under enumerated debt instruments. The timeline uses the **8-K filing date**, not the earlier petition date. | `8-K Item 1.03`: legally valid automatic `broken`. |

#### Contract replay

The frozen observable is **YoY gross-margin compression**, whether revenue is rising or falling. Its second consecutive filing was the 2022-08-08 10-Q; inventory and cash burn independently repeated in the same two periods. The contract would have become `challenged` on **2022-08-08**, **162 days before** the clearly wrong 2023-01-17 company announcement (roughly two filed-quarter cadences). A one-filing rule would have warned on 2022-05-09, 253 days before that announcement, but that filing still said liquidity sources were expected to cover at least 12 months and identified freight/helium pressures; waiting for Q2 removed much of the normal seasonal/supply-chain noise. Automatic `broken` remained correctly reserved for the 2023-01-18 Item 1.03, one day after the public wrong date.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD (162 days)**. Repeated margin, inventory, and cash-flow deterioration made the operating turnaround reviewable well before the terminal company announcement. Only the 2023-01-18 Item 1.03 filing was permitted to change `challenged` to automatic `broken`.

### TR-FA-1 — Carvana (2022–2024 false alarm)

#### Setup

Carvana was a scale-and-unit-economics turnaround after a capital-intensive expansion: holders expected inventory discipline, higher gross profit per unit, and a transition from cash burn to self-funding. The shares had risen more than twentyfold from the 2017 IPO to the 2021 peak before the 2022 distress window (setup-only tape context), and the nearest 10-K showed **large-cap** public float of $24.6 billion at June 30, 2021 ([2021 10-K, filed 2022-02-24](https://www.sec.gov/Archives/edgar/data/1690820/000169082022000080/cvna-20211231.htm)). Two filings then produced a raw margin-collapse pattern as severe as many true breaks, but ADESA closed between them, enlarged debt, and made the comparison inadmissible. The eventual recovery tests whether honoring that refusal, while printing liquidity and working-capital counterevidence, prevents a false terminal conclusion.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2022-05-10 | [10-Q, Acc. 0001690820-22-000166](https://www.sec.gov/Archives/edgar/data/1690820/000169082022000166/cvna-20220331.htm) | Q1 revenue grew **55.8%**, but gross margin fell to **8.52% from 15.06%, -6.53 pp YoY**; gross profit itself fell 11.8%. CFO less capex was **-$813 million** (-$593 million - $220 million), versus -$614 million. | Raw first margin/cash-burn hit. Carvana had agreed to acquire ADESA, but the transaction had not yet closed. |
| 2022-08-04 | [10-Q, Acc. 0001690820-22-000253](https://www.sec.gov/Archives/edgar/data/1690820/000169082022000253/cvna-20220630.htm) | Q2 revenue grew **16.4%**, but gross margin fell to **10.20% from 16.55%, -6.35 pp** and gross profit fell 28.3%. ADESA closed on May 9 and was included from that date. Inventory had declined to $2.865 billion from $3.149 billion at year-end, cash was $1.047 billion, and six-month CFO improved to -$487 million from -$1.139 billion. | `major acquisition/scope change`: the apparent second hit is **`unverifiable`**, so no challenge clock starts. Inventory and cash burn are favorable counterobservables. |
| 2023-05-04 | [10-Q, Acc. 0001690820-23-000163](https://www.sec.gov/Archives/edgar/data/1690820/000169082023000163/cvna-20230331.htm) | Q1 revenue fell 25.5%, but gross margin rebounded to **13.09% from 8.52%, +4.56 pp YoY** and gross profit rose 14.4%. Inventory fell to $1.485 billion; CFO less capex improved to **-$98 million** from -$813 million. | Raw reversal, still crossing unequal ADESA inclusion and therefore `unverifiable` for a symmetric recovery clock; working capital and self-funding improve. |
| 2023-07-19 | [10-Q, Acc. 0001690820-23-000219](https://www.sec.gov/Archives/edgar/data/1690820/000169082023000219/cvna-20230630.htm) | Q2 revenue fell 23.6%, but gross margin rose to **16.81% from 10.20%, +6.62 pp YoY** and gross profit rose 26.0%. Six-month CFO less capex was **+$393 million** ($443 million - $50 million), versus -$848 million, and inventory fell to $1.302 billion. | A second raw reversal with stronger self-funding, but the unequal acquisition window still blocks a clean margin-recovery clock. |
| 2024-02-22 | [10-K, Acc. 0001690820-24-000093](https://www.sec.gov/Archives/edgar/data/1690820/000169082024000093/cvna-20231231.htm) | FY2023 standalone CFO less capex was **positive $716 million**, and inventory ended at $1.150 billion, below the fully post-close $1.302 billion balance at June 30, 2023. The filing also showed raw gross profit up 38.4% on 20.8% lower revenue, but that YoY comparison crosses unequal ADESA inclusion. | First full-year post-ADESA operating evidence: standalone self-funding and further post-close inventory reduction support recovery, but no like-basis duration is claimed. |

#### Contract replay

The raw Q1 and Q2 margin declines cannot form a two-filing trigger: ADESA closed between them and was included in Q2 from May 9. The 2023 YoY reversals cross the same unequal inclusion windows, so they also cannot support a symmetric duration. The contract output is **`unverifiable`**, with **no valid challenge-to-recovery clock**. The February 22, 2024 10-K is the first full-year post-ADESA operating observation; standalone positive self-funding and a further inventory decline from a fully post-close balance support recovery, but they do not create a like-basis duration. A one-filing rule on the pre-close Q1 would have been faster but would have acted before the known acquisition changed scope; that is exactly the noise the refusal guard exists to stop.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE**. The balance sheet left little room for error, but the supposed two-print margin challenge was not admissible across ADESA. There was no Item 1.03 terminal filing and no Item 2.04 solvency-review event; inventory was already contracting and self-funding improved in the acquisition-affected filing. At the time, refusal plus those counters distinguished Carvana from Party City's simultaneous inventory accumulation and worsening burn; they did not make survival certain.

### TR-FA-2 — Teva Pharmaceutical Industries (2018–2024 false alarm)

#### Setup

Teva was a classic deleveraging turnaround after the Actavis Generics acquisition, U.S. generic-price erosion, and a management reset: holders expected cost reduction, debt repayment, and eventual revenue/gross-margin stabilization. The shares had more than doubled from their 2017 low into the 2018 rebound before giving much of that move back (setup-only tape context); the nearest 10-K put Teva in the **large-cap** band with $20.7 billion of public float at June 30, 2018 ([2018 10-K, filed 2019-02-19](https://www.sec.gov/Archives/edgar/data/818686/000119312519043564/d613675d10k.htm)). The false-alarm pattern was not cosmetic: two quarters showed severe revenue and gross-margin deterioration, and self-funding later weakened. What kept this from a deterministic break was the archetype's primary observable—deleveraging—continuing in the same filings, with no Item 2.04 solvency-review event and no Item 1.03 terminal event.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2018-08-02 | [10-Q, Acc. 0001193125-18-236536](https://www.sec.gov/Archives/edgar/data/818686/000119312518236536/d581454d10q.htm) | Q2 revenue fell **17.8%** ($4.701 billion / $5.720 billion - 1) and gross margin fell to **43.84% from 49.91%, -6.07 pp YoY**. At the same time, six-month long-term-debt repayments of $6.289 billion exceeded $4.435 billion of proceeds by **$1.854 billion**. | `gross-margin change YoY`: first hit. `net debt trajectory`: improving counterobservable, so review only. |
| 2018-11-01 | [10-Q, Acc. 0001193125-18-315734](https://www.sec.gov/Archives/edgar/data/818686/000119312518315734/d599127d10q.htm) | Q3 revenue fell **19.4%** and gross margin fell to **44.62% from 47.18%, -2.55 pp**. Nine-month debt repayments of $6.989 billion exceeded proceeds of $4.434 billion by **$2.555 billion**; nine-month CFO less capex improved to $1.641 billion from $759 million. | Second consecutive margin hit: `challenged`; debt/cash-generation evidence still argues against `broken`. |
| 2019-02-19 | [10-K, Acc. 0001193125-19-043564](https://www.sec.gov/Archives/edgar/data/818686/000119312519043564/d613675d10k.htm) | As filed, FY2018 revenue fell 15.8% and gross margin fell to **44.00% from 47.42%, -3.42 pp**. CFO less capex was $1.795 billion versus $1.351 billion, and debt repayments exceeded proceeds by **$3.012 billion**. | Operating challenge persists; `self_funding` and `net debt` still improve. |
| 2020-02-21 | [10-K, Acc. 0001193125-20-044221](https://www.sec.gov/Archives/edgar/data/818686/000119312520044221/d852939d10k.htm) | FY2019 revenue fell 7.6% on the filing's comparable basis; CFO less capex dropped to **$223 million** from $1.795 billion. Teva nevertheless repaid $3.944 billion of long-term debt against $2.083 billion of proceeds, a **$1.861 billion net repayment**. | `self_funding stall`: adverse; `net debt trajectory`: still favorable. Status remains `challenged`, not automatically broken. |
| 2024-02-12 | [10-K, Acc. 0001193125-24-031005](https://www.sec.gov/Archives/edgar/data/818686/000119312524031005/d600678d10k.htm) | FY2023 revenue rose **6.2%**, gross profit rose 9.6%, and gross margin expanded to **48.25% from 46.72%, +1.53 pp**. Cash rose $425 million to $3.226 billion; long-term-debt repayments of $4.152 billion exceeded $2.451 billion of proceeds by **$1.701 billion**. | Defined recovery: revenue/margin stabilization while deleveraging continues. |

#### Contract replay

Two consecutive filings of the same `gross-margin deterioration` observable would have set `challenged` on **2018-11-01**. Recovery is conservatively defined here as the first annual filing showing revenue growth, gross-margin expansion, and continuing net debt repayment together: **2024-02-12**, **1,929 days (about 21 quarters) after** the challenge. A one-filing rule would have challenged 91 days earlier on 2018-08-02 but would have been noisier because that very filing showed $1.854 billion of net long-term-debt repayment; the two-period rule correctly demanded review, while the archetype-specific solvency leg prevented an unjustified `broken` state.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE**. This was not an easy or quickly resolved false alarm: operating evidence remained challenged for years, and the early debt-paydown counterobservable did not guarantee success. It did, however, distinguish Teva from a terminal solvency break at the time; the filed debt trajectory persisted until revenue and margins recovered, and no legal hard stop appeared.

## Contracted / platform growth

### CP-TB-1 — Fastly (2020–2022 true break)

#### Setup

Fastly was a usage-led edge-cloud platform thesis: holders expected large customers to deepen usage, the forward contract book to replenish, and network scale to preserve gross margin while revenue compounded. From its 2019 IPO to the 2020 peak the shares rose roughly eightfold (setup-only tape context), and the nearest pre-break 10-K placed Fastly in the **mid-cap** band with $6.7 billion of public float at June 30, 2020 ([2020 10-K, filed 2021-03-01](https://www.sec.gov/Archives/edgar/data/1517413/000151741321000030/fsly-20201231.htm)). A largest-customer warning arrived first, but the admissible leading evidence was two consecutive sequential RPO declines. Signal Sciences closed in October 2020, so acquisition scope contaminates the YoY margin waterfall; the replay uses adjacent post-close RPO observations and prints raw margin components as context rather than a load-bearing second leg.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2020-10-14 | [8-K, Items 2.02/8.01/9.01, Acc. 0001517413-20-000227](https://www.sec.gov/Archives/edgar/data/1517413/000151741320000227/fsly-20201012.htm), [filed release](https://www.sec.gov/Archives/edgar/data/1517413/000151741320000227/fastly-8xkpressrelease.htm) | Fastly cut preliminary Q3 revenue to $70–71 million from $73.5–75.5 million and said prior guidance should not be relied on. It named lower-than-expected usage by its previously disclosed largest customer and several other customers. | Customer-specific `usage/conversion`: event warning; one observation, no automatic break. |
| 2021-05-07 | [10-Q, Acc. 0001517413-21-000069](https://www.sec.gov/Archives/edgar/data/1517413/000151741321000069/fsly-20210331.htm) | RPO fell to $140.1 million from $155.3 million at 2020 year-end, **-9.8% sequentially**. Q1 revenue grew 34.8%, but raw gross margin fell to **55.81% from 56.67%, -0.86 pp YoY**. Receivables grew 21.7% YoY versus revenue growth of 34.8%, a **-13.1 pp spread**, so collection did not confirm the warning. | First clean post-close `RPO replenishment decline`. The YoY margin comparison crosses unequal Signal Sciences scope and is context only. |
| 2021-08-06 | [10-Q, Acc. 0001517413-21-000154](https://www.sec.gov/Archives/edgar/data/1517413/000151741321000154/fsly-20210630.htm) | RPO fell again to $134.7 million, **-3.9% sequentially**. Q2 revenue grew 13.9%, while raw gross margin fell to **52.58% from 60.23%, -7.65 pp** and gross profit fell 0.6%. Receivables fell 3.9% YoY versus 13.9% revenue growth, a -17.8 pp spread. | Second clean post-close `RPO replenishment decline`: contract becomes `challenged`. Margin remains acquisition-contaminated context; collection still does not deteriorate. |
| 2022-03-01 | [10-K, Acc. 0001517413-22-000038](https://www.sec.gov/Archives/edgar/data/1517413/000151741322000038/fsly-20211231.htm) | FY2021 revenue growth had slowed to 21.8% from 45.1%; gross margin fell to **52.87% from 58.74%, -5.87 pp**. CFO burn widened to $38.482 million from $19.916 million, and year-end RPO of $152.3 million remained below the $155.3 million reported a year earlier. | Defined clearly-wrong point for the original high-growth/scale-economics thesis; persistent margin and self-funding deterioration confirm the prior challenge. |

#### Contract replay

Fastly's second consecutive clean post-close filing of `RPO replenishment decline` was 2021-08-06, so that single frozen observable sets `challenged` on **2021-08-06**. The YoY margin comparisons cross unequal Signal Sciences scope and do not vote. The clearly wrong date is defined as **2022-03-01**, when the full-year filing confirmed materially slower growth, a raw 5.87 pp gross-margin decline, greater CFO burn, and an unreplenished year-end RPO book: **207 days of lead** (about two quarterly cadences). A one-filing RPO rule would have challenged 91 days earlier on 2021-05-07, but one sequential book decline with healthy receivables would have been faster and materially noisier.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD (207 days)**. Two clean post-close RPO declines exposed the break before the annual confirmation; acquisition-contaminated margin did not carry the verdict. No Item 1.02 named-contract termination occurred, so deterministic status properly remained `challenged`; “clearly wrong” is the historical case verdict, not an unauthorized automatic `broken` state.

### CP-TB-2 — Twilio (2021–2023 true break)

#### Setup

Twilio was the archetypal communications-platform long: developers would add workloads, usage revenue would compound, Segment would broaden the customer-data layer, and scale would ultimately convert growth into cash. The stock had risen more than twentyfold from its 2016 IPO to the 2021 peak (setup-only tape context), and the nearest 10-K put it firmly in the **large-cap** band with $51.0 billion of public float at June 30, 2021 ([2021 10-K, filed 2022-02-22](https://www.sec.gov/Archives/edgar/data/1447669/000144766922000049/twlo-20211231.htm)). Raw gross-margin compression appeared early, but Segment made those YoY comparisons non-comparable; the clean forward-book clock only completed as cash flow and growth worsened. Twilio expressly excludes usage-based contracts and contracts of one year or less from disclosed RPO, so RPO is a partial within-name clock, not a complete demand measure or a cross-company denominator.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2021-10-28 | [10-Q, Acc. 0001447669-21-000266](https://www.sec.gov/Archives/edgar/data/1447669/000144766921000266/twlo-20210930.htm) | Q3 revenue grew **65.2%**, but raw gross margin fell to **49.26% from 51.54%, -2.28 pp YoY**. Receivables grew 69.6% YoY versus revenue growth of 65.2%, only a **+4.4 pp spread**; nine-month CFO was -$19.949 million versus +$17.753 million. | `major acquisition/scope change`: the YoY margin/CFO comparisons cross unequal Segment ownership and are `unverifiable`; collection spread is mild. |
| 2022-02-22 | [10-K, Acc. 0001447669-22-000049](https://www.sec.gov/Archives/edgar/data/1447669/000144766922000049/twlo-20211231.htm) | Derived from filed annual and nine-month components, Q4 revenue was **$842.744 million** ($2,841.839 million - $1,999.095 million), +53.8% YoY; raw Q4 gross profit was **$396.547 million**, giving **47.05% margin versus 51.47%, -4.42 pp**. Annual CFO reversed to -$58.192 million from +$32.654 million. RPO was $154.2 million. | A second raw margin decline, still `unverifiable` across unequal Segment scope; no valid challenge clock starts. |
| 2022-08-05 | [10-Q, Acc. 0001447669-22-000147](https://www.sec.gov/Archives/edgar/data/1447669/000144766922000147/twlo-20220630.htm) | Q2 revenue grew 41.0%, but gross margin fell another **2.32 pp YoY**. RPO fell to $140.8 million from $154.2 million at year-end, **-8.7%**; six-month CFO was -$80.141 million versus +$26.222 million. | First `RPO replenishment decline`; continued margin and self-funding stress. |
| 2022-11-04 | [10-Q, Acc. 0001447669-22-000195](https://www.sec.gov/Archives/edgar/data/1447669/000144766922000195/twlo-20220930.htm) | Q3 revenue growth slowed to 32.8% and gross margin fell **2.26 pp YoY**. RPO fell again to $122.1 million, **-13.3% sequentially and -20.8% from year-end**; nine-month CFO burn widened to $195.913 million from $19.949 million. | Second consecutive RPO decline plus continuing margin/cash deterioration: defined clearly-wrong point for the original platform-growth/operating-leverage thesis. |
| 2023-02-27 | [10-K, Acc. 0001447669-23-000049](https://www.sec.gov/Archives/edgar/data/1447669/000144766923000049/twlo-20221231.htm) | FY2022 revenue growth was 34.6% versus 61.3%; gross margin fell to **47.40% from 48.94%, -1.54 pp**, and CFO burn widened to $254.368 million. RPO recovered to $154.5 million, showing why the partial RPO clock alone was insufficient. | Post-wrong confirmation: business economics remain challenged even though one forward-book snapshot recovers. |

#### Contract replay

The pre-RPO margin sequence is refused because its YoY periods contain unequal Segment ownership. The first clean RPO decline appears on 2022-08-05 and the second on **2022-11-04**, which is also the defined clearly wrong date: the first filing where two consecutive forward-book declines coexisted with sharply worse CFO and materially slower growth. The strict replay therefore has **0 days of lead**. A one-filing RPO rule would have challenged 91 days earlier, but one decline in a partial RPO measure would have been materially noisier; no named agreement termination authorized automatic `broken`.

#### Honest verdict

**VISIBLE_ONLY_COINCIDENT — 0 days.** The acquisition-clean partial-RPO clock completed only when cash flow and growth made the original operating-leverage thesis clearly wrong. The 2023 RPO rebound is an important limitation: the field book should never pretend Twilio's disclosed RPO covers its usage base or could have carried the verdict alone.

### CP-FA-1 — Autodesk (2016–2018 subscription-transition false alarm)

#### Setup

Autodesk deliberately replaced high-upfront perpetual licenses with ratably recognized subscriptions, creating exactly the revenue-conversion and margin pattern a naive platform falsifier would call a break. Holders owned a larger, more predictable recurring-revenue base and accepted a temporary reported-revenue valley; the shares had roughly doubled over the preceding three years (setup-only tape context). The nearest 10-K placed Autodesk in the **large-cap** band with approximately $11.4 billion of public float at July 31, 2015 ([FY2016 10-K, filed 2016-03-23](https://www.sec.gov/Archives/edgar/data/769397/000076939716000067/adsk-0131201610xk.htm)). The case is a clean warning against treating revenue conversion as demand replenishment: subscriptions and ARR rose throughout the apparent deterioration.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2016-06-06 | [10-Q, Acc. 0000769397-16-000079](https://www.sec.gov/Archives/edgar/data/769397/000076939716000079/adsk-4302016x10q.htm) | Q1 revenue fell **20.8% YoY** and gross margin fell to **81.93% from 85.80%, -3.87 pp**. Yet total subscriptions rose 5% sequentially to 2.710 million, total ARR rose 4% to $1.436 billion, total deferred revenue was essentially flat-to-up at $1.524 billion versus $1.519 billion at year-end, and CFO rose to $164.4 million from $86.5 million. | First `revenue conversion decline`; every replenishment/self-funding counterobservable remains favorable. |
| 2016-08-30 | [10-Q, Acc. 0000769397-16-000087](https://www.sec.gov/Archives/edgar/data/769397/000076939716000087/adsk-7312016x10q.htm) | Q2 revenue fell **9.6% YoY** and gross margin slipped **0.19 pp**. Total subscriptions rose to 2.820 million (**+9% from fiscal year-end**) and ARR to $1.469 billion (**+7%**); total deferred revenue was $1.520 billion versus $1.519 billion at year-end. | Second consecutive conversion decline: a one-axis rule becomes `challenged`; contracted-demand replenishment remains favorable. |
| 2018-06-08 | [10-Q, Acc. 0000769397-18-000024](https://www.sec.gov/Archives/edgar/data/769397/000076939718000024/adsk-4302018x10q.htm) | Autodesk adopted ASC 606 using the modified-retrospective method, so a raw cross-standard waterfall must refuse. Its disclosed **ASC 605 like-basis** Q1 revenue was $573.5 million versus $485.7 million, **+18.1%**, while total ARR rose 4% from year-end to $2.126 billion. | First like-basis reversal of `revenue conversion decline`; `accounting-standard change` guard active. |
| 2018-08-30 | [10-Q, Acc. 0000769397-18-000042](https://www.sec.gov/Archives/edgar/data/769397/000076939718000042/adsk-7312018x10q.htm) | The filing's ASC 605 like-basis Q2 revenue was $610.5 million versus $501.8 million, **+21.7%**. Recurring revenue grew 28% YoY; ASC 606 ARR was $2.347 billion, **+14% from fiscal year-end**, and total subscriptions were 3.936 million, +6%. | Second like-basis reversal: defined recovery; forward-demand measures remained favorable throughout. |

#### Contract replay

A mechanical two-period rule on the same `reported revenue conversion decline` would set `challenged` on **2016-08-30**. Recovery is defined as the second consecutive filed quarter with positive like-basis revenue conversion and continuing ARR growth: **2018-08-30**, **730 days after** the challenge (eight quarterly cadences). A one-filing rule would have warned 85 days earlier on 2016-06-06, but it would have been strictly noisier: subscriptions, ARR, deferred revenue, and CFO were already contradicting the supposed break. ASC 606 later forces refusal of a raw 2016-to-2018 deferred-revenue bridge; the filed like-basis tables, not an invented restatement, support the recovery date.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE**. The conversion observable fired, but replenishment never did. This is the canonical reason the platform contract requires forward-book or collection confirmation rather than two revenue declines alone.

### CP-FA-2 — Okta (2021–2024 Auth0-integration false alarm)

#### Setup

Okta was an identity-platform compounder whose 2021 Auth0 acquisition was meant to join workforce and customer identity under one platform. The shares had risen more than tenfold from the 2017 IPO to the 2021 peak (setup-only tape context), and the nearest 10-K showed **large-cap** public float of $36.3 billion at July 31, 2021 ([FY2022 10-K, filed 2022-03-07](https://www.sec.gov/Archives/edgar/data/1660134/000166013422000010/okta-20220131.htm)). Two filings then showed severe gross-margin compression and receivables outrunning revenue—an apparently strong two-observable break. The contemporaneous escape hatch was not hindsight: Auth0 made the YoY scope non-comparable while RPO kept growing, so the primary comparison remained `unverifiable` and never earned `challenged`.

#### Dated evidence timeline

| Filing/public-release date | Point-in-time source | What was public on that date | Pre-declared observable |
|---|---|---|---|
| 2021-05-03 | [8-K, Items 3.02/8.01/9.01, Acc. 0001193125-21-146823](https://www.sec.gov/Archives/edgar/data/1660134/000119312521146823/d133101d8k.htm) | Okta filed the Auth0 closing. The later 10-Q measured consideration at roughly $5.671 billion before additional unvested/assumed awards, including about 19.2 million Okta shares. | `major acquisition/scope change`: explicit comparison/refusal stamp; not a break event. |
| 2021-09-02 | [10-Q, Acc. 0001660134-21-000020](https://www.sec.gov/Archives/edgar/data/1660134/000166013421000020/okta-20210731.htm); [prior-year 10-Q, Acc. 0001660134-20-000019](https://www.sec.gov/Archives/edgar/data/1660134/000166013420000019/okta-731202010q.htm) | Q2 revenue grew **57.4%**, but gross margin fell to **67.95% from 74.48%, -6.53 pp**. Receivables grew **115.7% YoY** versus 57.4% revenue growth, a **+58.3 pp spread**; RPO was $2.236 billion. | First raw margin and receivables-spread hit, but both are acquisition-scope contaminated; the contract output is `unverifiable`, and `challenged` is not earned. |
| 2021-12-02 | [10-Q, Acc. 0001660134-21-000026](https://www.sec.gov/Archives/edgar/data/1660134/000166013421000026/okta-20211031.htm); [prior-year 10-Q, Acc. 0001660134-20-000026](https://www.sec.gov/Archives/edgar/data/1660134/000166013420000026/okta-20201031.htm) | Q3 revenue grew **61.3%**, but gross margin fell to **68.73% from 73.82%, -5.10 pp**. Receivables grew **81.8% YoY** versus 61.3% revenue growth, a **+20.5 pp spread**. RPO rose to $2.350 billion, **+5.1% sequentially**. | Second raw margin/spread hit, but the known Auth0 scope change still forces `unverifiable`; no valid challenge clock starts. RPO replenishment is contemporaneous counterevidence. |
| 2023-12-01 | [10-Q, Acc. 0001660134-23-000068](https://www.sec.gov/Archives/edgar/data/1660134/000166013423000068/okta-20231031.htm) | Q3 revenue grew 21.4% and gross margin rose to **75.17% from 71.31%, +3.86 pp**. Receivables grew 9.8% versus revenue growth of 21.4%, a **-11.6 pp spread**; nine-month CFO rose to $338 million from $10 million and RPO was $3.073 billion. | First clean reversal of margin/collection deterioration; self-funding and forward book confirm. |
| 2024-03-01 | [10-K, Acc. 0001660134-24-000025](https://www.sec.gov/Archives/edgar/data/1660134/000166013424000025/okta-20240131.htm) | Derived Q4 revenue was $605 million versus $510 million, +18.6%; derived Q4 gross margin was **76.03% versus 72.75%, +3.29 pp**. Year-end receivables grew 16.2%, a -2.4 pp spread to Q4 revenue growth; annual CFO rose to $512 million from $86 million and RPO reached $3.385 billion. | Second clean comparable reversal: the later evidence resolves the acquisition-era ambiguity without retroactively creating a challenge clock. |

#### Contract replay

The raw repeated deterioration was `gross-margin compression`, corroborated by `receivables growth minus revenue growth`. It cannot mechanically set `challenged`: the Auth0 closing was already filed, and both YoY comparisons crossed a major scope change. The required output on both 2021-09-02 and 2021-12-02 is therefore **`unverifiable`**, with RPO growth printed as counterevidence. A one-filing rule would also return `unverifiable`; it cannot create valid lead from the first contaminated print. The 2023-12-01 and 2024-03-01 filings provide two later clean comparable reversals, but they resolve the evidence gap rather than clear a challenge that the contract never validly opened. There is consequently **no honest challenge-to-recovery duration** for this case.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE**. The raw alarm was real enough to review—Auth0 integration damaged reported margins and distorted working capital—but the filed acquisition stamp required refusal, while continuing RPO replenishment distinguished it from Fastly's forward-book depletion at the time. Here survival comes from honoring `unverifiable`, not from pretending an 820-day challenge clock was valid.

## Clinical / milestone / pre-revenue

Runway below is deliberately mechanical: disclosed cash plus marketable securities divided by the latest filed average quarterly operating-cash use. It is not management guidance and it is not a forecast. A named, filed primary-endpoint failure is treated as a predeclared terminal exception; an FDA delay or complete-response letter is not silently promoted to `broken` under LHB-R3.

### CL-TB-1 — FibroGen (2020–21 roxadustat U.S. approval thesis; true break)

#### Setup

FibroGen was a clinical/milestone long whose peak thesis joined a potentially first-in-class oral anemia drug, large global partners, existing ex-U.S. approvals, and a near-dated U.S. approval event. The shares had roughly tripled from the 2014 IPO price at their prior highs and again traded above $50 around the 2021 review, so this was a plausible post-run institutional hold rather than an undiscovered binary. **Size band (nearest contemporaneous 10-K public float): mid-cap** — the 2020 Form 10-K reported approximately **$2.128 billion** of non-affiliate market value at June 30, 2020 ([2020 10-K, filed 2021-03-01, accession 0001564590-21-009871](https://www.sec.gov/Archives/edgar/data/921299/000156459021009871/fgen-10k_20201231.htm)). The thesis at issue is narrow: U.S. approval of roxadustat from the submitted package, not the value of FibroGen's China business or pamrevlumab pipeline.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2020-12-18** | [8-K, Item 8.01, accession 0001564590-20-057715](https://www.sec.gov/Archives/edgar/data/921299/000156459020057715/fgen-8k_20201218.htm) | FDA extended the NDA review by three months to **2021-03-20** because FibroGen was submitting additional analyses of existing clinical data, classified as a major amendment. | **Milestone-date extension / major amendment — one review observation.** It does not establish a repeated named deterioration. |
| **2021-04-06** | [8-K, Item 8.01, accession 0001564590-21-017841, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/921299/000156459021017841/fgen-ex991_6.htm) | Management disclosed that previously presented primary cardiovascular-safety analyses used post-hoc changes to stratification factors. Prespecified analyses had higher hazard-ratio point estimates; several confidence intervals that had excluded 1.0 now included it. | **Evidence-integrity warning — meaningful one-filing review evidence, but not a second print of the earlier date-extension observable.** `challenged` is not earned under the strict replay. |
| **2021-05-10** | [10-Q, accession 0001564590-21-026053](https://www.sec.gov/Archives/edgar/data/921299/000156459021026053/fgen-10q_20210331.htm) | At March 31, cash was **$433.508m**, short-term investments **$110.724m**, and long-term investments **$93.679m**; Q1 operating cash use was **$44.984m**. Mechanical runway = **($433.508m + $110.724m + $93.679m) / $44.984m = 14.2 quarters**. | **Cash runway:** still comfortably reached the pending FDA outcome; financing was not the break. |
| **2021-08-11** | [8-K, Item 8.01, accession 0001564590-21-043233](https://www.sec.gov/Archives/edgar/data/921299/000156459021043233/fgen-8k_20210811.htm) | FDA issued a CRL, would not approve the NDA in its present form, and required an additional clinical study before resubmission. | **U.S. approval milestone failed for the submitted package.** Under house law a CRL is a hard review fact but not an automatic `broken` event; the human can nevertheless conclude that this narrowly defined hold thesis is wrong. |

#### Contract replay

The 2020-12-18 date extension and the 2021-04-06 post-hoc-analysis disclosure are related to the same NDA, but they are not two prints of the same named deterioration. Combining them into a broad “regulatory package changed” bucket would manufacture confirmation after the fact. The strict contract therefore has **no pre-outcome challenged date**. Define “clearly wrong” as the 2021-08-11 CRL requiring another clinical study: the April evidence-integrity disclosure was meaningful one-filing review evidence **127 days earlier**, but the required two-file replay recognizes the break only at the outcome. A one-filing evidence-integrity rule would have supplied lead; this field book does not silently substitute that rule.

#### Honest verdict

**VISIBLE_ONLY_COINCIDENT — 0 days under the required two-file rule.** The April filing was a serious 127-day advance warning, but there was no honest same-observable double confirmation before the CRL. The CRL itself remains review evidence rather than a mechanically terminal status under LHB-R3.

### CL-TB-2 — Allakos (2021 lirentelimab EG/EoD and EoE thesis; true break)

#### Setup

Allakos was the purest pre-revenue milestone archetype in this lane: holders owned it for lirentelimab's earlier open-label/Phase 2 signal and two late-stage readouts expected to validate both histology and patient-reported symptom benefit. From its **$18** July 2018 IPO price, the shares had risen several-fold and had exceeded $100 before the pivotal readout. **Size band (nearest contemporaneous 10-K public float): mid-cap** — the 2020 Form 10-K disclosed **$2.156 billion** of non-affiliate market value at June 30, 2020 ([2020 10-K, filed 2021-03-01, accession 0001564590-21-009651](https://www.sec.gov/Archives/edgar/data/1564824/000156459021009651/allk-10k_20201231.htm)). The predeclared thesis breaker is failure of the patient-reported symptomatic co-primary endpoints in ENIGMA 2 and KRYPTOS, not a price threshold.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2021-03-01** | [8-K, Item 2.02, accession 0001564590-21-009650, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1564824/000156459021009650/allk-ex991_6.htm) | Company expected topline Phase 3 EG/EoD and Phase 2/3 EoE data in **Q4 2021**. Year-end cash, equivalents, and marketable securities were **$659.0m**. | **Milestone clock initialized:** both named readouts due Q4 2021; state is `no_break_observed`. |
| **2021-11-08** | [8-K, Item 2.02, accession 0000950170-21-003460, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1564824/000095017021003460/allk-ex99_1.htm) | Both readouts were now expected in **Q4 2021 or early Q1 2022**, a deterministic slip from the original Q4 window. At September 30, cash/securities were **$505.6m** and nine-month operating cash use was **$142.476m**. Mechanical runway = **$505.6m / ($142.476m / 3) = 10.6 quarters**, versus a readout no more than roughly one quarter away. | **Named milestone-date change — first nonterminal deterioration.** Runway still reached the event by a very wide margin. |
| **2021-12-22** | [8-K, Item 8.01, accession 0000950170-21-005310](https://www.sec.gov/Archives/edgar/data/1564824/000095017021005310/allk-20211221.htm) | ENIGMA 2 and KRYPTOS met histologic co-primary endpoints but **did not achieve statistical significance on the patient-reported symptomatic co-primary endpoints**. | **Predeclared filed primary-endpoint failure — terminal exception.** `broken` is legal on this filing date; runway and dilution do not rescue endpoint efficacy. |

#### Contract replay

There was only one ordinary nonterminal deterioration before the outcome: the 2021-11-08 date slip. A strict two-consecutive rule therefore had **no pre-outcome challenged date**. The milestone slip and symptomatic endpoint failure are different observables and cannot be combined to manufacture confirmation. Independently, the predeclared endpoint-failure override sets `broken` on **2021-12-22**, the same day as the clearly wrong result. A one-filing rule on the November delay would have warned 44 days earlier but would have been noisier; the delay contained no efficacy information, while the endpoint result was objective and needed no confirmation.

#### Honest verdict

**VISIBLE_ONLY_COINCIDENT — 0 days.** The filed endpoint failure was definitive and legally auto-terminal because it was predeclared, but the ordinary two-period deterioration rule offered no lead. This is an honest coverage limit, not a missing-data failure.

### CL-FA-1 — Axsome Therapeutics (2021–22 AXS-05/Auvelity FDA delay; false alarm)

#### Setup

Axsome was a pre-commercial CNS platform long, but the near-term hold thesis centered on AXS-05 for major depressive disorder after positive pivotal studies and FDA Priority Review. The stock had risen from low single digits in 2018 to more than $100 at its 2020 high, making an FDA-process scare consequential for a large embedded gain. **Size band (nearest contemporaneous 10-K public float): mid-cap** — the 2020 Form 10-K reported approximately **$2.4 billion** of non-affiliate market value at June 30, 2020 ([2020 10-K, filed 2021-03-01, accession 0001564590-21-009924](https://www.sec.gov/Archives/edgar/data/1579428/000156459021009924/axsm-10k_20201231.htm)). The false alarm is useful because the missed milestone remained undated across two filed observations and runway tightened, yet the clinical evidence had not failed.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2021-04-26** | [8-K, Item 8.01, accession 0001564590-21-020419, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1579428/000156459021020419/axsm-ex991_6.htm) | FDA accepted the AXS-05 NDA, granted Priority Review, and set **2021-08-22** as the PDUFA target date. | **Milestone clock initialized:** dated regulatory outcome; state is `no_break_observed`. |
| **2021-08-09** | [8-K, Items 2.02 and 8.01, accession 0001564590-21-042348, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1579428/000156459021042348/axsm-ex991_9.htm) | FDA had identified unspecified deficiencies that precluded labeling discussions. The letter explicitly said it was **not a final decision**; the PDUFA date remained August 22. Q2 cash was **$141.219m**. | **Regulatory review warning:** serious review evidence, but the dated milestone had not moved; it cannot start the frozen delay observable. |
| **2021-08-23** | [8-K, Item 8.01, accession 0001564590-21-045336](https://www.sec.gov/Archives/edgar/data/1579428/000156459021045336/axsm-8k_20210823.htm) | FDA said review would not be completed by the August 22 target; review remained ongoing and no replacement action date was supplied. | **AXS-05 decision milestone delayed or undated — first observation;** `challenged` is not yet earned. |
| **2021-11-08** | [10-Q, accession 0000950170-21-003466](https://www.sec.gov/Archives/edgar/data/1579428/000095017021003466/axsm-20210930.htm) | Review remained ongoing with no replacement decision date. Cash was **$114.623m**; nine-month operating cash use was **$79.385m**, so mechanical runway was **$114.623m / ($79.385m / 3) = 4.3 quarters**. The filing also disclosed an amended Hercules facility of up to $300m, much of it milestone-conditioned, and management stated existing cash covered at least 12 months. | **Same delayed/undated milestone — second observation;** contract becomes `challenged`. Runway remained sufficient to reach the eventual decision. |
| **2022-08-19** | [8-K, Item 8.01, accession 0001193125-22-224610](https://www.sec.gov/Archives/edgar/data/1579428/000119312522224610/d367288d8k.htm) | FDA approved AUVELITY (AXS-05) for adult MDD. | **Recovery / falsifier cleared:** named approval milestone achieved; prior delay did not invalidate efficacy. |

#### Contract replay

The same observable was **“AXS-05 FDA decision milestone delayed or undated.”** The milestone first actually missed on 2021-08-23; the 2021-11-08 periodic filing then confirmed that review remained ongoing without a replacement date, so `challenged` begins **2021-11-08**. Define recovery as the filed FDA approval on 2022-08-19: the challenge preceded recovery by **284 days**. A one-filing delay rule would have challenged **77 days earlier** on August 23. The August 9 deficiency notice cannot start that clock because the original date still stood; the two-filing rule correctly demanded review without pretending that a warning equaled a delay or endpoint failure.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE.** What distinguished it in real time was positive filed pivotal evidence, FDA's explicit “not final” language, no endpoint failure, and enough mechanical runway to reach an outcome. It was not knowable that approval would arrive, but the contract's `challenged` cap prevented an unsupported auto-exit.

### CL-FA-2 — Immunomedics (2019–20 sacituzumab govitecan CRL; false alarm)

#### Setup

Immunomedics was a clinical-to-commercial transition long built around sacituzumab govitecan in metastatic triple-negative breast cancer after Breakthrough Therapy designation and an accepted BLA. Shares had risen from roughly $3 in 2016 to above $25 in 2018, so the January 2019 CRL looked exactly like a post-run thesis break. **Size band (nearest contemporaneous 10-K public float): mid-cap** — the transition Form 10-K reported **$4.421 billion** of non-affiliate market value at June 30, 2018 ([10-KT, filed 2019-02-25, accession 0000722830-19-000005](https://www.sec.gov/Archives/edgar/data/722830/000072283019000005/immu201810-kt.htm)). The case is a false alarm because the problem was filed as remediable CMC execution, not a failure of the drug's clinical effect.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2019-01-18** | [8-K, Item 8.01, accession 0001104659-19-002351, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/722830/000110465919002351/a19-3149_1ex99d1.htm) | FDA issued a CRL instead of approval. Immunomedics stated the approvability issues were **exclusively CMC** and that no new clinical or preclinical data were required. | **Sacituzumab approval milestone slippage — first observation.** Serious challenge evidence, but neither a primary-endpoint failure nor a legal auto-break. |
| **2019-02-25** | [10-KT, accession 0000722830-19-000005](https://www.sec.gov/Archives/edgar/data/722830/000072283019000005/immu201810-kt.htm) | FDA would reinspect the Morris Plains manufacturing site; CMC remediation remained unresolved and resubmission timing was pending. Cash/securities were **$497.8m** and six-month operating cash use was **$130.664m**. Mechanical runway = **$497.8m / ($130.664m / 2 quarters) = 7.6 quarters**, or about **1.9 years**; management said resources funded operations through 2020. | **Same CMC-remediation/approval milestone remains unresolved — second adjacent filed observation;** contract becomes `challenged`, not `broken`. Runway reaches a plausible remediation cycle. |
| **2019-09-30** | [8-K, Item 8.01, accession 0001171843-19-006184](https://www.sec.gov/Archives/edgar/data/722830/000117184319006184/f8k_092719.htm) | The BLA resubmission target was revised to **late November or early December**. | **Challenge persists:** a replacement submission window is now named, but the clinical evidence still has not failed. |
| **2019-12-09** | [8-K, Items 1.01 and 8.01, accession 0001104659-19-071004, Exhibit 99.3](https://www.sec.gov/Archives/edgar/data/722830/000110465919071004/tm1924762d1_ex99-3.htm) | Company closed an offering of 16.429m shares at $17.50 for approximately **$272m net proceeds**. | **Actual dilution / runway extension:** share issuance is visible and costly, but it extended the remediation runway; it does not by itself break the clinical thesis. |
| **2020-04-22** | [8-K, Item 8.01, accession 0001171843-20-002751](https://www.sec.gov/Archives/edgar/data/722830/000117184320002751/f8k_042220.htm) | FDA granted accelerated approval to TRODELVY (sacituzumab govitecan-hziy) for the filed mTNBC indication. | **Recovery / falsifier cleared:** the original clinical value proposition survived CMC remediation. |

#### Contract replay

The replay names one observable: **“the sacituzumab approval milestone remains unresolved because CMC remediation is incomplete.”** The CRL filed 2019-01-18 was the first deterioration; the next periodic filing on 2019-02-25 confirmed the same unresolved CMC remediation and pending resubmission, setting `challenged` on **2019-02-25**. Define recovery as FDA approval filed 2020-04-22: the challenge preceded recovery by **422 days**. A one-filing rule would have challenged 38 days earlier at the CRL; that would have been faster but noisier because the same filing isolated the problem to CMC and said no new clinical data were needed. The two-filing rule was the better patience rule here.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE.** The contemporaneous separator was unusually explicit: CMC-only CRL, no new efficacy study, roughly 7.6 quarters of mechanical runway, and later added cash. Dilution damaged per-share value and belongs in the packet, but a financing that carried the asset to approval was not itself a thesis break.

## Cyclical / commodity-sensitive

For these cases, “gross margin” is calculated only from filed revenue and filed cost components and the arithmetic is shown. Capital intensity is filed capital expenditure divided by filed revenue for the same period. Acquisition-contaminated consolidated bridges are refused rather than normalized; where a clean operating-segment series exists, that raw series is used instead.

### CY-TB-1 — Arch Coal (2014–16 leveraged coal thesis; true break)

#### Setup

Arch Coal was a leveraged U.S. thermal/metallurgical coal hold: the bull case was that a diversified mine portfolio and large liquidity reserve could bridge depressed coal pricing until supply rationalized. It had once been a multi-billion-dollar institutional miner after the prior coal cycle, but by the evidence window the equity was already a recovery wager rather than an undiscovered compounder. **Size band (nearest contemporaneous 10-K public float): small-cap** — the 2014 Form 10-K reported approximately **$771.8m** of non-affiliate market value at June 30, 2014 ([2014 10-K, filed 2015-02-27, accession 0001047469-15-001419](https://www.sec.gov/Archives/edgar/data/1037676/000104746915001419/a2223254z10-k.htm)). The common-equity thesis became unambiguously wrong at the Chapter 11 filing, but repeated revenue contraction alongside rising capital intensity was visible earlier.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2015-04-30** | [10-Q, accession 0001104659-15-032255](https://www.sec.gov/Archives/edgar/data/1037676/000110465915032255/a15-7869_110q.htm) | Q1 revenue fell to **$677.005m** from $735.971m (**-8.0% YoY**). Q1 capex/revenue rose to **$22.880m / $677.005m = 3.4%**, from $14.454m / $735.971m = 2.0% a year earlier. Inventory was $240.113m versus $190.253m at the prior year-end, a sequential context figure that is not used as a YoY trigger. | **Revenue contracts while capex/revenue rises YoY — first observation.** Inventory is printed as context only because the filing does not provide a comparable prior-year quarter-end denominator. |
| **2015-07-31** | [10-Q, accession 0001104659-15-055127](https://www.sec.gov/Archives/edgar/data/1037676/000110465915055127/a15-12091_110q.htm) | Q2 revenue fell to **$644.462m** from $713.776m (**-9.7% YoY**). Six-month capex/revenue rose to **$99.361m / $1,321.467m = 7.5%**, from $95.746m / $1,449.747m = 6.6%. Q2 operating margin deteriorated to **-$69.546m / $644.462m = -10.8%**, from -5.0% a year earlier. Inventory was $223.929m, below the March balance, so it cannot supply the second trigger. | **Same revenue-contraction/rising-capital-intensity condition — second observation;** contract becomes `challenged`. Margin rollover corroborates it without being combined into a score. |
| **2015-11-09** | [10-Q, accession 0001104659-15-076941](https://www.sec.gov/Archives/edgar/data/1037676/000110465915076941/a15-17988_110q.htm) | Nine-month revenue was **$2.010bn**, down 8.3% YoY. Arch recorded **$2.139bn** of impairment/mine-closure charges, had **$5.108bn** of long-term debt and a **$605.4m stockholders' deficit**, and disclosed no meaningful revolver availability plus notice to terminate that facility. | **Challenge deepens:** balance-sheet and impairment facts confirm that the capital burden was not benign. No nonterminal item is promoted to `broken`. |
| **2016-01-11** | [8-K, Items 1.03 and 2.04, accession 0001104659-16-088942](https://www.sec.gov/Archives/edgar/data/1037676/000110465916088942/a16-1432_18k.htm) | Arch and substantially all domestic subsidiaries filed voluntary Chapter 11 petitions; the filing accelerated obligations under the named debt instruments. | **Filed terminal event:** Item 1.03 sets `broken` automatically. |

#### Contract replay

The same observable was **“revenue contracts while capex/revenue rises YoY.”** It printed on 2015-04-30 and again on 2015-07-31, so the contract would set `challenged` on **2015-07-31**. The quarter and year-to-date ratios are each compared with their like-basis prior-year periods; inventory is expressly excluded from the trigger because the balance-sheet denominators were not comparable. Define “clearly wrong” as the Item 1.03 Chapter 11 filing on 2016-01-11: the challenge led by **164 days**, roughly two reported quarters. A one-filing rule would have challenged 92 days earlier but would have been materially noisier because a single capex-heavy quarter can reflect project timing; the second filing showed persistence and added margin damage.

#### Honest verdict

**VISIBLE_IN_FILINGS_WITH_LEAD — 164 days.** Repeated revenue contraction with rising capital intensity supplied the operating warning; the later margin and liquidity disclosures made the equity risk acute; Item 1.03 supplied the only automatic terminal status.

### CY-TB-2 — U.S. Silica (2018–20 frac-sand capital-cycle rollover; true break)

#### Setup

U.S. Silica was a classic capital-cycle long: holders owned a high-volume frac-sand supplier with new in-basin mines, SandBox logistics, and an industrial-minerals stabilizer. The stock had risen from single digits in early 2016 to above $50 in 2017 as shale completion activity and margins surged. **Size band at cycle onset (nearest pre-break 10-K public float): mid-cap** — the 2017 Form 10-K reported **$2.871bn** of non-affiliate market value at June 30, 2017 ([2017 10-K, filed 2018-02-21, accession 0001628280-18-001983](https://www.sec.gov/Archives/edgar/data/1524741/000162828018001983/slca-20171231x10xk.htm)); the 2018 10-K later showed the float had fallen to $1.934bn. The break was excess/stranded Oil & Gas capacity and leverage after the spending boom, not the stock decline used to describe it.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2018-02-21** | [8-K, Item 2.02, accession 0001193125-18-052015, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1524741/000119312518052015/d537299dex991.htm) | FY2017 revenue was **$1.241bn**, up 122%, and the company guided to **$325m–$350m** of 2018 capex — **26.2%–28.2%** of trailing revenue. Net PP&E had already risen to **$1.169bn** from $783.313m (**+49.3%**). | **Company capacity build / capex-to-revenue trajectory — capital-cycle exposure declared.** This is context, not yet a break. |
| **2018-10-23** | [8-K, Item 2.02, accession 0001628280-18-012774, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1524741/000162828018012774/ex991_slcax20180930.htm) | Q3 Oil & Gas tons rose **10% sequentially**, but segment revenue fell 7% and segment contribution margin fell to **$89.550m / 3.821m tons = $23.43/ton**, from $33.08/ton in Q2 and $30.54/ton a year earlier. Q3 capex was another **$61.6m**. | **Oil & Gas contribution margin per ton rollover — first observation.** The EP Minerals acquisition makes the consolidated revenue/margin bridge contaminated, so it is refused; the separately filed Oil & Gas series is used. |
| **2019-02-19** | [8-K, Item 2.02, accession 0001628280-19-001511, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1524741/000162828019001511/ex991_slcax20181231.htm) | Q4 Oil & Gas contribution margin fell again to **$54.254m / 3.704m tons = $14.65/ton**, down **37.5% sequentially and 51.5% YoY per ton** (margin dollars fell 39% sequentially and 43% YoY). The company recorded **$265.715m** of impairments, principally because customers shifted from Northern White sand to cheaper local in-basin sand. Filed quarterly capex sums to **$72.3m + $86.9m + $61.6m + $119.0m = $339.8m**, or **21.5% of $1.577bn revenue**; PP&E rose to $1.826bn, inventory to $162.087m, and debt to about $1.260bn. | **Same segment unit-margin rollover — second observation;** `challenged` on the same filing that made stranded-capacity damage unmistakable. Inventory build and capex remain separate printed facts. |
| **2020-02-25** | [8-K, Item 2.02, accession 0001628280-20-002147, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1524741/000162828020002147/ex991slca20191231.htm) | Company recorded another **$363.847m** of Oil & Gas impairments, including $243.1m long-lived assets and $115.4m lease right-of-use assets, citing sharply lower demand for Northern White/regional non-basin sand and significant price decreases. 2020 capex guidance collapsed to **$30m–$40m**. | **Structural break confirmed:** prior capacity was not merely underutilized for one quarter. This confirms, rather than originates, the earlier wrong date. |

#### Contract replay

The comparable, acquisition-clean observable was **“Oil & Gas contribution margin per ton declines.”** It first deteriorated on 2018-10-23 and deteriorated again on 2019-02-19, so the two-filing contract sets `challenged` on **2019-02-19**. Define “clearly wrong” as that same filing: it named the structural customer shift and recognized $265.715m of impairments after the $339.8m capex year. Lead time is therefore **0 days / coincident**; the 2020 impairment is confirmation, not a conveniently delayed outcome date. A one-filing rule on 2018-10-23 would have led by 119 days and happened to be better here, but it would also fire on ordinary one-quarter sand pricing volatility; this case does not justify erasing the confirmation rule.

#### Honest verdict

**VISIBLE_ONLY_COINCIDENT — 0 days under the two-filing rule.** The capital boom was visible well in advance, but capital spending alone was not a break. The repeat segment-unit-margin deterioration and the first large stranded-asset impairment arrived together; the major acquisition correctly forces refusal of a consolidated per-share or margin bridge.

### CY-FA-1 — Micron Technology (2018–20 memory downturn; false alarm)

#### Setup

Micron was a memory-cycle long whose thesis combined structurally broader DRAM/NAND demand with improving industry discipline, while accepting violent inventory and pricing cycles. Shares rose roughly sixfold from the 2016 trough to the 2018 high, so two quarters of collapsing revenue and gross margin could plausibly trigger a long-hold falsifier. **Size band (nearest contemporaneous 10-K public float): large-cap** — the FY2019 Form 10-K disclosed **$36.2bn** of non-affiliate market value at February 28, 2019 ([2019 10-K, filed 2019-10-17, accession 0000723125-19-000094](https://www.sec.gov/Archives/edgar/data/723125/000072312519000094/a2019q4.htm)). The case is not “nothing happened”: the deterioration was severe, but it was a survivable memory downcycle rather than a permanent business break.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2019-03-21** | [10-Q, accession 0000723125-19-000014](https://www.sec.gov/Archives/edgar/data/723125/000072312519000014/a2019q2.htm) | Fiscal Q2 revenue fell to **$5.835bn** from $7.351bn. Filed gross profit was $2.864bn, so gross margin was **49.1%**, versus **58.1%** a year earlier (**-9.0pp**). Inventory rose to $4.390bn from $3.595bn at FY2018 year-end. | **Gross-margin contraction with revenue contraction — first observation.** Inventory build is printed separately. |
| **2019-06-26** | [10-Q, accession 0000723125-19-000035](https://www.sec.gov/Archives/edgar/data/723125/000072312519000035/a2019q3.htm) | Fiscal Q3 revenue fell to **$4.788bn** from $7.797bn. Gross profit was $1.828bn: margin **38.2%**, versus **60.6%** a year earlier (**-22.4pp**). Inventory reached $4.905bn. | **Same gross-margin/revenue contraction — second observation;** contract becomes `challenged`. |
| **2019-10-17** | [10-K, accession 0000723125-19-000094](https://www.sec.gov/Archives/edgar/data/723125/000072312519000094/a2019q4.htm) | FY2019 revenue was **$23.406bn**, down from $30.391bn, and gross margin was **45.7%** versus 58.9%. Inventory rose to **$5.118bn** from $3.595bn (**+42.4%**). Net PP&E capex rose to **$9.03bn / $23.406bn = 38.6% of revenue**, from $7.99bn / $30.391bn = 26.3%, although Micron remained profitable and disclosed $7bn–$8bn planned FY2020 capex. | **Challenge persists:** inventory and capital intensity worsened, but there is no terminal event and no justification for `broken`. |
| **2020-09-29** | [8-K, Item 2.02, accession 0000723125-20-000079, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/723125/000072312520000079/a2020q4exhibit991-pres.htm) | Fiscal Q4 revenue was **$6.056bn** versus $4.870bn (**+24.4% YoY**); GAAP gross margin was **34.1%** versus 28.6% (**+5.5pp**). FY2020 net capex fell to $7.95bn and operating cash flow was $8.31bn. | **Recovery:** the exact revenue/margin observable reversed while capex discipline improved. |

#### Contract replay

The same observable was **“YoY gross-margin contraction while revenue also contracts.”** It printed in the 2019-03-21 and 2019-06-26 filings, so `challenged` begins **2019-06-26**. Define recovery as the 2020-09-29 filed quarter in which both revenue and gross margin expanded YoY: the challenge remained open for **461 days**, about five filed quarters. A one-filing rule would have flagged one quarter earlier but would not have changed the correct status; memory margins routinely fall sharply in an industry downcycle. The two-filing rule was appropriately skeptical, while the ban on auto-`broken` prevented a cyclical trough from becoming a forced fundamental exit.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE.** The contemporaneous distinction was not that the numbers were mild — they were extreme — but that the company remained profitable, generated cash, retained net liquidity, and the deterioration matched an industry supply/demand cycle rather than a filed company-specific terminal event. Peer-relative framing would likely have reduced the alarm further; this field-book case does not claim a peer calculation was run.

### CY-FA-2 — Freeport-McMoRan (2014–17 copper/oil collapse and recovery; false alarm)

#### Setup

Freeport-McMoRan was a large-cap commodity hold built around long-lived copper assets, with the oil-and-gas acquisition adding both upside and balance-sheet risk. The shares had multiplied several-fold in the post-2008 commodity rebound before retreating into 2014–15; a holder entering the evidence window still owned a highly liquid institutional cyclical, not a microcap rescue. **Size band (nearest contemporaneous 10-K public float): large-cap** — the 2014 Form 10-K reported non-affiliate market value of **$37.3bn at June 30, 2014** and $21.8bn at February 20, 2015 ([2014 10-K, filed 2015-02-27, accession 0000831259-15-000016](https://www.sec.gov/Archives/edgar/data/831259/000083125915000016/a2014form10-k.htm)). This is a false alarm only for the narrow long-lived-copper/cycle thesis; the oil acquisition and ensuing dilution did permanently damage the broader allocator thesis.

#### Dated evidence timeline

| Filing / release date | Point-in-time primary source | What became public on that date | Predeclared observable |
|---|---|---|---|
| **2015-05-08** | [10-Q, accession 0000831259-15-000027](https://www.sec.gov/Archives/edgar/data/831259/000083125915000027/fcxq11510-q.htm) | Q1 revenue fell to **$4.153bn** from $4.985bn. Excluding the separately filed oil impairment, operating gross profit before SG&A was **$4.153bn - $2.912bn production/delivery - $0.939bn DDA = $0.302bn**, or **7.3%**, versus **25.7%** a year earlier. Q1 capex was $1.867bn, **45.0% of revenue**, and a $3.104bn oil-and-gas impairment was recorded. | **Gross-margin contraction with revenue contraction — first observation.** Capex trajectory and impairment remain independent lines. |
| **2015-08-10** | [10-Q, accession 0000831259-15-000043](https://www.sec.gov/Archives/edgar/data/831259/000083125915000043/fcxq21510-q.htm) | Q2 revenue fell to **$4.248bn** from $5.522bn. On the same pre-impairment basis, gross profit was **$4.248bn - $2.848bn - $0.890bn = $0.510bn**, or **12.0%**, versus **25.8%** a year earlier. Six-month capex was **$3.528bn / $8.401bn = 42.0% of revenue**, versus $3.562bn / $10.507bn = 33.9%; debt was $20.902bn at June 30. | **Same gross-margin/revenue contraction — second observation;** contract becomes `challenged`. |
| **2016-02-26** | [10-K, accession 0000831259-16-000062](https://www.sec.gov/Archives/edgar/data/831259/000083125916000062/a2015form10-k.htm) | Year-end debt was **$20.4bn** against **$224m cash**. From August 2015 through January 5, 2016, FCX sold **210m shares** at an average $9.47 for about $2bn gross proceeds. Management cut 2016 capex plans to approximately $3.4bn and pursued asset sales. | **Challenge remains, with actual dilution visible.** This is serious per-share damage but neither Item 1.03 nor another filed terminal event. |
| **2017-07-25** | [8-K, Items 2.02/7.01, accession 0000831259-17-000023, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/831259/000083125917000023/a2q2017exhibit991.htm) | Q2 revenue rose to **$3.711bn** from $3.334bn and operating income to **$669m** from $18m. Operating cash flow was $1.037bn; capex was $362m; cash was $4.667bn and debt $15.354bn. | **Recovery — first observation:** revenue/operating profitability and balance-sheet direction reverse. |
| **2017-10-25** | [8-K, Items 2.02/7.01, accession 0000831259-17-000030, Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/831259/000083125917000030/a3q2017exhibit991.htm) | Q3 revenue rose to **$4.310bn** from $3.877bn and operating income to **$917m** from $359m. Nine-month operating cash flow was $3.012bn; capex was **$1.014bn / $11.362bn revenue = 8.9%**; cash reached $5.0bn and debt fell to $14.8bn. | **Recovery — second observation / challenge clears:** the same operating series improved twice and capital intensity normalized. |

#### Contract replay

The deterioration observable was **“gross-margin contraction while revenue contracts.”** It appeared in filings on 2015-05-08 and 2015-08-10, setting `challenged` on **2015-08-10**. Define recovery conservatively as the second consecutive filed improvement, 2017-10-25: the challenge remained open for **807 days**, approximately nine quarters. A one-filing rule would have flagged 94 days earlier but would only have lengthened an already long review state; it would not establish permanent breakage during a common commodity shock. The correct contract behavior was to print the challenge, dilution, and debt facts without auto-terminal escalation.

#### Honest verdict

**FALSE_ALARM_CORRECTLY_SURVIVABLE.** For the narrow copper-cycle thesis, filed operating cash generation returned, capex/revenue normalized, and debt fell materially. Nothing in August 2015 guaranteed that outcome, and the oil/allocator thesis suffered real permanent damage; preserving those two interpretations is exactly why the packet must not synthesize one verdict across archetypes.

---

## Synthesis

### What the 24 replays say

Seven of the 12 selected true breaks produced a two-filing `challenged` state before the defined wrong date. Five—Hertz, Twilio, FibroGen, Allakos, and U.S. Silica—were visible only coincident with the break under the strict two-observation rule. Counting coincident cases as zero lead, the median lead across all 12 true breaks was **93.5 days**; among the seven cases that actually led, the median was **162 days**. These are descriptive results for the selected cases, not a coverage estimate: the sample was selected for verifiable filing evidence and is neither random nor survivorship-correct.

Ten of the 12 false alarms reached a valid `challenged` state; Carvana and Okta were correctly refused as `unverifiable` because ADESA and Auth0 contaminated their comparison periods. Among those 10 valid challenge clocks, the conservative median challenge-to-recovery interval was **552.5 days**. The rule did not make normal cyclicality disappear. The main protection was therefore not that two filings eliminated false alarms; it was that nonterminal deterioration stayed at `challenged`, refused comparisons stayed refused, counterevidence remained visible, and the state could later de-escalate.

### Per-archetype replay summary

| Archetype | True-break lead under two-filing rule | Median lead | False alarms under the same rule | Observables that did the work | Observables that did not separate on their own |
|---|---|---:|---|---|---|
| Quality compounder | Under Armour 90d; V.F. 97d | **93.5d** | Texas Roadhouse recovered after 567d, confirmed after 644d; Ulta recovered on a clean pre-shock comparison after 637d, confirmed after 727d | Persistent margin direction; inventory growth versus demand; cash conversion | Absolute margin magnitude; slower-but-positive comps without margin/cash damage |
| Owner-operator / allocator | 2U 141d; Stitch Fix 210d | **175.5d** | Amazon FCF recovered after 265d, annual confirmation at 364d; FedEx margin recovered after 274d, confirmed at 364d | Actual FCF/share and share count; whether buybacks offset dilution; operating corroboration after succession | Item 5.02 alone; announced buyback dollars; one acquisition/capex year |
| Turnaround / distressed | Hertz 0d/no pre-break double confirmation; Party City 162d | **81d** | Carvana was acquisition-refused, with first full-year post-ADESA operating evidence by 2024-02-22; Teva's conservative recovery took 1,929d | Inventory plus cash burn and liquidity; debt direction; Item 1.03 for terminal state | Margin decline alone; high leverage alone; dilution that extends runway |
| Contracted / platform growth | Fastly 207d; Twilio 0d/coincident | **103.5d** | Autodesk recovered after 730d; Okta was acquisition-refused, with clean comparable evidence by 2024-03-01 | Repeated comparable RPO/forward-book depletion; separate margin or CFO corroboration when admissible | Reported revenue conversion alone; cross-company RPO levels; acquisition-contaminated margin/receivables spreads |
| Clinical / milestone / pre-revenue | FibroGen 0d/coincident; Allakos 0d/coincident | **0d** | Axsome resolved after 284d; Immunomedics after 422d | Same-observable changes to the exact evidentiary package; filed endpoint outcome; runway relative to the next milestone | Delay alone; CRL alone; cash runway as an efficacy signal; financing alone |
| Cyclical / commodity-sensitive | Arch Coal 164d; U.S. Silica 0d/coincident | **82d** | Micron recovered after 461d; Freeport after 807d | Segment unit margin after a capacity build; revenue contraction with rising capital intensity; solvency | Absolute capex/revenue; even very large margin compression; peer-common downcycles |

### Breaks that fundamentals cannot catch

**Five of 12 true breaks, or 41.7%, had no useful two-filing lead.** That is the honest no-lead fraction in this purposive sample.

- **Hertz:** the February 2020 10-K still showed improving revenue and operating cash flow. The abrupt travel shutdown produced one public warning and one adverse quarter before the public Chapter 11 announcement. The later Item 1.03 filing recognized the terminal fact; it did not forecast it.
- **Twilio:** early margin and cash comparisons crossed unequal Segment ownership. The clean partial-RPO sequence completed only on the filing that also established the operating-leverage break.
- **FibroGen:** an April evidence-integrity disclosure was a serious one-filing warning 127 days before the CRL, but the earlier date extension was not the same observable. The required double-confirmation rule therefore had no honest lead.
- **Allakos:** the November milestone slip contained no efficacy information. The named symptomatic endpoints failed only when the results were filed. A binary endpoint bus can be exact and still have zero lead.
- **U.S. Silica:** the capital boom was visible long before the break, but capacity investment is not itself falsification. The second comparable segment-margin deterioration and the first large stranded-asset impairment arrived in the same filing.

No selected case received the exact `NOT_VISIBLE_IN_FUNDAMENTALS` verdict because the case-selection rule required a verifiable public-filing endpoint. That is a selection boundary, not proof that tape-, valuation-, or narrative-only holding errors do not exist. In this selected set, the contract supplied advance review in **seven of 12** true breaks; that fraction must not be extrapolated to a population. Abrupt macro shocks, binary outcomes, acquisition-scope refusals, and some capital-cycle inflections had little or no strict two-file lead. A6 is a hard-stop bus, not a lead generator.

### Cross-case observable findings

| Observable | What the cases showed | Calibration implication |
|---|---|---|
| Gross/operating margin | Magnitude did not separate outcomes. Under Armour broke after -46 bp then -125 bp; Texas Roadhouse survived -213 bp then -116 bp. Okta printed -653 bp then -510 bp but was acquisition-refused; Micron survived -900 bp then -2,240 bp in a memory downcycle. | Preserve direction/persistence, but do not claim a universal absolute break threshold. Scope and peer context are mandatory before interpretation. |
| Receivables growth minus revenue growth | Okta's false alarm printed +58.3 pp then +20.5 pp after Auth0; Fastly's true break had healthy negative spreads, and Twilio's early raw spread was only +4.4 pp but also acquisition-contaminated. | Not a standalone separator in this book. Acquisition normalization and a second demand/cash fact are required. |
| Inventory build | It helped in V.F. and Party City, while Micron's 42% inventory build was survivable. Arch's non-comparable quarter-end denominators were refused rather than pressed into service. | Useful as a named challenge sensor; not terminal without company-specific demand, cash, or solvency deterioration. |
| Capex/revenue and net PP&E | U.S. Silica's build preceded stranded capacity, but Amazon, Micron, and Freeport survived very high investment intensity. | Use within-company and cohort trajectory, never a cross-sector level. Investment must roll into margin/return damage before it supports a break review. |
| FCF/share and self-funding | Repeated negative per-share cash economics plus dilution led 2U; absolute negative FCF falsely challenged Amazon; Carvana's improving burn was contemporaneous counterevidence during a refused raw alarm. | Direction, funding source, and share count matter more than the sign in one period. |
| Net issuance / buyback execution | Stitch Fix buybacks failed to stop dilution; FedEx buybacks reduced diluted shares; Immunomedics issuance extended runway to approval; Freeport issuance repaired a stressed balance sheet at real per-share cost. | Actual share-count outcome belongs in the packet. Issuance or authorization alone cannot decide the thesis. |
| RPO/backlog/deferred revenue | Two clean sequential forward-book declines led Fastly but only coincided with Twilio's defined break; Autodesk and Okta continued to replenish. | Strong selected platform review sensor, but issuer definitions, practical-expedient omissions, and the Twilio no-lead result forbid a universal coverage claim. |
| Milestone date and runway | FibroGen supplied one material evidence-integrity warning but no same-observable double confirmation; Axsome and Immunomedics delays survived because efficacy had not failed and cash reached the decision. Allakos had ample runway and still failed. | Runway can distinguish financing risk from scientific risk; it cannot forecast efficacy. Delay is review, not terminal evidence. |
| 8-K hard-stop items | Item 1.03 supplied exact legal finality in Hertz, Party City, 2U, and Arch. Item 2.04 opened solvency review and generally arrived alongside bankruptcy. No selected case made Item 1.02, 3.01, or 4.02 load-bearing. | The selected Item 1.03 cases show exact legal finality, not population-level precision. A6's lead claim and the absent item routes remain uncalibrated by this book. |
| Item 5.02 / Form 4 | Item 5.02 mattered as context in Stitch Fix and FedEx but separated nothing alone. Form 4 open-market disposal was not load-bearing in any selected case. | Do not invent a departure or insider-sale threshold from this sample. A7 remains correctly deferred. |

### Threshold recommendations — priors to be checked against our data

The following are **starting priors, not tested results**. They must not be described as calibrated, validated, or predictive. The sample is too small, purposive, and heterogeneous for that claim.

| Contract lane | Field-book prior | Why this prior, and what would falsify it |
|---|---|---|
| Quality / A2 gross-margin pilot | Require two adjacent YoY declines with comparable scope. Use **100 bp company-under-peer deterioration on the second print** as a review-priority prior, not an absolute company threshold. Permit a smaller decline when a separately named cash/inventory sensor also repeats. | A universal 200 bp floor would miss Under Armour and still fire on Texas Roadhouse. Peer-relative spread, not raw magnitude, is the plausible discriminator to check. |
| Receivables stretch after LHB-R6 enrichment | Start a collection review only after the receivables-minus-revenue spread exceeds **+15 pp twice**, with an acquisition/recast refusal and a separate demand or CFO observation. | Okta shows that even +58/+20 pp can be acquisition noise; Twilio/Fastly show that true breaks need not have collection stress. Retire standalone use if this overlap persists in the broader data. |
| Inventory / demand | Treat **+15 pp inventory-growth minus revenue-growth twice** as `challenged` context, not a break. Require cash conversion, margin, or liquidity deterioration to be named separately. | Party City clears it and fails; Micron clears it and survives. Peer/cycle context must decide whether the build is abnormal. |
| Owner-operator / allocator | Item 5.02 never fires alone. Require two periods of declining FCF/share or actual share-count expansion after buybacks, plus a separate operating or leverage deterioration. | Stitch Fix and 2U fit; FedEx and Amazon supply the counterexamples. A planned succession or one investment year should defeat the rule. |
| Turnaround / solvency | Use two periods of worsening self-funding plus either **less than four quarters of disclosed liquidity runway** or a repeated inventory/demand spread as a review-priority prior. Item 2.04 opens solvency review; only Item 1.03 is terminal by itself. | Hertz shows that an abrupt shock can bypass the rule. Carvana and Teva show that leverage or negative margin without worsening cash/inventory can recover. |
| Contracted/platform | Use two sequential comparable RPO/backlog declines with a **cumulative decline of roughly 10% or more from the reference filing** as a review-priority prior. Print separately comparable gross-margin or CFO deterioration as corroboration; never let acquisition-contaminated corroboration start the clock. | Fastly and Twilio clear the decline shape, but only Fastly led; Autodesk and Okta did not deplete. Retire the percentage if broader issuer definitions make it non-comparable. |
| Clinical/milestone | A date slip alone caps at review. For financing stress, start with disclosed liquid resources reaching the revised milestone **plus two quarterly filing cadences**; shorter coverage is a runway challenge. A filed predeclared primary-endpoint failure may be terminal; a CRL is not automatically terminal. | Axsome and Immunomedics survived long delays; Allakos failed with ample cash. The runway prior must never be interpreted as an efficacy probability. |
| Cyclical/capital cycle | Retain the charter's within-name **+3 pp capex/revenue versus two years earlier** as a supply-build prior, but do not challenge until two comparable segment margin/return rollovers appear. Keep peer-common cycles visible rather than calling them company-specific breaks. | U.S. Silica supplies the structural pattern; Micron and Freeport show why capex or margin magnitude alone fails. |

### Would peer-relative framing rescue false alarms?

Texas Roadhouse's commodity/labor squeeze, FedEx's freight slowdown, Micron's memory downcycle, and Freeport's commodity collapse are qualitative candidates for de-escalation by a future point-in-time peer replay. This book did not run that engine, so it claims neither a rescue count nor that peers would have changed any verdict. Teva's generic-pricing pressure is another candidate to test.

Peer framing would not solve the idiosyncratic false alarms: Amazon's capacity build, Carvana's acquisition/inventory reset, Autodesk's business-model conversion, Okta's Auth0 scope change, or the Axsome/Immunomedics regulatory delays. Those required scope guards, forward-book counterevidence, or milestone/runway logic. A peer gate also cannot veto a filed terminal event; Item 1.03 and a predeclared endpoint failure retain their archetype-routed authority.

### Contract implications, without changing the charter

1. **Keep two-filing confirmation.** It preserved material lead in seven selected true breaks and delayed single observations from becoming `challenged`. Its role is evidence discipline, not terminal protection; LHB-R3's cap on automatic `broken` supplies that protection.
2. **Keep `challenged` sticky but reversible.** Several honest false alarms needed two to nine quarters to resolve; Teva took much longer. A short automatic expiry would erase real uncertainty, while automatic escalation would destroy patience.
3. **Print counterobservables beside the fire.** Margin dollars, actual share count, debt direction, RPO replenishment, runway, and scope/refusal stamps often distinguished survivable alarms at the trigger date.
4. **Treat A6 as legal finality, not foresight.** Item 1.03 supplied an unambiguous terminal state, usually after the useful economic work had either happened or become impossible.
5. **Do not universalize thresholds across archetypes.** The largest margin and capex deteriorations in the book often survived. The named business mechanism and comparable denominator are the contract.
6. **Preserve `unverifiable`.** Autodesk's accounting change, Okta's acquisition, Amazon's split, Carvana's acquisition, and U.S. Silica's EP Minerals scope demonstrate why refusal is an output, not a missing feature to be papered over.

## Cases considered and rejected

- **Chipotle (2015–16):** the decisive evidence was a food-safety event and store closures, not a clean quality-compounder filing sensor; it would test event response more than persistence.
- **Nike (2015–17):** it would cluster the quality sample in athletic apparel alongside Under Armour and V.F. and offered a less discrete recovery endpoint than Texas Roadhouse or Ulta.
- **Meta Platforms (2022–23):** rejected as a second mega-cap allocator false alarm; Amazon supplied a cleaner two-annual-filing FCF replay.
- **Twitter:** the take-private endpoint would adjudicate transaction completion, not operating falsification or recovery.
- **Bed Bath & Beyond:** its Item 1.03 is verifiable, but adding another 2022–23 leveraged-retail inventory/liquidity bankruptcy would duplicate Party City and flatter the terminal bus.
- **WeWork:** SPAC accounting, rapid scope changes, and short listed history made adjacent-period denominators unusually non-comparable.
- **DocuSign:** its RPO practical expedient omits contracts of one year or less; using the incomplete clock as the primary falsifier would overstate observability.
- **Snowflake:** filings established consumption deceleration but not a clean point when the business thesis became clearly wrong; choosing from the drawdown would reintroduce the forbidden tape axis.
- **Adobe/Figma:** the mutual merger termination was not the endpoint of Adobe's underlying platform-growth thesis. Routing Item 1.02 to an unrelated thesis would violate the hard-stop contract.
- **Biogen/aducanumab:** the path from 2019 discontinuation to 2021 approval is a contested regulatory-evidence case, not a clean pre-revenue replay.
- **Clovis Oncology:** the 2022 bankruptcy combines clinical, commercial, financing, and legal stress; selecting Item 1.03 would be less informative and more selection-flattering than the endpoint-pure Allakos case.
- **Sarepta Therapeutics:** repeated FDA and trial controversies did not yield a clean, agreed “clearly wrong” date in the selected window.
- **Peabody Energy (2016):** it would duplicate Arch in commodity, year, macro exposure, and Item 1.03 outcome.
- **Covia (2018–20):** it would duplicate the frac-sand capital cycle and over-concentrate the archetype in the 2020 shock.
- **SunEdison (2016):** its bankruptcy was primarily a yieldco/project-finance and liquidity-architecture failure, not a commodity-sensitive operating capital cycle.

## Source discipline and limitations

- Sources are free primary public records: SEC filings, company investor-relations releases furnished to the SEC, FDA or other agency records, and bankruptcy/court notices. Secondary articles are not load-bearing evidence.
- The sample is purposive and small. It can reveal failure modes, plausible timing, and threshold priors; it cannot estimate population frequencies or validate return prediction.
- Equal true-break and false-alarm counts are imposed by design. Any apparent 50% precision, false-positive rate, or base rate would be fabricated.
- Historical XBRL tags and issuer definitions change. Where comparable facts could not be reconciled, the book says `unverifiable` or refuses the calculation.
- “Recovery” means the business observable or registered milestone recovered, not merely that the share price bounced. “Clearly wrong” is defined inside each true-break replay before lead time is calculated.
- Mid-cap status is an approximate contemporaneous size classification used only to audit sample breadth; it is not an analytical variable.

## Reproducibility note

Every load-bearing timeline row links to the contemporaneous filing or first-party release. The arithmetic is intentionally simple enough to reproduce from the cited tables. This is a field guide for contract calibration, not a machine-generated dataset or authorization to code a threshold; any later implementation must independently recheck the case facts against the original filings.
