# BTC Re-Entry Trigger Evaluation — Override-Registry W4

**Generated:** 2026-07-01  
**Program:** Engine-Fix Masterplan W1-RESEARCH → fire-conditional re-entry triggers  
**Signal frame:** 2014-09-17 → 2026-07-01 (4,306 daily bars, 194 columns)  
**Evaluation script:** `research/entry_timing/btc_trigger_eval.py`

---

## PRE-REGISTERED QUALIFYING BAR

*Stated here, before any results, and cannot be moved post-hoc.*

A trigger **qualifies** for W4 tranche duty if ALL three conditions hold:

| Criterion | Threshold |
|---|---|
| hit_rate_180d | >= 70% |
| % of fires with 90d MAE worse than -25% | <= 30% |
| n independent fires | >= 4 |

---

## Triggers Evaluated

| Label | Definition |
|---|---|
| **(a) MVRV-Z cross<0** | First day `mvrv_z` < 0 after >= 90 consecutive days where `mvrv_z >= 0` |
| **(b) 20w-MA reclaim** | Weekly close (completed week, shift-1 non-repainting) crosses above 20-week SMA after >= 60 calendar days below |
| **(c) BP>=0.45** | `bottom_pressure` first crosses >= 0.45 after >= 20 consecutive days below |
| **(c) BP>=0.60** | Same as above but with >= 0.60 threshold |
| **(d1) (a) AND (c@0.45)** | Both (a) and (c@0.45) fire within a 60-day window; fire date = the later of the two |
| **(d2) (a) THEN (b) 120d** | MVRV-Z (a) fires first, then within 120 days the 20w-MA reclaim (b) fires; recorded at the (b) date |

---

## Summary Table

| Trigger | n | indep | hit90 | hit180 | hit365 | med180 | MAE<-15% | MAE<-25% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| (a) MVRV-Z cross<0    |  3 |  3 | 33% |  67% | 100% |  +53% | 67% | 33% |
| (b) 20w-MA reclaim    | 10 |  9 | 44% |  56% |  78% |  +13% | 60% | 40% |
| (c) BP>=0.45          | 41 | 18 | 60% |  64% |  76% |  +19% | 51% | 29% |
| (c) BP>=0.60          | 35 | 16 | 61% |  59% |  65% |  +24% | 46% | 29% |
| (d1) (a) AND (c@0.45) |  3 |  3 | 33% |  67% | 100% |  +53% | 67% | 33% |
| (d2) (a) THEN (b) 120d|  0 |  0 | N/A |  N/A |  N/A |  N/A  | N/A | N/A |

*n = total fires; indep = fires > 180d apart from prior fire (honest denominator); med180 = median 180d forward return.*

---

## Per-Trigger Detail

### (a) MVRV-Z First Cross Below 0 (after >=90d above)

**Fire dates (3 total, 3 independent):** 2018-11-19, 2020-03-12, 2022-06-13

| Horizon | Median | Mean | Hit-rate |
|---|---:|---:|---:|
| +90d  |  -2.8% |  +25.8% | 33% |
| +180d | +53.4% |  +46.1% | 67% |
| +365d | +71.6% | +388.4% | 100% |

**MAE (90d):** median -16.3%, 67% of fires worse than -15%, 33% worse than -25%

**Bear-phase fires (all 3 were in bear regimes):**  
- Median days to cycle bottom: 26 days  
- Median % below fire price at bottom: -29.8%

*Interpretation:* Each fire to date was near a major bear-market turning point; the 100% 365d hit-rate and +71.6% median are compelling, but 2020-03-12 was the COVID crash floor (+3,200% over 365d) and inflates the mean dramatically. The 90d median is -2.8% — i.e., you are often still drawingdown through 90d post-fire. The n=3 sample is insufficient to evaluate statistically.

---

### (b) 20-Week MA Reclaim (after >=60d below, non-repainting)

**Fire dates (10 total, 9 independent):**  
2014-12-05, 2015-06-26, 2018-08-03, 2019-03-29, 2020-01-24, 2021-08-20, 2022-04-08, 2022-11-11, 2023-01-20, 2026-05-08

| Horizon | Median | Mean | Hit-rate |
|---|---:|---:|---:|
| +90d  |  -3.4% | +15.1% | 44% |
| +180d | +13.2% | +15.4% | 56% |
| +365d | +52.8% | +74.5% | 78% |

**MAE (90d):** median -17.3%, 60% of fires worse than -15%, 40% worse than -25%

**Bear-phase fires:** 1 fire in bear regime; median 10d to bottom, -7.4% below fire price

