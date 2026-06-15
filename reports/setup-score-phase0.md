# Setup-score — Phase 0 validation

*Survivorship-clean deep S&P-500 panel · PIT membership · 2014-06-30..2026-02-27 · 141 monthly rebalances · ~448 names/date · residual-alpha windows 252/252/21 shrink 0.66.*

Does the **setup score** (selection × timing) rank forward returns better than its legs? `alpha` = the validated sector-neutral residual-momentum context leg (baseline); `setup` adds the cycle-timing + reversal overlay.


## Forward horizon: 21 trading days

| signal | mean IC | IC-IR | HAC t | p | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|---|
| alpha (baseline) | +0.0101 | +0.06 | +0.82 | 0.414 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| alpha + reversal overlay | +0.0093 | +0.05 | +0.75 | 0.455 | -0.09 | FAILS multiple-testing haircut (DSR<0.90) |
| timing only (no alpha) | -0.0046 | -0.05 | -0.67 | 0.501 | -0.47 | FAILS multiple-testing haircut (DSR<0.90) |
| setup (shipped) | -0.0013 | -0.01 | -0.13 | 0.894 | -0.18 | FAILS multiple-testing haircut (DSR<0.90) |

## Forward horizon: 63 trading days

| signal | mean IC | IC-IR | HAC t | p | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|---|
| alpha (baseline) | +0.0231 | +0.15 | +1.18 | 0.240 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| alpha + reversal overlay | +0.0227 | +0.15 | +1.16 | 0.248 | -0.09 | FAILS multiple-testing haircut (DSR<0.90) |
| timing only (no alpha) | -0.0058 | -0.07 | -0.83 | 0.404 | -0.47 | FAILS multiple-testing haircut (DSR<0.90) |
| setup (shipped) | +0.0107 | +0.10 | +0.90 | 0.367 | -0.18 | FAILS multiple-testing haircut (DSR<0.90) |

## Verdict (primary horizon 21d)

- setup mean IC -0.0013 vs alpha +0.0101 → **no IC gain**
- setup L/S Sharpe -0.18 vs alpha -0.16 → **no Sharpe gain**

**NEUTRAL / cosmetic** — the timing tilt does not lift forward IC or Sharpe over alpha alone. HONEST CALL: downgrade the UI from 'ranked by setup conviction' to 'an ordering aid', and lean on the separately validated alpha (context) and cycle (calibrated timing) legs. No edge is claimed that isn't there.

- *Diagnostic:* timing-only mean IC -0.0046 (flat/negative — cycle timing is risk-placement, not return-prediction (matches its calibration)).
- *Diagnostic:* alpha+reversal mean IC +0.0093 vs alpha +0.0101 (reversal overlay neutral/hurts at this horizon).
