# W2-C — Global-healthcare -> CN-pharma read-through — Phase-0 Report

Mirror of the validated global-AI-semis -> CN-CPO weekly confirmer (#773, reports/china-global-theme.md, phase0-verdicts row 14). XLV (primary) / XLV+IBB+XBI (robustness) 4w log-momentum -> next-week return of the Shenwan L1 Pharma index (801150, survivorship-clean) and three THS pharma baskets. Weekly W-FRI, Newey-West HAC t (lags=4). uni = univariate; mv = with SPY + CN-universe controls (horse race).

DESCRIPTIVE positioning lens (§754/§773), NOT validated alpha, NOT a buy list. NOTHING wired to any page regardless of outcome.

PRE-REGISTERED GATE — GO: uni full |t|>=3 AND pre-2024 |t|>=2 AND horse-race |t|>=2 (swind_801150). ACCRUE: 2<=|t|<3 full OR 2024+-only. NO-GO otherwise.

**MACHINE VERDICT: NO-GO**  (uni_full_t=-0.48, uni_pre_t=-0.59, uni_2024+_t=-0.09, mv_full_t=-0.49)

```
W2-C · global-healthcare 4w-mom -> next-week CN pharma return (mirror of #773 AI-semis->CPO)
weekly W-FRI · NW-HAC t (lags=4) · horse-race controls = SPY 4w-mom + CN-universe 4w-mom
driver = XLV (PRIMARY). uni_* = univariate HC; mv_hc_t = HC t WITH SPY+CN controls.

== PRIMARY DRIVER: XLV (US Health Care Select Sector) ==
target            era         n   uni_b  uni_t  uni_p   mv_hc_t mv_spy_t mv_cn_t
--------------------------------------------------------------------------------
swind_801150      full      239 -0.0255  -0.48 0.6345     -0.49     0.17    0.15
swind_801150      pre-2024  115  -0.041  -0.59 0.5557     -0.63     0.11    0.82
swind_801150      2024+     124 -0.0074  -0.09 0.9282     -0.15     0.19   -0.47

ths_innovative_rx full      241 -0.0119  -0.11 0.9092      0.28    -0.65   -0.13
ths_innovative_rx pre-2024  117 -0.0015  -0.01 0.9887     -0.08     0.07    0.22
ths_innovative_rx 2024+     124 -0.0238  -0.13 0.8944      0.17    -0.87   -0.34

ths_synbio        full      241  0.0317   0.41 0.6799     -0.16     1.25     0.1
ths_synbio        pre-2024  117  0.0369   0.33 0.7445     -0.15     0.58    0.76
ths_synbio        2024+     124  0.0254   0.24 0.8103      -0.0     1.02   -0.55

ths_med_devices   full      241 -0.0096  -0.13 0.8938     -0.69     1.16    0.51
ths_med_devices   pre-2024  117 -0.0973   -1.2 0.2328     -1.89     1.34    0.59
ths_med_devices   2024+     124  0.0896   0.81 0.4205      0.42      1.3    0.11

ths_baijiu        full      241 -0.0272  -0.43 0.6702     -0.43    -0.04    0.26
ths_baijiu        pre-2024  117 -0.0549  -0.53 0.5948     -1.53     1.45    0.53
ths_baijiu        2024+     124  0.0043   0.07 0.9483      0.34    -0.88    0.08

ths_gold          full      241  0.0787   1.52 0.1289      0.73     0.63    1.29
ths_gold          pre-2024  117   0.055   0.81 0.4186     -0.35     1.18    0.91
ths_gold          2024+     124  0.1054   1.29 0.1983       1.2     0.21    0.92

ths_cpo           full      241 -0.0415  -0.49 0.6281     -1.25      1.7    0.31
ths_cpo           pre-2024  117 -0.1209  -1.07 0.2871     -2.73      3.1    0.49
ths_cpo           2024+     124  0.0481    0.4 0.6911       0.2     0.61    0.01

== ROBUSTNESS DRIVER: XLV+IBB+XBI composite (mirrors 3-name semis composite) ==
target            era         n   uni_b  uni_t  uni_p   mv_hc_t mv_spy_t mv_cn_t
--------------------------------------------------------------------------------
swind_801150      full      239   0.005   0.13 0.8959       0.2    -0.22    0.21
swind_801150      pre-2024  115  0.0002    0.0 0.9967      0.18    -0.47    0.85
swind_801150      2024+     124  0.0033   0.05 0.9587      0.02     0.12   -0.44

ths_innovative_rx full      241 -0.0115  -0.15 0.8816      0.34    -0.64   -0.18
ths_innovative_rx pre-2024  117 -0.0017  -0.02 0.9823     -0.11      0.1    0.23
ths_innovative_rx 2024+     124 -0.0431  -0.29 0.7709      0.23    -0.77   -0.36

ths_synbio        full      241  0.0291   0.57 0.5712     -0.18     1.09    0.12
ths_synbio        pre-2024  117  0.0146    0.2  0.839     -0.44      0.7     0.8
ths_synbio        2024+     124  0.0305   0.41  0.682      0.02     0.93   -0.54

ths_med_devices   full      241  0.0305   0.63 0.5295     -0.08      0.7    0.56
ths_med_devices   pre-2024  117 -0.0361  -0.68 0.4957     -0.77     0.36    0.66
ths_med_devices   2024+     124    0.11   1.34  0.182       0.6     0.93    0.08

== SHUFFLED-DRIVER PLACEBO: 2000-permutation null (seed=773), XLV-mom -> swind_801150 ==
real uni_t = 1.68  |  null: mean=0.015 sd=0.993  P(|t_null|>=2)=0.041  perm_p(real)=0.085
(a valid null centers on 0 sd~1; real t sits at an unremarkable percentile => no genuine lead)

== POSITIVE CONTROL: same harness, known-good semis->ths_cpo (must fire) ==
semis->cpo uni_t full=3.08 pre-2024=3.12  (published #773: 3.27 / 3.03) => instrument confirmed live

== SECONDARY: literal HC-momentum SIGN vs next-week CN-pharma return (swind_801150) ==
era          n  sign_hit  up_mean%  dn_mean%  welch_t
full      1302     0.528     0.328     0.012     1.49
pre-2024  1176     0.536     0.384    -0.019      1.8
2024+      126      0.46    -0.245     0.263     -0.8

== PRE-REGISTERED MACHINE VERDICT (swind_801150, XLV primary) ==
uni_full_t=-0.48  uni_pre_t=-0.59  uni_2024+_t=-0.09  mv_full_t=-0.49
VERDICT: NO-GO
```
