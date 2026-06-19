# BTC on-chain valuation DRAWDOWN gauge — Phase-0

- Sample: 2010-07-18 -> 2026-06-17 (15.9y), 5814 daily bars; composite valid 5392 obs from 2011-09-13.
- Signal: rolling-1460d (4.0y) percentile of MVRV & Reserve Risk, composite = mean. Target: forward [21, 63, 126] max-drawdown.

## 1. Forward max-drawdown IC (composite -> fwd_mdd), BH-FDR

Sign hypothesis: NEGATIVE Spearman (rich valuation -> deeper drawdown). Sampled every `h` days to limit overlap; ic_summary uses NW-HAC.

- fwd 21d: full-sample Spearman = **-0.089** (n=5391)  |  per-block mean_ic=-0.6169, IC-IR=-1.607, t_HAC=-24.215, p_HAC=0.0, hit=0.09, blocks=256
- fwd 63d: full-sample Spearman = **-0.134** (n=5391)  |  per-block mean_ic=-0.6138, IC-IR=-1.642, t_HAC=-17.566, p_HAC=0.0, hit=0.071, blocks=85
- fwd126d: full-sample Spearman = **-0.166** (n=5391)  |  per-block mean_ic=-0.5618, IC-IR=-1.534, t_HAC=-10.88, p_HAC=0.0, hit=0.095, blocks=42

BH-FDR (q<=0.10) across horizons:
  - fwd126: p=0.0, q=0.0, reject_null=True
  - fwd63: p=0.0, q=0.0, reject_null=True
  - fwd21: p=0.0, q=0.0, reject_null=True

=> FDR any-horizon reject: True; all-horizons NEGATIVE sign: True

## 2. Split-half stability (fwd63d, sign + magnitude)

- first half  (2011-09-13->2019-01-28): Spearman -0.105
- second half (2019-01-29->2026-06-16): Spearman -0.169
=> same-sign(&neg)=True; |Δmag|=0.063 same-magnitude=True

## 3. Purged-fold sign consistency (fwd63d, k=5, embargo=63)

  - fold1 (2011-09-13->2014-06-23, n=1015): -0.171
  - fold2 (2014-08-26->2017-06-05, n=1015): +0.171
  - fold3 (2017-08-08->2020-05-18, n=1015): -0.333
  - fold4 (2020-07-21->2023-05-01, n=1015): -0.175
  - fold5 (2023-07-04->2026-04-14, n=1016): -0.159
=> all non-empty folds NEGATIVE: False (4/5)

## 4. Leave-one-crisis-out (drop each crash year, fwd63 Spearman holds)

- full-sample fwd63 Spearman: -0.134
  - drop 2013 (n=5026): -0.132  sign-holds=True
  - drop 2018 (n=5026): -0.096  sign-holds=True
  - drop 2022 (n=5026): -0.164  sign-holds=True
=> leave-one-crisis-out (all stay NEGATIVE): True

## 5. Honest-N (independent crash clusters)

- deep (fwd63 mdd<-30%) obs: 856; distinct clusters (>120d gap): 12
- => EFFECTIVE independent stress episodes ~ 12; raw n=5391 is massively overlapping. Judge sign/ordering, not t-magnitude.

## 6. De-risk overlay vs dumb baselines (drawdown reduction)

- buy&hold    : CAGR   87.96%  Sharpe   1.0  MaxDD  -84.5%  time_in_mkt 100.0%
- onchain p80 : CAGR   38.71%  Sharpe   0.7  MaxDD  -78.2%  time_in_mkt 100.0%
- 200dma      : CAGR   90.62%  Sharpe  1.11  MaxDD  -71.7%  time_in_mkt 100.0%
- vol p80     : CAGR    73.2%  Sharpe  0.97  MaxDD  -80.3%  time_in_mkt 100.0%

- drawdown REDUCTION vs hodl (pp, +=shallower): onchain -6.4  |  200dma -12.8  |  vol -4.3
- onchain MaxDD shallower than 200dma: False; than vol-timer: True
- trend-only MaxDD -71.7%  vs  trend-OR-onchain MaxDD -60.9% (Sharpe 0.84 vs trend 1.11)
  => on-chain ADDS drawdown protection on top of trend: True (but at lower Sharpe — protection is not free)

## 7. DSR + bootstrap CI of the overlay vs hodl

- overlay net Sharpe(ann365)=0.84  DSR=0.9109  sr0=0.49  T=5392  n_trials=18
  => MARGINAL (0.90≤DSR<0.95)
- split-half overlay vs hodl: first beats_cagr=False (strat 38.71 vs 137.17), second beats_cagr=False (strat 38.74 vs 49.0); robust=False
- rolling-63d dd-reduction bootstrap (overlay-hodl): mean +1.51pp  CI95 [+0.81, +2.32]pp  excludes-0=True

## VERDICT — gate tally

  [PASS] FDR any-horizon q<=0.10
  [PASS] all-horizons NEGATIVE sign
  [PASS] split-half same-sign(neg)
  [PASS] split-half same-magnitude(<0.10)
  [FAIL] purged-folds all negative
  [PASS] leave-one-crisis-out holds
  [FAIL] overlay beats 200dma (shallower MaxDD)
  [PASS] overlay beats vol-timer (shallower MaxDD)
  [PASS] overlay DSR>=0.90
  [PASS] dd-reduction CI excludes 0

- honest-N: ~12 independent crash clusters (NOT 5329 rows).
