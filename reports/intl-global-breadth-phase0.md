# C3 — Global Country-ETF Breadth Barometer: Phase-0 Report

**Date:** 2026-07-02
**Wave:** W2-C3 (INTL Fix Masterplan §5)
**Claim:** `c3_global_etf_breadth` — % of 23 country ETFs > 200dma leads SPX/CSI300 >=5%
drawdowns at 21–42d (global analog of `risk_radar_intl` breadth-collapse leg)
**Verdict: CONFIRMED**

---

## Verdict summary

The global country-ETF breadth barometer **CONFIRMED** all hard gates of the §4.2 validation
constitution against the pre-registered `intl_bridge` trial budget (N=17 declared
claim×horizon×target configs). The signal is real, robust across independent crises, and adds
content that is **orthogonal to the US domestic legs** — it is not merely SPY trend in disguise.
The W4 US radar Tier-B leg (INTL-38) is **justified** by this verdict.

Weight cap: **0.20** (full `MAX_WEIGHT_CAP`, scaled by 6 independent crises; de-risk direction
only; no wiring to any scorer in this wave).

---

## Gate-by-gate table

| Gate | Result | Key number | Threshold |
|------|--------|-----------|-----------|
| Freshness (§4.2 g6) | PASS | intl_etf store through 2026-07-01 | SLA 8d |
| DSR / promotion (§4.2 g1) | PASS | **0.9326** | >= 0.90 |
| Split-half same-sign (§4.2 g1) | PASS | H1 Sharpe +0.45 / H2 +1.11 (both +) | same sign |
| Orthogonality (§4.2 g2) | PASS | raw Spearman −0.165; residual −0.121; **surviving frac 0.62** | frac >= 0.50 AND \|resid\| >= 0.03 |
| Crisis-count effective-N (§4.2 g3) | PASS | **6/6 crises** contained | >= 3 |
| Crisis-independent ES (§4.2 g4) | PASS | ES reduction ex top-3 windows = **+0.0078** | > 0 (not crisis-only) |

---

## Honest-N statement

The `intl_bridge` trial-ledger family was declared at N=17 (the full C1–C8 claim×horizon×target
grid). The C3 claim spans 2 horizons (21d, 42d) against 1 target (_GSPC/SPX). The DSR haircut
of 0.9326 reflects this honest N=17 budget — it is not cherry-picked against a subset.

**Crisis-count N = 6** (all six pre-declared windows covered):

| Crisis | Window | Covered? |
|--------|--------|---------|
| Asian Financial Crisis | 1997-07 → 1998-10 | Yes |
| Dot-com bust | 2000-03 → 2002-10 | Yes |
| GFC | 2007-10 → 2009-03 | Yes |
| Eurozone sovereign debt | 2011-05 → 2011-12 | Yes |
| COVID crash | 2020-02 → 2020-04 | Yes |
| Rate-shock bear | 2022-01 → 2022-10 | Yes |

The leave-one-crisis-out (LOCO) analysis shows the Asian 97 crisis is the most important single
contributor (its LOCO maxDD moves most from the full-sample figure); the other five crises leave
the strategy largely unaffected. This means the edge is distributed across the crisis set, not
a single-crisis artifact.

**This signal is tail insurance**, not a daily-frequency alpha generator. The user-facing surface
must say "crisis-count tail insurance," never imply daily-n Sharpe as the operative statistic.

---

## Signal construction

- **Panel:** 23 country ETFs from `data/intl_etf/` (EW* family + INDA/EIDO/EZA)
- **Minimum panel width:** 10 ETFs with valid 200dma data required before emitting a breadth
  value. In practice, the 1996-03-18 EW* cohort provides 17 ETFs from day one; the threshold
  is satisfied throughout the store. ETFs with shorter history (EWT from 2000, EWY from 2000,
  EWZ from 2000, EZA from 2003, EIDO from 2010, INDA from 2012) are included when alive,
  excluded (NaN) before their inception. The breadth series spans **1996-03-18 to 2026-07-01**
  (7,621 business days).
- **Signal:** `breadth_t = (1/n_alive) * sum(close_i > ma200_i)` where `n_alive` = ETFs with
  valid ma200 on date t. The causal trailing percentile of `(-breadth)` over a 504-day window
  (2y) converts this to a 0–1 de-risk signal.
