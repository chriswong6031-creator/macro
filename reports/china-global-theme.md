# Does global AI-narrative momentum predict next-week CN AI-supply baskets?

EW 4w log-momentum of SMH+SOXX+TSM -> next-week EW return of each THS AI basket. Weekly W-FRI, Newey-West HAC t (lags=4). uni = univariate; mv = with SPY + CN-universe 4w-mom controls (the horse race). Placebo = baijiu/gold/innovative-rx.

KEY TEST = does the semis t survive in **pre-2024** (not just the 2024+ AI run)?

```
basket            era         n   uni_b  uni_t  uni_p mv_semis_t mv_spy_t mv_cn_t
---------------------------------------------------------------------------------
ths_ai            full      241  0.0494   1.77 0.0776       1.02    -0.46    0.68
ths_ai            pre-2024  117  0.0498    1.5 0.1351       1.22    -0.86    0.29
ths_ai            2024+     124  0.0306   0.65 0.5138      -0.09      0.4    0.31

ths_cpo           full      241   0.089   3.27 0.0012       2.27    -1.17    0.27
ths_cpo           pre-2024  117  0.0975   3.03 0.0031       2.06     -1.2   -0.03
ths_cpo           2024+     124  0.0626   1.36 0.1765       0.88    -0.24    0.09

ths_pcb           full      241  0.0815   2.93 0.0037       1.74    -0.76    0.48
ths_pcb           pre-2024  117   0.063   1.99 0.0487       1.38    -0.81    0.13
ths_pcb           2024+     124  0.0787   1.78 0.0774       0.81    -0.04    0.25

ths_storage_chip  full      241  0.0844   2.49 0.0136       1.94    -1.38    0.32
ths_storage_chip  pre-2024  117  0.0361   0.92 0.3586       0.85    -0.66    0.01
ths_storage_chip  2024+     124  0.1054   2.26 0.0257       1.69    -1.12    0.36

ths_adv_pkg       full      241  0.0825   2.55 0.0114       1.82    -1.16    0.38
ths_adv_pkg       pre-2024  117  0.0318   0.81 0.4211       0.75    -0.57    0.18
ths_adv_pkg       2024+     124  0.1121   2.55  0.012       1.56     -0.9    0.37

ths_liquid_cool   full      241  0.0462   1.84 0.0672       1.36    -0.87    0.61
ths_liquid_cool   pre-2024  117  0.0157   0.54 0.5926       0.82     -1.0    0.77
ths_liquid_cool   2024+     124  0.0585   1.53 0.1284        0.6     0.09    0.08

ths_aidc          full      241  0.0497   1.75  0.082       1.45    -1.04    0.55
ths_aidc          pre-2024  117  0.0408    1.1 0.2726       1.14     -1.0    0.34
ths_aidc          2024+     124  0.0402   0.89 0.3776       0.59    -0.26    0.24

ths_baijiu        full      241 -0.0012  -0.06 0.9561        0.1    -0.22    0.25
ths_baijiu        pre-2024  117  0.0618   2.33 0.0217       2.24    -1.25    0.09
ths_baijiu        2024+     124 -0.0523  -1.56 0.1211      -1.69      1.2   -0.02

ths_gold          full      241  0.0495   1.86 0.0646       0.67     0.21    1.24
ths_gold          pre-2024  117   0.059   2.28 0.0244       0.89     0.14     0.5
ths_gold          2024+     124   0.034   0.81  0.422       0.17     0.17    0.99

ths_innovative_rx full      241 -0.0086  -0.36 0.7174      -0.32     0.15   -0.03
ths_innovative_rx pre-2024  117 -0.0095  -0.35 0.7284      -0.06     -0.4    0.87
ths_innovative_rx 2024+     124 -0.0163  -0.44 0.6633      -1.06     0.94   -0.87

```
