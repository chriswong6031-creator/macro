# Field Guide — CPI Bridge Forward-Looking Instruments (ex-energy blocks)

**Status:** UNDERSTANDING PHASE (house law: understanding-before-backtest). This is a
research inventory, NOT a prereg and NOT a backtest. It catalogs candidate forward-looking
instruments for the `cpi_bridge` ex-energy blocks and gates each on three tests (forward /
PIT / identifiability). Any leg built from this guide requires its own frozen prereg with a
forward window; nothing here is gauntlet-passed.

**Authored:** 2026-07-14 (research fan-out wf_cb44b900-a41: 4 field lanes + adversarial
synthesis). **Motivation:** the June-2026 CPI cold print (headline -0.4% / core -0.02% MoM)
post-mortem found ~0.26pp of the bridge's ~0.43pp ex-energy overshoot was core-side
disinflation invisible to lag-1 persistence. See [[cpi-june2026-cold-print-postmortem]] /
defect_notices.json and the MRI masterplan. This guide answers "what it has to relearn":
which forward instruments could give the ex-energy blocks eyes at inflection points.

**Doctrine anchors:** context-accrual (build the data layer first; a null instrument is
retained context, not a dead end); measurement-lens (separate not-identifiable from
not-collected from not-free); understanding-before-playbook (this guide precedes any ruler).

---

## Why persistence fails at turns

`engine/release_cpi_bridge.py` nowcasts headline CPI MoM as a weighted sum of per-block contributions. Every ex-energy block is a lag-1 persistence read: it replays the prior (already-published) month's own MoM. Persistence is the minimum-variance estimator when a series is a random walk with drift, but it is structurally blind at inflection points — it cannot see a turn until the turn is already in the printed history. The June-2026 cold print (headline -0.4%, core -0.02%) is the archetype: gasoline was nailed via `GASREGW` reference-month averaging (a genuine same-reference-month instrument), while ~0.43pp of ex-energy overshoot came from disinflation that lag-1 could not detect. ~0.26pp of that was core-side (core_services_ex_shelter + core_goods).

The engineering goal of this guide is NOT to declare any instrument gauntlet-passed. It is to inventory candidate FORWARD legs — readings available at CPI T-1 for reference month M that carry information the block's own lag-1 does not — and to gate each one on three tests the orchestrator must respect at prereg time:

- **FORWARD test:** the instrument must PUBLISH a reading covering (or leading) month M *before* CPI-M is released. An instrument that prints after CPI-M can only ever supply an M-1 reading at T-1, so its "lead" is one month at best. Verified release chain for June-2026 (all BLS/EIA official): CPI-M = July 14; PPI-M = July 15 (1 day AFTER CPI-M); Import Prices-M = July 17 (3 days AFTER CPI-M). Therefore at CPI-M T-1 only PPI **M-1** and Import-Price **M-1** are available. Their forward value is real but is a 1-month lead, not a same-reference-month read.
- **PIT test:** no revised-series look-ahead. FRED non-vintaged pulls of PPI/import/CPI sub-series must be treated `revision_optimistic`; only ALFRED-vintaged legs (PPIFIS, PPIFES, ECIWAG, ECIALLCIV, plus the Fed CPI-derivative series) are PIT-clean in-repo.
- **IDENTIFIABILITY test:** the instrument must supply an observable that separates the block's *turn* from persistence. A high contemporaneous correlation that collapses at any lead (e.g. WPU0543 vs retail electricity) fails this test — it is coincidence, not lead.

## Master candidate-instrument table

