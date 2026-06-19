# ETH Vector `optimal` — Track-A SCORED verification (phase-0)

Port of the BTC Vector `optimal` grid to ETH. REUSES the BTC pure signal builders (`engine.btc_signals.momentum/risk/allocation`) fed ETH price only — on-chain votes absent → momentum collapses to its PRICE subset, Risk Index to downside-vol-pctile + drawdown-from-high + momentum-deterioration (the BTC `risk_idx` ingredients available without on-chain). MVRV overlay active: **True** (coinmetrics ETH MVRV, z-scored on the same 4y window).

Window 2017-11-09..2026-06-18 (3144 rows, ~8.6y), net 10.0bps one-way, same `optimal` grid + confirm_days + conviction sizing + drawdown brake as the live BTC engine.

## Headline

| | ETH-strat | ETH-HODL |
|---|--:|--:|
| Sharpe | 0.82 | 0.66 |
| MaxDD | -46.8% | -94.0% |
| CAGR | 29.4% | 21.8% |
| DD cut | 2.01x | (>=2x bar) |
| final/HODL | 1.68 | |
| time-in-mkt | 78% | |

## Gates

- **DSR** (DD/Sharpe payoff) n=50: **0.5546** (FAILS multiple-testing haircut (DSR<0.90)); n=65 live cfg: 0.5154. SR0_ann=0.77, skew=0.593, kurt=19.465, T=3144.
- **Block-bootstrap**: Sharpe CI [0.07, 0.81, 1.53], MaxDD CI% [-84.4, -58.7, -38.9], P(Sharpe>0)=0.983 (lower CI>0: True).
- **Split-half (pre/post 2021)**: DD-cut both halves=True, Sharpe>HODL both halves=True.
    - pre2021: Sharpe 1.10 vs 0.77; MaxDD -37.8% vs -94.0% (+56.1pp).
    - post2021: Sharpe 0.65 vs 0.59; MaxDD -46.8% vs -79.4% (+32.5pp).
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge=False.
    - drop 2018_bear: Sharpe 0.92 vs 0.78; MaxDD -46.8% vs -87.4% (+40.5pp).
    - drop 2020_covid: Sharpe 0.80 vs 0.66; MaxDD -46.8% vs -94.0% (+47.1pp).
    - drop 2021_may: Sharpe 0.77 vs 0.66; MaxDD -46.8% vs -94.0% (+47.1pp).
    - drop 2022_bear: Sharpe 0.71 vs 0.75; MaxDD -74.6% vs -94.0% (+19.4pp).
    - drop 2024_25_chop: Sharpe 0.91 vs 0.73; MaxDD -46.8% vs -94.0% (+47.1pp).
- **Brake-matched 200dma**: 200dma+brake Sharpe 0.82/MaxDD -65.9%; optimal beats it on Sharpe=False AND on DD=True.
- **Decomposition (raw grid, no conviction/brake)**: Sharpe 0.80 vs HODL 0.66, MaxDD -51.6% vs -94.0% — grid edge is NOT a pure brake artifact: True.
- **Honest-N**: only ~3 independent ETH bear cycles since 2017-11 (2018_bear, 2021-22_bear/cascade, 2024-25_chop); daily rows=3144 overstate the effective N. ETH misses the pre-2018 cycle BTC's 2015 start captured → BORDERLINE.
- **Direction (NON-claim)**: P(7d up|long)=0.551 vs base 0.512 — coin-flip.

## Verdict

SCORED core gates pass: **False**. The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and never claimed.
