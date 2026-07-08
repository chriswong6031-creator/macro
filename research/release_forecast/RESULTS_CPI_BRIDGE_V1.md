# Results — CPI Component Bridge V1 (Track CB, MRI-R25)

**Run date:** 2026-07-08
**Spec:** research/release_forecast/PREREG_CPI_BRIDGE_V1.md (frozen 2026-07-08)
**Ruling:** MRI-R25 (research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md §11)

---

## Weight Coverage

Share of CPI basket backed by modelled (non-prior) blocks:
- **Headline: 103.1%** (exceeds 100% due to core_goods / core_services_ex_shelter overlap)
- **Core: 97.8%** (no energy blocks, otherwise same overlap)

Note: weight_coverage_pct > 100% is an artefact of the double-counting gap documented in
PREREG_CPI_BRIDGE_V1.md §3.5. The bridge's core_goods_pipeline (RI weight 19.2) and
core_services_ex_shelter (RI weight 44.3) both apply to overlapping CPI baskets. This is a
known structural limitation — see Caveats section below.

### Which blocks had live proxies vs fell to prior:

| Block | Proxy | Status |
|---|---|---|
| energy_gasoline | GASREGW (EIA weekly, unrevised) | LIVE — data present 1990+ |
| energy_electricity | APU000072610 (BLS avg price) | LIVE — data present 1978+ |
| shelter | ZORI + CUSR0000SAH1 | LIVE — ZORI from ~2015; falls to CPI shelter prior before |
| food_at_home | WPU01 (farm PPI) + CUSR0000SAF11 | LIVE — both present 1913+/1952+ |
| core_goods_pipeline | PPIFIS + PPIFES (ALFRED-vintaged) | LIVE from 2014-03 only; PRIOR before that |
| core_services_ex_shelter | CUSR0000SASLE (persistence) | LIVE — data present 1967+ |

All other blocks (food away, vehicles, airfare, lodging, medical, apparel, recreation,
education, insurance, other) = PRIOR-ONLY, confidence = 0.0. No free PIT proxies available.

---

## Headline Results (cpi_headline)

- Bridge walk-forward steps: 352
- Champion walk-forward steps: 292
- Aligned (both have result): 292

### cpi_headline — era metrics (MAE in percentage-points MoM)

| Era | N | MAE bridge | MAE naive | MAE champion | MAE trailing3m |
|---|---|---|---|---|---|
| full | 282 | **0.1639** | 0.2591 | 0.1593 | 0.2563 |
| pre_2010 | 96 | 0.1760 | 0.3340 | 0.1415 | 0.3408 |
| 2010_2020 | 122 | **0.1373** | 0.2081 | 0.1659 | 0.2072 |
| 2021_plus | 64 | **0.1962** | 0.2442 | 0.1732 | 0.2233 |
| covid_separate | 4 | 0.2285 | 0.5611 | 0.2479 | 0.6513 |

COVID rows excluded from kill-rule era stats (shown separately per spec).

### Kill Rule — cpi_headline

- Bridge MAE (full): 0.1639 vs naive: 0.2591 → kill_full=**False** (bridge beats naive)
- Bridge MAE (2021+): 0.1962 vs naive: 0.2442 → kill_2021=**False** (bridge beats naive)
- **Kill rule triggered: False**
- **Verdict: SHADOW-ELIGIBLE — bridge beats naive in at least one required slice.**

---

## Core Results (cpi_core)

- Bridge walk-forward steps: 352
- Champion walk-forward steps: 292
- Aligned: 292

### cpi_core — era metrics (MAE in percentage-points MoM)

| Era | N | MAE bridge | MAE naive | MAE champion | MAE trailing3m |
|---|---|---|---|---|---|
| full | 282 | 0.1117 | **0.0931** | 0.0910 | 0.0925 |
| pre_2010 | 96 | 0.1105 | **0.0935** | 0.0832 | 0.0866 |
| 2010_2020 | 122 | 0.0846 | **0.0735** | 0.0721 | 0.0722 |
| 2021_plus | 64 | 0.1652 | **0.1297** | 0.1386 | 0.1401 |
| covid_separate | 4 | 0.2598 | 0.3383 | 0.2247 | 0.3323 |

