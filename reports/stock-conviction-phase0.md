# Unified Conviction Profile — Phase 0 gate

*SHALLOW ~3y live cache (NO deep panel, NO PIT membership — UNDERPOWERED, survivorship-inflated) · 2025-06-30..2025-11-28 · 6 monthly rebalances · ~1506 names/date · residual windows 252/252/21 shrink 0.66 · primary horizon 63d · L/S net of 5bps one-way.*

Does the holistic four-AXIS **conviction** composite rank forward returns better than the validated **selection** leg each board ranks by today — well enough to actually re-order the SHIPPED board? Axes are sector-neutral winsor-z; the composite is a Löwdin-orthogonal (equal-risk) blend across axes. The tailwind axis is a declared sector tilt, shown standalone, never folded into the cross-axis rank.

**Gate:** a market earns `GO` (board re-ranked by the composite) only if a composite beats selection on BOTH mean rank-IC AND quintile L/S Sharpe at 63d AND the split-half IC is same-sign. Otherwise `NEUTRAL` (display-only; the board keeps the validated rank and the composite rides as the per-name profile).

> **POWER GUARD ACTIVE.** The deep survivorship-clean matrix (`data/breadth/_closes_deep.parquet`) and PIT membership (`data/breadth/sp500_pit_membership.parquet`) are absent locally, so this is a shallow diagnostic only. Every market's gate is FORCED to `NEUTRAL` — the build will never flip a rank on powerless data. Run `scripts.residual_alpha_fetch` + `scripts.residual_alpha_pit` for a real GO test.


## Market: US — gate: **NEUTRAL**


### Forward horizon: 63 trading days (PRIMARY)

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — validated leg the board ranks by) | -0.0044 | -0.06 | — | — | — | — | -0.35 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0619 | -0.89 | — | — | — | — | -2.09 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | -0.0627 | -0.90 | — | — | — | — | -2.3 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | -0.0336 | -0.47 | — | — | — | — | -1.09 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0809 | -1.29 | — | — | — | — | -2.67 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | -0.0349 | -1.29 | — | — | — | — | -1.83 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | n/a | | | | | | None | — |

### Forward horizon: 21 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — validated leg the board ranks by) | -0.0386 | -0.27 | — | — | — | — | -0.11 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0668 | -0.74 | — | — | — | — | -2.11 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | -0.0676 | -0.73 | — | — | — | — | -2.26 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | -0.0561 | -0.44 | — | — | — | — | -0.85 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0532 | -0.63 | — | — | — | — | -2.77 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | -0.0251 | -0.55 | — | — | — | — | -1.89 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | n/a | | | | | | None | — |

### Forward horizon: 126 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — validated leg the board ranks by) | +0.0072 | +0.13 | — | — | — | — | -0.48 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0550 | -1.20 | — | — | — | — | -2.03 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | -0.0559 | -1.18 | — | — | — | — | -2.24 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | -0.0199 | -0.39 | — | — | — | — | -1.0 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0890 | -1.65 | — | — | — | — | -2.7 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | -0.0334 | -1.69 | — | — | — | — | -1.62 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | n/a | | | | | | None | — |

**US verdict (63d):**
- UNPOWERED shallow run (no deep panel / no PIT membership) — gate FORCED to display-only regardless of the diagnostic above
- conviction_orth: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- conviction_ew: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- selection_led: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero

**NEUTRAL — keep the US board on its validated selection rank.** The conviction composite rides as the displayed per-name profile/verdict (the honest product is a readable profile, not a re-order claimed without the power to back it).

## Market: CN — gate: **NEUTRAL**

_skipped — CN not tested here (no deep survivorship panel for this market in-repo) — gate NEUTRAL / display-only, matching the shipped trust tier (CN reversal-context · HK no-edge screen)_


## Market: HK — gate: **NEUTRAL**

_skipped — HK not tested here (no deep survivorship panel for this market in-repo) — gate NEUTRAL / display-only, matching the shipped trust tier (CN reversal-context · HK no-edge screen)_


## Market: CA — gate: **NEUTRAL**


### Forward horizon: 63 trading days (PRIMARY)

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — validated leg the board ranks by) | -0.0044 | -0.06 | — | — | — | — | -0.35 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0619 | -0.89 | — | — | — | — | -2.09 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | -0.0627 | -0.90 | — | — | — | — | -2.3 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | -0.0336 | -0.47 | — | — | — | — | -1.09 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0809 | -1.29 | — | — | — | — | -2.67 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | -0.0349 | -1.29 | — | — | — | — | -1.83 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | n/a | | | | | | None | — |

### Forward horizon: 21 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — validated leg the board ranks by) | -0.0386 | -0.27 | — | — | — | — | -0.11 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0668 | -0.74 | — | — | — | — | -2.11 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | -0.0676 | -0.73 | — | — | — | — | -2.26 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | -0.0561 | -0.44 | — | — | — | — | -0.85 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0532 | -0.63 | — | — | — | — | -2.77 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | -0.0251 | -0.55 | — | — | — | — | -1.89 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | n/a | | | | | | None | — |

### Forward horizon: 126 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — validated leg the board ranks by) | +0.0072 | +0.13 | — | — | — | — | -0.48 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0550 | -1.20 | — | — | — | — | -2.03 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | -0.0559 | -1.18 | — | — | — | — | -2.24 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | -0.0199 | -0.39 | — | — | — | — | -1.0 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0890 | -1.65 | — | — | — | — | -2.7 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | -0.0334 | -1.69 | — | — | — | — | -1.62 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | n/a | | | | | | None | — |

**CA verdict (63d):**
- UNPOWERED shallow run (no deep panel / no PIT membership) — gate FORCED to display-only regardless of the diagnostic above
- conviction_orth: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- conviction_ew: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- selection_led: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero

**NEUTRAL — keep the CA board on its validated selection rank.** The conviction composite rides as the displayed per-name profile/verdict (the honest product is a readable profile, not a re-order claimed without the power to back it).

---

**How to read.** `selection` is the baseline the board ships today. A composite must beat it on BOTH IC and Sharpe at 63d *and* not flip sign across halves to earn a GO. The orthogonal composite decorrelates the axes (so it is not just re-weighted selection); the EW and selection-led variants bound the design space. The DSR deflates for the whole family screened (composites × horizons). On a shallow local run the gate is display-only by construction — only the deep + PIT panel can earn a re-rank.

## Axis overlap diagnostic (US/CA panel)

- mean |cross-axis corr| raw → orth: **0.047** → **0.037**
- VIF: {'selection': 1.0, 'entry': 1.03, 'tailwind': 1.0, 'quality': 1.04}
