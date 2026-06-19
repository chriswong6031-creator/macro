# Levered active-commodity — Phase-0 (silver & copper)

Re-run of `engine.active_commodity.evaluate()` (net 3 bps + 1% financing on the levered part, 2000→2026) + the MISSING gate: deflated Sharpe on the LEVERED net series, leave-one-crisis-out, and beats-dumb-baseline (same-asset 200dma).

Honest n_trials headline = 30 (vol-target x leverage-cap x lookback x leg-structure search); reported across a sweep so the verdict is robust to the count.


## cm_silver_active (SI=F)

- full: CAGR **16.25** vs B&H 10.8 | Sharpe **0.69** vs 0.48 | MaxDD -64.6 vs -75.8 | avg_lev 0.91 max_lev 3.0
- split-half robust (beats CAGR both halves): **True**
- net moments: sr_daily 0.0432, skew 0.06, kurt 13.49, n 6477
- **DSR (n=30) = 0.9188** — MARGINAL (0.90≤DSR<0.95) (sr_ann 0.69, haircut sr0_ann 0.41)
- DSR sweep: n12=0.9645, n20=0.9418, n30=0.9188, n50=0.8838, n100=0.8263
- dumb 200dma baseline: CAGR 5.44 / Sharpe 0.34 / MaxDD -70.2 → model beats baseline: **True**
- leave-one-crisis-out all positive & beat B&H: **True** (min Sharpe 0.677)

## cm_copper_active (HG=F)

- full: CAGR **9.66** vs B&H 7.98 | Sharpe **0.54** vs 0.42 | MaxDD -60.6 vs -69.4 | avg_lev 0.75 max_lev 2.7
- split-half robust (beats CAGR both halves): **True**
- net moments: sr_daily 0.0340, skew 0.11, kurt 18.09, n 6480
- **DSR (n=30) = 0.7454** — FAILS multiple-testing haircut (DSR<0.90) (sr_ann 0.54, haircut sr0_ann 0.41)
- DSR sweep: n12=0.8574, n20=0.7975, n30=0.7454, n50=0.6763, n100=0.5804
- dumb 200dma baseline: CAGR 7.4 / Sharpe 0.45 / MaxDD -51.9 → model beats baseline: **True**
- leave-one-crisis-out all positive & beat B&H: **False** (min Sharpe 0.548)

## cm_gold_active (GC=F)

- full: CAGR **12.31** vs B&H 11.3 | Sharpe **0.76** vs 0.69 | MaxDD -33.4 vs -44.4 | avg_lev 0.92 max_lev 2.5
- split-half robust (beats CAGR both halves): **False**
- net moments: sr_daily 0.0480, skew -0.52, kurt 9.97, n 6475
- **DSR (n=30) = 0.9584** — SURVIVES multiple-testing (DSR≥0.95) (sr_ann 0.76, haircut sr0_ann 0.42)
- DSR sweep: n12=0.9839, n20=0.9716, n30=0.9584, n50=0.937, n100=0.899
- dumb 200dma baseline: CAGR 7.96 / Sharpe 0.59 / MaxDD -39.9 → model beats baseline: **True**
- leave-one-crisis-out all positive & beat B&H: **True** (min Sharpe 0.745)
