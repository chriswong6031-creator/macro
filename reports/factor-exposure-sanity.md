# Factor-exposure — Phase-0 sanity gate

*Causal rolling OLS of each name's daily return on 8 observable, market-orthogonalised factor proxies (Market, Size (small-cap), Momentum, US dollar, Semis / AI, Crypto, Oil, Rates (10y)), 252d window, VIF-pruned. EXPOSURE, not a forecast.*

## 1. Correctness — does the dominant beta land on the known factor?

| ticker | expected | dominant | R² | ✓ |
|---|---|---|--:|:--:|
| NVDA | semis | semis | 0.60 | ✅ |
| AMD | semis | semis | 0.52 | ✅ |
| COIN | crypto | crypto | 0.52 | ✅ |
| MARA | crypto | crypto | 0.51 | ✅ |
| XLE | oil | oil | 0.44 | ✅ |
| XOM | oil | oil | 0.40 | ✅ |
| CVX | oil | oil | 0.38 | ✅ |

**Correct dominant factor: 7/7 known names.**

## 2. Stability & fit (universe-wide)

- Names modelled: **1135**
- Median R²: **0.24** · share with R²≥0.30: **37%** (low-R² names are idiosyncratic/defensive — honestly flagged, not forced)
- Beta stability: median |Δβ| between the current window and one ~126d earlier = **0.05** (standardised betas; small = stable exposure)
- Dominant-factor persistence across those windows: **76%**
- VIF pruning triggered on **0%** of names (≥1 collinear factor dropped)

## Verdict: EXPOSURE measurement VALIDATED — display / risk-decomposition only

- Betas land on the right factor for known names and are stable across windows, with multicollinearity controlled (VIF) and honest R².
- This is a RISK decomposition (what bets you hold), **not** an alpha forecast — betas do not predict returns and must never enter a scoring path.
- Coverage gaps are honest: with no gold/credit factor, metals & pure-credit names read as low-R²; that shows as a weak fit rather than a spurious label.

*Run: `python -m scripts.factor_exposure_sanity`*