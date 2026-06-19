# Commodity xsec momentum — adversarial refutation

```
====================================================================================================
ADVERSARIAL REFUTATION — commodity xsec momentum
====================================================================================================

### (1) LOOKAHEAD — independent IC re-derivation (signal strictly past, fwd strictly future)
  mom_12_1 [overlapping 21d-rebal       ] mean_IC=-0.0181  t_NW=-1.01  p=0.314  n=271
  mom_12_1 [NON-overlapping (rebal=h=21)] mean_IC=-0.0181  t_NW=-1.01  p=0.314  n=271
  NULL check (shuffle fwd across names): mean_IC=+0.0120 (should be ~0) n=271

### (2) DATA — continuous-contract splice/roll-gap detector (daily log-ret outliers)
  leg        maxAbsDayMove #|move|>25% #|move|>40%  (roll-gap / splice symptom)
  gold              12.8%           0           0
  silver            45.7%           1           1
  copper            28.6%           1           0
  platinum          76.9%           2           1
  palladium         26.4%           2           0
  wti               37.7%           5           0
  brent             32.3%           2           0
  natgas            90.4%          10           2
  heatoil           28.1%           1           0
  rbob              47.0%           5           1
  corn              30.8%           1           0
  soybean           26.4%           1           0
  wheat             21.8%           0           0
  coffee            18.1%           0           0
  cotton            31.4%           1           0
  sugar             26.6%           1           0
  cocoa             29.8%           1           0
  cattle            16.9%           0           0
  hogs              31.2%           5           0
  survivorship: last valid date per leg —
    delisted/stale legs (>10d behind last index date): NONE (no survivorship gap)

### (3) MULTIPLE-TESTING — honest n_trials = lookbacks x rebal x (tercile|quintile)
  honest n_trials = 5lb x 3rebal x 2frac = 30 configs
  grid Sharpes: [-0.52, -0.66, -0.4, -0.64, -0.4, -0.6, -0.35, -0.33, -0.29, -0.33, -0.22, -0.22, -0.39, -0.31, -0.29, -0.33, -0.25, -0.19, -0.48, -0.38, -0.5, -0.41, -0.25, -0.42, -0.42, -0.49, -0.39, -0.4, -0.51, -0.48]
  BEST config lb=252 skip=0 rebal=21 frac=5 -> Sharpe=-0.194
  BEST-of-30 DSR=0.0013 (SR_ann=-0.19) -> FAILS multiple-testing haircut (DSR<0.90)
  ALL 30 grid Sharpes positive? False   any>0? False  max=-0.194

### (4) BASELINE — does ANY momentum variant beat EW-long & 200dma? (gross AND net)
  baselines: EW-long Sharpe=+0.636   200dma Sharpe=+0.177
  mom 12-1m : NET Sharpe=-0.218  GROSS Sharpe=-0.163  beats both baselines net? False
  mom 6-1m  : NET Sharpe=-0.403  GROSS Sharpe=-0.325  beats both baselines net? False
  mom 12m   : NET Sharpe=-0.249  GROSS Sharpe=-0.183  beats both baselines net? False
  mom 3-1m  : NET Sharpe=-0.505  GROSS Sharpe=-0.365  beats both baselines net? False
  mom 1m    : NET Sharpe=-0.250  GROSS Sharpe=-0.078  beats both baselines net? False

### (5) HONEST-N — effective independent regimes
  IC series: n=271 monthly obs, AR(1)=-0.017  -> effective indep IC obs ~ 280
  cross-section width=19 -> terciles ~6 long/6 short; quintiles ~3/3 (very thin)
  => even a TRUE |IC|~0.05 with n_eff~280 gives t~0.84 — at the noise floor

### (6) REGIME/DECAY — supercycle 2002-2011 vs post-financialization 2011-2026
  supercycle 2002-2011  : L/S Sharpe=-0.456  mean_IC=-0.0299  n_ic=98
  post 2012-2026        : L/S Sharpe=-0.082  mean_IC=-0.0128  n_ic=161
  (if momentum were real-but-decayed, supercycle IC>0 then erodes; here check the sign)

====================================================================================================
REFUTATION VERDICT
====================================================================================================
```
