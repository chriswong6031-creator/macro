# D0R Workstream C — Defense Equity Archetype Router and driver taxonomy

**Purpose:** different defense businesses convert demand into earnings on different clocks. One generic “defense score” would be wrong and is forbidden (`can_rank=false` remains).

**Router status:** SPEC ONLY. D0R freezes the contract; D2/D4 implement. Multiple archetypes per issuer are allowed with a primary + secondary and valid-time.

## C5. Output contract (implement later)

```text
input:  issuer_id, as_of, known_at, optional segment_id
output: {
  primary_archetype, secondary[],
  confidence: {reviewed|inferred|unresolved},
  valid_from, valid_to,
  drivers: {demand, access, monetization, expectations, risk},
  product_lenses: [...],   # which V3 surfaces to open
  null_behavior: print unresolved, do not default to "prime"
}
```

- Stock Identity owns ticker/share class/listing. The router owns *economic archetype*, not identity.
- Segment-level archetypes (GD Marine vs Aerospace) beat issuer-level when the 10-K supports it.
- Historical validity intervals are required; a 2012 LCS thesis is not a 2026 Constellation thesis.
- Ambiguity: show both archetypes and refuse a blended score.

## C4. Driver hierarchy (applies to every archetype)

**Demand and policy:** threat/discourse; doctrine/mission gap; budget/appropriation/supplemental; NATO/allied; FMS/export; replenishment vs fleet replacement.

**Access and competition:** program position; incumbent; vehicle/IDIQ eligibility; win/loss/protest; teaming/JV/sub; local-content/ITAR.

**Monetization:** funded vs total backlog; production rate; capacity/supply; contract type + escalation; delivery; revenue recognition; margin/EAC; WC/cash.

**Expectations and valuation:** guidance; consensus revisions; prior press; price/options run-up; crowding; relative multiples; rates/FX.

**Risk:** delay/cancel; fixed-price charge; protest/recompete loss; legal/cyber/quality; labor/supplier; customer concentration; de-escalation.

## C2–C3. Archetypes

### 1. Platform prime / systems integrator

| Field | Freeze |
|---|---|
| Economic unit | Multi-year platform franchise (jet, ship combat system, ground vehicle) booked as sales + funded backlog, not as a single award headline |
| Demand signals | Recurring PE lines, FRP quantities, FMS cases, service TAM |
| Leading indicators | Authorization/appropriation vs prior FY; LRIP→FRP; international LOAs; GAO/DOT&E on the platform |
| Revenue/margin timing | Years; EAC revisions matter more than a one-day award print |
| Backlog meaning | Total backlog ≠ funded; options inflate; cancellation risk sits in unfunded |
| Contract-type risk | Mix of FPIF/FPAF/cost-plus; development FP is the blow-up |
| Capacity | Final assembly + supplier BOM, not the prime’s floor space alone |
| WC | Progress payments / billings in excess; inventory on FP production |
| Valuation anchors | EV/backlog, ROIC, FCF conversion, peer franchise multiple |
| + catalysts | Multi-year procurement, FMS, quantity add, EAC beat |
| − catalysts | Nunn-McCurdy, FP charge, quantity cut, protest loss |
| Sources | 10-K segment, P-1, DSCA, GAO, award tape |
| Residual control | Other primes on different platforms; not “defense ETF” |
| False positives | Ceiling increase with no obligation; press “win” that is IDIQ |
| Prophet overlap | Theme residual (air dominance, shipbuilding) — context only |
| Lenses | Program dossier + company cockpit + gov vs company |

### 2. Missiles, munitions, and effects

| Field | Freeze |
|---|---|
| Economic unit | Unit production + replenishment of expendables (Patriot, AMRAAM, 155mm, GMLRS, Javelin) |
| Demand | War/out-of-stock + allied restock + DoD inventory objective |
| Leading | Supplemental, multiyear procurement, SRM/energetics bottlenecks, line-rate announcements |
| Timing | Faster than platforms once the line is hot; still months, not days |
| Backlog | Book-to-bill spikes are real; capacity can cap conversion |
| Contract | Often FP production; commodity/energetics inflation |
| Capacity | SRM, warheads, seekers, fuzes — the bottleneck *is* the thesis |
| WC | Inventory build before shipments |
| Valuation | Cycle-adjusted; do not pay peak replenishment as perpetuity |
| + | Multi-year, new line, FMS cluster |
| − | Ceasefire, inventory fill, line delay |
| Sources | DoD announcements, P-1 ammo, company munitions commentary |
| Residual | Other munitions names, not primes |
| False positives | Headline “$1.2B Patriot” that was already in guidance |
| Prophet | Replenishment theme |
| Lenses | Theme war room + bottleneck atlas |

### 3. Sensors, EW, C4ISR, mission electronics

