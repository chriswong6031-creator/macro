# SLF-051 — Market-Level Margin Impulse Phase-0

**Family:** `slf051_cn_margin_impulse` | **Framing:** R3-legal de-escalation/conditioning gate — no escalation fused

**Run date:** 2026-07-06 | **Signal lag:** 2 calendar days (conservative PIT; publication T+1 + extra buffer)

**Index:** CSI300 ETF 510300.SS | **Sample:** 2012-05-04 – 2026-07-03 (3427 trading days)

**Margin data:** balance.parquet rows=3,947 (2010-03-31 – 2026-07-02); daily_trade.parquet rows=3,014 (2014-02-11 – 2026-07-02)

  sig_roc20: 3427 non-null obs on trading calendar
  sig_roc60: 3427 non-null obs on trading calendar
  sig_turnrat_z: 2939 non-null obs on trading calendar
  sig_washout: 3427 non-null obs on trading calendar

## Pre-Registered Gates

| Gate | Description |
|------|-------------|
| G1 | Pre-registered direction holds with |t_HAC|>=2; BH-FDR q<=0.10 across 4x2 signal-horizon family |
| G2 | Washout de-escalation signal beats CSI300-below-200dma dumb baseline for 21d/63d forward return mean |
| G3 | Leave-one-cycle-out {2015 deleveraging, 2018 bear, 2020, 2024-09 stimulus}: same-sign in each sub-period |
| G4 | Split-half same-sign: top-decile mean fwd return same sign in both halves of sample |

## Signal Definitions and PIT Discipline

- **sig_roc20**: 20d % change of margin_total balance. Publication lag: +2 calendar days applied to all signals.
  Pre-registered direction: top decile -> **negative** fwd returns (crash-risk).

- **sig_roc60**: 60d % change of margin_total balance. Same lag.   Pre-registered direction: top decile -> **negative** fwd returns (crash-risk).

- **sig_turnrat_z**: margin_total / rolling-20d avg of market turnover (market turnover = margin_trade_amt / (trade_amt_ratio/100), per pre-registered spec), 252d z-score. Measures balance crowding relative to total market activity. Same lag.   Pre-registered direction: top decile -> **negative** fwd returns (crash-risk).
  Construction note: trade_amt_ratio is margin_trade_amt as % of total market turnover;   dividing recovers absolute turnover. An earlier draft used trade_amt_ratio directly   as denominator (correlation 0.185 with correct denominator) — that deviation is now   corrected to match the pre-registered spec.

- **sig_washout**: Binary: balance < trailing 252d 20th percentile AND 20d ROC > 0.   Pre-registered direction: state==1 -> **positive** fwd 21d/63d returns (de-escalation).

## Decile Analysis — Crash-Risk Signals (top decile -> negative fwd)

```
signal-horizon           n  top_dec_mean  bot_dec_mean    spread   t_HAC   p_HAC  dir_ok
roc20_21d             3406       1.0640%       1.1580%  -0.0940%    1.10  0.2723      NO
roc20_63d             3364       3.0740%       3.2530%  -0.1790%    1.36  0.1752      NO
roc60_21d             3406       2.4240%      -0.1300%   2.5550%    1.85  0.0646      NO
roc60_63d             3364       7.2920%       0.3680%   6.9230%    2.58  0.0099      NO
turnrat_z_21d         2918       2.9040%      -0.5890%   3.4930%    3.89  0.0001      NO
turnrat_z_63d         2876       1.7920%       0.8990%   0.8930%    1.70  0.0897      NO
```

## Washout-Then-Rising Event Study (De-escalation)

Washout fire count: 114 dates (out of 3427 valid signal obs)

```
  21d: mean fwd = -0.9090%  t_HAC = -1.21  p = 0.2281  dir_ok = False
  63d: mean fwd = 0.6360%  t_HAC = 0.36  p = 0.7213  dir_ok = True
```

## Diagnostic: Why Crash-Risk Return Direction Fails

**Key finding:** Top-decile ROC signals show *positive* mean forward returns, opposite to the pre-registered direction. The mechanism: rapid margin balance growth coincides with bull-market momentum phases. When leverage is surging, markets are usually already running — so 21d/63d mean returns are positive, not negative. The crash-risk framing assumes a contrarian reversal that does not manifest in mean returns over this 2012-2026 sample.

**However:** The drawdown metric tells a different story (see next section). High ROC is associated with *significantly worse* max drawdowns over the same 63d window — the market goes up more on average, but suffers larger interim pullbacks. This means the signal captures fragility rather than direction, a distinction the pre-registered direction for fwd-mean-returns did not accommodate.

**Implication for future work:** If re-registered, the crash-risk framing should target drawdown probability (AUC gate) rather than signed forward returns. roc60 x fwd_return passes BH (q=0.079) but fails direction — re-registering with drawdown-probability direction would likely yield G1-pass.

## Drawdown Elevation — Crash-Risk Signals (top decile vs rest: fwd 63d max-DD)

```
signal           n_top  n_bot    top_dd    bot_dd   t_HAC  dir_ok
roc20              343   3021  -9.2980%  -5.8110%   -8.35     YES
roc60              343   3021 -10.2410%  -5.7040%   -7.71     YES
turnrat_z          295   3069  -4.3190%  -6.3440%   -8.97      NO
```

