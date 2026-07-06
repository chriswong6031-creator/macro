# Expect-Drift Family — Ruler-P Study Results

**Family:** `long_hold.expect_drift` | **m = 7** | **Ruler-P cutoff:** fires ≤ 2023-12-31 | **Generated:** 2026-07-06

> **Authority ceiling:** DISPLAY ONLY. No SURVIVE/KILL vocabulary. All cells are UPPER BOUND (survivorship-biased). The word 'validated' does not appear in this document (CI-enforced).

---

## In plain English

> **What this study asked:**
> At the moment of a tactical entry fire, do post-earnings signals — how
> strong the recent earnings surprise was, how long it has been positive,
> whether the stock absorbed bad news or held good news — predict which
> fires end up as cheap traps (durable hold candidates at 252 days)
> versus tactical-only fires (bounced but faded)?
>
> **The contrast:**
> cheap_trap vs tactical_only, measured at 252 days, fires 2014-2023 only.
> cheap_trap = entry fires where the stock traded below its fire-date price
> again within 252 days (the 'left behind' outcome). The hypothesis is that
> earnings-momentum signals at entry predict this bad outcome — that a fire
> without earnings support is more likely to become a cheap trap.
>
> **What the results mean:**
> All results here carry a survivorship-bias stamp (UPPER BOUND) because the
> 2014-2021 cohorts include only stocks that survived. This inflates apparent
> edges. A feature passing both BH-FDR and the reshuffle-null descriptive
> gates may be used in display copy, but no result is a final verdict.
> Final ratification requires Ruler-H on OOS-2 (2025+ honest fires)
> at the G1-Retest trigger (~2027-H2).

## Population summary

| Metric | Value |
|---|---|
| Ruler-P fires (≤ 2023-12-31) | 5458 |
| cheap_trap | 2730 |
| tactical_only | 2728 |
| BH q threshold | 0.1 (DESCRIPTIVE per LH-R11.2) |
| Reshuffle permutations | 1000 (seed=42 LOCKED) |
| n-floor per arm | 25 episode-clusters |

## Feature coverage

| Feature | ID | Type | Expected sign | Coverage | Status |
|---|---|---|---|---|---|
| `sue_latest` | ED-1 | cont | + | 46.2% | RETAINED |
| `sue_streak` | ED-2 | cont | + | 46.2% | RETAINED |
| `pead_drift` | ED-3 | cont | + | 41.5% | RETAINED |
| `bad_news_absorption` | ED-4 | bin | + | 46.1% | RETAINED |
| `good_news_hold` | ED-5 | bin | + | 45.8% | RETAINED |
| `sue_accel` | ED-6 | cont | + | 46.2% | RETAINED |
| `confirmed_absorption` | ED-7 | bin | + | 40.5% | RETAINED |

## Cell: `full_ruler_p_2014-2023`

**Survivorship stamp:** UPPER_BOUND | cheap_trap n = 2663 | tactical_only n = 2662 (after episode-cluster dedup)