| Field | Freeze |
|---|---|
| Economic unit | Recurring mission equipment + upgrades (radar, EW, C2, radio) |
| Demand | Doctrine (JADC2, counter-A2/AD), threat emitters, fleet upgrade |
| Leading | RDT&E PE, OTAs, classified hints only as *limits* not facts |
| Timing | Mix of product + services; upgrades faster than new platforms |
| Backlog | IDIQ vehicles common; task-order rate is the tell |
| Contract | Mix; software sustainment vs hardware FP |
| Capacity | Microelectronics, RF components, clearances |
| WC | Typical industrial |
| Valuation | Growth/ROE vs prime; multiple sensitive to margin mix |
| + | Vehicle win + first task orders; EW urgent operational need |
| − | Vehicle loss; continuing resolution delaying OTAs |
| Sources | Award tape on electronics PEs, 10-K mix |
| Residual | Other C4ISR, not munitions |
| False positives | IDIQ ceiling as if it were funded |
| Prophet | C4ISR theme |
| Lenses | Program + company dossier |

### 4. Shipbuilding and nuclear naval

| Field | Freeze |
|---|---|
| Economic unit | Hull delivery + nuclear yard throughput (EB, NNS, Ingalls) |
| Demand | 30-year shipbuilding plan, AUKUS, Columbia/Virginia cadence |
| Leading | Advance procurement, shipyard CAPEX, labor, steel, supplier (propulsor, VLS) |
| Timing | Decade; one hull slip moves years of FCF |
| Backlog | Enormous and slow; funded vs work remaining |
| Contract | Block-buy / multiyear; FP disaster history (LCS, Zumwalt, Constellation risk) |
| Capacity | Dry dock, nuclear-qualified labor — hardest constraint in the set |
| WC | Long-cycle inventory; progress payments |
| Valuation | NAV / delivery slot; FCF yield often the honest anchor |
| + | Extra Virginia, AUKUS, labor win |
| − | Schedule slip, cost cap, labor strike |
| Sources | Navy 30-year plan, HII/GD commentary, GAO shipbuilding |
| Residual | Other yards, not air primes |
| False positives | “$X billion contract” that is a block already known |
| Prophet | Shipbuilding theme |
| Lenses | Program dossier + bottleneck + cash cockpit |

### 5. Defense services, IT, cyber, engineering, mission support

| Field | Freeze |
|---|---|
| Economic unit | Funded headcount on cost-plus / T&M / hybrid (C4ISR support, logistics, cyber) |
| Demand | O&M, cyber, professional services ceilings |
| Leading | Recompete calendar, protest, on-site vs remote mix, clearance pipeline |
| Timing | Quarter-scale; recompete is the event |
| Backlog | Funded backlog + pipeline; win rates |
| Contract | Cost-plus common; margin is utilization + mix |
| Capacity | Cleared labor |
| WC | Receivables; low inventory |
| Valuation | EV/EBITA, FCF, recompete risk discount |
| + | Vehicle win, expanded ceiling *with* funding |
| − | Protest loss, CR, labor |
| Sources | SAM recompetes (when live), 10-K, award mods |
| Residual | Other services names |
| False positives | Ceiling-only awards |
| Prophet | Weak; services rarely a tape theme |
| Lenses | Recompete watch + company dossier |

### 6. Aerospace components, propulsion, materials, aftermarket

| Field | Freeze |
|---|---|
| Economic unit | Content per platform + spare/aftermarket (castings, aerostructures, engines) |
| Demand | Build rates + installed-base flight hours (civil+defense mix is the trap) |
| Leading | OEM build-rate letters, aftermarket R&O, powder/metal |
| Timing | OEM lag + aftermarket cycle |
| Backlog | OEM orders vs aftermarket (higher conversion) |
| Contract | Long-term agreements; metal inflation |
| Capacity | Forgings, coatings, engines — bottleneck names live here |
| WC | Inventory intensive |
| Valuation | Aftermarket mix multiple |
| + | Rate increase, exclusive LTA |
| − | Rate cut, quality escape, OEM destock |
| Sources | OEM commentary, company aftermarket, awards as confirmation |
| Residual | Industrial aero, not “defense ETF” |
| False positives | Dual-use name treated as pure-play war stock |
| Prophet | Aero aftermarket / industrial |
| Lenses | Bottleneck atlas + company cockpit |

### 7. Space, launch, missile-warning, satellite systems

