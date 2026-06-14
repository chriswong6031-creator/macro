# Macro-risk → buy/sell signal integration

Make aggregate macro risk a **deterministic, risk-OFF factor** in per-sector and
per-stock signals — penalising macro-sensitive (cyclical) names when macro risk
is high, leaving defensives nearly untouched. Built on branch
`quant-factor-expansion`; ships behind `engine.macro_overlay.enabled`.

## What existed before (the gap)

Macro risk was deterministic only at the **top**, and faded going down:

| Tier | Where | Macro risk before |
|---|---|---|
| Index / posture | `playbook.exposure_dial` | **Full** — NFCI + recession dial the ±2 exposure stance |
| Sector / heat | `technicals._score_components` | **Partial** — a *binary* +7 for ~4 quad-preferred sectors; **no risk-off penalty**; 7/11 sectors macro-blind |
| Per-stock ladder | `cycles.ladder_state` | **Minimal** — one *global* net-liquidity nudge applied identically to every name |

There was **no per-sector or per-stock macro *sensitivity*** anywhere: a high-beta
cyclical and a defensive were treated identically when macro risk rose. (Also a
confirmed bug: `holdings_signals._ladder_for` called `analyze()` with no
`liquidity=`, so the accumulation-overlay ladder disagreed with the sector card.)

## The evidence constraint (why this is small and risk-off-only)

`research/DISLOCATION_VALIDATION.md` (SPY index) shows **one** robust cell — 63d
*median* drawdown ~4pp shallower in non-recession stress; tail drawdown and all
return/hit diffs span 0, and the veto's return edge inverted post-2009. And the
broad cross-section's price cache is only 2023→ (one bull regime, zero risk-off
episodes), so **per-stock macro betas cannot be estimated or validated**. The
SPDRs, however, have deep history. Therefore:

- Frame the overlay strictly as **drawdown / sizing caution, never alpha**.
- Measure sensitivity only at the **sector** tier; per-stock **inherits its
  sector tier** (labelled "sector-level sensitivity"). No per-name fitted beta.
- Magnitudes are **conservative and FIXED** (not tuned to a backtest).

## Methodology

**MRS — macro-risk score ∈ [0,1]** (`engine.conditions.macro_risk_score` /
`macro_risk_series`). A weighted mean of already-persisted, already-lagged legs
(no new data, no new look-ahead), renormalised over whatever is available:

| Leg | Source | Weight |
|---|---|---|
| recession | `conditions.recession.score` | 1.0 |
| drawdown | `conditions.drawdown_risk.score` (the one measured-dd-edge gauge) | 1.0 |
| nfci | `financial_conditions.nfci_pctile`, only when tightening & nfci>0 | 0.5 |
| liquidity | `liquidity_overlay == contracting` (risk-off half only) | 0.5 |
| transition | `transition_state` TRANSITIONING/NEW_REGIME=1, WEAKENING=0.5 | 0.25 |

**Sensitivity** — a coarse 3-tier table over the 11 SPDRs
(`engine.confluence.sector_macro_beta`), keyed by SPDR ticker AND GICS/display
sector name: cyclical/long-duration +1.0 (XLK/XLY/XLF/XLC/XLI/XLB), rate-sensitive
+0.5 (XLRE), neutral 0 (XLE), defensive −0.4 (XLP/XLU/XLV).

**Integration** — two additive seams, both mirroring the existing liquidity nudge,
both no-ops by default:
- **Sector heat** (`_score_components`): `macro_pts = clamp(−macro_max·MRS·beta,
  −macro_max, +macro_max/2)` — asymmetric (penalties bite harder than the small
  defensive credit). Mirrored in `calibrate()` on the historical MRS series so the
  honesty bands track the live score.
- **Per-stock ladder** (`cycles.ladder_state`): `score −= macro_headwind·MRS·
  max(beta,0)` — **subtract-only, buy-setup-only** (FRESH BUY / TURN SIGNALED),
  shown as a separate line from the liquidity nudge. Per-stock beta = its sector's
  beta. *On contracting liquidity, net liquidity is counted both as the uniform
  `LIQ_HEADWIND` and as one MRS leg (≈1pt sector-scaled) — an intentional, bounded
  overlap that adds sector differentiation to the liquidity signal; the validated
  cyclical/defensive split (B-1) depends on the leg, so it is kept rather than
  removed.*

`macro_max = macro_headwind = 7` (conservative; ≤ the +7 regime swing / liquidity
nudge). `enabled:false` ⇒ exact pre-overlay behaviour.

## Validation gate (B-1) — PASS

`scripts/research_macro_sector.py` — on the deep SPDR history, conditional on high
MRS (≥0.5), weekly-declustered, split @ 2016:

```
high-MRS days        cyclical median dd   defensive median dd   gap (neg = correct)
FULL  (1998→2026)        -7.96%               -4.86%             -3.10 pp
H1    (<2016)           -11.21%               -5.55%             -5.66 pp
H2    (≥2016)            -3.73%               -3.04%             -0.69 pp
```

Cyclicals take **deeper** forward-63d drawdowns than defensives under high macro
risk, **sign-stable across both halves** (compressed post-2016, as the Fed-put era
predicts). Gate passed ⇒ conservative magnitude shipped live. The tail (p10) shows
the same ordering. Honest caveat: this validates **drawdown ordering, not a return
edge** — the overlay is a risk filter, not alpha.

## Guardrails

- Low-parameter & FIXED magnitudes; MRS leg-weights are the only config knob.
- Risk-off, subtract-only at the stock tier; asymmetric at the sector tier.
- `calibrate()` mirror kept in exact sync (CI test asserts live == calibrate).
- MRS reads only already-lagged fields ⇒ near-zero new look-ahead; fully
  deterministic in the daily build (pure function of latest.json + static config).
- Kill-switch (`enabled`) + every new param defaults to no-op (fail-soft).
- Honest framing in code/UI: "sector-level sensitivity", drawdown/sizing caution.

## Deferred (do NOT build)

Per-name fitted macro beta — no multi-regime per-name history exists to estimate
or validate it. Revisit only when the breadth caches accumulate a risk-off episode
in both split halves, with point-in-time betas.

## Files

`config.yml` (engine.macro_overlay, engine.confluence.sector_macro_beta) ·
`engine/conditions.py` (macro_risk_score / macro_risk_series / sector_macro_beta) ·
`engine/run.py` (persist `latest.macro_risk`) · `engine/technicals.py`
(`_score_components` + `calibrate` mirror) · `engine/cycles.py` (`ladder_state`
macro block) · `engine/playbook.py` (wire live drag + per-sector beta) ·
`engine/holdings_signals.py` (Track A fix + macro threading) ·
`scripts/build_stock_library.py` + `scripts/build_site.py` (current_macro / beta
wiring) · `scripts/research_macro_sector.py` (B-1 gate) ·
`tests/test_macro_overlay.py`.