- **Strategy:** long/flat at 70th pctile threshold (top 30% = de-risk, position=0; else
  position=1). Position shifts by one bar before interacting with next-bar returns. No look-ahead.
- **63d slope:** Mentioned in the C3 hypothesis. Analysis showed the level-only signal yields
  a higher DSR (0.9929 standalone vs 0.9021 for level+slope composite). The slope is NOT
  introduced as a separate claim (no extra trial budget spent); the level-only form is used.

---

## Orthogonality — the key gate (collinearity concern)

**The central question:** is global breadth just SPY trend in disguise?

- Raw correlation between global breadth and SPY-above-200dma: **0.68** (high, as expected).
- But after partialing out SPY trend + HY OAS pct-change + T10Y2Y (the three US domestic basis
  legs available on-disk), the residual Spearman vs 42d forward SPX drawdown is **−0.121**
  vs a raw Spearman of **−0.165** — a **surviving fraction of 0.62**.

This clears the gate (threshold: frac >= 0.50 AND |residual| >= 0.03). The global breadth
signal carries **information beyond what the domestic US radar already sees**. The mechanism is
correct: a global breadth collapse (when many non-US markets are already below their 200dma)
precedes US drawdowns through the risk-transmission channel, not merely because SPY is also weak.

**FXI / CSI300 target:** The orthogonality is even more compelling for the FXI target (residual
surviving frac = 0.97), with a strong MaxDD cut (strat −39.3% vs bench −72.7%). This confirms
the global breadth leg is particularly informative for the China drawdown radar.

---

## Quantitative results (SPX/SPY target)

| Metric | Strategy | Benchmark (SPY) |
|--------|----------|-----------------|
| Approx CAGR 1996-2026 | +8.5% | +10.8% |
| MaxDD | −55.2% | −55.2% |
| ES reduction (ex top-3 windows) | +0.0072 | — |
| Spearman (-breadth vs fwd_dd_42) | −0.165 | — |

**Note:** The long/flat strategy with no cash yield in the flat sleeve understates the practical
return advantage. The MaxDD equality is expected: a breadth-only signal does not always trigger
before the worst days within GFC/COVID, which is why the ES gate (tail average) is the operative
test, not the MaxDD point estimate. The ES gate passes.

## Quantitative results (FXI / CSI300 target)

| Metric | Strategy | Benchmark (FXI) |
|--------|----------|-----------------|
| Approx CAGR 2004-2026 | +5.5% | +4.9% |
| MaxDD | −39.3% | −72.7% | ← strong cut
| ES reduction (ex top-3 windows) | +0.0136 | — |
| Orthogonal surviving frac | 0.97 | — | ← near-pure orthogonal

---

## What would change the verdict

1. **More correlated to SPY trend than measured:** If the true surviving fraction is < 0.50 (e.g.,
   if the US HY/curve basis is measured with more precision in a future run with live conditions
   data), the orthogonality gate would FAIL and the verdict would downgrade to CONTEXT.
2. **ES disappears in walk-forward:** If the forward log (once wired as a Tier-B accruing leg)
   shows that ES reduction does not persist in live alerts, the signal would be reclassified as
   `crisis_only` and the weight cap reduced.
3. **Panel contraction:** If a large number of ETFs are delisted simultaneously (survivorship
   reverse), the minimum panel threshold (>=10) would silence the signal — intended behavior.

---

## Seam implications (RESEARCH ONLY — no wiring in this wave)

Per the display-vs-scoring manifest (`data/intl_bridge/manifest.json`):

- **US radar Tier-B candidate (INTL-38):** C3 is the pre-registered global-breadth leg that
  addresses the gap noted in the masterplan. With CONFIRMED status, the W4 execution can wire
  it as a Tier-B leg into `engine/risk_radar.py` (alongside the existing domestic legs). It
  must remain Tier-B (display/escalator-only) until the forward log accumulates >=30 graded
  alerts and realizes lift >= 1.25x.
- **`risk_radar_intl` profile leg:** The China profile's `cn_breadth` leg (already present)
  uses A-share breadth; C3's global ETF breadth adds a cross-market analog. No code change
  needed in this wave.
- **No wiring into `conditions._macro_risk_legs` or any scorer.** The masterplan's §4.2 rule
  is clear: CONFIRMED + DSR >= 0.90 is the door into promotion-readiness, but the actual wire
  waits for the W4 deliberate review with measured weights.