| Field | Freeze |
|---|---|
| Economic unit | SDA/PWSA tranche, OPIR, SATCOM (IRDM golden), launch |
| Demand | Proliferated architecture + missile warning + commercial overlap |
| Leading | SDA awards, launch cadence, on-orbit failures, SATCOM service mods |
| Timing | Tranche awards then deliveries; service revenue (IRDM) is different from bus manufacturing |
| Backlog | Milestone vs service ARR — split them |
| Contract | Mix of FP development (pain) and service (IRDM P00032 is funding of existing SATCOM) |
| Capacity | Launch, radiation-hard parts, buses |
| WC | Varies wildly (service vs OEM) |
| Valuation | Service yield vs growth EV/sales for manufacturers |
| + | Tranche award, on-orbit acceptance |
| − | Launch fail, program restructure, commercial SATCOM price war |
| Sources | SDA, USAspending, 10-K SATCOM |
| Residual | Space names, not air primes |
| False positives | Treating a service incremental fund as a new constellation win — **live IRDM case** |
| Prophet | Space / Golden Dome overlap |
| Lenses | Program + company + change tape |

### 8. Autonomy, drones, counter-UAS

| Field | Freeze |
|---|---|
| Economic unit | Attritable production + software/kill-chain integration |
| Demand | Urgent operational needs, Replicator-class, base defense |
| Leading | OTAs, service announcements, export policy |
| Timing | Faster; also more cancelable |
| Backlog | Small; print-to-print volatility |
| Contract | OTA/other transactions; prototype ≠ production |
| Capacity | Airframes cheap; seekers/radios not |
| WC | Growth-company WC |
| Valuation | Often unprofitable; do not use prime multiples |
| + | Production decision, FMS |
| − | OTA ends, protest by incumbent, policy |
| Sources | DoD, SAM, company |
| Residual | Other autonomy, not LMT |
| False positives | Demo contract as franchise |
| Prophet | Autonomy theme |
| Lenses | Theme war room; high uncertainty state |

### 9. Critical industrial bottleneck

| Field | Freeze |
|---|---|
| Economic unit | Constrained input (SRM, TNT, microelectronics, rare earths, nuclear labor, bearings) |
| Demand | Derived from munitions/ship/space rates |
| Leading | DPA Title III, plant CAPEX, incidents, import restrictions |
| Timing | CAPEX years; price spikes can be fast |
| Backlog | Sometimes none (commodity-like) |
| Contract | Indexation, take-or-pay |
| Capacity | **This is the model** |
| WC | Inventory / working-capital swings |
| Valuation | Replacement cost / scarcity, not PE |
| + | DPA award, second line |
| − | Accident, import dump, demand fade |
| Sources | DPA announcements, permits, job postings |
| Residual | Must not be the downstream prime |
| False positives | “Critical mineral” narrative without a DoD demand path |
| Prophet | Bottleneck theme |
| Lenses | Industrial Bottleneck Atlas |

### 10. Diversified aerospace / industrial

| Field | Freeze |
|---|---|
| Economic unit | Defense as a *segment*, often <50% (BA, GE/HON aero, some materials) |
| Demand | Mixed civil + defense; civil can dominate the tape |
| Leading | Civil OEM rates *and* defense PEs |
| Timing | Civil cycle may swamp a defense award |
| Backlog | Segment breakout required |
| Contract | Mixed |
| Capacity | Shared factories |
| WC | Civil-driven |
| Valuation | Sum-of-parts; never a pure-play multiple |
| + | Segment inflects *and* civil stable |
| − | Civil shock with intact defense |
| Sources | Segment 10-K, OEM, awards as secondary |
| Residual | Industrial aero peers |
| False positives | Mapping a BA award to “defense beta” on a 737 day |
| Prophet | Often not a defense pick |
| Lenses | Company cockpit with segment filter |

### 11. International pure-play / national champion

| Field | Freeze |
|---|---|
| Economic unit | Home MoD + export (BAE, Rheinmetall, Thales, Saab, Leonardo, Hanwha) |
| Demand | Home budget law + NATO %GDP + export licenses |
| Leading | Home budget bills, German Sondervermögen-class funds, export licenses |
| Timing | Local FY, not US FY |
| Backlog | Home currency; FX is a driver |
| Contract | National rules; offset |
| Capacity | Home yards/plants + ITAR-like constraints |
| WC | Local |
| Valuation | Home index + FX |
| + | Home budget lift, export license |
| − | License denial, home election, FX |
| Sources | MoD, company IFRS, SIPRI as context not price |
| Residual | Home market, not SPX defense |
| False positives | Treating a European name as a US supplemental pure-play |
| Prophet | NATO rearmament theme |
| Lenses | Theme war room + FX-aware cockpit |

## Router notes for D2

- IRDM is archetype **7 (space/SATCOM service)**, not a munitions name and not a prime. P00032 is incremental funding of an existing DISA SATCOM contract — monetization = service obligation, not a new platform win.
- HII is **4 (shipbuilding)**; a late award discovery on `N0002415C2114` is identity/clock, not a new hull.
- Do not route GE/BWXT solely because they appear on the compact filmstrip (21 vs graph 19).
