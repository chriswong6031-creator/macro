# W2 S-LQ Liquidity Hygiene Band Study — Entry-Stack Expansion

**Status:** W2 study report only — no promotion decision (RUL-3).
**Date:** 2026-07-05
**Family:** esx_lq_bands (budget=12 — pre-registered at W0).

## Study Design

**Lane:** S-LQ (§3 F4). HYGIENE STUDY.
**Horizon doctrine (RUL-13):** 21d primaries. 63d+ NOT used for entry verdicts.

**Proxies:**
- Amihud ILLIQ: |ret| / (close × volume), smoothed 20d rolling mean (all panels).
- Corwin-Schultz HL-spread: two-day HL estimator (panels with H/L).

**Band rule (FIXED, NEVER FITTED):** Cross-sectional terciles on trailing 252-bar (1-year) proxy values at each fire date.
- Band 0 = top third of proxy values = worst liquidity (least liquid / widest spread).
- Band 1 = middle third.
- Band 2 = bottom third of proxy values = best liquidity.

**Deterioration metric (fixed window = 20 bars):** Sign of 20d slope of proxy series at fire date. +1 = deteriorating (proxy rising), -1 = improving.

**Adjacency (R2 per RUL-2):** None. Census: zero EOD spread proxies repo-wide prior to W0 (masterplan §3 F4). No falsified relative.

**Hygiene bar (§5 pre-registered):**
- Clause A: CI-excluding-0 degradation on stop5 (CI_lo > 0) OR fwd_mdd_21 (CI_hi < 0) for the worst band (band 0).
- Clause B: Affected volume of worst band <= 10% of fires.

**Sign convention:**
- stop5 is ADVERSE. CI_lo > 0 means significantly MORE stops (degradation).
- fwd_mdd_21 values are <=0. CI_hi < 0 means more-negative MDD (degradation).
- zone_held_21 is BENEFICIAL. CI_lo > 0 means better zone-holding (improvement).

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only. Comparisons within-era are directionally valid.

## NC Yardstick (RUL-3 mandatory preamble)

**Source: W1-NC artifact** (`research/entry_stack/W1_NC_REPORT.md`).
Numbers below are parsed from that file at runtime — NOT hardcoded.
Per masterplan §10 RUL-3: null-competitors appear as the first table.
Direction note: stop5 is ADVERSE — a BETTER signal has a MORE NEGATIVE coefficient. Degradation (hygiene bar) = CI_lo > 0 (significantly more stops).

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |
|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | -0.0019 | [-0.016, +0.008] | no | 89.1% |
| deep | NC-1B (ticks=0) | 0.0001 | [-0.015, +0.007] | no | 90.8% |
| deep | NC-2 (prox top-tercile) | -0.0427 | [-0.044, -0.031] * | YES * | 33.4% |
| baskets | NC-1A (T1-only) | -0.0036 | [-0.011, +0.006] | no | 85.9% |
| baskets | NC-1B (ticks=0) | 0.0099 | [+0.002, +0.015] * | YES * | 90.9% |
| baskets | NC-2 (prox top-tercile) | -0.1012 | [-0.108, -0.096] * | YES * | 34.0% |

## Panel: deep

**Total fires loaded:** 38250
**Gradable fires:** 37722
**FE granularity:** `date` (frozen per RUL-12)

### Proxy: amihud

**Fires with computable band:** 29619 of 37722 (78.5%)

#### Band Distribution

| Band | Label | N fires | % of total |
|---|---|---|---|
| 0 | bottom_tercile (worst) | 9738 | 25.8% |
| 1 | mid_tercile | 10172 | 27.0% |
| 2 | top_tercile (best) | 9709 | 25.7% |

#### Band 0 — bottom_tercile (worst)

