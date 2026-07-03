# W3-A — Abnormal-turnover cross-sectional signal — Phase-0 Report

Flagship of the volume program (F7). Tests whether ABNORMAL TURNOVER (volume-based proxy) predicts A-share returns — external evidence: low-abnormal-turnover long leg +1.24%/mo t=3.35 (2000-2019). Substrate `data/china_stocks_raw` (append-only, survivorship-clean, real volume). CSI300-relative excess, fill-realistic T+1 (H+L)/2 entries, locked-limit rows excluded, split/ex-div artifacts zeroed. **NOTHING wired to any page/board/rank regardless of outcome.**

PROXY: `abn_turn = ln(mean(vol,21d) / mean(vol,252d skip 21))`. Volume-z fallback for the float-normalised turnover ratio the paper uses (we lack historical float shares) — a within-name ratio so a constant float cancels; tests the MECHANISM, not the paper's point estimate.

PRE-REGISTERED GATE — GO: primary fill-realistic L/S |t|>=3 full AND sign-stable across BOTH era splits AND T2 residual |t|>=2 AND positive control fires. ACCRUE: 2<=|t|<3, or era-only, or residual borderline. NO-GO: |t|<2, or sign-unstable, or T2 residual |t|<2 (REDUNDANT-WITH-REVERSAL) regardless of raw t, or positive control fails.

**MACHINE VERDICT: NO-GO** — primary |t|=0.69<2 (null; placebo perm_p=0.511); also sign_stable=False, residual |t|=0.72<2 — redundant with reversal

```
W3-A abnormal-turnover phase-0 · substrate china_stocks_raw · CSI300-relative excess
universe 1279 names after filters (excluded {'history': 44, 'locked': 5, 'adv': 142, 'no_sector': 98}) · benchmark 2012-05-04->2026-07-03 · 169 monthly rebalances

== T1 · PRIMARY low-minus-high decile L/S (CSI300-relative, fill-realistic) ==
era           n    mean%   t_HAC  Sharpe   maxDD%    hit
full        169    0.362    0.69    0.18    -47.6  0.574
early        85    0.904    1.32    0.44    -44.9  0.647
late         84   -0.186   -0.24    -0.1    -47.6    0.5
pre-2024    140    0.623    1.17    0.32    -44.9  0.593
2024+        29   -0.896   -0.57   -0.42    -47.6  0.483
full·SN     169    0.296    0.73    0.19    -48.9  0.562

== T6 · fill-realistic vs close-to-close (full) ==
fill-realistic mean 0.362%/reb (t 0.69); close-to-close mean 0.331%/reb (t 0.57); grading tax = -0.031pp/reb

== T3 · decile monotonicity (mean CSI300-relative excess %/reb, D0=lowest abn_turn) ==
D0:0.801  D1:0.71  D2:0.896  D3:0.985  D4:0.899  D5:0.854  D6:0.968  D7:0.889  D8:0.912  D9:0.439
  Spearman(decile#, excess) = 0.079  (negative = low-abn-turn wins, monotone)

== T2 · ORTHOGONALITY vs within-sector 3M reversal (residual spread) ==
raw abn_turn spread   t_HAC 0.69  mean 0.362%  n 169
residual (⊥reversal)  t_HAC 0.72  mean 0.309%  n 169
=> REDUNDANT-WITH-REVERSAL (residual |t|<2)

== T5 · POSITIVE CONTROL: within-sector 3M reversal through same harness (must be > 0) ==
reversal high-minus-low spread  mean 0.638%  t_HAC 1.18  Sharpe 0.33  n 169  => instrument LIVE

== T4 · 2000-permutation placebo (seed=3) on primary L/S spread ==
real t_HAC 0.69  |  null mean 0.026 sd 1.053 perm_p 0.5115

== PRE-REGISTERED MACHINE VERDICT ==
VERDICT: NO-GO  (primary |t|=0.69<2 (null; placebo perm_p=0.511); also sign_stable=False, residual |t|=0.72<2 — redundant with reversal)
```

## Reading
- **T1 primary**: low-minus-high decile L/S full-sample t_HAC = 0.69 (mean 0.362%/reb). Positive = low-abnormal-turnover names outperform.
- **T2 orthogonality**: residual-vs-reversal t_HAC = 0.72 (REDUNDANT — the edge is the reversal factor on the volume plane).
- **T3 monotonicity**: Spearman(decile, excess) = 0.079.
- **T4 placebo**: perm_p = 0.5115 (null mean 0.026, sd 1.053).
- **T5 positive control**: reversal high-minus-low spread mean 0.638% t 1.18 => instrument LIVE.
- **T6 fill tax**: close-to-close 0.331%/reb vs fill-realistic 0.362%/reb.

Honest caveats: volume-z proxy (not the float-normalised ratio); raw plane is unadjusted so corporate-action days are zeroed in the return metric (not the signal); excess is gross of cost and abnormal-turnover is a high-turnover family (~254% in the source), so a positive gross spread still needs a net-of-cost pass before any wiring. CSI300-relative window starts 2012-05-04 (benchmark availability).
