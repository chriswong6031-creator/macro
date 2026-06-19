# Credit Carry & Duration Timing — TRACK-A VERIFY (signal_lab)

*Re-ran the LIVE `engine.strategies` allocations (`_credit_alloc` / `_duration_alloc`)
through `engine.validation` from scratch on the deepest on-disk history. Reproduces the
two original phase-0 reports and recomputes every signal_lab gate. READ-ONLY.*
Script: `scripts/credit_duration_verify_phase0.py`. Cost 3.0 bps one-way, de-risked
sleeve earns the cash carry (5y Tsy for credit, T-bills for duration). No look-ahead
(live legs PIT-lagged; `backtest_core` acts next bar).

> DATA NOTE: the store now prefers a **3-yr** `BAMLHYH0A0HYM2TRIV` stub for `hy_tr()`
> (cached after the reports were written), which would truncate Credit Carry to ~786
> rows. For an honest DEEP re-run I used the full **HYG adjusted close (2007→, 19.2yr)**
> exactly as the original report did. TLT is full depth (2002→, 23.9yr).

## Computed results (my numbers, n_trials=8 = report's honest sweep count)

| | Credit Carry | Duration Timing |
|---|--:|--:|
| history | HYG 2007→ (19.2yr) | TLT 2002→ (23.9yr) |
| STRAT CAGR / Sharpe / MaxDD | 4.29 / **0.745** / **−14.7** | 3.61 / **0.494** / **−18.1** |
| B&H CAGR / Sharpe / MaxDD | 4.93 / 0.496 / −34.2 | 3.73 / 0.328 / −48.4 |
| 200dma CAGR / Sharpe / MaxDD | 4.59 / **0.822** / −9.2 | 0.76 / 0.124 / −40.3 |
| buy-every-drawdown placebo Sharpe | 0.420 | 0.298 |
| baseline-Sharpe to beat | **0.822** (200dma) | 0.328 (B&H) |
| **DSR** (n=8) | **0.9625** | **0.8312** |
| DSR (n=4 visible variants) | 0.9856 | 0.914 |
| turnover / yr · %inMkt | 2.55 · 99.3 | 1.81 · 95.2 |

These match the cached reports (Credit DSR 0.9633→**0.9625**, MaxDD −14.7; Duration DSR
0.828→**0.8312**, MaxDD −18.1) — independently reproduced, not copied.

## Gate-by-gate (signal_lab SCORED bar)

| gate | Credit Carry | Duration Timing |
|---|:--:|:--:|
| (a) MaxDD >10pp shallower vs B&H | PASS (+19.5pp) | PASS (+30.3pp) |
| **(b) beat dumb baseline Sharpe** | **FAIL** (0.745 < 0.822 naive 200dma on HY) | PASS (0.494 > 0.328) |
| (c) dd-reduction bootstrap CI excludes 0 | PASS [6.0, 15.6, 30.7] | PASS [7.2, 18.1, 34.3] |
| (d) leave-one-crisis-out edge>0 (all) | PASS (+0.12…+0.29) | PASS (+0.08…+0.18) |
| (e) turnover < 4/yr | PASS (2.55) | PASS (1.81) |
| (f) both split-halves beat B&H (same sign) | PASS (+0.27 / +0.21) | PASS (+0.11 / +0.19) |
| **(g) DSR ≥ 0.90** | PASS (0.96, survives ≥0.95) | **FAIL** (0.83 < 0.90) |

**The scored bar = DSR≥0.90 AND beats the dumb baseline. Each strategy fails a
DIFFERENT one of those two — neither clears both → neither is scored.**
- Credit Carry: clears DSR (0.96) but a **naive 200-day trend on HY beats it on Sharpe**
  (0.822 vs 0.745). The de-risk logic is no better risk-adjusted than a moving average.
- Duration Timing: beats its baseline but **DSR 0.83 < 0.90** — the risk-adjusted edge is
  marginal/noise at this sample depth.

## Honest-N (the binding constraint)

Both are single-asset long/flat timers. **Total excess return vs B&H is NEGATIVE for both
(−0.20 log)** — they GIVE UP CAGR; ~99% of any excess is "earned" on de-risk days and the
whole proposition is drawdown control, not return. The de-risk glide fires in ~40 (credit)
/ ~21 (duration) micro-episodes, but the economically-independent bets are the **~5–6 macro
crises** (GFC/euro/EM/COVID/2022 ± 2023). That is the real N. DSR/CI/leave-one-out are
computed on ~5k–6k autocorrelated daily rows but rest on a handful of bears → confidence is
bounded by the crisis count, not the row count. This is why both must cap at **confirmer**.

## VERDICT: CONFIRMER (both)

Confirms the candidate spec exactly. Validated DRAWDOWN-CONTEXT engines (deep MaxDD cut,
survives leave-one-crisis-out + dd-reduction CI excludes 0), but **NOT scored**: Credit
Carry fails beat-baseline-Sharpe (0.745 < 0.822), Duration Timing fails DSR≥0.90 (0.83).
Their own reports already say DISPLAY-ONLY; honest tier = confirmer (display-grade context
that confirms the equity de-risk picture), never a scored signal. Honest-N (~5–6 crises) is
too thin to promote even if a single gate had cleared.