*Note:* The 20w-MA reclaim was previously OOS-validated cross-cycle in the BTC MTF work (see `research/BTC_VECTOR_FIX_MASTERPLAN.md`). The n=10 / 9 independent gives meaningful sample power, but the 56% hit-rate at 180d is below the 70% bar, and the 40% MAE>-25% rate exceeds the 30% ceiling. The 2022-04-08 and 2022-11-11 fires were both in the extended bear market — the April fire in particular was a false reclaim before the LUNA/3AC/FTX cascade.

---

### (c) bottom_pressure >= 0.45 (after >=20d below)

**Fire dates (41 total, 18 independent):**  
2014-12-16, 2015-04-13, 2015-08-18, 2015-11-11, 2016-01-15, 2016-08-02, 2017-01-11, 2017-03-17, 2017-07-11, 2017-09-13, 2017-12-22, 2018-03-08, 2018-05-23, 2018-08-08, 2018-11-16, 2019-07-14, 2019-08-29, 2019-09-23, 2019-11-19, 2020-02-26, 2020-09-04, 2021-01-21, 2021-04-21, 2021-09-20, 2021-11-18, 2022-04-14, 2022-08-22, 2022-11-09, 2023-03-08, 2023-08-18, 2024-01-22, 2024-04-17, 2024-06-17, 2024-08-05, 2024-09-05, 2025-02-25, 2025-04-08, 2025-08-31, 2025-10-16, 2026-01-30, 2026-06-01

| Horizon | Median | Mean | Hit-rate |
|---|---:|---:|---:|
| +90d  | +13.8% | +24.4% | 60% |
| +180d | +19.1% | +54.7% | 64% |
| +365d | +68.2% | +139.1% | 76% |

**MAE (90d):** median -15.7%, 51% of fires worse than -15%, **29% worse than -25%**

**Bear-phase fires (10):**  
- Median days to cycle bottom: 102 days  
- Median % below fire price at bottom: -35.3%

*Note:* MAE<-25% at 29% *marginally* clears the 30% ceiling, but hit_rate_180d at 64% is below 70%. The high total fire count (41) reflects frequent re-firing during volatile periods; 18 independent episodes is the meaningful denominator. The 365d hit-rate of 76% is encouraging but the 180d bar is the binding constraint.

---

### (c) bottom_pressure >= 0.60 (after >=20d below)

**Fire dates (35 total, 16 independent):**  
2015-01-04, 2015-08-18, 2016-01-15, 2016-08-02, 2017-01-11, 2017-03-18, 2017-07-14, 2017-09-13, 2018-01-11, 2018-03-10, 2018-05-23, 2018-08-12, 2018-11-19, 2019-07-16, 2019-08-29, 2019-09-24, 2019-11-23, 2020-02-27, 2021-01-21, 2021-04-22, 2021-07-16, 2021-09-21, 2021-12-04, 2022-05-07, 2022-06-12, 2022-11-09, 2024-04-17, 2024-06-24, 2024-09-06, 2025-02-26, 2025-04-08, 2025-11-14, 2026-02-01, 2026-06-03, 2026-06-28

| Horizon | Median | Mean | Hit-rate |
|---|---:|---:|---:|
| +90d  |  +5.5% | +28.6% | 61% |
| +180d | +24.0% | +47.0% | 59% |
| +365d | +38.6% | +132.7% | 65% |

**MAE (90d):** median -10.5%, 46% of fires worse than -15%, **29% worse than -25%**

**Bear-phase fires (13):**  
- Median days to cycle bottom: 125 days  
- Median % below fire price at bottom: -33.7%

*Note:* The higher threshold (0.60) tightens the MAE distribution (median -10.5% vs -15.7% for 0.45) but doesn't improve hit-rates — likely because the 0.60 threshold fires more often during counter-trend bounces inside downtrends. The median is lower and the 365d hit-rate drops to 65%.

---

### (d1) (a) AND (c@0.45) Combo within 60 days

**Fire dates (3 total, 3 independent):** 2018-11-19, 2020-03-12, 2022-06-13  
*(These are identical to the (a) fire dates — in all observed cases, BP>=0.45 co-occurred within 60d of the MVRV-Z cross)*

| Horizon | Median | Mean | Hit-rate |
|---|---:|---:|---:|
| +90d  |  -2.8% |  +25.8% | 33% |
| +180d | +53.4% |  +46.1% | 67% |
| +365d | +71.6% | +388.4% | 100% |

**MAE (90d):** median -16.3%, 67% of fires worse than -15%, 33% worse than -25%

*Note:* The combo fires collapsed to the same three dates as (a). Adding the BP>=0.45 co-requirement did not filter out any fires — it was met every time MVRV-Z fired. This trigger has no additive filtering power over (a) alone given current history.

---

### (d2) (a) THEN (b) within 120 days

**Fire dates: 0 (zero fires)**