| Instrument | CPI block | Block wt | Source (FRED id / URL) | Cost | Latency vs CPI-M | PIT | Lead | In-repo | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| ZORI national | shelter (OER+rent) | 35.625 | Zillow public CSV | free | M-2/M-3 at T-1 (45d fence) | non-vintaged, fenced | ~12m YoY | **YES** `data/zori/national.parquet`, wired k=0.35 | redundant_with_existing (already best-instrumented) |
| Sticky/Median/Flex CPI | core_svc_ex_shelter (momentum) | 25.118 | STICKCPIM157SFRBATL, CORESTICKM157SFRBATL, MEDCPIM158SFRBCLE, FLEXCPIM157SFRBATL | free | same-day/M-1 usable | vintage-tracked | lag-1 momentum, R²~0.3-0.4 | **YES** all 4 in `data/fred/` + vintages | strong_prereg_candidate (lag-1 base swap) |
| Health-insurance April/Oct reset flag | core_svc_ex_shelter (health ins ~1.2-1.5pp) | 25.118 | BLS method (calendar fact) + CUSR0000SEMC lag-1 | free | reset date known months ahead | calendar PIT-safe | same-month mechanical shock | NONE (boolean flag + track sub-index) | strong_prereg_candidate |
| Manheim MUVVI (final monthly) | used_cars_and_trucks | 2.759 | Cox Auto coxautoinc.com/insights (headline free) | free-tier | month-M final ~5th biz day M+1 = BEFORE CPI-M | unrevised final | **coincident (same ref month), not forward** | NONE (scraper) | prereg_candidate — see redteam flag on lead mislabel |
| Edmunds new-vehicle ATP + incentives | new_vehicles | 3.838 | edmunds.com/industry-center (press release free) | free-tier | M-1 at T-1; partial-M sometimes | informal revision | 1m (M-1) | NONE (scraper) | prereg_candidate |
| BLS Import Price IR400 (apparel/footwear/HH) | apparel (+HH goods) | 2.368 | FRED IR400 | free | M-1 only (IP-M prints July 17 > CPI July 14) | revised 3m, non-vintaged | 1m via M-1 | NONE | prereg_candidate |
| BLS Import Price IR4 (consumer goods ex-auto) | core_goods aggregate | 19.176 | FRED IR4 | free | M-1 only | revised 3m, non-vintaged | 1m, broad/noisy | NONE | prereg_candidate (low S/N for residual) |
| BLS Import Price IZ315 (apparel NAICS) | apparel | 2.368 | FRED IZ315 | free | M-1 only | revised 3m | 1m, narrower than IR400, short history (2005) | NONE | prereg_candidate (corroborator) |
| CUSR0000SEFV (CPI food-away) | food_away_from_home | 5.373 | FRED CUSR0000SEFV | free | releases WITH CPI → M-1 at T-1 | non-vintaged | lag-1 persistence only | NONE (1-line FRED add) | strong_prereg_candidate (enables persistence at zero collector cost) |
| CES7000000003 (AHE leisure/hospitality) | food_away_from_home | 5.373 | FRED CES7000000003 | free | Jobs report ~10d before CPI → M-1 | benchmark-revised | genuine T-1 monthly labor read | NONE (1-line FRED add) | strong_prereg_candidate |
| ECIWAG / ECIALLCIV | food_away, core_svc (structural) | 5.373 / 25.118 | FRED, ALFRED | free | quarterly, ~1q lag | **vintage-tracked in-repo** | 2-4q regime anchor only | **YES** `data/fred/` + vintages | weak_candidate (regime/confluence only) |
| WPU012 (PPI processed foods) | food_at_home | 8.325 | FRED WPU012 | free | M-1 (PPI-M > CPI-M) | non-vintaged | 3m r=0.24; 1m r=0.09 < persistence 0.525 | **YES** `data/fred/WPU012.parquet` | weak_candidate (blend into existing signal) |
| WPU01 (PPI farm) | food_at_home | 8.325 | FRED WPU01 | free | M-1 | non-vintaged | 1m r=0.22, directional | **YES**, already wired | weak_candidate (existing) |
| WPU03 (PPI textiles) | apparel | 2.368 | FRED WPU03 | free | M-1 | non-vintaged | domestic pipeline, weakened post-2000 | NONE | weak_candidate |
| WPU141 (PPI motor vehicles) | new_vehicles | 3.838 | FRED WPU141 | free | M-1 | non-vintaged | misses incentive dimension (JD Power drives CPI) | NONE | weak_candidate |
| WPU05720301 (PPI jet fuel) | airline_fares | 0.881 | FRED | free | M-1 | non-vintaged | dir. sign ~60%, tiny headline impact | NONE | weak_candidate |
| DHHNGSP (EIA jet/kerosene spot) | airline_fares | 0.881 | FRED DHHNGSP | free | weekly, partial ref-M at T-1 | unrevised | 1-2m directional | **YES** `data/fred/` | weak_candidate |
| PCU5241265241261 (PPI auto insurance) | motor_vehicle_insurance | 2.754 | FRED | free | M-1 | non-vintaged, regime-dependent wedge | 6-18m REGIME lead only, not monthly | NONE | weak_candidate (regime flag) |
| WPU511101 / WPU512101 (PPI physician/hospital) | medical_care_services | 6.935 | FRED | free | M-1 | non-vintaged | 1-3m directional, level divergence | NONE | weak_candidate |
| WPU0543 (PPI electric power) | energy_electricity | 2.375 | FRED WPU0543 | free | M-1 | non-vintaged | 1m r=0.215 < persistence 0.239 | **YES** in-repo, unwired | **NULL** (fails identifiability — no lead) |
| DHHNGSP → electricity | energy_electricity | 2.375 | FRED | free | daily | unrevised | r<0.12 all leads | YES | **NULL** |
| APU000072610 (BLS avg elec price) | energy_electricity | 2.375 | FRED | free | releases WITH CPI → M-1 | non-vintaged | lag-1 only | **YES**, wired | redundant_with_existing |
| COT ag positioning | food_at_home | 8.325 | CFTC (repo COT) | free | weekly, current | unrevised | r<0.07, r<-0.10 wheat | **YES** in-repo | **NULL** (not identifiable) |
| R-CPI-NTR / R-CPI-ATR | shelter | 35.625 | bls.gov/pir/ntr | free | quarterly, ~3m stale; **PAUSED as of Apr-2026** | unrevised | 6-12m YoY | NONE | weak_candidate (blocked: pub paused) |
| Apartment List rent | shelter | 35.625 | apartmentlist.com | free | ~M-1 | non-govt, revised | 6-12m (undocumented vs CPI) | NONE | weak_candidate |
| CoreLogic/Cotality SFRI | shelter | 35.625 | press-release only | free-tier | M-2 | press only | 12m | NONE | not_free (no machine-readable series) |
| RealPage/CoStar rent | shelter | 35.625 | paid | paid | — | — | 12m | NONE | not_free |
| STR/CoStar hotel ADR | lodging_away | 1.289 | paid | paid | — | — | no documented lead | NONE | not_free |
| Manheim (full data file) | used_cars | 2.759 | Cox paid file | paid | — | — | — | NONE | not_free (headline is the free path) |
| JD Power / Cox / KBB new-veh transaction | new_vehicles | 3.838 | BLS-licensed | paid | IS the CPI source | — | zero lead | NONE | not_free |
| PCOTTINDUSDM (cotton) | apparel | 2.368 | FRED | free | M-1 | minimal revision | 6-12m raw-input lag, weakened | NONE | weak_candidate (too long-lag for T-1) |
| Kayak/Google airfare trends | airline_fares | 0.881 | free-tier | free-tier | real-time | unrevised | no documented CPI lead | NONE | **NULL** (not identifiable vs SABRE frame) |
| State DOI / NAIC loss ratios | motor_veh_insurance | 2.754 | free-tier | free-tier | 6-12m AFTER | annual revision | 4-6q regime only | NONE | weak_candidate (not monthly) |
| APU000072620 (util nat gas) | utility_gas (NOT electricity) | 1.003 | FRED | free | WITH CPI | non-vintaged | wrong block | NONE | out-of-scope for electricity |
| Cleveland daily nowcast | headline/core (cross-check) | — | repo collector | free | daily, ahead of CPI | PIT-stored | no component breakdown | **YES** in-repo | weak_candidate (output cross-check, not input) |
| Kalshi CPI brackets | headline | — | repo collector | free | daily | PIT-stored | IS the aggregate nowcast | **YES** in-repo | weak_candidate (calibration, not input) |

