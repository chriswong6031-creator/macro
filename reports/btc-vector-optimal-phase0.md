# BTC Vector `optimal` — Track-A SCORED verification (phase-0)

**W1 N7 decontamination**: grading `alloc_optimal_raw` (pure engine) as the headline. Pre-gate figures (0.9965 DSR, Sharpe 1.44) were computed before the midterm-blackout override was wired into compute_all — they certified a strategy that no longer exists. Fresh dual-track compute as of 2026-07. `alloc_optimal` (gated) shown as comparison only.

Re-ran the LIVE engine (`engine/btc_signals.compute_all` → `alloc_optimal_raw`) over 2015-01-01..2026-07-01, net of 10.0bps one-way. NO rebuild — same code path build_vector ships.

## Gated comparison (alloc_optimal — midterm blackout active)

| | gated strat | HODL |
|---|--:|--:|
| Sharpe | 1.56 | 1.01 |
| MaxDD | -32.3% | -83.8% |
| CAGR | 70.3% | 57.7% |

*Gated is 0% through the 2026 midterm-blackout window by human override, not signal.*

## Headline — RAW (ungated, SCORED)

| | RAW strat | HODL | prior spec (retired) |
|---|--:|--:|---|
| Sharpe | 1.43 | 1.01 | ~1.41 vs ~1.03 |
| MaxDD | -41.2% | -83.8% | ~-42.8 vs -83.8 |
| CAGR | 63.3% | 57.7% | |
| DD cut | 2.03x | | >=2x |
| final/HODL | 1.50 | | |

## Gates

- **DSR (RAW)** n=50: **0.9960** (SURVIVES multiple-testing (DSR≥0.95)); n=68 (live cfg 65 + override dof 3): 0.9945. SR0_ann=0.66, skew=0.607, kurt=12.983, T=4200.
- **Block-bootstrap**: Sharpe CI [0.81, 1.44, 2.04], MaxDD CI% [-65.7, -44.8, -32.1], P(Sharpe>0)=1.0 (lower CI>0: True).
- **Split-half**: DD-cut both halves=True, Sharpe>HODL both halves=True.
    - pre: Sharpe 1.86 vs 1.39; MaxDD -41.2% vs -83.8% (+42.6pp).
    - post: Sharpe 0.85 vs 0.51; MaxDD -35.2% vs -76.7% (+41.5pp).
- **Leave-one-crisis-out**: DD edge survives any drop=True, Sharpe edge=True.
    - drop 2018_bear: Sharpe 1.46 vs 1.11; MaxDD -35.2% vs -76.7% (+41.5pp).
    - drop 2020_covid: Sharpe 1.45 vs 1.03; MaxDD -41.2% vs -83.8% (+42.6pp).
    - drop 2021_may: Sharpe 1.39 vs 1.04; MaxDD -41.5% vs -83.8% (+42.3pp).
    - drop 2022_bear: Sharpe 1.24 vs 1.11; MaxDD -74.9% vs -83.8% (+8.9pp).
    - drop 2024_25_chop: Sharpe 1.61 vs 1.11; MaxDD -41.2% vs -83.8% (+42.6pp).
- **Dumb baselines**: 200dma Sharpe 1.13/MaxDD -70.7%; optimal beats-200dma(Sharpe)=True, DD-shallower=True.
- **Honest-N**: ~5 independent crash/de-risk episodes drive the DD payoff (daily rows=4200 overstate the effective N for the claim).
- **Direction (NON-claim)**: P(7d up|long)=0.578 vs base 0.545 — coin-flip.

## Verdict

SCORED core gates pass (RAW series): **True**. The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and not claimed. Pre-gate figures (DSR 0.9965, Sharpe 1.44) retired 2026-07; fresh dual-track as of this run.
