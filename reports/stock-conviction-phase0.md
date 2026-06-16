# Unified Conviction Profile — Phase 0 gate

*DEEP survivorship-clean panel + PIT membership · 2008-06-30..2025-11-28 · 210 monthly rebalances · ~419 names/date · residual windows 252/252/21 shrink 0.66 · primary horizon 63d · L/S net of 5bps one-way.*

Does the holistic four-AXIS **conviction** composite rank forward returns better than the validated **selection** leg each board ranks by today — well enough to actually re-order the SHIPPED board? Axes are sector-neutral winsor-z; the composite is a Löwdin-orthogonal (equal-risk) blend across axes. The tailwind axis is a declared sector tilt, shown standalone, never folded into the cross-axis rank.

**Gate:** a market earns `GO` (board re-ranked by the composite) only if a composite beats selection on BOTH mean rank-IC AND quintile L/S Sharpe at 63d AND the split-half IC is same-sign. Otherwise `NEUTRAL` (display-only; the board keeps the validated rank and the composite rides as the per-name profile).


## Market: US — gate: **NEUTRAL**


### Forward horizon: 63 trading days (PRIMARY)

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — residual momentum, the v1 rank) | +0.0086 | +0.05 | +0.48 | 0.632 | 0.8452 | -0.0031→0.0204 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| EDGE (v2 — validated event core: SUE; live also folds insider + revisions) | +0.0048 | +0.06 | +0.47 | 0.639 | 0.8452 | 0.0073→0.0023 | -0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0039 | -0.03 | -0.27 | 0.788 | 0.8452 | -0.0195→0.0117 | -0.25 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | +0.0030 | +0.02 | +0.20 | 0.845 | 0.8452 | -0.0078→0.0138 | -0.25 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | +0.0083 | +0.06 | +0.50 | 0.618 | 0.8452 | -0.0021→0.0187 | -0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0027 | -0.02 | -0.33 | 0.745 | 0.8452 | 0.0016→-0.0071 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | +0.0027 | +0.03 | +0.20 | 0.843 | 0.8452 | 0.0118→-0.0063 | -0.06 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | +0.0075 | +0.07 | +0.44 | 0.660 | 0.8452 | 0.0339→-0.018 | 0.28 | FAILS multiple-testing haircut (DSR<0.90) |

### Forward horizon: 21 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — residual momentum, the v1 rank) | +0.0044 | +0.03 | +0.41 | 0.683 | 0.8007 | 0.0015→0.0073 | -0.24 | FAILS multiple-testing haircut (DSR<0.90) |
| EDGE (v2 — validated event core: SUE; live also folds insider + revisions) | +0.0069 | +0.09 | +1.16 | 0.245 | 0.8007 | 0.006→0.0078 | -0.06 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0036 | -0.03 | -0.39 | 0.701 | 0.8007 | -0.0123→0.0051 | -0.36 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | +0.0022 | +0.02 | +0.22 | 0.827 | 0.8269 | -0.0039→0.0082 | -0.33 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | +0.0044 | +0.03 | +0.43 | 0.670 | 0.8007 | -0.0002→0.0091 | -0.24 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0034 | -0.03 | -0.45 | 0.655 | 0.8007 | -0.0066→-0.0003 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | +0.0045 | +0.04 | +0.55 | 0.584 | 0.8007 | 0.0083→0.0008 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | +0.0134 | +0.12 | +0.96 | 0.335 | 0.8007 | 0.0142→0.0126 | 0.17 | FAILS multiple-testing haircut (DSR<0.90) |

### Forward horizon: 126 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — residual momentum, the v1 rank) | +0.0175 | +0.10 | +0.74 | 0.457 | 0.832 | -0.0015→0.0365 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |
| EDGE (v2 — validated event core: SUE; live also folds insider + revisions) | -0.0031 | -0.03 | -0.25 | 0.805 | 0.832 | -0.0085→0.0023 | -0.17 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0040 | -0.03 | -0.21 | 0.831 | 0.832 | -0.0286→0.0206 | -0.26 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | +0.0077 | +0.05 | +0.39 | 0.699 | 0.832 | -0.0107→0.0262 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | +0.0162 | +0.10 | +0.74 | 0.462 | 0.832 | -0.0019→0.0342 | -0.15 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0088 | -0.08 | -1.16 | 0.245 | 0.832 | -0.0087→-0.009 | -0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | +0.0038 | +0.03 | +0.21 | 0.832 | 0.832 | 0.0113→-0.0037 | -0.07 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | -0.0080 | -0.08 | -0.63 | 0.526 | 0.832 | 0.0071→-0.0225 | 0.49 | FAILS multiple-testing haircut (DSR<0.90) |

**US verdict (63d):**
- edge: NO — IC≤baseline
- conviction_orth: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- conviction_ew: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- selection_led: NO — IC≤baseline, split-half flips/zero

**NEUTRAL — keep the US board on its validated selection rank.** The conviction composite rides as the displayed per-name profile/verdict (the honest product is a readable profile, not a re-order claimed without the power to back it).

## Market: CN — gate: **NEUTRAL**

_skipped — CN not tested here (no deep survivorship panel for this market in-repo) — gate NEUTRAL / display-only, matching the shipped trust tier (CN reversal-context · HK no-edge screen)_


## Market: HK — gate: **NEUTRAL**