The MVRV-Z signal (a) has fired 3 times. The 20w-MA reclaim (b) has never fired within 120 days *after* an MVRV-Z cross below 0 — the reclaims occurred outside the 120d window or before the MVRV-Z event. This combination produced zero fires in 11 years of history, making it untestable and irrelevant for W4 consideration.

---

## Verdict Table

| Trigger | hit_rate_180d | MAE>-25% | n indep | VERDICT |
|---|---:|---:|---:|---|
| (a) MVRV-Z cross<0     | 67% | 33% | 3 | **DOES NOT QUALIFY** — fails all three bars |
| (b) 20w-MA reclaim     | 56% | 40% | 9 | **DOES NOT QUALIFY** — hit-rate and MAE both fail |
| (c) BP>=0.45           | 64% | 29% | 18| **DOES NOT QUALIFY** — hit-rate 64% < 70% |
| (c) BP>=0.60           | 59% | 29% | 16| **DOES NOT QUALIFY** — hit-rate 59% < 70% |
| (d1) (a) AND (c@0.45)  | 67% | 33% | 3 | **DOES NOT QUALIFY** — fails all three bars |
| (d2) (a) THEN (b) 120d | N/A | N/A | 0 | **DOES NOT QUALIFY** — zero fires in history |

**All six triggers fail the pre-registered qualifying bar. None qualifies for W4 tranche duty.**

---

## What W4 Must Know

### Closest to qualifying: (c) BP>=0.45

- Fails only on hit_rate_180d (64% vs 70% bar), not on MAE criterion (29% < 30%)
- n=18 independent episodes is the largest available sample
- **The MAE margin is razor-thin**: 29% falls just inside the 30% ceiling; one additional bad fire moves it over
- ~16 hand-set DOF in the composite means any in-sample near-qualification should be treated as hypothesis only

### Structural problem: no trigger cleared 70% hit-rate at 180d

The best 180d hit-rate observed (a) and (d1) at 67% is driven by a 3-fire sample including the anomalous 2020-03-12 COVID bottom. The 20w-MA reclaim (b) — previously OOS-validated — hits only 56% at 180d because 2022 produced two bear-market reclaim false-alarms (April and November) that dragged down the rate.

### (d2) structural issue

No historical MVRV-Z cross has been followed within 120 days by a 20w-MA reclaim. The sequence order in the current market structure does not support this trigger combination.

### Suggested W4 posture

Given no trigger qualifies:
1. **Do not use any single trigger as an automatic tranche gate**
2. **Use (a) + (c@0.45) confluence as a soft-alert**: all 3 historical joint fires occurred at genuine cycle lows; the issue is n=3 not quality
3. **Re-evaluate (b) 20w-MA reclaim cross-cycle**: the 9 independent episodes give real power; the disqualifying factor is the two 2022 bear-market false-alarms. A gating rule (e.g., require (a) to have fired within 180d prior) would have filtered both false-alarms — worth pre-registering as a W5 hypothesis
4. **Track (c) BP>=0.45 real-time**: with 41 total fires it has the most live history; the 64% hit-rate falls short but the -19.1% median 180d return is real

---

## Caveats

1. **bottom_pressure DOF**: The composite uses approximately 16 hand-set parameters (~8 scoring conditions with individual weights and thresholds). These were calibrated using visual inspection of known BTC cycle lows. Any qualification of (c) or (d1) is in-sample by construction and should be treated as hypothesis-generating, not a validated edge.

2. **Overlapping windows**: The "n" column in the summary table shows total fires, many of which have overlapping 90/180/365d forward windows. The "indep" column (fires > 180d apart) is the honest denominator for forward-return statistics. The hit-rates and medians are computed over all fires (which inflates N but uses overlapping data).

3. **MVRV-Z effective N**: The underlying rolling-window z-score uses overlapping data even though the 90d above-streak cooldown prevents daily re-fires. Effective information content is less than the 3 fire dates suggest.

4. **Small-sample warning**: n=3–18 for all triggers. Any result is statistically fragile. Two or three unusual events (COVID crash, LUNA collapse) dominate the mean returns. Do not over-fit post-hoc explanations to individual fire outcomes.

5. **20w-MA non-repainting implementation**: The weekly reclaim trigger uses `shift(1)` on the weekly series (completed weeks only) and maps back to the nearest daily date. In real-time implementation, the reclaim is only confirrmed at the weekly close — the mapping adds up to 5 calendar days of latency vs the daily date shown here.

6. **MVRV-Z data coverage**: On-chain MVRV-Z data in the signal frame begins 2015-09-16 (258 null rows at start). The 2015 bear cycle lows are not covered by this trigger, reducing the available cycle history by one complete bear market.

---

*Report generated by `research/entry_timing/btc_trigger_eval.py` — run results are deterministic given the signals.parquet frame.*
