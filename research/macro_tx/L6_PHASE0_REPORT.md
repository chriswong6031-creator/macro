# L6-P0 Macro-Transmission Phase-0 Report

**Run date:** 2026-07-06  
**Prereg:** research/macro_tx/L6_PHASE0_PREREG.md (frozen 2026-07-06)  
**Fire tape:** spine_index.parquet track_record, outcome_graded=True, horizons 5/21/63  
**Verdict horizon:** h21  
**Cumulative macro_tx trial count:** 12  
**SPY/S&P 500 drawdown source:** data/yahoo/SPY.parquet (close, range 1993-01-29 to 2026-07-02)  
**USD series source:** data/fred/DTWEXBGS.parquet (broad_dollar, FRED)  

---

## In plain English

> This study asks: when a macro condition is hostile at the time a signal fires — when rates are rising fast, the dollar is surging, credit spreads are blowing out, or financial conditions are tight — does the signal perform differently versus normal times? Each macro axis is tested separately (never combined). The verdict requires the hostile-vs-normal hit-rate gap to be stable across two time periods AND the statistical confidence interval to exclude zero in both periods. Any axis that passes this gate re-opens the question of whether macro conditioning should be wired into the signal engine (subject to further approval). A fail means the gap is not reliably there. Either outcome is informative and is printed honestly.

---

## Achieved counts (printed before outcome statistics)

Total fires loaded (track_record, graded, h5+h21+h63): 165,710

| Axis | Coverage window | Total episodes | h21 hostile fires | h21 benign fires | Half1 ep | Half2 ep |
|---|---|---|---|---|---|---|
| A1_rates_shock | 1962-01-02 to 2026-07-01 | 128 | 9114 | 46171 | 60 | 68 |
| A2_usd_shock | 2006-01-02 to 2026-06-26 | 44 | 5152 | 22749 | 21 | 23 |
| A3_credit_shock | 1996-12-31 to 2026-07-02 | 35 | 5718 | 32277 | 17 | 18 |
| A4_fin_conditions | 1971-01-08 to 2026-06-26 (weekly, ffill to BD) | 28 | 15350 | 38677 | 17 | 11 |

---

## Per-axis results (all 12 cells including nulls and defers)

### A1_rates_shock
**Description:** 20-BD change >=+1.5σ AND >=+25 bp  
**Coverage:** 1962-01-02 to 2026-07-01  
**Total episodes:** 128  
**OOS midpoint:** 1994-04-02  
**Verdict (h21):** P0-PASS  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 9114 | 46272 | -0.0398 | -0.0570 | -0.0240 | -0.0712 | [-0.0986, -0.0475] | -0.0304 | [-0.0496, -0.0100] | True | computed |
| h21(verdict) | 9114 | 46171 | -0.0349 | -0.0484 | -0.0218 | -0.0521 | [-0.0754, -0.0298] | -0.0296 | [-0.0454, -0.0126] | True | computed |
| h63(descriptive) | 9021 | 46018 | -0.0261 | -0.0367 | -0.0161 | -0.0394 | [-0.0586, -0.0215] | -0.0218 | [-0.0340, -0.0092] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 6003 | 36352 | 0.8431 | 0.8809 | -0.0379 | 10304.4 |
| dd_5_10 | 1094 | 3793 | 0.8940 | 0.9122 | -0.0182 | 1698.2 |
| dd_10_20 | 1095 | 3943 | 0.8320 | 0.8975 | -0.0656 | 1714.0 |
| dd_20plus | 922 | 2083 | 0.9013 | 0.8934 | 0.0079 | 1278.2 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0446 (hostile n=3365, benign n=12957)

### A2_usd_shock
**Description:** 20-BD return >=+1.5σ AND >=+2.0%  
**Coverage:** 2006-01-02 to 2026-06-26  
**Total episodes:** 44  
**OOS midpoint:** 2016-03-30  
**Verdict (h21):** P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half)  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 5152 | 22850 | 0.0007 | -0.0209 | 0.0225 | 0.0023 | [-0.0294, 0.0335] | -0.0012 | [-0.0342, 0.0316] | True | computed |
| h21(verdict) | 5152 | 22749 | -0.0032 | -0.0210 | 0.0170 | -0.0151 | [-0.0483, 0.0196] | 0.0095 | [-0.0138, 0.0350] | True | computed |
| h63(descriptive) | 5109 | 22546 | -0.0086 | -0.0220 | 0.0082 | -0.0216 | [-0.0491, 0.0089] | 0.0034 | [-0.0105, 0.0184] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 2636 | 16926 | 0.8839 | 0.8790 | 0.0049 | 4561.6 |
| dd_5_10 | 678 | 2813 | 0.9218 | 0.9012 | 0.0207 | 1092.6 |
| dd_10_20 | 1018 | 2291 | 0.8723 | 0.9009 | -0.0286 | 1409.6 |
| dd_20plus | 820 | 719 | 0.8805 | 0.9193 | -0.0388 | 766.2 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0022 (hostile n=3392, benign n=12930)