_skipped — HK not tested here (no deep survivorship panel for this market in-repo) — gate NEUTRAL / display-only, matching the shipped trust tier (CN reversal-context · HK no-edge screen)_


## Market: CA — gate: **NEUTRAL**


### Forward horizon: 63 trading days (PRIMARY)

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — residual momentum, the v1 rank) | +0.0086 | +0.05 | +0.48 | 0.632 | 0.8452 | -0.0031→0.0204 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| EDGE (v2 — validated event core: SUE; live also folds insider + revisions) | +0.0048 | +0.06 | +0.47 | 0.639 | 0.8452 | 0.0073→0.0023 | -0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0039 | -0.03 | -0.27 | 0.788 | 0.8452 | -0.0195→0.0117 | -0.25 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | +0.0030 | +0.02 | +0.20 | 0.845 | 0.8452 | -0.0078→0.0138 | -0.25 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | +0.0083 | +0.06 | +0.50 | 0.618 | 0.8452 | -0.0021→0.0187 | -0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0027 | -0.02 | -0.33 | 0.745 | 0.8452 | 0.0016→-0.0071 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | +0.0027 | +0.03 | +0.20 | 0.843 | 0.8452 | 0.0118→-0.0063 | -0.06 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | +0.0075 | +0.07 | +0.44 | 0.660 | 0.8452 | 0.0339→-0.018 | 0.28 | FAILS multiple-testing haircut (DSR<0.90) |

### Forward horizon: 21 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — residual momentum, the v1 rank) | +0.0044 | +0.03 | +0.41 | 0.683 | 0.8007 | 0.0015→0.0073 | -0.24 | FAILS multiple-testing haircut (DSR<0.90) |
| EDGE (v2 — validated event core: SUE; live also folds insider + revisions) | +0.0069 | +0.09 | +1.16 | 0.245 | 0.8007 | 0.006→0.0078 | -0.06 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0036 | -0.03 | -0.39 | 0.701 | 0.8007 | -0.0123→0.0051 | -0.36 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | +0.0022 | +0.02 | +0.22 | 0.827 | 0.8269 | -0.0039→0.0082 | -0.33 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | +0.0044 | +0.03 | +0.43 | 0.670 | 0.8007 | -0.0002→0.0091 | -0.24 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0034 | -0.03 | -0.45 | 0.655 | 0.8007 | -0.0066→-0.0003 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | +0.0045 | +0.04 | +0.55 | 0.584 | 0.8007 | 0.0083→0.0008 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | +0.0134 | +0.12 | +0.96 | 0.335 | 0.8007 | 0.0142→0.0126 | 0.17 | FAILS multiple-testing haircut (DSR<0.90) |

### Forward horizon: 126 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| selection (BASELINE — residual momentum, the v1 rank) | +0.0175 | +0.10 | +0.74 | 0.457 | 0.832 | -0.0015→0.0365 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |
| EDGE (v2 — validated event core: SUE; live also folds insider + revisions) | -0.0031 | -0.03 | -0.25 | 0.805 | 0.832 | -0.0085→0.0023 | -0.17 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (orthogonal across axes) | -0.0040 | -0.03 | -0.21 | 0.831 | 0.832 | -0.0286→0.0206 | -0.26 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite (equal-weight) | +0.0077 | +0.05 | +0.39 | 0.699 | 0.832 | -0.0107→0.0262 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| selection-led blend (0.6 sel + 0.4 entry/quality) | +0.0162 | +0.10 | +0.74 | 0.462 | 0.832 | -0.0019→0.0342 | -0.15 | FAILS multiple-testing haircut (DSR<0.90) |
| entry axis (reversal proxy) | -0.0088 | -0.08 | -1.16 | 0.245 | 0.832 | -0.0087→-0.009 | -0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| quality axis (orth factors + SUE) | +0.0038 | +0.03 | +0.21 | 0.832 | 0.832 | 0.0113→-0.0037 | -0.07 | FAILS multiple-testing haircut (DSR<0.90) |
| tailwind axis (sector tilt — declared, not a picker) | -0.0080 | -0.08 | -0.63 | 0.526 | 0.832 | 0.0071→-0.0225 | 0.49 | FAILS multiple-testing haircut (DSR<0.90) |

**CA verdict (63d):**
- edge: NO — IC≤baseline
- conviction_orth: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- conviction_ew: NO — IC≤baseline, Sharpe≤baseline, split-half flips/zero
- selection_led: NO — IC≤baseline, split-half flips/zero

**NEUTRAL — keep the CA board on its validated selection rank.** The conviction composite rides as the displayed per-name profile/verdict (the honest product is a readable profile, not a re-order claimed without the power to back it).

---

**How to read.** `selection` is the baseline the board ships today. A composite must beat it on BOTH IC and Sharpe at 63d *and* not flip sign across halves to earn a GO. The orthogonal composite decorrelates the axes (so it is not just re-weighted selection); the EW and selection-led variants bound the design space. The DSR deflates for the whole family screened (composites × horizons). On a shallow local run the gate is display-only by construction — only the deep + PIT panel can earn a re-rank.

## Axis overlap diagnostic (US/CA panel)

- mean |cross-axis corr| raw → orth: **0.022** → **0.01**
- VIF: {'selection': 1.01, 'entry': 1.0, 'tailwind': 1.0, 'quality': 1.01}
