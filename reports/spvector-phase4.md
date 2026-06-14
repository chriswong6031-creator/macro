# S&P / Macro Vector — Phase 4 (diversified sleeve) A/B + GATE

*Same validated Phase-3 weight (vector_alloc); SPY buy & hold 1993-2026, cash@DTB3, 3.0bps. Treasury sleeve = synthetic constant-maturity 10y TR (~8y duration).*

| structure | CAGR | Sharpe | Sortino | MaxDD | pre/post Sh | 2022 ret | 2022 DD | 2008 ret | DSR |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| buy & hold | 10.81 | 0.65 | 0.82 | -55.2 | — | -18.2 | — | -36.8 | — |
| A SPY + bills (Phase-3) | 13.0 | 0.92 | 1.2 | -33.2 | 0.83/1.02 | -13.5 | -20.1 | -3.8 | 0.999 |
| B SPY + Treasury | 13.66 | 0.97 | 1.28 | -31.2 | 0.88/1.05 | -17.3 | -23.0 | 8.9 | 0.9996 |
| C RS + bills | 11.79 | 0.73 | 0.96 | -54.1 | 0.47/1.0 | -10.9 | -23.2 | -6.9 | 0.9785 |
| D RS + Treasury | 12.44 | 0.77 | 1.02 | -50.1 | 0.52/1.02 | -14.8 | -26.1 | 5.3 | 0.987 |
| E SPY + corr-gated Treasury | 13.66 | 0.97 | 1.27 | -31.2 | 0.88/1.05 | -15.7 | -22.1 | 8.9 | 0.9996 |

## GATE (each diversified structure vs A = Phase-3 bills)

**B SPY + Treasury** — REJECT
  - PASS CAGR > A
  - PASS MaxDD not worse than A
  - PASS both split-halves >= A
  - FAIL survives 2022 (>= A's 2022)
  - PASS DSR > 0.90

**C RS + bills** — REJECT
  - FAIL CAGR > A
  - FAIL MaxDD not worse than A
  - FAIL both split-halves >= A
  - PASS survives 2022 (>= A's 2022)
  - PASS DSR > 0.90

**D RS + Treasury** — REJECT
  - FAIL CAGR > A
  - FAIL MaxDD not worse than A
  - FAIL both split-halves >= A
  - FAIL survives 2022 (>= A's 2022)
  - PASS DSR > 0.90

**E SPY + corr-gated Treasury** — REJECT
  - PASS CAGR > A
  - PASS MaxDD not worse than A
  - PASS both split-halves >= A
  - FAIL survives 2022 (>= A's 2022)
  - PASS DSR > 0.90

## Read
- A (Phase-3 bills) is the bar: CAGR 13.0 / Sharpe 0.92 / MaxDD -33.2, 2022 -13.5%.
- The Treasury sleeve's 2022 column is the decisive test: in the 2022 rates bear, bonds fell WITH stocks, so de-risking into duration was a SECOND losing bet (stock-bond correlation breakdown). If B/D's 2022 return is materially below A's, the duration sleeve is rejected for THIS macro-timed book regardless of its full-sample CAGR.
- RS rotation (C) adds CAGR only if the winner-momentum across indices beats always-SPY net of its extra turnover; judged on OOS split-half + DSR, not the full-sample number.
- E (corr-gated Treasury) tests the obvious fix — hold bonds only when they hedge. It FAILS too: realized stock-bond correlation in 2022 averaged ~0.06 and only turned positive AFTER the bond drawdown, so the lagging regime signal still held duration through the damage. No non-lagging signal gates the 2022 duration tail away.

### Verdict: NONE clear the bar — KEEP bills (Phase-3 is the product). Diversification's CAGR edge does not survive the 2022 stock-bond breakdown / OOS test on this macro-timed switch.