### A3_credit_shock
**Description:** 20-BD change >=+1.5σ AND >=+50 bp  
**Coverage:** 1996-12-31 to 2026-07-02  
**Total episodes:** 35  
**OOS midpoint:** 2011-10-01  
**Verdict (h21):** P0-FAIL (BH_fail, CI_includes_0_in_a_half)  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 5718 | 32378 | -0.0042 | -0.0270 | 0.0202 | -0.0034 | [-0.0385, 0.0308] | -0.0078 | [-0.0421, 0.0271] | True | computed |
| h21(verdict) | 5718 | 32277 | 0.0018 | -0.0174 | 0.0225 | 0.0006 | [-0.0292, 0.0323] | 0.0009 | [-0.0293, 0.0303] | True | computed |
| h63(descriptive) | 5718 | 32031 | -0.0003 | -0.0140 | 0.0156 | -0.0101 | [-0.0349, 0.0164] | 0.0069 | [-0.0117, 0.0262] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 1539 | 23814 | 0.8577 | 0.8811 | -0.0234 | 2891.2 |
| dd_5_10 | 1378 | 3221 | 0.8999 | 0.9087 | -0.0089 | 1930.2 |
| dd_10_20 | 1631 | 3407 | 0.9105 | 0.8703 | 0.0402 | 2206.0 |
| dd_20plus | 1170 | 1835 | 0.9009 | 0.8926 | 0.0082 | 1428.9 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0053 (hostile n=2361, benign n=13961)

### A4_fin_conditions
**Description:** level >= 80th percentile of trailing 756-BD window  
**Coverage:** 1971-01-08 to 2026-06-26 (weekly, ffill to BD)  
**Total episodes:** 28  
**OOS midpoint:** 1998-10-02  
**Verdict (h21):** P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half)  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 15350 | 38778 | -0.0039 | -0.0169 | 0.0093 | 0.0016 | [-0.0192, 0.0211] | -0.0045 | [-0.0205, 0.0122] | True | computed |
| h21(verdict) | 15350 | 38677 | -0.0068 | -0.0190 | 0.0060 | 0.0033 | [-0.0179, 0.0241] | -0.0116 | [-0.0270, 0.0034] | True | computed |
| h63(descriptive) | 15350 | 38431 | -0.0105 | -0.0197 | -0.0005 | -0.0058 | [-0.0224, 0.0112] | -0.0132 | [-0.0250, -0.0013] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 10019 | 31078 | 0.8720 | 0.8776 | -0.0055 | 15153.0 |
| dd_5_10 | 2128 | 2759 | 0.9074 | 0.9087 | -0.0012 | 2402.8 |
| dd_10_20 | 2123 | 2915 | 0.8738 | 0.8902 | -0.0165 | 2456.7 |
| dd_20plus | 1080 | 1925 | 0.8870 | 0.9008 | -0.0137 | 1383.7 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0076 (hostile n=4507, benign n=11815)

---

## Summary: h21 verdict per axis

| Axis | Verdict | Stratified delta | 95% CI | H1 CI excludes 0 | H2 CI excludes 0 |
|---|---|---|---|---|---|
| A1_rates_shock | P0-PASS | -0.0349 | [-0.0484, -0.0218] | True | True |
| A2_usd_shock | P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half) | -0.0032 | [-0.0210, 0.0170] | False | False |
| A3_credit_shock | P0-FAIL (BH_fail, CI_includes_0_in_a_half) | 0.0018 | [-0.0174, 0.0225] | False | False |
| A4_fin_conditions | P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half) | -0.0068 | [-0.0190, 0.0060] | False | False |

---

## Pre-committed branches

- **P0-PASS(axis):** that axis re-opens the L6 charter question at the docket (two-lobe cap + separate masterplan+prereg still required; no live flag, chip, world_state key, or per-name output ships from this study).
- **P0-FAIL:** null printed; L6 stays gated; noisy-sector precedent stands as honest ceiling.
- **P0-DEFER:** floors or data unmet; achieved counts printed above with come-back condition.

---

*Opus stats review required before verdict is acted on. Fable adjudicates. This report is a contamination surface: any later prereg on this tape carries `derived_from_surface: macro_tx_phase0_v1`.*