## Per-component sections

### core_goods_pipeline (weight 19.176) — the heterogeneity problem
**Institutional practice:** Goldman/JPM/Bloomberg Economics/Cleveland Fed split this block; they do not model it as a single PPI aggregate. Used vehicles → Manheim MUVVI (wholesale→retail ~1m propagation); new vehicles → JD Power transaction data (which BLS now uses *directly* in CPI new-vehicles since Apr-2022, so any external new-veh proxy misses the incentive/rebate swing that drives monthly CPI moves) or Edmunds ATP+incentives as the free proxy; apparel → BLS import prices (~97% import share). The current PPIFIS/PPIFES lag-1 leg is PIT-clean (ALFRED-vintaged) but top-down: it masks intra-block dispersion (used cars -12% while medical commodities +0.5%).
**Playbook (T-1 for month M):** decompose into new_veh (3.838) / used (2.759) / apparel (2.368) / residual (10.211) and apply instrument-adjusted nowcasts to the first three, PPIFES lag-1 to the residual. Note two identification caveats: (i) the sub-weights are *top-level* CPI RI weights assumed to sit inside `commodities_less_food_and_energy` — new/used vehicles and apparel are genuine core commodities so this is approximately correct, but `household_furnishings_and_operations` (3.378, folded in the residual) includes *services* (operations), so the residual is not pure goods; (ii) Manheim/Edmunds/import-price legs are heterogeneous in latency — the month-M Manheim final is coincident, whereas import-price and PPI legs are M-1 (see red-team flags).
**Was June-2026 knowable ex-ante?** PARTIALLY. Used-car disinflation was visible in the June Manheim final (published July 8, +2.1% YoY but a *slower* pace — a decelerating wholesale market) available before the July 14 CPI print. Apparel softening was visible in M-1 (May) import prices. But medical commodities and the residual furnishings/recreation sub-blocks had no free forward read. So the core-goods leg of the ~0.26pp miss was PARTIALLY knowable — the vehicle+apparel ~47% of the block was instrumentable; the ~53% residual was not.

