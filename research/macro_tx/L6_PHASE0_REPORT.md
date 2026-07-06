# L6-P0 Macro-Transmission Phase-0 Report

**Run date:** 2026-07-06  
**Prereg:** research/macro_tx/L6_PHASE0_PREREG.md (frozen 2026-07-06)  
**Fire tape:** spine_index.parquet track_record, outcome_graded=True, horizons 5/21/63  
**Verdict horizon:** h21  
**Cumulative macro_tx trial count:** 12  
**S&P 500 drawdown source:** data/yahoo/_GSPC.parquet (S&P 500, range 1927-12-30 to 2026-06-12)  
**USD series source:** data/fred/DTWEXBGS.parquet (broad_dollar, FRED)  

---

## In plain English

> **What is being measured:** The outcome metric `hit` equals 1 when the signal achieved *any* positive favorable excursion versus the benchmark within 21 sessions of firing (i.e., `outcome_excess > 0`). The metric is floored at zero — it is an achieved-favorable-excursion indicator, not a signed return or a 'beat the market' measure. The base rate across all fires is approximately 88% (roughly 12% of fires never achieved any favorable excursion). The delta reported here measures how much MORE OFTEN hostile-window fires FAIL to achieve any favorable excursion compared to benign-window fires. A negative delta means hostile fires reach favorable excursion less often than benign fires.  
>
> **What is being asked:** When a macro condition is hostile at the time a signal fires — when rates are rising fast, the dollar is surging, credit spreads are blowing out, or financial conditions are tight — does the signal's favorable excursion rate change versus normal times? Each macro axis is tested separately (never combined). The verdict requires the hostile-vs-benign gap to be stable across two time periods AND the bootstrap confidence interval to exclude zero in both periods.  
>
> **Family composition caveat:** The spine fires are drawn from four signal families (sell, buy, cut, rebuy) in unequal proportions. The hostile arm may have a different mix of these families than the benign arm. The pooled stratified delta is NOT decomposed for family mix — part of the observed delta may reflect composition differences rather than macro transmission. Per-family within-deltas are reported descriptively; treat them as hypothesis-generating, not as verdicts.  
>
> Any axis that passes this gate re-opens the question of whether macro conditioning should be wired into the signal engine (subject to further approval and a separate masterplan). A fail means the gap is not reliably there. Either outcome is informative and is printed honestly.

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
| h5(descriptive) | 9114 | 46272 | -0.0379 | -0.0598 | -0.0176 | -0.0707 | [-0.1044, -0.0376] | -0.0305 | [-0.0566, -0.0050] | True | computed |
| h21(verdict) | 9114 | 46171 | -0.0340 | -0.0514 | -0.0171 | -0.0513 | [-0.0798, -0.0238] | -0.0295 | [-0.0517, -0.0078] | True | computed |
| h63(descriptive) | 9021 | 46018 | -0.0254 | -0.0389 | -0.0119 | -0.0388 | [-0.0628, -0.0156] | -0.0217 | [-0.0382, -0.0060] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 4881 | 30822 | 0.8459 | 0.8809 | -0.0350 | 8427.4 |
| dd_5_10 | 1653 | 6106 | 0.8820 | 0.8998 | -0.0177 | 2601.7 |
| dd_10_20 | 1488 | 6017 | 0.8179 | 0.8906 | -0.0728 | 2386.0 |
| dd_20plus | 1092 | 3226 | 0.8947 | 0.8924 | 0.0023 | 1631.7 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0464 (hostile n=3365, benign n=12957)

#### Family composition and within-family deltas (h21, descriptive)

| Family | N hostile | N benign | Hostile share | Benign share | Within-family delta |
|---|---|---|---|---|---|
| buy | 3238 | 17922 | 0.3553 | 0.3882 | -0.0055 |
| cut | 679 | 3472 | 0.0745 | 0.0752 | -0.0733 |
| rebuy | 804 | 4415 | 0.0882 | 0.0956 | -0.0201 |
| sell | 4393 | 20362 | 0.4820 | 0.4410 | -0.0380 |

> **Composition caveat:** The hostile and benign arms may have different mixes of signal families (sell/buy/cut/rebuy). The pooled stratified delta above is not decomposed for this composition effect — part of the observed delta may reflect which families fire more often during hostile windows, not pure macro transmission. Within-family deltas are descriptive only and do not carry verdict status.