| Feature | ID | Type | RBC | p-value | q-value (BH) | Rej (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sue_latest` | ED-1 | cont | -0.051 | 0.0320 | 0.0747 | True | False | 0.029 | -0.169 | 0.032 | 1013 | 1447 | **NULL** |
| `sue_streak` | ED-2 | cont | -0.061 | 0.0096 | 0.0338 | True | False | 0.031 | -0.100 | 0.092 | 1013 | 1447 | **NULL** |
| `pead_drift` | ED-3 | cont | 0.037 | 0.1333 | 0.2106 | False | True | 0.031 | -0.126 | 0.093 | 937 | 1264 | **NULL** |
| `bad_news_absorption` | ED-4 | bin | 0.015 | 0.3246 | 0.3787 | False | False | 0.022 | -0.022 | 0.096 | 1015 | 1437 | **NULL** |
| `good_news_hold` | ED-5 | bin | 0.018 | 0.1504 | 0.2106 | False | True | 0.017 | -0.004 | 0.108 | 1011 | 1426 | **NULL** |
| `sue_accel` | ED-6 | cont | -0.018 | 0.4520 | 0.4520 | False | False | 0.029 | -0.108 | 0.096 | 1013 | 1447 | **NULL** |
| `confirmed_absorption` | ED-7 | bin | 0.041 | 0.0083 | 0.0338 | True | True | 0.024 | 0.004 | 0.151 | 913 | 1241 | **DESCRIPTIVE_PASS** |

## Cell: `fit_2014-2019`

**Survivorship stamp:** UPPER_BOUND | cheap_trap n = 376 | tactical_only n = 378 (after episode-cluster dedup)

| Feature | ID | Type | RBC | p-value | q-value (BH) | Rej (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sue_latest` | ED-1 | cont | -0.062 | 0.2196 | 0.3843 | False | False | 0.057 | -0.165 | 0.160 | 252 | 271 | **NULL** |
| `sue_streak` | ED-2 | cont | -0.062 | 0.2181 | 0.3843 | False | False | 0.055 | -0.151 | 0.254 | 252 | 271 | **NULL** |
| `pead_drift` | ED-3 | cont | -0.051 | 0.3352 | 0.3911 | False | False | 0.079 | -0.297 | 0.061 | 235 | 253 | **NULL** |
| `bad_news_absorption` | ED-4 | bin | 0.046 | 0.1806 | 0.3843 | False | False | 0.061 | -0.106 | 0.106 | 248 | 273 | **NULL** |
| `good_news_hold` | ED-5 | bin | 0.046 | 0.0552 | 0.3843 | False | True | 0.031 | 0.006 | 0.164 | 248 | 273 | **NULL** |
| `sue_accel` | ED-6 | cont | -0.034 | 0.4992 | 0.4992 | False | False | 0.063 | -0.141 | 0.195 | 252 | 271 | **NULL** |
| `confirmed_absorption` | ED-7 | bin | 0.035 | 0.2869 | 0.3911 | False | False | 0.053 | -0.053 | 0.122 | 219 | 241 | **NULL** |
| `sue_latest` | ED-1 | cont | -0.062 | 0.2196 | 0.3843 | False | False | 0.057 | -0.165 | 0.160 | 252 | 271 | **NULL** |
| `sue_streak` | ED-2 | cont | -0.062 | 0.2181 | 0.3843 | False | False | 0.055 | -0.151 | 0.254 | 252 | 271 | **NULL** |
| `pead_drift` | ED-3 | cont | -0.051 | 0.3352 | 0.3911 | False | False | 0.079 | -0.297 | 0.061 | 235 | 253 | **NULL** |
| `bad_news_absorption` | ED-4 | bin | 0.046 | 0.1806 | 0.3843 | False | False | 0.061 | -0.106 | 0.106 | 248 | 273 | **NULL** |
| `good_news_hold` | ED-5 | bin | 0.046 | 0.0552 | 0.3843 | False | True | 0.031 | 0.006 | 0.164 | 248 | 273 | **NULL** |
| `sue_accel` | ED-6 | cont | -0.034 | 0.4992 | 0.4992 | False | False | 0.063 | -0.141 | 0.195 | 252 | 271 | **NULL** |
| `confirmed_absorption` | ED-7 | bin | 0.035 | 0.2869 | 0.3911 | False | False | 0.053 | -0.053 | 0.122 | 219 | 241 | **NULL** |

## Cell: `oos_biased_2020-2023`

**Survivorship stamp:** UPPER_BOUND | cheap_trap n = 2287 | tactical_only n = 2284 (after episode-cluster dedup)

| Feature | ID | Type | RBC | p-value | q-value (BH) | Rej (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sue_latest` | ED-1 | cont | -0.047 | 0.0791 | 0.1385 | False | False | 0.031 | -0.254 | 0.049 | 761 | 1176 | **NULL** |
| `sue_streak` | ED-2 | cont | -0.061 | 0.0239 | 0.0837 | True | False | 0.034 | -0.193 | 0.052 | 761 | 1176 | **NULL** |
| `pead_drift` | ED-3 | cont | 0.059 | 0.0362 | 0.0845 | True | True | 0.028 | -0.070 | 0.278 | 702 | 1011 | **DESCRIPTIVE_PASS** |
| `bad_news_absorption` | ED-4 | bin | 0.008 | 0.6667 | 0.6667 | False | False | 0.023 | -0.022 | 0.151 | 767 | 1164 | **NULL** |
| `good_news_hold` | ED-5 | bin | 0.012 | 0.4041 | 0.5657 | False | False | 0.023 | -0.009 | 0.131 | 763 | 1153 | **NULL** |
| `sue_accel` | ED-6 | cont | -0.014 | 0.6046 | 0.6667 | False | False | 0.029 | -0.174 | 0.104 | 761 | 1176 | **NULL** |
| `confirmed_absorption` | ED-7 | bin | 0.044 | 0.0153 | 0.0837 | True | True | 0.027 | 0.000 | 0.227 | 694 | 1000 | **DESCRIPTIVE_PASS** |

## Cell: `oos_2020-2021`

**Survivorship stamp:** UPPER_BOUND | cheap_trap n = 467 | tactical_only n = 470 (after episode-cluster dedup)

| Feature | ID | Type | RBC | p-value | q-value (BH) | Rej (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sue_latest` | ED-1 | cont | 0.062 | 0.2602 | 0.8255 | False | True | 0.036 | -0.334 | 0.417 | 190 | 263 | **NULL** |
| `sue_streak` | ED-2 | cont | 0.018 | 0.7476 | 0.8722 | False | False | 0.041 | -0.188 | 0.438 | 190 | 263 | **NULL** |
| `pead_drift` | ED-3 | cont | 0.046 | 0.4236 | 0.8255 | False | False | 0.088 | -0.200 | 0.600 | 185 | 227 | **NULL** |
| `bad_news_absorption` | ED-4 | bin | -0.004 | 1.0000 | 1.0000 | False | False | 0.052 | -0.283 | 0.109 | 187 | 253 | **NULL** |
| `good_news_hold` | ED-5 | bin | 0.031 | 0.3207 | 0.8255 | False | False | 0.041 | -0.031 | 0.375 | 183 | 240 | **NULL** |
| `sue_accel` | ED-6 | cont | 0.040 | 0.4717 | 0.8255 | False | False | 0.051 | -0.542 | 0.256 | 190 | 263 | **NULL** |
| `confirmed_absorption` | ED-7 | bin | 0.019 | 0.6194 | 0.8671 | False | False | 0.059 | -0.278 | 0.167 | 178 | 224 | **NULL** |

## Cell: `oos_2022-2023`

**Survivorship stamp:** UPPER_BOUND | cheap_trap n = 1820 | tactical_only n = 1814 (after episode-cluster dedup)

| Feature | ID | Type | RBC | p-value | q-value (BH) | Rej (BH) | Passes reshuffle | Reshuffle p90 | CI lo | CI hi | n_pos | n_neg | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sue_latest` | ED-1 | cont | -0.093 | 0.0025 | 0.0169 | True | False | 0.043 | -0.407 | -0.029 | 571 | 913 | **NULL** |
| `sue_streak` | ED-2 | cont | -0.087 | 0.0048 | 0.0169 | True | False | 0.045 | -0.273 | 0.041 | 571 | 913 | **NULL** |
| `pead_drift` | ED-3 | cont | 0.066 | 0.0428 | 0.0749 | True | True | 0.032 | -0.226 | 0.258 | 517 | 784 | **DESCRIPTIVE_PASS** |
| `bad_news_absorption` | ED-4 | bin | 0.015 | 0.4998 | 0.5831 | False | False | 0.029 | -0.030 | 0.271 | 580 | 911 | **NULL** |
| `good_news_hold` | ED-5 | bin | 0.007 | 0.6697 | 0.6697 | False | False | 0.024 | -0.044 | 0.141 | 580 | 913 | **NULL** |
| `sue_accel` | ED-6 | cont | -0.035 | 0.2578 | 0.3609 | False | False | 0.035 | -0.128 | 0.250 | 571 | 913 | **NULL** |
| `confirmed_absorption` | ED-7 | bin | 0.055 | 0.0114 | 0.0267 | True | True | 0.032 | 0.005 | 0.320 | 516 | 776 | **DESCRIPTIVE_PASS** |

---

## Protocol notes

- **BH-FDR:** q ≤ 0.1 across all m = 7 registered features (DESCRIPTIVE per LH-R11.2 — not ratifying)
- **Reshuffle null:** 1000 permutations, seed = 42 (LOCKED in pre-registration)
- **Episode-cluster floor:** ≥ 25 per arm
- **Episode-cluster dedup:** ± 14 calendar days (≈ ± 10 trading days, documented deviation from LH-R4)
- **CI method:** wider of cluster-bootstrap (ticker × macro_regime; seed = 44) and block-bootstrap (seed = 43)
- **Ruler-P cutoff:** fires ≤ 2023-12-31 only. OOS-2 2025+ cohort is reserved for Ruler-H at G1-Retest (~2027-H2). No contact.
- **Authority ceiling:** DISPLAY ONLY. A feature passing both BH-FDR and reshuffle null may be shown in display copy. SURVIVE/KILL vocabulary is banned until Ruler-H.
- **TrialLedger:** `log_declared_budget(7, family='long_hold.expect_drift')` called BEFORE p-value computation (CI gate passed).
- **Survivorship bias:** all Ruler-P cells are UPPER BOUND (pre-2021-07 tickers survivorship-biased per LH-R3).
- **OOS-2 contamination guard:** hard assertion `fire_date <= 2023-12-31` — no 2024+ fires enter any feature-outcome join (AMENDMENT_A2_G1_RETEST.md §4).
- The word 'validated' does not appear in this document (CI-enforced).

**G1 ratification:** PENDING RULER-H (OOS-2, ~2027-H2). These results are display-tier upper bounds only.