### Kill Rule — cpi_core

- Bridge MAE (full): 0.1117 vs naive: 0.0931 → kill_full=**True** (bridge worse than naive)
- Bridge MAE (2021+): 0.1652 vs naive: 0.1297 → kill_2021=**True** (bridge worse than naive)
- **Kill rule triggered: True**
- **Verdict: NULL — kill rule triggered (MAE >= naive in BOTH full AND 2021+). NOT SHADOWED.**

---

## Summary

| Target | MAE Bridge | MAE Naive | MAE Champion | Kill | Verdict |
|---|---|---|---|---|---|
| cpi_headline | 0.1639 (full) | 0.2591 | 0.1593 | False | SHADOW-ELIGIBLE |
| cpi_core | 0.1117 (full) | 0.0931 | 0.0910 | True | NULL |

**cpi_headline:** Bridge outperforms naive by 0.0952 pp MAE (full) and 0.0480 pp (2021+).
Trails champion by 0.0046 pp (full) — the bridge is competitive with the ridge on headline.
The bridge's energy and shelter blocks carry real signal, particularly in the pre-COVID era.

**cpi_core:** Bridge underperforms naive by 0.0186 pp (full) and 0.0355 pp (2021+). The
core bridge's weight overlap (core_goods + core_services_ex_shelter double-counting) and
the persistence-only core_services_ex_shelter leg add noise without improving accuracy.

---

## Caveats and Known Gaps

1. **Weight overlap:** core_goods_pipeline (RI weight 19.2) and core_services_ex_shelter
   (RI weight 44.3) cover overlapping CPI baskets. The bridge sums their contributions
   additively — this double-counts the core goods universe. The residual_pp is 0 by
   construction but the headline estimate may be biased. This is a known design gap
   declared in PREREG_CPI_BRIDGE_V1.md §3.5.

2. **Core goods pipeline gap pre-2014:** PPIFIS/PPIFES only available from 2014-03 in
   ALFRED vintages. Before 2014-03, the core_goods_pipeline block falls to prior_only.
   This structural break hurts pre-2014 metrics.

3. **Food-at-home signal quality:** WPU01 (farm products PPI) is a coarse proxy for
   food-at-home CPI. The directional signal (threshold 1.0pp, scale 0.2) is conservative.
   This block is intentionally weak (confidence=0.4).

4. **Non-ALFRED-vintaged series:** APU000072610, CUSR0000SAF11, WPU01, CUSR0000SASLE,
   CUSR0000SAH1, ZORI all declared revision_optimistic. The backtest uses latest-revised
   values — in real-time these may have differed slightly. This is a mild look-ahead bias.

5. **CSXS series definition mismatch:** CUSR0000SASLE is 'all items less food, energy,
   shelter' (broad aggregate including both goods and services). Using it as persistence
   for 'core services ex-shelter' introduces scope mismatch.

6. **Bridge has no confidence intervals:** Point estimate only. Unlike the champion ridge
   which has empirical residual quantiles (p10/p25/p50/p75/p90), the bridge produces no
   distributional estimate.

---

## Shadow Eligibility

**cpi_headline: SHADOW-ELIGIBLE** — nightly rows tagged `model='cpi_bridge'` accrue for
forward scoring. Champion card unchanged. Promotion to card requires new adjudication citing
forward evidence (C-9-class) per MRI-R25.

**cpi_core: NULL** — bridge fails the kill rule (MAE worse than naive in both full and 2021+
slices). NOT shadowed. Second attempt requires new adjudication.

Per MRI-R25: "No weight/feature/block iteration post-results." This is attempt 1 of max 2.
