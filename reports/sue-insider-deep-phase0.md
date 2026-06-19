# Event-edge gate (T8) — SUE cadence + SUE×insider blend, survivorship-clean

*`scripts/sue_insider_deep_phase0.py`. The gate before a NEW validated long-only rank: an event signal must (1) rank winners — IC>0 surviving BH-FDR — and (2) clear DSR≥0.90 on the net-of-cost backtest with split-half same-sign AND beat a random placebo, BEATING the 12-1 momentum incumbent the board already ranks on. Survivorship-clean: deep+delisted prices, point-in-time S&P-1500 membership. Causal SUE + causal insider filings.*

## VERDICT

**QUARTERLY (native SUE cadence) → NEUTRAL.** SUE IC -0.0007 (vs momentum -0.0016); EVENT signals surviving BH-FDR: NONE (family incl. momentum: NONE). Best event long-only active DSR = insider_opp_buyers 0.7657 vs placebo 0.7523 / momentum 0.7221 → MATCHED BY NOISE / does not beat incumbent (artifact, not selection).

**MONTHLY (board cadence) → NEUTRAL.** SUE IC 0.0013 (vs momentum 0.0062); EVENT signals surviving BH-FDR: NONE (family incl. momentum: NONE). Best event long-only active DSR = insider_opp_buyers 0.8231 vs placebo 0.841 / momentum 0.7841 → MATCHED BY NOISE / does not beat incumbent (artifact, not selection).

**Decision: NEUTRAL — ship NO new scored rank.** Cross-sectional event IC is ~0 on the survivorship-clean S&P-1500 at this horizon, at BOTH quarterly (native) and monthly cadence — quarter-end sampling does NOT recover an edge, and SUE×insider does not beat SUE. The long-only top-decile active Sharpe (~0.7) is a concentrated-EW-vs-broad-EW artifact: the random PLACEBO earns the same. The board's gate stays NEUTRAL; SUE/insider remain display-only context, the validated leg stays each market's residual-alpha RANK, and the shipped edge is the T1–T7 risk-control reshape, not a new alpha leg.

### QUARTERLY (native SUE cadence)

Span 2011-03-31..2025-12-31 · 60 rebalances · ~717 eligible names · forward 63d · survivorship-clean (deep+delisted, PIT S&P-1500).

| signal | mean IC | IC-IR | t_HAC | p | q_FDR | hit | IC h1→h2 | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| insider_opp_buyers | 0.0081 | 0.145 | 1.215 | 0.2243 | 0.8972 | 0.55 | 0.0079→0.0084 | 60 |
| sue_x_insider | 0.0007 | 0.01 | 0.082 | 0.9344 | 0.9346 | 0.567 | 0.0024→-0.0011 | 60 |
| sue | -0.0007 | -0.01 | -0.082 | 0.9346 | 0.9346 | 0.5 | 0.0003→-0.0016 | 60 |
| momentum_12_1 | -0.0016 | -0.013 | -0.108 | 0.9137 | 0.9346 | 0.483 | 0.0073→-0.0104 | 60 |

**Survive BH-FDR(10%):** NONE

Long-only top-decile, EW, net of cost — ACTIVE return = decile − eligible-universe EW. _Read the active **Sharpe/DSR** vs the `placebo_random` row (a noise signal through the same machinery) — that is the artifact floor. The absolute cum-% is distorted by delisting-tail compounding on the deep+delisted matrix and is NOT comparable; the risk-adjusted stats are._

| signal | active Sharpe | active DSR | active maxDD % | h1→h2 ann% | P(SR>0) | (cum % — distorted) |
|---|--:|--:|--:|--:|--:|--:|
| momentum_12_1 | 0.68 | 0.7221 | -100.0 | 65.7→123.1 | 0.996 | -99.4 |
| sue | 0.72 | 0.7627 | -100.9 | 81.7→132.6 | 0.998 | -105.1 |
| insider_opp_buyers | 0.72 | 0.7657 | -94.5 | 38.0→64.2 | 0.997 | 3788.0 |
| sue_x_insider | 0.72 | 0.7651 | -101.0 | 81.3→133.5 | 0.998 | -105.9 |
| placebo_random | 0.71 | 0.7523 | -100.5 | 87.4→130.8 | 0.997 | -101.7 |

