# Results — CPI Component Bridge V1 (Track CB, MRI-R25)

**Run date:** 2026-07-10
**Spec:** research/release_forecast/PREREG_CPI_BRIDGE_V1.md (frozen 2026-07-08)
**Ruling:** MRI-R25

---

## Weight Coverage

Share of CPI basket backed by modelled (non-prior) blocks:
- Headline: **83.9%** of basket
- Core: **70.3%** of basket

Note: weight_coverage_pct can exceed 100% because core_services_ex_shelter
weight (44.3) overlaps with core_goods (19.2) — both applied to same broad basket.
The 5 modelled blocks cover blocks with direct HF proxies; other blocks are prior-only.

### Which blocks had live proxies vs fell to prior:
| Block | Proxy | Status |
|---|---|---|
| energy_gasoline | GASREGW (EIA weekly, unrevised) | LIVE — data present 1990+ |
| energy_electricity | APU000072610 (BLS avg price) | LIVE — data present 1978+ |
| shelter | ZORI + CUSR0000SAH1 | LIVE — ZORI from ~2015; falls to CPI shelter prior before |
| food_at_home | WPU01 (farm PPI) + CUSR0000SAF11 | LIVE — both present 1913+ / 1952+ |
| core_goods_pipeline | PPIFIS + PPIFES (ALFRED-vintaged) | LIVE — from 2014-03 only; PRIOR before that |
| core_services_ex_shelter | CUSR0000SASLE (persistence) | LIVE — data present 1967+ |

---

## Headline Results

- Bridge walk-forward steps: 352
- Champion walk-forward steps: 292
- Aligned (both have result): 292


### cpi_headline — era metrics

| Era | N | MAE bridge | MAE naive | MAE champ | MAE trail3m | MAE ExpandMean* |
|---|---|---|---|---|---|---|
| full | 282 | 0.1542 | 0.2591 | 0.1593 | 0.2563 | 0.2293 |
| pre_2010 | 96 | 0.1654 | 0.3340 | 0.1415 | 0.3408 | 0.2753 |
| 2010_2020 | 122 | 0.1318 | 0.2081 | 0.1659 | 0.2072 | 0.1817 |
| 2021_plus | 64 | 0.1799 | 0.2442 | 0.1732 | 0.2233 | 0.2516 |
| covid_separate | 4 | 0.2098 | 0.5611 | 0.2479 | 0.6513 | 0.5459 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Strongest naive = min(MAE naive, MAE trail3m, MAE ExpandMean).

### Kill Rule — cpi_headline
- Bridge MAE (full): 0.1542 vs naive: 0.2591 → kill_full=False
- Bridge MAE (2021+): 0.1799 vs naive: 0.2442 → kill_2021=False
- **Kill rule triggered: False**
- **Verdict: SHADOW-ELIGIBLE — bridge beats naive in at least one required slice.**

### Vs Strongest Naive — cpi_headline (REPORTED, MRI-R28b)
- Full: bridge MAE=0.1542 vs strongest_naive=0.2293 — margin=0.0751 (BEATS)
- 2021+: bridge MAE=0.1799 vs strongest_naive=0.2233 — margin=0.0435 (BEATS)

---

## Core Results

- Bridge walk-forward steps: 352
- Champion walk-forward steps: 292
- Aligned: 292


### cpi_core — era metrics

| Era | N | MAE bridge | MAE naive | MAE champ | MAE trail3m | MAE ExpandMean* |
|---|---|---|---|---|---|---|
| full | 282 | 0.0971 | 0.0931 | 0.0910 | 0.0925 | 0.0957 |
| pre_2010 | 96 | 0.0955 | 0.0935 | 0.0832 | 0.0866 | 0.0780 |
| 2010_2020 | 122 | 0.0747 | 0.0735 | 0.0721 | 0.0722 | 0.0640 |
| 2021_plus | 64 | 0.1422 | 0.1297 | 0.1386 | 0.1401 | 0.1823 |
| covid_separate | 4 | 0.2851 | 0.3383 | 0.2247 | 0.3323 | 0.2913 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Strongest naive = min(MAE naive, MAE trail3m, MAE ExpandMean).