### core_services_ex_shelter / supercore (weight 25.118) — the largest blind spot
**Institutional practice:** SF Fed (2023) ties ~half of core services to labor slack, but the ECI→monthly-supercore-MoM coefficient is small (~0.1pp/1pp) — a quarterly regime anchor, not a monthly predictor. The three forecastability tiers are: (1) MECHANICALLY PREDICTABLE — health insurance April/October semiannual retained-earnings reset (verified: BLS switched annual→semiannual starting April-2024, 2-year smoothed MA; the reset date and rough sign are knowable months ahead); (2) DIRECTIONALLY FORECASTABLE WITH NOISE — airfares via jet fuel (weak R², tiny 0.881 weight), auto insurance via PPI at *regime* horizon only (6-18m lead, monthly-imprecise; the 2022-24 PPI-CPI wedge — PPI +6.5% vs CPI +20% — makes it look-ahead-hazardous as a level proxy); (3) ESSENTIALLY UNFORECASTABLE monthly — recreation, FAFH, other personal services.
**Playbook (T-1):** (STEP 1, highest value) if M is April/October, replace lag-1 with health-insurance-adjusted prior; (STEP 2) swap the lag-1 base from CUSR0000SASLE to Sticky/Median CPI lag-1 momentum (both vintage-tracked in-repo, R²~0.3-0.4 vs SASLE — a low-cost, in-repo, high-value upgrade); (STEP 3) small jet-fuel tilt (weight 0.1); (STEP 4) quarterly ECI regime drift; (STEP 5) auto-insurance regime flag.
**Was June-2026 knowable ex-ante?** MOSTLY NO. June is not an April/October reset month, so the highest-signal lever did not fire. The Sticky-CPI base swap would have helped only to the extent the volatile-component filter reduced overshoot — a modest, not decisive, improvement. The bulk of the supercore leg of the miss was broad, low-persistence disinflation across recreation/personal services that has no free forward instrument. Honest verdict: **no** for the supercore-noise component; a Sticky-CPI base and ECI regime tilt would have shaved, not caught, the turn.

