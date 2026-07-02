# ETH Vector `optimal` — Track-A SCORED verification (phase-0)

Port of the BTC Vector `optimal` grid to ETH. REUSES the BTC pure signal builders (`engine.btc_signals.momentum/risk/allocation`) fed ETH price only — on-chain votes absent → momentum collapses to its PRICE subset, Risk Index to downside-vol-pctile + drawdown-from-high + momentum-deterioration (the BTC `risk_idx` ingredients available without on-chain). MVRV overlay active: **False** (coinmetrics ETH MVRV, z-scored on the same 4y window).

Window 2017-11-09..2026-07-01 (3157 rows, ~8.6y), net 10.0bps one-way, same `optimal` grid + confirm_days + conviction sizing + drawdown brake as the live BTC engine.

## Headline

| | ETH-strat | ETH-HODL |
|---|--:|--:|
| Sharpe | 0.80 | 0.65 |
| MaxDD | -46.6% | -94.0% |
| CAGR | 27.5% | 20.3% |
| DD cut | 2.02x | (>=2x bar) |
| final/HODL | 1.66 | |
| time-in-mkt | 44% | |

## Gates

- **DSR** (DD/Sharpe payoff) n=50: **0.5345** (FAILS multiple-testing haircut (DSR<0.90)); n=65 live cfg: 0.4952. SR0_ann=0.77, skew=0.673, kurt=22.493, T=3157.
- **Block-bootstrap**: Sharpe CI [0.05, 0.8, 1.52], MaxDD CI% [-83.3, -57.3, -37.3], P(Sharpe>0)=0.98 (lower CI>0: True).
- **Split-half (pre/post 2021)**: DD-cut both halves=True, Sharpe>HODL both halves=True.
    - pre2021: Sharpe 1.15 vs 0.77; MaxDD -35.8% vs -94.0% (+58.2pp).
    - post2021: Sharpe 0.58 vs 0.57; MaxDD -46.6% vs -79.4% (+32.7pp).
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge=False.
    - drop 2018_bear: Sharpe 0.87 vs 0.76; MaxDD -46.6% vs -87.4% (+40.7pp).
    - drop 2020_covid: Sharpe 0.79 vs 0.64; MaxDD -46.6% vs -94.0% (+47.3pp).
    - drop 2021_may: Sharpe 0.75 vs 0.65; MaxDD -46.6% vs -94.0% (+47.3pp).
    - drop 2022_bear: Sharpe 0.68 vs 0.73; MaxDD -74.6% vs -94.0% (+19.3pp).
    - drop 2024_25_chop: Sharpe 0.92 vs 0.71; MaxDD -46.6% vs -94.0% (+47.3pp).
- **Brake-matched 200dma**: 200dma+brake Sharpe 0.82/MaxDD -65.9%; optimal beats it on Sharpe=False AND on DD=True.
- **Decomposition (raw grid, no conviction/brake)**: Sharpe 0.80 vs HODL 0.65, MaxDD -50.5% vs -94.0% — grid edge is NOT a pure brake artifact: True.
- **Honest-N**: only ~3 independent ETH bear cycles since 2017-11 (2018_bear, 2021-22_bear/cascade, 2024-25_chop); daily rows=3157 overstate the effective N. ETH misses the pre-2018 cycle BTC's 2015 start captured → BORDERLINE.
- **Direction (NON-claim)**: P(7d up|long)=0.549 vs base 0.510 — coin-flip.

## Verdict

SCORED core gates pass: **False**. The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and never claimed.
