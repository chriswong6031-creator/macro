# Cross-Asset Confirmation — Phase-0 validation

Split-half **2013-01-01** · target: forward **63-day** S&P max drawdown (and P(≥10% drawdown)).

**Question.** Does the cross-asset DIVERGENCE add INCREMENTAL forward-drawdown info beyond the equity-side drawdown_risk gauge?

No look-ahead: signals = causal engine.bonds/conditions frames; target = strictly-forward 63d S&P drawdown. Analysis is restricted to the window where the credit (HY-OAS) and rates-vol (MOVE) inputs exist (else the pre-half is all-zero flags). The validated `lead_caution` construct = credit + rates-vol + un-inversion (a BOND-leading proxy); it is intentionally NOT byte-identical to the engine's risk-leg votes, and FX is excluded (literature: dollar/EM-FX risk-off is COINCIDENT, not leading — display-only by construction). The block-bootstrap CI resamples the flagged-only series, so it is an approximate (not calendar-contiguous) interval. Several `ci_excludes_base` tests are run, so treat a single marginal pass as weak (no formal FDR applied). CONFIRMED-to-score needs incremental edge after controlling for drawdown_risk AND a both-halves-meaningful split.

## 1 · `lead_caution` (0–3 bond leading flags) vs forward drawdown

- IC(stress, forward dd-depth) full / pre / post = **0.099 / 0.187 / 0.021** → standalone **DIRECTIONAL**.
- span 2002-11-12..2026-03-18, n 6092.

## 2 · The decisive test — incremental partial IC (controlling for `drawdown_risk`)

Partial Spearman(`lead_caution`, forward-dd | `drawdown_risk`): full **0.046**, pre **0.075**, post **-0.003** (n 6092).

_partial Spearman(lead_caution, forward-dd | drawdown_risk). ~0 ⇒ redundant with the gauge we already have (DISPLAY-ONLY confirmed)._

## 3 · The divergence config (panel headline: leading caution while equities calm)

Within **low-drawdown_risk** days, `lead_caution ≥ 2` → P(dd10) **0.096** vs base **0.076** (+1.9pp); bootstrap CI [0.037, 0.094, 0.165] — excludes base: **False** (n 4421, firings 732).

## 4 · Cycle divergence (bond clock later than equities)

`cycle_divergence` → P(dd10) **0.114** vs base **0.133** (-1.9pp), n 6092, firings 1605.

## 5 · Component flags (standalone forward-dd lift)

| flag | n | firings | P(dd10) flagged | base | lift (pp) | CI excludes base |
|---|--:|--:|--:|--:|--:|---|
| f_credit | 6092 | 3686 | 0.178 | 0.133 | +4.5 | False |
| f_rates_vol | 6092 | 2317 | 0.181 | 0.133 | +4.8 | False |
| f_uninv | 6092 | 301 | 0.083 | 0.133 | -5.0 | False |

## Decision

**DISPLAY-ONLY (confirmed) — the cross-asset caution count adds ~no forward-drawdown information beyond the drawdown_risk gauge, and the divergence config does not robustly lift the drawdown rate. This matches the literature (these reads are largely COINCIDENT) and the bonds calibration (composite ≈ the drawdown_risk leg alone). The confirmation panel stays a context/early-attention read and is NEVER scored.**

_Honesty bar: this is the gate that decides whether the cross-asset confirmation read is allowed to feed a score. Display-only unless the incremental edge is real and holds on both halves — and even then, only after a re-confirm on the next data refresh._