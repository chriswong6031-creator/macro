# BTC Vector `optimal` — Track-A SCORED verification (phase-0)

Re-ran the LIVE engine (`engine/btc_signals.compute_all` → `alloc_optimal`) over 2015-01-01..2026-06-23, net of 10.0bps one-way. NO rebuild — same code path build_vector ships.

## Headline

| | strat | HODL | spec |
|---|--:|--:|---|
| Sharpe | 1.44 | 1.03 | ~1.41 vs ~1.03 |
| MaxDD | -41.2% | -83.8% | ~-42.8 vs -83.8 |
| CAGR | 63.5% | 58.8% | |
| DD cut | 2.03x | | >=2x |
| final/HODL | 1.40 | | |

## Gates

- **DSR** n=50: **0.9961** (SURVIVES multiple-testing (DSR≥0.95)); n=65 live cfg: 0.9947. SR0_ann=0.66, skew=0.606, kurt=12.959, T=4192.
- **Block-bootstrap**: Sharpe CI [0.8, 1.44, 2.04], MaxDD CI% [-65.7, -44.8, -32.2], P(Sharpe>0)=1.0 (lower CI>0: True).
- **Split-half**: DD-cut both halves=True, Sharpe>HODL both halves=True.
    - pre: Sharpe 1.86 vs 1.39; MaxDD -41.2% vs -83.8% (+42.6pp).
    - post: Sharpe 0.86 vs 0.53; MaxDD -35.2% vs -76.7% (+41.5pp).
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge=True.
    - drop 2018_bear: Sharpe 1.46 vs 1.12; MaxDD -35.2% vs -76.7% (+41.5pp).
    - drop 2020_covid: Sharpe 1.46 vs 1.05; MaxDD -41.2% vs -83.8% (+42.6pp).
    - drop 2021_may: Sharpe 1.39 vs 1.05; MaxDD -41.5% vs -83.8% (+42.3pp).
    - drop 2022_bear: Sharpe 1.24 vs 1.12; MaxDD -74.9% vs -83.8% (+8.9pp).
    - drop 2024_25_chop: Sharpe 1.61 vs 1.12; MaxDD -41.2% vs -83.8% (+42.6pp).
- **Dumb baselines**: 200dma Sharpe 1.13/MaxDD -70.7%; optimal beats-200dma(Sharpe)=True, DD-shallower=True.
- **Honest-N**: ~5 independent crash/de-risk episodes drive the DD payoff (daily rows=4192 overstate the effective N for the claim).
- **Direction (NON-claim)**: P(7d up|long)=0.578 vs base 0.546 — coin-flip.

## Verdict

SCORED core gates pass: **True**. The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and not claimed.