### A2_usd_shock
**Description:** 20-BD return >=+1.5σ AND >=+2.0%  
**Coverage:** 2006-01-02 to 2026-06-26  
**Total episodes:** 44  
**OOS midpoint:** 2016-03-30  
**Verdict (h21):** P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half)  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 5152 | 22850 | 0.0001 | -0.0260 | 0.0272 | 0.0029 | [-0.0367, 0.0406] | -0.0032 | [-0.0436, 0.0381] | True | computed |
| h21(verdict) | 5152 | 22749 | -0.0040 | -0.0284 | 0.0197 | -0.0152 | [-0.0587, 0.0252] | 0.0077 | [-0.0210, 0.0389] | True | computed |
| h63(descriptive) | 5109 | 22546 | -0.0085 | -0.0284 | 0.0101 | -0.0213 | [-0.0607, 0.0131] | 0.0036 | [-0.0133, 0.0212] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 2457 | 16546 | 0.8824 | 0.8791 | 0.0033 | 4278.6 |
| dd_5_10 | 816 | 2852 | 0.9167 | 0.9039 | 0.0127 | 1268.9 |
| dd_10_20 | 968 | 2478 | 0.8750 | 0.8902 | -0.0152 | 1392.2 |
| dd_20plus | 911 | 873 | 0.8804 | 0.9255 | -0.0452 | 891.6 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0037 (hostile n=3392, benign n=12930)

#### Family composition and within-family deltas (h21, descriptive)

| Family | N hostile | N benign | Hostile share | Benign share | Within-family delta |
|---|---|---|---|---|---|
| buy | 2182 | 8427 | 0.4235 | 0.3704 | -0.0059 |
| cut | 388 | 1746 | 0.0753 | 0.0768 | 0.0006 |
| rebuy | 471 | 2137 | 0.0914 | 0.0939 | 0.0013 |
| sell | 2111 | 10439 | 0.4097 | 0.4589 | -0.0057 |

> **Composition caveat:** The hostile and benign arms may have different mixes of signal families (sell/buy/cut/rebuy). The pooled stratified delta above is not decomposed for this composition effect — part of the observed delta may reflect which families fire more often during hostile windows, not pure macro transmission. Within-family deltas are descriptive only and do not carry verdict status.

### A3_credit_shock
**Description:** 20-BD change >=+1.5σ AND >=+50 bp  
**Coverage:** 1996-12-31 to 2026-07-02  
**Total episodes:** 35  
**OOS midpoint:** 2011-10-01  
**Verdict (h21):** P0-FAIL (BH_fail, CI_includes_0_in_a_half)  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 5718 | 32378 | -0.0045 | -0.0331 | 0.0250 | -0.0031 | [-0.0442, 0.0430] | -0.0073 | [-0.0500, 0.0354] | True | computed |
| h21(verdict) | 5718 | 32277 | 0.0020 | -0.0240 | 0.0281 | 0.0011 | [-0.0405, 0.0387] | 0.0020 | [-0.0371, 0.0400] | True | computed |
| h63(descriptive) | 5718 | 32031 | 0.0001 | -0.0199 | 0.0190 | -0.0095 | [-0.0471, 0.0199] | 0.0074 | [-0.0180, 0.0302] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 1419 | 23230 | 0.8541 | 0.8807 | -0.0265 | 2674.6 |
| dd_5_10 | 1366 | 3526 | 0.8997 | 0.9132 | -0.0135 | 1969.1 |
| dd_10_20 | 1665 | 3369 | 0.9165 | 0.8641 | 0.0525 | 2228.6 |
| dd_20plus | 1268 | 2152 | 0.8927 | 0.8941 | -0.0013 | 1595.8 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0032 (hostile n=2361, benign n=13961)

#### Family composition and within-family deltas (h21, descriptive)

| Family | N hostile | N benign | Hostile share | Benign share | Within-family delta |
|---|---|---|---|---|---|
| buy | 2959 | 11611 | 0.5175 | 0.3597 | 0.0012 |
| cut | 486 | 2396 | 0.0850 | 0.0742 | 0.0050 |
| rebuy | 390 | 3171 | 0.0682 | 0.0982 | -0.0147 |
| sell | 1883 | 15099 | 0.3293 | 0.4678 | -0.0129 |