Dollar-neutral top-vs-bottom-quintile (net of cost, DSR-deflated):

| signal | net Sharpe | cum % | DSR | verdict |
|---|--:|--:|--:|---|
| momentum_12_1 | -0.06 | -30.2 | 0.0989 | FAILS multiple-testing haircut (DSR<0.90) |
| sue | -0.44 | -60.5 | 0.0033 | FAILS multiple-testing haircut (DSR<0.90) |
| sue_x_insider | -0.46 | -59.1 | 0.0027 | FAILS multiple-testing haircut (DSR<0.90) |

### MONTHLY (board cadence)

Span 2011-01-31..2026-02-27 · 182 rebalances · ~717 eligible names · forward 63d · survivorship-clean (deep+delisted, PIT S&P-1500).

| signal | mean IC | IC-IR | t_HAC | p | q_FDR | hit | IC h1→h2 | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| momentum_12_1 | 0.0062 | 0.047 | 0.417 | 0.6764 | 0.8713 | 0.549 | 0.014→-0.0017 | 182 |
| insider_opp_buyers | 0.003 | 0.053 | 0.488 | 0.6256 | 0.8713 | 0.533 | 0.0052→0.0008 | 182 |
| sue_x_insider | 0.002 | 0.032 | 0.266 | 0.7901 | 0.8713 | 0.582 | 0.0029→0.0011 | 182 |
| sue | 0.0013 | 0.02 | 0.162 | 0.8713 | 0.8713 | 0.544 | 0.0013→0.0013 | 182 |

**Survive BH-FDR(10%):** NONE

Long-only top-decile, EW, net of cost — ACTIVE return = decile − eligible-universe EW. _Read the active **Sharpe/DSR** vs the `placebo_random` row (a noise signal through the same machinery) — that is the artifact floor. The absolute cum-% is distorted by delisting-tail compounding on the deep+delisted matrix and is NOT comparable; the risk-adjusted stats are._

| signal | active Sharpe | active DSR | active maxDD % | h1→h2 ann% | P(SR>0) | (cum % — distorted) |
|---|--:|--:|--:|--:|--:|--:|
| momentum_12_1 | 0.73 | 0.7841 | -100.7 | 85.2→137.4 | 0.998 | -103.6 |
| sue | 0.74 | 0.7989 | -100.5 | 86.8→141.2 | 0.999 | -104.1 |
| insider_opp_buyers | 0.76 | 0.8231 | -92.5 | 37.8→69.2 | 0.999 | 6820.3 |
| sue_x_insider | 0.74 | 0.7989 | -100.3 | 87.6→143.7 | 0.999 | -102.5 |
| placebo_random | 0.78 | 0.841 | -100.1 | 121.6→145.2 | 0.999 | -100.3 |

Dollar-neutral top-vs-bottom-quintile (net of cost, DSR-deflated):

| signal | net Sharpe | cum % | DSR | verdict |
|---|--:|--:|--:|---|
| momentum_12_1 | 0.08 | -3.9 | 0.2254 | FAILS multiple-testing haircut (DSR<0.90) |
| sue | -0.5 | -65.2 | 0.0014 | FAILS multiple-testing haircut (DSR<0.90) |
| sue_x_insider | -0.48 | -62.3 | 0.0018 | FAILS multiple-testing haircut (DSR<0.90) |

---

**How to read.** The honest question is whether SUE *at quarter-end cadence* (aligned to the reporting calendar) recovers the edge the monthly board samples off-cadence and dilutes; and whether SUE+insider beats SUE alone enough to promote. If the event signals do NOT beat momentum on BOTH the IC/FDR gate and the long-only active DSR, the board's current display-only treatment of SUE is correct and we ship NO new scored rank — the edge that survives is the risk-control reshape (T1–T7), not a new alpha leg.