### shelter (weight 35.625) — already best-instrumented
**Institutional practice:** Cleveland Fed (EC-202417), Zillow, Boston/SF Fed all confirm the ~12-month YoY lead of new-tenant/market-rent indices; the mechanism is lease-renewal inertia (~1.8%/month turnover). The current bridge wires ZORI at k=0.35 against CPI-shelter lag-1 over an M-12..M-6 window (verified in `engine/release_components_cpi.py`: `_ZORI_LAG_DAYS = 45`, window `range(6,13)`, divergence guard halves k at 3σ). This is PIT-safe and aligned with institutional practice.
**Playbook:** unchanged — the k=0.35 and window are defensible. Lodging-away (1.289) has no free proxy and stays prior_only. R-CPI-NTR is a future enhancement but is currently PAUSED (BLS suspended publication Apr-2026 after an Oct-2025 collection gap) — do NOT prereg a leg that depends on a suspended series.
**Note:** the shelter lane correctly reports ECIWAG/ECIALLCIV as vintage-tracked; the food_energy lane's claim that they are "not ALFRED-vintaged in repo" is WRONG (both are in `data/fred_vintage/vintages.parquet`). Use the shelter/supercore lane's PIT status.

### food_at_home (8.325) / food_away_from_home (5.373) / electricity (2.375)
**food_at_home:** WPU01 (wired) + WPU012 (in-repo, unwired) both have 1m-lead correlations (0.22 / 0.09) dominated by persistence (0.525); the 3m-lead of WPU012 (r=0.24) is the stronger structure but stale at T-1. Modest directional blend only.
**food_away_from_home:** two zero-collector-cost wins — CUSR0000SEFV (1-line FRED add) turns the block from a null-proxy into a real persistence read (block is ~70% labor-driven and highly sticky); CES7000000003 (AHE leisure/hospitality, releases ~10d before CPI) is the one genuine T-1 monthly labor signal for this block.
**electricity:** APU000072610 lag-1 persistence is correct and defensible; WPU0543 (r=0.215) is WORSE than persistence and DHHNGSP (r<0.12) is uninformative — regulatory rate-case lag decouples wholesale from retail. Both fail the identifiability test.


---

## Ranked prereg build candidates

These are the recommended *next* constructions, each needing its own frozen prereg + forward window. Ranked by weight x identifiability x (inverse) data cost.

| Priority | Component | Instrument(s) | Effort | Rationale |
|---|---|---|---|---|
| P1 | food_away_from_home | CUSR0000SEFV (CPI food-away, 1-line FRED add) + CES7000000003 (AHE leisure/hospitality, 1-line FRED add) | free-in-repo wire — both are single config.yml FRED lines, no new collector | 5.373 weight currently a hard null (prior_only, confidence 0.0). CUSR0000SEFV converts it to a real persistence read at zero collector cost; CES7000000003 releases ~10d before CPI giving a genuine T-1 monthly labor signal for a ~70%-labor-driven block. Highest weight-x-identifiability-per-effort in the whole inventory. |
| P1 | core_services_ex_shelter | STICKCPIM157SFRBATL / MEDCPIM158SFRBCLE lag-1 momentum base + April/October health-insurance reset calendar flag | free-in-repo wire for the Sticky-CPI base; new small collector (boolean flag + track CUSR0000SEMC sub-index) for the health-insurance leg | 25.118 weight, the single largest blind spot. Both Sticky/Median CPI series are already in data/fred/ AND vintage-tracked; swapping the lag-1 base from CUSR0000SASLE (which is broader than the block and biased) to Sticky-CPI momentum (R2 ~0.3-0.4) is a free in-repo upgrade. The health-insurance April/Oct reset is a mechanically-predictable, calendar-PIT-safe shock (BLS semiannual method verified). |
| P2 | core_goods_pipeline (apparel sub-block) | BLS Import Price IR400 (apparel/footwear/HH) lag-1, corroborated by IZ315 and WPU03 | new FRED collector for IR400/IZ315/WPU03 (not currently in data/fred/) | 2.368 apparel weight inside the 19.176 block; ~97% import share makes import prices the primary documented pass-through channel. M-1 import prices are a verified 1-month forward leg (import-M prints July 17, after CPI-M July 14). Free on FRED. |
| P2 | core_goods_pipeline (vehicles sub-blocks) | Manheim MUVVI monthly final (used) + Edmunds ATP/incentives (new) | new web-scraper collectors (coxautoinc.com insights, edmunds industry center); free-tier headline only | used (2.759) + new (3.838) = 6.597 of 19.176 (34%) currently absorbed into a top-down PPI aggregate with no vehicle-specific signal. Manheim month-M final is available ~1 week before CPI-M (additive same-month info, NOT a forward lead — see red-team). Free headline path exists. Downgraded from P1 to P2 because both require web scrapers and the lead is coincident not forward. |
| P3 | food_at_home | WPU012 (processed foods) blended into the existing WPU01 directional leg | free-in-repo wire | WPU012 is already in data/fred/ (in-repo, zero data cost) and has a stronger 3m-lead correlation (0.24) than WPU01 alone; blending is a marginal improvement over the existing directional signal, dominated by persistence at the 1m horizon usable at T-1. |