> **Composition caveat:** The hostile and benign arms may have different mixes of signal families (sell/buy/cut/rebuy). The pooled stratified delta above is not decomposed for this composition effect — part of the observed delta may reflect which families fire more often during hostile windows, not pure macro transmission. Within-family deltas are descriptive only and do not carry verdict status.

### A4_fin_conditions
**Description:** level >= 80th percentile of trailing 756-BD window  
**Coverage:** 1971-01-08 to 2026-06-26 (weekly, ffill to BD)  
**Total episodes:** 28  
**OOS midpoint:** 1998-10-02  
**Verdict (h21):** P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half)  

#### Cell table (all 3 horizons)

| Horizon | N hostile | N benign | Strat delta | CI low | CI high | H1 delta | H1 CI | H2 delta | H2 CI | Floor | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h5(descriptive) | 15350 | 38778 | -0.0024 | -0.0189 | 0.0144 | 0.0032 | [-0.0253, 0.0306] | -0.0051 | [-0.0266, 0.0151] | True | computed |
| h21(verdict) | 15350 | 38677 | -0.0063 | -0.0223 | 0.0093 | 0.0039 | [-0.0254, 0.0323] | -0.0120 | [-0.0318, 0.0068] | True | computed |
| h63(descriptive) | 15350 | 38431 | -0.0104 | -0.0230 | 0.0023 | -0.0045 | [-0.0285, 0.0176] | -0.0135 | [-0.0301, 0.0021] | True | computed |

#### Per-stratum table (h21)

| Stratum | N hostile | N benign | Hit hostile | Hit benign | Delta | Harmonic N |
|---|---|---|---|---|---|---|
| dd_0_5 | 7899 | 27054 | 0.8707 | 0.8778 | -0.0071 | 12227.8 |
| dd_5_10 | 2888 | 4652 | 0.8965 | 0.9000 | -0.0036 | 3563.7 |
| dd_10_20 | 2814 | 4454 | 0.8742 | 0.8785 | -0.0043 | 3449.0 |
| dd_20plus | 1749 | 2517 | 0.8885 | 0.8983 | -0.0098 | 2063.9 |

#### Modern cohort sensitivity (>=2015, h21)

Modern delta: -0.0087 (hostile n=4507, benign n=11815)

#### Family composition and within-family deltas (h21, descriptive)

| Family | N hostile | N benign | Hostile share | Benign share | Within-family delta |
|---|---|---|---|---|---|
| buy | 6563 | 14107 | 0.4276 | 0.3647 | -0.0028 |
| cut | 1251 | 2808 | 0.0815 | 0.0726 | -0.0065 |
| rebuy | 1398 | 3719 | 0.0911 | 0.0962 | -0.0110 |
| sell | 6138 | 18043 | 0.3999 | 0.4665 | -0.0165 |

> **Composition caveat:** The hostile and benign arms may have different mixes of signal families (sell/buy/cut/rebuy). The pooled stratified delta above is not decomposed for this composition effect — part of the observed delta may reflect which families fire more often during hostile windows, not pure macro transmission. Within-family deltas are descriptive only and do not carry verdict status.

---

## Summary: h21 verdict per axis

| Axis | Verdict | Stratified delta | 95% CI | H1 CI excludes 0 | H2 CI excludes 0 |
|---|---|---|---|---|---|
| A1_rates_shock | P0-PASS | -0.0340 | [-0.0514, -0.0171] | True | True |
| A2_usd_shock | P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half) | -0.0040 | [-0.0284, 0.0197] | False | False |
| A3_credit_shock | P0-FAIL (BH_fail, CI_includes_0_in_a_half) | 0.0020 | [-0.0240, 0.0281] | False | False |
| A4_fin_conditions | P0-FAIL (BH_fail, sign_unstable, CI_includes_0_in_a_half) | -0.0063 | [-0.0223, 0.0093] | False | False |

---

## Pre-committed branches

- **P0-PASS(axis):** that axis re-opens the L6 charter question at the docket (two-lobe cap + separate masterplan+prereg still required; no live flag, chip, world_state key, or per-name output ships from this study).
- **P0-FAIL:** null printed; L6 stays gated; noisy-sector precedent stands as honest ceiling.
- **P0-DEFER:** floors or data unmet; achieved counts printed above with come-back condition.

---

*Opus stats review required before verdict is acted on. Fable adjudicates. This report is a contamination surface: any later prereg on this tape carries `derived_from_surface: macro_tx_phase0_v1`.*