### Kill Rule — cpi_core
- Bridge MAE (full): 0.0971 vs naive: 0.0931 → kill_full=True
- Bridge MAE (2021+): 0.1422 vs naive: 0.1297 → kill_2021=True
- **Kill rule triggered: True**
- **Verdict: NULL — kill rule triggered (MAE >= naive in BOTH full AND 2021+). NOT SHADOWED.**

### Vs Strongest Naive — cpi_core (REPORTED, MRI-R28b)
- Full: bridge MAE=0.0971 vs strongest_naive=0.0925 — margin=-0.0046 (LAGS)
- 2021+: bridge MAE=0.1422 vs strongest_naive=0.1297 — margin=-0.0125 (LAGS)

---

## Caveats and Known Gaps

1. **Weight overlap:** core_goods_pipeline (RI weight 19.2) and core_services_ex_shelter
   (RI weight 44.3) cover overlapping CPI baskets. The bridge sums their contributions
   additively — this double-counts the core goods universe. The residual_pp is 0 by
   construction but the headline estimate may be biased. This is a known design gap.

2. **Core goods pipeline gap pre-2014:** PPIFIS/PPIFES only available from 2014-03 in
   ALFRED vintages. Before 2014-03, the core_goods_pipeline block falls to prior_only.
   This structural break hurts pre-2014 metrics.

3. **Food-at-home signal quality:** WPU01 (farm products PPI) is a coarse proxy for
   food-at-home CPI. The directional signal (threshold 1.0pp, scale 0.2) is conservative.
   This block is intentionally weak (confidence=0.4).

4. **Non-ALFRED-vintaged series:** APU000072610, CUSR0000SAF11, WPU01, CUSR0000SASLE,
   CUSR0000SAH1, ZORI all declared revision_optimistic. The backtest uses latest-revised
   values — in real-time these may have differed. This is a look-ahead bias for those blocks.

5. **CSXS series definition mismatch:** CUSR0000SASLE is 'all items less food, energy,
   shelter' (a broad aggregate including both goods and services). Using it as persistence
   for 'core services ex-shelter' introduces scope mismatch.

6. **Bridge has no confidence intervals:** The bridge produces a point estimate only.
   No quantile distribution is computed (unlike the champion ridge which has empirical
   residual quantiles). This limits its usefulness for surprise characterization.

---

## Shadow Eligibility

**cpi_headline:** SHADOW-ELIGIBLE — bridge beats naive in at least one required slice.
**cpi_core:** NULL — kill rule triggered (MAE >= naive in BOTH full AND 2021+). NOT SHADOWED.

Per MRI-R25: A track failing the kill rule is NOT shadowed.
The champion (frozen v2 ridge) keeps the card regardless.
If shadow-eligible, nightly rows tagged `cpi_bridge` accrue for forward scoring.

---

## §12 Restatement (2026-07-10, MRI-R28/R29/F7)

**MRI-R29 (bridge claim VOIDED):** The previous 'edges champion' verdict for this
backtest is VOIDED as a promotion argument per MRI-R29. The bridge reads latest-revised
sub-index parquets (audit F2), making its apparent edge revision-optimistic — this is
not a real-time advantage. Forward-ledger evidence is the only valid promotion basis.

**expanding_mean benchmark** added to era tables above (REPORTED, non-binding per MRI-R28b).
Bridge verdicts (kill rule, shadow eligibility) stand unchanged — they were not
predicated on the 'edges champion' margin that MRI-R29 voids.

**F7 fix:** This file is fully regenerated from current code (stale-numbers problem fixed).
Run date above reflects actual regeneration date.