---

## Red-team / PIT caveats (MUST carry into any prereg)

The synthesis red-teamed its own lanes. Each flag below is a trap a future builder must not fall into:

1. MANHEIM LEAD MISLABEL (core_goods lane): the INSTRUMENTS block claims June Manheim gives 'a genuine 1-month forward lead on July CPI used-car component' — this compares month-M Manheim to month-M+1 CPI. Verified release chain (Cox July 8 for June final; BLS CPI July 14 for June) shows the month-M Manheim final is available ~1 week BEFORE CPI-M, i.e. COINCIDENT with the reference month it predicts, not forward. Its real value is that the current lag-1 proxy carries ZERO same-month information, so Manheim is additive — but any prereg must label it a coincident nowcast input, not a forward lead, or the lead claim is invalid.

2. MANHEIM MID-MONTH FLASH MISUSE (core_goods lane playbook): the playbook says 'if mid-month flash diverges strongly from M-1 final, weight the flash directionally.' Cox Automotive explicitly disclaims this: the mid-month MUVVI 'is not a flash estimate, and it is not meant to provide any directional estimate of what the full month number will be' and 'should not be compared to the official index reading.' Using the mid-month checkpoint as a directional signal contradicts the publisher's own methodology — drop this step from any prereg.

3. IMPORT-PRICE / PPI 'M' vs 'M-1' LEAK RISK: several INSTRUMENTS entries assert a '1-month forward' lead but the forward premise holds ONLY because Import-Price-M (July 17) and PPI-M (July 15) print AFTER CPI-M (July 14), so only M-1 is knowable at T-1. Any collector that pulls the M reading (available days later) into a backtest as-if-known-at-T-1 would be look-ahead. Prereg must fence these to M-1 explicitly and treat non-vintaged FRED pulls as revision_optimistic (they are revised up to 3 months post-print).

4. AUTO-INSURANCE PPI LEVEL LOOK-AHEAD (supercore lane): PCU5241265241261 is flagged as a monthly signal in some framing but the lane's own PIT note says the PPI-CPI wedge is regime-dependent (2022-24: PPI +6.5% vs CPI +20%+). Using PPI auto-insurance as a monthly LEVEL proxy imports a regime-specific bias; it is only defensible as a 6-18m directional REGIME flag. Prereg must not treat it as a monthly-precision leg.

5. ECI VINTAGE-STATUS CONTRADICTION (food_energy lane vs shelter/supercore lanes): food_energy lane states ECIWAG/ECIALLCIV are 'Not ALFRED-vintaged in repo.' This is FALSE — both appear in data/fred_vintage/vintages.parquet (verified). The shelter and supercore lanes correctly report them as vintage-tracked. A prereg that inherited the food_energy lane's claim would wrongly declare an ECI leg revision_optimistic when it is in fact PIT-clean.



