# BTC Vector `optimal` — Track-A SCORED verification (phase-0)

Re-ran the LIVE engine (`engine/btc_signals.compute_all` → `alloc_optimal`) over 2015-01-01..2026-06-18, net of 10.0bps one-way. NO rebuild — same code path build_vector ships.

## Headline

| | strat | HODL | spec |
|---|--:|--:|---|
| Sharpe | 1.44 | 1.03 | ~1.41 vs ~1.03 |
| MaxDD | -37.5% | -83.8% | ~-42.8 vs -83.8 |
| CAGR | 61.6% | 59.1% | |
| DD cut | 2.23x | | >=2x |
| final/HODL | 1.19 | | |

## Gates

- **DSR** n=50: **0.9965** (SURVIVES multiple-testing (DSR≥0.95)); n=65 live cfg: 0.9953. SR0_ann=0.66, skew=0.734, kurt=13.803, T=4187.
- **Block-bootstrap**: Sharpe CI [0.79, 1.45, 2.07], MaxDD CI% [-65.8, -44.6, -31.0], P(Sharpe>0)=1.0 (lower CI>0: True).
- **Split-half**: DD-cut both halves=True, Sharpe>HODL both halves=True.
    - pre: Sharpe 1.87 vs 1.39; MaxDD -37.5% vs -83.8% (+46.3pp).
    - post: Sharpe 0.86 vs 0.54; MaxDD -31.4% vs -76.7% (+45.3pp).
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge=True.
    - drop 2018_bear: Sharpe 1.44 vs 1.12; MaxDD -32.8% vs -76.7% (+43.9pp).
    - drop 2020_covid: Sharpe 1.44 vs 1.05; MaxDD -37.5% vs -83.8% (+46.3pp).
    - drop 2021_may: Sharpe 1.39 vs 1.05; MaxDD -37.5% vs -83.8% (+46.3pp).
    - drop 2022_bear: Sharpe 1.22 vs 1.13; MaxDD -75.1% vs -83.8% (+8.7pp).
    - drop 2024_25_chop: Sharpe 1.63 vs 1.13; MaxDD -37.5% vs -83.8% (+46.3pp).
- **Dumb baselines**: 200dma Sharpe 1.13/MaxDD -70.7%; optimal beats-200dma(Sharpe)=True, DD-shallower=True.
- **Honest-N**: ~5 independent crash/de-risk episodes drive the DD payoff (daily rows=4187 overstate the effective N for the claim).
- **Direction (NON-claim)**: P(7d up|long)=0.579 vs base 0.546 — coin-flip.

## Verdict

SCORED core gates pass: **True**. The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and not claimed.
