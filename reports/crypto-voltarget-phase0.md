# Crypto vol-targeted risk-parity sleeve (BTC+ETH) — Phase-0

Vol-managed / vol-targeted crypto sleeve. Scale exposure inverse to trailing realized vol (Moreira-Muir), equal-risk BTC+ETH, target 50%/yr portfolio vol, leverage cap 2.0x, net 10.0bps one-way. Idle cash + levered financing on the local 3m bill (DTB3). Next-bar (weights.shift(1)) — no look-ahead.

Grid for the DSR multiple-testing haircut: vol_win [21, 42, 63] x target [0.4, 0.5, 0.6] x cap [1.5, 2.0, 2.5] = **27 trials**.

## Headline (per market/asset)

| sleeve | Sharpe | HODL Sh | 200dma Sh | brake Sh | sleeve MaxDD | HODL MaxDD | DD cut | sleeve CAGR | HODL CAGR | avg lev |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| BTC+ETH | 0.57 | 0.72 | 0.87 | 0.91 | -76% | -88% | 1.15x | 18% | 29% | 0.85 |
| BTC | 1.05 | 0.96 | 1.14 | 1.34 | -72% | -83% | 1.16x | 55% | 52% | 0.95 |

## BTC+ETH  (2017-11-09..2026-06-19  rows=3145)

- **DSR** best-of-grid (cfg (21, 0.4, 1.5)): **0.4673** (FAILS multiple-testing haircut (DSR<0.90)); SR_ann=0.66, SR0_ann=0.69, skew=0.063, kurt=13.128, T=3145. Default-cfg DSR=0.3588.
- **Block-bootstrap**: Sharpe CI [-0.19, 0.57, 1.35], MaxDD CI% [-97.3, -79.7, -54.9], P(Sharpe>0)=0.927 (lower CI>0: False).
- **Drawdown-reduction CI** (pp, sleeve_dd - HODL_dd): [-7.8, 4.1, 17.2] -> favorable(lower>0)=False, excludes0=False.
- **Split-half (pre/post 2021)**: DD-cut both halves=True, Sharpe>HODL both halves=False.
    - pre2021: Sharpe 0.74 vs HODL 0.92 (edge -0.17); DD better +11.6pp.
    - post2021: Sharpe 0.34 vs HODL 0.59 (edge -0.25); DD better +5.6pp.
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge survives=False.
    - drop 2018_bear: Sharpe edge +0.07; DD better +5.6pp.
    - drop 2020_covid: Sharpe edge -0.11; DD better +11.6pp.
    - drop 2021_22: Sharpe edge -0.17; DD better +11.6pp.
- **Dumb baselines**: 200dma Sharpe 0.87/MaxDD -66% (CAGR 35%); brake-matched Sharpe 0.91. sleeve beats-200dma(Sharpe)=False, DD-shallower=False, beats-brake(Sharpe)=False, Sharpe>HODL=False.
- **Honest-N**: ~3 independent crash/de-risk episodes drive the DD payoff (daily rows=3145 overstate the effective N).
- **Gate tally**: FAIL DSR>=0.90 (best-of-grid), FAIL DSR>=0.95 survives, FAIL boot P(Sh>0)==1, FAIL boot lower CI>0, FAIL DD-reduction CI excludes 0 (favorable), PASS split-half DD same-sign, FAIL split-half Sharpe same-sign, PASS LOO DD edge holds, FAIL LOO Sharpe edge holds, FAIL beats 200dma (Sharpe or DD), FAIL beats brake-matched (Sharpe), FAIL Sharpe>HODL

**Verdict (BTC+ETH): DISPLAY**  (scored=False, confirmer=False)

## BTC  (2014-09-17..2026-06-19  rows=4294)

- **DSR** best-of-grid (cfg (42, 0.4, 2.5)): **0.9497** (MARGINAL (0.90≤DSR<0.95)); SR_ann=1.08, SR0_ann=0.60, skew=0.004, kurt=16.201, T=4294. Default-cfg DSR=0.9412.
- **Block-bootstrap**: Sharpe CI [0.39, 1.06, 1.75], MaxDD CI% [-94.3, -74.9, -54.7], P(Sharpe>0)=0.999 (lower CI>0: True).
- **Drawdown-reduction CI** (pp, sleeve_dd - HODL_dd): [-8.5, 3.1, 17.7] -> favorable(lower>0)=False, excludes0=False.
- **Split-half (pre/post 2021)**: DD-cut both halves=True, Sharpe>HODL both halves=False.
    - pre2021: Sharpe 1.53 vs HODL 1.27 (edge +0.26); DD better +11.3pp.
    - post2021: Sharpe 0.41 vs HODL 0.53 (edge -0.12); DD better +4.7pp.
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge survives=True.
    - drop 2018_bear: Sharpe edge +0.13; DD better +4.7pp.
    - drop 2020_covid: Sharpe edge +0.14; DD better +11.3pp.
    - drop 2021_22: Sharpe edge +0.09; DD better +11.3pp.
- **Dumb baselines**: 200dma Sharpe 1.14/MaxDD -70% (CAGR 57%); brake-matched Sharpe 1.34. sleeve beats-200dma(Sharpe)=False, DD-shallower=False, beats-brake(Sharpe)=False, Sharpe>HODL=True.
- **Honest-N**: ~3 independent crash/de-risk episodes drive the DD payoff (daily rows=4294 overstate the effective N).
- **Gate tally**: PASS DSR>=0.90 (best-of-grid), FAIL DSR>=0.95 survives, FAIL boot P(Sh>0)==1, PASS boot lower CI>0, FAIL DD-reduction CI excludes 0 (favorable), PASS split-half DD same-sign, FAIL split-half Sharpe same-sign, PASS LOO DD edge holds, PASS LOO Sharpe edge holds, FAIL beats 200dma (Sharpe or DD), FAIL beats brake-matched (Sharpe), PASS Sharpe>HODL

**Verdict (BTC): DISPLAY**  (scored=False, confirmer=False)

## Honest read

Vol-targeting/vol-management is a real risk-control device: it reliably runs the book light into vol spikes, which CAPS the left tail. But on these data the *Sharpe* lift over a dumb buy&hold is thin, and the drawdown reduction (the genuine effect) does not clear the full SCORED bar of beating a brake-matched 200dma on Sharpe with an honest-N of only ~2-3 crypto cycles. See per-asset verdicts above for the EVIDENCE-supported tier.

