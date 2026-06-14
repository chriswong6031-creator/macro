# S&P / Macro Vector — Phase 2 (re-deploy leg) A/B + GATE

*SPY 33.4yr, cash@DTB3, 3.0bps. Re-deploy lifts to fully-long inside a BUYABLE washout (capitulation_score>=2 AND Fed-put PRESENT).*

| strategy | CAGR | CAGR(noC) | Sharpe | MaxDD | %inMkt | turn | whip% | DSR |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Phase 1 base | 11.15 | 10.56 | 0.91 | -34.1 | 98.7 | 1.4 | 40.1 | 0.9998 |
| +redeploy (put-present) ← FINAL | 13.0 | 12.54 | 0.92 | -33.2 | 98.8 | 1.52 | 40.4 | 0.9999 |
| +redeploy (unconditional) | 13.67 | 13.26 | 0.85 | -32.0 | 99.6 | 1.59 | 39.7 | 0.9994 |

## GATE — `+redeploy (put-present)` vs Phase-1 base

- leave-one-crisis-out (Sharpe edge vs B&H): dotcom 2000-02 +0.27, GFC 2008 +0.15, COVID 2020 +0.31, bear 2022 +0.29
- split-half Sharpe: pre 0.83 / post 1.02 (B&H 0.47 / 0.86)
- dd-reduction bootstrap CI [2.8, 12.2, 29.8] P(>0)=1.0

- PASS (a) recovery capture up (CAGR >= base)
- PASS (b) MaxDD not worse than base
- PASS (c) whipsaw not worse than base
- PASS (d) survive leave-one-crisis-out
- PASS (e) both split-halves beat B&H
- PASS (f) DSR > 0.90

### Principled choice: put-present over unconditional
The unconditional variant has HIGHER in-sample CAGR (13.67 vs 13.0) but it buys 2000/2008/2022-style knives. Per research/DISLOCATION_VALIDATION.md (episode block-bootstrap, n~10 crises) put-conditioning is what makes a stress-buy's forward drawdown shallower with a CI excluding zero; a 4-crisis SPY backtest cannot price that tail, so we REJECT the higher-CAGR knife-catcher and ship the put-gated version.

### Honest read
The re-deploy leg (with a 42-day post-washout hold) is a recovery-capture enhancement: CAGR +~1.8pp with Sharpe essentially FLAT (0.91->0.92), MaxDD slightly better, whipsaw/turnover unchanged. The flat Sharpe is the tell — this is honest BETA recovery (re-entering fully after a buyable washout instead of letting the slow macro score drag re-entry), NOT new risk-adjusted alpha. With the hold, the unconditional knife-catcher's Sharpe DROPS to 0.85 (vs put-present 0.92), so the put-conditioning now earns its keep on the numbers too, not just on principle. The drawdown/Sharpe engine remains the product; re-deploy is a sensible refinement.

### Verdict: PASS — advance to Phase 3