---

## Null findings (closed search directions — retained as context)

Per house law these are findings, not failures: they close a specific construction, not the search space, and stay as confluence context.

- WPU0543 (PPI electric power) → energy_electricity: 1-month-lead r=0.215 is WORSE than the APU lag-1 persistence baseline r=0.239; strong contemporaneous r=0.648 collapses at any lead and goes negative (r=-0.21) at 3-5m from utility rate-case mean-reversion. Fails the identifiability test — regulatory rate-setting lag decouples wholesale cost from retail price. In-repo but not worth wiring. Closes the 'wholesale electricity as a retail-CPI lead' search direction.
- DHHNGSP (Henry Hub) → energy_electricity: r<0.12 at all leads 0-6 despite nat-gas being ~42% of generation; regulated rate pass-through kills the signal. Not identifiable for short-horizon electricity CPI.
- COT ag positioning (corn/wheat/soybeans/cattle) → food_at_home: r<0.07 (corn/soy/cattle), r<-0.10 (wheat) across 0-4m leads. Positioning != price level, and even farm spot prices have small pass-through (KC Fed RWP24-16: farm commodities ~15c of the food dollar). In-repo but bridge-irrelevant; closes the 'commodity positioning as food-CPI lead' direction.
- Kayak/Google airfare trends → airline_fares: no documented quantitative lead-lag vs CPI airfares; measures demand-side listing prices, not the SABRE-sampled fares BLS collects (fares departing within 90 days). Not identifiable without bespoke regression; and airline_fares is only 0.881 weight so even a perfect call moves headline ~0.026pp.
- CoreLogic/Cotality SFRI, RealPage/CoStar, STR hotel ADR, Manheim full data file, JD Power/Cox new-vehicle transaction DB: all NOT-FREE (press-release-only or paid license). The free paths (ZORI for shelter, Manheim/Edmunds headline for vehicles) already cover the identifiable signal; the paid versions are not required. STR is correctly the reason lodging_away (1.289) stays prior_only.
- R-CPI-NTR / R-CPI-ATR → shelter: genuinely leading (6-12m YoY, used by Cleveland Fed model) but BLS PAUSED publication as of April 2026 (Oct-2025 collection gap). Not available ex-ante for any 2026 prereg — do not build a leg dependent on a suspended series; ZORI already captures the same economic signal monthly.
- PCOTTINDUSDM (cotton) → apparel: 6-12m raw-input pipeline lag, not a T-1 nowcast signal; cotton channel weakened since 2000 as synthetics dominate. Not identifiable at monthly horizon.
- Medical care commodities/services, recreation, other personal services, lodging-away, alcoholic beverages: no free instrument with a documented monthly lead. These are the honest residual — persistence with wide error bars; the supercore-noise component of the June-2026 miss was structurally NOT knowable ex-ante from any free instrument in the inventory.


---

## What this guide does NOT claim

- No instrument here is gauntlet-passed or promotion-eligible. Verdicts are candidate
  rankings for a future prereg, judged on the forward ledger only.
- The June-2026 miss was PARTIALLY knowable (used-vehicle + apparel legs, ~47% of core
  goods) and MOSTLY NOT knowable for the supercore-services noise component. No inventory
  instrument would have fully caught the turn; the honest expected gain is "shave, not catch."
- Shelter is already the best-instrumented block (ZORI wired at k=0.35); this guide does
  NOT recommend re-opening it. The free new-tenant-rent alternative (BLS R-CPI-NTR) is
  suspended by BLS as of April-2026 and cannot be built on.

## Provenance

Research lanes (sonnet) + adversarial synthesis (opus), wf_cb44b900-a41, 2026-07-14. Every
instrument claim is sourced to a BLS/FRED/EIA/publisher citation in the lane transcripts.
Contradictions between lanes were adjudicated in synthesis (notably the ECI vintage-status
question: ECIWAG/ECIALLCIV ARE ALFRED-vintaged in data/fred_vintage/vintages.parquet — the
shelter/supercore lanes were correct, the food_energy lane was wrong).