N treatment: 9738 | N control: 19881 | Affected volume: 25.8% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | 0.0060 | [-0.0154, 0.0170] | 0.9260 | 0.9614 | no |
| fwd_mdd_21 | -0.0028 | [-0.0046, 0.0007] | 0.1220 | 0.2745 | no |
| rotational_liftoff | 0.0147 | [-0.0049, 0.0260] | 0.2000 | 0.3827 | no |
| dead_money | -0.0006 | [-0.0021, 0.0012] | 0.7520 | 0.8330 | no |
| cushion_rot | 0.0163 | [-0.0092, 0.0289] | 0.3240 | 0.5165 | no |
| zone_held_21 | 0.0087 | [-0.0009, 0.0158] | 0.0660 | 0.1828 | no |
| stop_vol_21 | -0.0087 | [-0.0158, 0.0009] | 0.0660 | excl | excl |
| days_to_10 | -2.9908 | [-3.8629, -0.9907] * | 0.0000 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 5785 |
| -1 (improving) | 3952 |
| None | 1 |

**Era table (band 0 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| pre_2012 | 0 | 12111 | 13.2% | -0.0881 |
| pre_2012 | 1 | 5853 | 12.9% | -0.0879 |
| 2012-2015 | 0 | 2122 | 5.1% | -0.0571 |
| 2012-2015 | 1 | 1065 | 7.8% | -0.0716 |
| 2016-2019 | 0 | 2125 | 7.3% | -0.0669 |
| 2016-2019 | 1 | 1056 | 8.2% | -0.0790 |
| 2020-2022 | 0 | 1748 | 13.8% | -0.0939 |
| 2020-2022 | 1 | 883 | 15.4% | -0.1009 |
| 2023-2026 | 0 | 1775 | 9.6% | -0.0774 |
| 2023-2026 | 1 | 881 | 11.2% | -0.0773 |

**Era sign-stability (stop5, >=3/4 eras):** YES

#### Band 1 — mid_tercile

N treatment: 10172 | N control: 19447 | Affected volume: 27.0% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | 0.0014 | [-0.0033, 0.0158] | 0.2220 | 0.3996 | no |
| fwd_mdd_21 | 0.0007 | [-0.0013, 0.0016] | 0.6620 | 0.8003 | no |
| rotational_liftoff | -0.0032 | [-0.0160, 0.0098] | 0.6640 | 0.8003 | no |
| dead_money | -0.0017 | [-0.0025, -0.0006] * | 0.0000 | 0.0000 | YES |
| cushion_rot | -0.0076 | [-0.0200, 0.0033] | 0.1580 | 0.3346 | no |
| zone_held_21 | -0.0063 | [-0.0140, 0.0012] | 0.0880 | 0.2185 | no |
| stop_vol_21 | 0.0063 | [-0.0012, 0.0140] | 0.0880 | excl | excl |
| days_to_10 | 1.5368 | [0.1429, 2.4085] * | 0.0240 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 5785 |
| -1 (improving) | 3952 |
| None | 1 |

**Era table (band 1 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| pre_2012 | 0 | 11702 | 12.9% | -0.0883 |
| pre_2012 | 1 | 6262 | 13.5% | -0.0876 |
| 2012-2015 | 0 | 2121 | 6.0% | -0.0639 |
| 2012-2015 | 1 | 1066 | 6.0% | -0.0580 |
| 2016-2019 | 0 | 2106 | 7.5% | -0.0722 |
| 2016-2019 | 1 | 1075 | 7.8% | -0.0684 |
| 2020-2022 | 0 | 1760 | 14.8% | -0.0966 |
| 2020-2022 | 1 | 871 | 13.3% | -0.0955 |
| 2023-2026 | 0 | 1758 | 10.3% | -0.0770 |
| 2023-2026 | 1 | 898 | 9.7% | -0.0781 |

**Era sign-stability (stop5, >=3/4 eras):** NO

#### Band 2 — top_tercile (best)

N treatment: 9709 | N control: 19910 | Affected volume: 25.7% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | -0.0073 | [-0.0216, 0.0105] | 0.4180 | 0.6019 | no |
| fwd_mdd_21 | 0.0021 | [-0.0015, 0.0047] | 0.3040 | 0.4975 | no |
| rotational_liftoff | -0.0114 | [-0.0303, 0.0167] | 0.6020 | 0.8003 | no |
| dead_money | 0.0022 | [-0.0002, 0.0041] | 0.0820 | 0.2185 | no |
| cushion_rot | -0.0088 | [-0.0227, 0.0199] | 0.9480 | 0.9614 | no |
| zone_held_21 | -0.0024 | [-0.0111, 0.0076] | 0.7400 | 0.8330 | no |
| stop_vol_21 | 0.0024 | [-0.0076, 0.0111] | 0.7400 | excl | excl |
| days_to_10 | 1.5269 | [-0.7223, 2.9969] | 0.2560 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 5785 |
| -1 (improving) | 3952 |
| None | 1 |

**Era table (band 2 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| pre_2012 | 0 | 12115 | 13.2% | -0.0878 |
| pre_2012 | 1 | 5849 | 12.8% | -0.0886 |
| 2012-2015 | 0 | 2131 | 6.9% | -0.0648 |
| 2012-2015 | 1 | 1056 | 4.2% | -0.0562 |
| 2016-2019 | 0 | 2131 | 8.0% | -0.0736 |
| 2016-2019 | 1 | 1050 | 6.8% | -0.0653 |
| 2020-2022 | 0 | 1754 | 14.4% | -0.0982 |
| 2020-2022 | 1 | 877 | 14.2% | -0.0923 |
| 2023-2026 | 0 | 1779 | 10.5% | -0.0777 |
| 2023-2026 | 1 | 877 | 9.5% | -0.0767 |

**Era sign-stability (stop5, >=3/4 eras):** YES

### Proxy: corwin_schultz

**Fires with computable band:** 23791 of 37722 (63.1%)

#### Band Distribution

| Band | Label | N fires | % of total |
|---|---|---|---|
| 0 | bottom_tercile (worst) | 7753 | 20.6% |
| 1 | mid_tercile | 12481 | 33.1% |
| 2 | top_tercile (best) | 3557 | 9.4% |

#### Band 0 — bottom_tercile (worst)

N treatment: 7753 | N control: 16038 | Affected volume: 20.6% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | 0.0262 | [0.0160, 0.0313] * | 0.0000 | 0.0000 | YES |
| fwd_mdd_21 | -0.0050 | [-0.0066, -0.0037] * | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0084 | [-0.0036, 0.0159] | 0.2020 | 0.3827 | no |
| dead_money | 0.0004 | [-0.0013, 0.0018] | 0.9360 | 0.9614 | no |
| cushion_rot | -0.0018 | [-0.0146, 0.0052] | 0.3540 | 0.5310 | no |
| zone_held_21 | -0.0105 | [-0.0167, -0.0023] * | 0.0160 | 0.0576 | YES |
| stop_vol_21 | 0.0105 | [0.0023, 0.0167] * | 0.0160 | excl | excl |
| days_to_10 | -1.9279 | [-2.9997, -1.1017] * | 0.0000 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 6010 |
| -1 (improving) | 1738 |
| 0 (flat) | 5 |

**Era table (band 0 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| pre_2012 | 0 | 9970 | 12.3% | -0.0847 |
| pre_2012 | 1 | 4760 | 14.8% | -0.0931 |
| 2012-2015 | 0 | 1712 | 5.6% | -0.0605 |
| 2012-2015 | 1 | 847 | 6.9% | -0.0654 |
| 2016-2019 | 0 | 1737 | 6.4% | -0.0675 |
| 2016-2019 | 1 | 852 | 10.8% | -0.0766 |
| 2020-2022 | 0 | 1247 | 12.3% | -0.0901 |
| 2020-2022 | 1 | 624 | 16.2% | -0.0983 |
| 2023-2026 | 0 | 1372 | 9.8% | -0.0756 |
| 2023-2026 | 1 | 670 | 11.2% | -0.0840 |

**Era sign-stability (stop5, >=3/4 eras):** YES

#### Band 1 — mid_tercile

N treatment: 12481 | N control: 11310 | Affected volume: 33.1% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | -0.0242 | [-0.0294, -0.0153] * | 0.0000 | 0.0000 | YES |
| fwd_mdd_21 | 0.0042 | [0.0031, 0.0053] * | 0.0000 | 0.0000 | YES |
| rotational_liftoff | -0.0061 | [-0.0149, 0.0033] | 0.2860 | 0.4903 | no |
| dead_money | -0.0004 | [-0.0014, 0.0010] | 0.8640 | 0.9148 | no |
| cushion_rot | 0.0004 | [-0.0059, 0.0100] | 0.7420 | 0.8330 | no |
| zone_held_21 | 0.0071 | [-0.0022, 0.0113] | 0.1860 | 0.3720 | no |
| stop_vol_21 | -0.0071 | [-0.0113, 0.0022] | 0.1860 | excl | excl |
| days_to_10 | 1.7695 | [1.0948, 2.8170] * | 0.0000 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 6010 |
| -1 (improving) | 1738 |
| 0 (flat) | 5 |

**Era table (band 1 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| pre_2012 | 0 | 6898 | 14.4% | -0.0921 |
| pre_2012 | 1 | 7832 | 11.9% | -0.0834 |
| 2012-2015 | 0 | 1251 | 6.7% | -0.0647 |
| 2012-2015 | 1 | 1308 | 5.3% | -0.0596 |
| 2016-2019 | 0 | 1222 | 9.9% | -0.0730 |
| 2016-2019 | 1 | 1367 | 6.0% | -0.0682 |
| 2020-2022 | 0 | 963 | 15.3% | -0.0984 |
| 2020-2022 | 1 | 908 | 11.8% | -0.0869 |
| 2023-2026 | 0 | 976 | 10.5% | -0.0822 |
| 2023-2026 | 1 | 1066 | 9.9% | -0.0749 |

**Era sign-stability (stop5, >=3/4 eras):** YES

**NC-2 proximity marginality test (band 1):**

stop5 after NC-2 band FE: coef=-0.0290 CI=[-0.0365, -0.0170] CI_excl_0=YES
Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 12481/12481; N control = 11310.

#### Band 2 — top_tercile (best)

N treatment: 3557 | N control: 20234 | Affected volume: 9.4% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | -0.0051 | [-0.0141, 0.0054] | 0.4000 | 0.5878 | no |
| fwd_mdd_21 | 0.0020 | [0.0006, 0.0040] * | 0.0120 | 0.0480 | YES |
| rotational_liftoff | -0.0052 | [-0.0146, 0.0116] | 0.6780 | 0.8003 | no |
| dead_money | -0.0000 | [-0.0015, 0.0017] | 0.9720 | 0.9720 | no |
| cushion_rot | 0.0032 | [-0.0095, 0.0244] | 0.4540 | 0.6409 | no |
| zone_held_21 | 0.0076 | [0.0007, 0.0214] * | 0.0320 | 0.0960 | YES |
| stop_vol_21 | -0.0076 | [-0.0214, -0.0007] * | 0.0320 | excl | excl |
| days_to_10 | 0.4167 | [-0.6542, 1.4978] | 0.4620 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 6010 |
| -1 (improving) | 1738 |
| 0 (flat) | 5 |

**Era table (band 2 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| pre_2012 | 0 | 12592 | 13.0% | -0.0870 |
| pre_2012 | 1 | 2138 | 13.7% | -0.0897 |
| 2012-2015 | 0 | 2155 | 5.9% | -0.0619 |
| 2012-2015 | 1 | 404 | 6.4% | -0.0634 |
| 2016-2019 | 0 | 2219 | 7.8% | -0.0714 |
| 2016-2019 | 1 | 370 | 7.8% | -0.0649 |
| 2020-2022 | 0 | 1532 | 13.6% | -0.0915 |
| 2020-2022 | 1 | 339 | 13.6% | -0.0986 |
| 2023-2026 | 0 | 1736 | 10.4% | -0.0784 |
| 2023-2026 | 1 | 306 | 9.2% | -0.0782 |

**Era sign-stability (stop5, >=3/4 eras):** YES

**NC-2 proximity marginality test (band 2):**

stop5 after NC-2 band FE: coef=0.0012 CI=[-0.0063, 0.0153] CI_excl_0=no
Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 3557/3557; N control = 20234.

## Panel: baskets

**Total fires loaded:** 113542
**Gradable fires:** 107127
**FE granularity:** `date` (frozen per RUL-12)

### Proxy: amihud

**Fires with computable band:** 98928 of 107127 (92.3%)

#### Band Distribution

| Band | Label | N fires | % of total |
|---|---|---|---|
| 0 | bottom_tercile (worst) | 32985 | 30.8% |
| 1 | mid_tercile | 32958 | 30.8% |
| 2 | top_tercile (best) | 32985 | 30.8% |

#### Band 0 — bottom_tercile (worst)

N treatment: 32985 | N control: 65943 | Affected volume: 30.8% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | 0.0777 | [0.0365, 0.2520] * | 0.0080 | 0.0339 | YES |
| fwd_mdd_21 | -0.0174 | [-0.0246, 0.0057] | 0.1200 | 0.2745 | no |
| rotational_liftoff | 0.0453 | [-0.0223, 0.2643] | 0.0860 | 0.2185 | no |
| dead_money | 0.0001 | [-0.0000, 0.0002] | 0.8340 | 0.8962 | no |
| cushion_rot | 0.0125 | [-0.0352, 0.1926] | 0.1180 | 0.2745 | no |
| zone_held_21 | -0.0100 | [-0.2071, 0.0370] | 0.2440 | 0.4285 | no |
| stop_vol_21 | 0.0100 | [-0.0370, 0.2071] | 0.2440 | excl | excl |
| days_to_10 | -6.3315 | [-13.4301, -1.3672] * | 0.0220 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 19555 |
| -1 (improving) | 13406 |
| None | 24 |

**Era table (band 0 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| 2012-2015 | 0 | 4501 | 14.8% | -0.1165 |
| 2012-2015 | 1 | 2249 | 22.9% | -0.1483 |
| 2016-2019 | 0 | 20648 | 11.3% | -0.0942 |
| 2016-2019 | 1 | 10330 | 18.6% | -0.1228 |
| 2020-2022 | 0 | 18964 | 23.5% | -0.1368 |
| 2020-2022 | 1 | 9482 | 30.3% | -0.1566 |
| 2023-2026 | 0 | 21830 | 18.4% | -0.1187 |
| 2023-2026 | 1 | 10924 | 27.3% | -0.1526 |

**Era sign-stability (stop5, >=3/4 eras):** YES

#### Band 1 — mid_tercile

N treatment: 32958 | N control: 65970 | Affected volume: 30.8% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | 0.0034 | [-0.0214, 0.0454] | 0.6320 | 0.8003 | no |
| fwd_mdd_21 | -0.0021 | [-0.0068, 0.0036] | 0.4900 | 0.6657 | no |
| rotational_liftoff | 0.0098 | [-0.0070, 0.0588] | 0.3540 | 0.5310 | no |
| dead_money | -0.0002 | [-0.0020, 0.0011] | 0.3300 | 0.5165 | no |
| cushion_rot | 0.0088 | [0.0008, 0.0586] * | 0.0200 | 0.0686 | YES |
| zone_held_21 | -0.0137 | [-0.0185, 0.0074] | 0.2160 | 0.3988 | no |
| stop_vol_21 | 0.0137 | [-0.0074, 0.0185] | 0.2160 | excl | excl |
| days_to_10 | -1.1057 | [-6.6539, 1.0848] | 0.4480 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 19555 |
| -1 (improving) | 13406 |
| None | 24 |

**Era table (band 1 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| 2012-2015 | 0 | 4498 | 17.7% | -0.1255 |
| 2012-2015 | 1 | 2252 | 17.2% | -0.1302 |
| 2016-2019 | 0 | 20660 | 13.8% | -0.1027 |
| 2016-2019 | 1 | 10318 | 13.5% | -0.1058 |
| 2020-2022 | 0 | 18964 | 25.2% | -0.1406 |
| 2020-2022 | 1 | 9482 | 26.9% | -0.1491 |
| 2023-2026 | 0 | 21848 | 21.4% | -0.1285 |
| 2023-2026 | 1 | 10906 | 21.4% | -0.1330 |

**Era sign-stability (stop5, >=3/4 eras):** NO

#### Band 2 — top_tercile (best)

N treatment: 32985 | N control: 65943 | Affected volume: 30.8% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | -0.0812 | [-0.0883, -0.0258] * | 0.0000 | 0.0000 | YES |
| fwd_mdd_21 | 0.0195 | [0.0034, 0.0209] * | 0.0000 | 0.0000 | YES |
| rotational_liftoff | -0.0551 | [-0.0683, -0.0255] * | 0.0020 | 0.0090 | YES |
| dead_money | 0.0001 | [-0.0011, 0.0020] | 0.6720 | 0.8003 | no |
| cushion_rot | -0.0213 | [-0.0592, -0.0070] * | 0.0140 | 0.0531 | YES |
| zone_held_21 | 0.0237 | [-0.0071, 0.0275] | 0.1860 | 0.3720 | no |
| stop_vol_21 | -0.0237 | [-0.0275, 0.0071] | 0.1860 | excl | excl |
| days_to_10 | 7.7221 | [3.6698, 8.8227] * | 0.0000 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 19555 |
| -1 (improving) | 13406 |
| None | 24 |

**Era table (band 2 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| 2012-2015 | 0 | 4501 | 20.1% | -0.1393 |
| 2012-2015 | 1 | 2249 | 12.4% | -0.1027 |
| 2016-2019 | 0 | 20648 | 16.1% | -0.1143 |
| 2016-2019 | 1 | 10330 | 9.1% | -0.0826 |
| 2020-2022 | 0 | 18964 | 28.6% | -0.1528 |
| 2020-2022 | 1 | 9482 | 20.1% | -0.1245 |
| 2023-2026 | 0 | 21830 | 24.4% | -0.1428 |
| 2023-2026 | 1 | 10924 | 15.4% | -0.1044 |

**Era sign-stability (stop5, >=3/4 eras):** YES

**NC-2 proximity marginality test (band 2):**

stop5 after NC-2 band FE: coef=-0.0673 CI=[-0.0718, -0.0226] CI_excl_0=YES
Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 32985/32985; N control = 65943.

### Proxy: corwin_schultz

**Fires with computable band:** 87765 of 107127 (81.9%)

#### Band Distribution

| Band | Label | N fires | % of total |
|---|---|---|---|
| 0 | bottom_tercile (worst) | 29241 | 27.3% |
| 1 | mid_tercile | 52007 | 48.5% |
| 2 | top_tercile (best) | 6517 | 6.1% |

#### Band 0 — bottom_tercile (worst)

N treatment: 29241 | N control: 58524 | Affected volume: 27.3% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | 0.0496 | [0.0228, 0.0513] * | 0.0000 | 0.0000 | YES |
| fwd_mdd_21 | -0.0116 | [-0.0118, -0.0037] * | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0299 | [0.0142, 0.0375] * | 0.0000 | 0.0000 | YES |
| dead_money | -0.0018 | [-0.0021, -0.0003] * | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.0172 | [0.0033, 0.0283] * | 0.0240 | 0.0751 | YES |
| zone_held_21 | -0.0218 | [-0.0229, 0.0028] | 0.1480 | 0.3229 | no |
| stop_vol_21 | 0.0218 | [-0.0028, 0.0229] | 0.1480 | excl | excl |
| days_to_10 | -4.1469 | [-4.3983, -2.5887] * | 0.0000 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 23125 |
| -1 (improving) | 6114 |
| 0 (flat) | 2 |

**Era table (band 0 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| 2012-2015 | 0 | 4515 | 15.5% | -0.1172 |
| 2012-2015 | 1 | 2262 | 20.6% | -0.1385 |
| 2016-2019 | 0 | 19035 | 13.4% | -0.0999 |
| 2016-2019 | 1 | 9503 | 17.0% | -0.1175 |
| 2020-2022 | 0 | 16391 | 23.4% | -0.1363 |
| 2020-2022 | 1 | 8189 | 29.6% | -0.1573 |
| 2023-2026 | 0 | 18583 | 19.9% | -0.1213 |
| 2023-2026 | 1 | 9287 | 25.2% | -0.1437 |

**Era sign-stability (stop5, >=3/4 eras):** YES

#### Band 1 — mid_tercile

N treatment: 52007 | N control: 35758 | Affected volume: 48.5% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | -0.0492 | [-0.0511, -0.0192] * | 0.0000 | 0.0000 | YES |
| fwd_mdd_21 | 0.0115 | [0.0040, 0.0117] * | 0.0000 | 0.0000 | YES |
| rotational_liftoff | -0.0321 | [-0.0360, -0.0110] * | 0.0000 | 0.0000 | YES |
| dead_money | 0.0011 | [0.0002, 0.0013] * | 0.0020 | 0.0090 | YES |
| cushion_rot | -0.0186 | [-0.0247, 0.0008] | 0.0580 | 0.1670 | no |
| zone_held_21 | 0.0208 | [0.0022, 0.0227] * | 0.0240 | 0.0751 | YES |
| stop_vol_21 | -0.0208 | [-0.0227, -0.0022] * | 0.0240 | excl | excl |
| days_to_10 | 4.4185 | [2.3104, 4.6860] * | 0.0000 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 23125 |
| -1 (improving) | 6114 |
| 0 (flat) | 2 |

**Era table (band 1 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| 2012-2015 | 0 | 2723 | 19.4% | -0.1354 |
| 2012-2015 | 1 | 4054 | 15.7% | -0.1169 |
| 2016-2019 | 0 | 11285 | 16.9% | -0.1163 |
| 2016-2019 | 1 | 17253 | 13.2% | -0.0989 |
| 2020-2022 | 0 | 10458 | 29.1% | -0.1532 |
| 2020-2022 | 1 | 14122 | 22.7% | -0.1360 |
| 2023-2026 | 0 | 11292 | 24.3% | -0.1406 |
| 2023-2026 | 1 | 16578 | 19.9% | -0.1208 |

**Era sign-stability (stop5, >=3/4 eras):** YES

**NC-2 proximity marginality test (band 1):**

stop5 after NC-2 band FE: coef=-0.0418 CI=[-0.0434, -0.0152] CI_excl_0=YES
Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 52007/52007; N control = 35758.

#### Band 2 — top_tercile (best)

N treatment: 6517 | N control: 81248 | Affected volume: 6.1% of fires

| Outcome | Coef | 95% CI (boot) | p | BH q | BH rej? |
|---|---|---|---|---|---|
| stop5 | -0.0022 | [-0.0225, 0.0146] | 0.4900 | 0.6657 | no |
| fwd_mdd_21 | 0.0005 | [-0.0049, 0.0011] | 0.7500 | 0.8330 | no |
| rotational_liftoff | 0.0098 | [-0.0298, 0.0155] | 0.6460 | 0.8003 | no |
| dead_money | 0.0029 | [-0.0007, 0.0035] | 0.3000 | 0.4975 | no |
| cushion_rot | 0.0064 | [-0.0352, 0.0165] | 0.6180 | 0.8003 | no |
| zone_held_21 | 0.0048 | [-0.0467, 0.0114] | 0.7840 | 0.8553 | no |
| stop_vol_21 | -0.0048 | [-0.0114, 0.0467] | 0.7840 | excl | excl |
| days_to_10 | -1.0173 | [-1.4660, 1.7735] | 0.4760 | excl | excl |

**Deterioration sign distribution (band 0 fires):**

| Deterioration sign | N fires |
|---|---|
| +1 (deteriorating) | 23125 |
| -1 (improving) | 6114 |
| 0 (flat) | 2 |

**Era table (band 2 vs rest):**

| era | stratum | n_fires | stop5_rate | mae63_mean (63d context, NOT a verdict metric) |
|---|---|---|---|---|
| 2012-2015 | 0 | 6316 | 17.4% | -0.1246 |
| 2012-2015 | 1 | 461 | 13.5% | -0.1201 |
| 2016-2019 | 0 | 26756 | 14.5% | -0.1055 |
| 2016-2019 | 1 | 1782 | 16.1% | -0.1102 |
| 2020-2022 | 0 | 22311 | 25.2% | -0.1438 |
| 2020-2022 | 1 | 2269 | 27.5% | -0.1383 |
| 2023-2026 | 0 | 25865 | 21.8% | -0.1290 |
| 2023-2026 | 1 | 2005 | 20.1% | -0.1260 |

**Era sign-stability (stop5, >=3/4 eras):** NO

## Hygiene Bar Summary (masterplan §5)

**Pre-registered clauses:**
- Clause A: CI-excluding-0 degradation on stop5 (CI_lo > 0) OR fwd_mdd_21 (CI_hi < 0) for the WORST band (band 0 = least liquid).
- Clause B: Affected volume of worst band <= 10% of fires (hygiene rule that eats recall = gate in disguise).
- Both clauses must be met for HYGIENE BAR MET.

| Proxy | Panel | Worst band N | Clause A (degradation excl-0)? | stop5 CI_lo>0 | fwd_mdd_21 CI_hi<0 | Clause B (vol<=10%)? | Affected vol | HYGIENE BAR MET? |
|---|---|---|---|---|---|---|---|---|
| amihud | deep | 9738 | NO | NO | NO | NO | 25.8% | NOT MET |
| corwin_schultz | deep | 7753 | YES | YES | YES | NO | 20.6% | NOT MET |
| amihud | baskets | 32985 | YES | YES | NO | NO | 30.8% | NOT MET |
| corwin_schultz | baskets | 29241 | YES | YES | YES | NO | 27.3% | NOT MET |

## Overall Verdict (pre-registered, no adjudication here)

**VERDICT: SHIP NOTHING.** No band cleared the pre-registered hygiene bar (CI-excluding-0 degradation of the worst band on stop5 OR fwd_mdd_21, with affected volume <= 10%). The Amihud and Corwin-Schultz primitives remain available as kernel context (as planned in masterplan §3 F4). No liquidity tilt is introduced. This is the honest null — printed, not hidden.

## BH Correction Scope

Family-wide BH: one BH pass pooling ALL proxy x band x outcome cells of esx_lq_bands (budget=12).
Pool excludes stop_vol_21 (mechanical mirror of zone_held_21) and days_to_10 (collider). BH q <= 0.10.
Pool size: 72 cells. BH-rejected: 24.

## Headline Numbers (orchestrator summary)

**Worst-band deltas and affected-volume percentages:**

| Proxy | Panel | Band 0 stop5 coef | Band 0 stop5 CI | Band 0 fwd_mdd_21 coef | Band 0 fwd_mdd_21 CI | Affected vol | Hygiene bar met? |
|---|---|---|---|---|---|---|---|
| amihud | deep | 0.0060 | [-0.0154, 0.0170] | -0.0028 | [-0.0046, 0.0007] | 25.8% | NOT MET |
| corwin_schultz | deep | 0.0262 | [0.0160, 0.0313] | -0.0050 | [-0.0066, -0.0037] | 20.6% | NOT MET |
| amihud | baskets | 0.0777 | [0.0365, 0.2520] | -0.0174 | [-0.0246, 0.0057] | 30.8% | NOT MET |
| corwin_schultz | baskets | 0.0496 | [0.0228, 0.0513] | -0.0116 | [-0.0118, -0.0037] | 27.3% | NOT MET |

*Generated by `scripts/research/run_w2_slq.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*'validated' word deliberately absent (CI-enforced).*
*No promotion language. Hygiene study only.*