Direction: top decile -> MORE NEGATIVE (worse) forward 63d max drawdown = direction_ok=YES

Note: These t_HAC values (-6 to -8.4) are large and would survive BH-FDR easily. This finding is informative but was not the pre-registered G1 metric, so it does not override the NULL verdict. It is reported honestly as a diagnostic for re-registration.

## GATE 1 — Direction + |t_HAC| >= 2, BH-FDR q <= 0.10 (4x2 family)

```
signal-horizon             p   q(BH) reject_H0 |t|>=2?
roc20_21d             0.2723  0.3112        no    1.10
roc20_63d             0.1752  0.2803        no    1.36
roc60_21d             0.0646  0.1723        no    1.85
roc60_63d             0.0099  0.0396       YES    2.58
turnrat_z_21d         0.0001  0.0008       YES    3.89
turnrat_z_63d         0.0897  0.1794        no    1.70
washout_21d           0.2281  0.3041        no    1.21
washout_63d           0.7213  0.7213        no    0.36

GATE 1: FAIL (no signal-horizon pair meets all G1 criteria)
```

## GATE 2 — Washout vs CSI300-Below-200dma Dumb Baseline

```
  200dma baseline: n_below = 1460
  200dma 21d mean fwd: 0.6510%  dir_ok: True
  200dma 63d mean fwd: 1.8290%  dir_ok: True
  Washout 21d mean fwd: -0.9090%  beats baseline: False
  Washout 63d mean fwd: 0.6360%  beats baseline: False
GATE 2: FAIL (washout beats 200dma baseline on SOME/NONE horizons)
```

## GATE 3 — Leave-One-Cycle-Out {2015, 2018, 2020, 2024-09}

Testing two canonical reads separately:

### Crash-risk (sig_roc20 x fwd_63d, direction=-1)

```
  full sample top-decile mean: 3.0740%
  -2015_deleveraging        : excised= 182  mean= 5.5330%  dir_ok=False
  -2018_bear                : excised= 243  mean= 3.3310%  dir_ok=False
  -2020_covid               : excised= 117  mean= 3.2030%  dir_ok=False
  -2024_stimulus            : excised=  80  mean= 3.3940%  dir_ok=False
GATE 3 (crash-risk roc20x63d): FAIL
```

### De-escalation (sig_washout fires, fwd_21d, direction=+1)

Note: sig_washout is binary; LOCO evaluates the fire-date subset (s==1) directly — qcut collapses to a single bin at ~96.7% zeros and must not be used.

```
  full sample fire-date mean: -0.9090% (n_fires=114)
  -2015_deleveraging        : excised= 182  n_fires=114  mean=-0.9090%  dir_ok=False
  -2018_bear                : excised= 243  n_fires= 97  mean=-0.2470%  dir_ok=False
  -2020_covid               : excised= 117  n_fires=114  mean=-0.9090%  dir_ok=False
  -2024_stimulus            : excised=  80  n_fires=111  mean=-0.9030%  dir_ok=False
GATE 3 (washout x 21d): FAIL
```

**GATE 3 overall: FAIL** (pass if EITHER canonical read passes)

## GATE 4 — Split-Half Same-Sign

### Crash-risk (sig_roc20 x fwd_63d)

```
  first_half: n=1682  mean=2.4460%  dir_ok=False
  second_half: n=1682  mean=1.7590%  dir_ok=False
GATE 4 (crash roc20x63d): FAIL
```

### De-escalation (sig_washout x fwd_21d)

Note: is_binary=True; evaluates fire-date (s==1) subsets in each half.

```
  first_half: n=1703  n_fires=52  mean=-1.5170%  dir_ok=False
  second_half: n=1703  n_fires=62  mean=-0.4000%  dir_ok=False
GATE 4 (washout x 21d): FAIL
```

**GATE 4 overall: FAIL** (pass if EITHER canonical read passes)

## Gate Summary

| Gate | Result | Criterion |
|------|--------|-----------|
| G1 | FAIL | Direction + |t_HAC|>=2 + BH-FDR q<=0.10 |
| G2 | FAIL | Washout beats 200dma baseline (both horizons) |
| G3 | FAIL | Leave-one-cycle-out same-sign (either read) |
| G4 | FAIL | Split-half same-sign (either read) |

**VERDICT: FAIL / NULL** (0/4 gates passed)

**NULL result:** Gates not satisfied. Print the null, no display recommendation. Signal Commons: do not add to NW conditioning layer at this time.

## In Plain English

Margin financing in China's A-share market is a proxy for leveraged retail speculation. When it accelerates fast (high 20d or 60d rate-of-change), the market is crowded with borrowed money — historically that has preceded sharp drawdowns. When margin hits a multi-year low AND starts recovering, it suggests the deleveraging has run its course and risk appetite is bottoming.

This test asks: do those two reads hold up statistically, or are they noise? A 'PASS' means the pattern is directionally consistent, passes false-discovery correction across the full signal family, survives removing individual historical crises from the sample, and replicates in both halves of the data. A 'FAIL' means we print the null and do not add it to the dashboard.
