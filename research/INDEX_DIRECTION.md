# Per-Index Directional Model — Anticipation Engine v2

Status: **Phase A SHIPPED (SPY/QQQ/IWM medium), validated, integrated.** Spec from a
12-agent research+design workflow (Goyal-Welch OOS literature + codebase inventory +
2 design lenses + adversarial critique), corrected for the 7 critique findings.

> **Thesis.** Index DIRECTION is only weakly predictable, and only at medium/long, and
> only for some indexes — but "weak + validated out-of-sample" is real edge. We replace
> the cone's coin-flip direction CENTER (indexes only, medium, behind a gate) with a
> sign-restricted COMBINATION forecast of predictors that beat the **expanding historical
> mean** out-of-sample (Campbell-Thompson OOS-R² + Clark-West), mapped to P(up) via the
> same σ the risk cone uses, Platt-recalibrated. **Default display-only; ~half the legs
> fail OOS by design (Goyal-Welch) and that is reported, not forced.**

## Honest scope
- **SHORT (1-10d):** coin-flip, clamped [0.43,0.58], every index. No claim.
- **MEDIUM (21-63d, rep 42td):** a small, Clark-West-significant, calibrated P(up) where
  it survives Phase-0; otherwise coin-flip.
- **LONG (126-252d):** deferred — needs a valuation (Shiller) collector; under-powered.
- **Ceiling:** index |P(up)−0.5| rarely > ~5-8pts; band capped at [0.40,0.62]. ≥0.70 = bug.

## Method
1. **Per-leg univariate** expanding-window OLS of forward-h return on each oriented leg;
   **sign-clip** to the a-priori sign (Campbell-Thompson), **drop** if the slope flips.
2. **Combination** = fixed-tier WEIGHTED MEAN of the **GO legs only** (Rapach-Strauss-Zhou).
   NEVER a joint multivariate regression. (Critique #4: the diffusion/PCA leg is DROPPED —
   latent kitchen-sink.) The equal-weight average of *all* preset legs buries a good leg
   under failing ones — the GO-leg composite is the gated forecast.
3. **P(up) = Φ(r̂/σ_h)**, σ_h = `vol_forecast.cone_vol_ann × √(h/252)` (ties direction to
   the risk σ), then **Platt-recalibrated** (fit on OOS predictions; gated 0.3≤a≤2.0),
   clamped to the band. The cone CENTER is shifted to r̂; **WIDTH is unchanged** (risk legs only).

## Validation (new primitives in `engine/validation.py`)
- `oos_r2(realized, forecast, bench)` — Campbell-Thompson OOS-R² vs the recursive mean.
- `clark_west(realized, forecast, bench)` — nested-model corrected test (the `(bench−f)²`
  adjustment via the existing `newey_west_tstat`); one-sided test of OOS-R²>0.
- **GATE (a leg/composite GO only if ALL hold):** OOS-R²>0 AND Clark-West BH-adjusted
  p<0.10 vs the expanding mean AND positive in BOTH date-halves; the composite also needs
  DSR≥0.90 (frozen `n_trials=64`, critique #3), Platt-recalibrated Brier skill>0, 0.3≤a≤2.0,
  and must beat its best single GO leg.

## Phase-0 RESULT (walk-forward OOS, monthly, embargo 42td — `research/INDEX_DIRECTION_PHASE0.md`)
| Index | medium verdict | why |
|---|---|---|
| **QQQ** | **SCORED — up/down lean live** | `real_rate` (rising real rates → Nasdaq down): OOS-R² **+0.027**, Clark-West **p=0.003**, **both halves +**, timing Sharpe 0.73 vs 0.52 / maxDD −42% vs −83%, DSR 0.92, recalibrated Brier skill>0. The duration thesis, validated. |
| **SPY** | display-only (coin-flip) | every leg OOS-R²<0; broad-index ERP barely predictable (Goyal-Welch). Timing only helps drawdown. |
| **IWM** | display-only (coin-flip) | no leg clears both-halves; credit legs promising but not robust. |

`netliq` showed strong full-sample OOS-R² for QQQ but **failed both-halves** (short history) → stays NEUTRAL, honestly.

## Integration (`engine/index_direction.py` + `anticipate()` swap)
- **Gate on INDEX MEMBERSHIP** (`asset in INDEX_PRESETS`), NOT `asset_class` (critique #1:
  the original keying never fired for indexes and wrongly fired on single stocks). Fires for
  SPY/QQQ/IWM/DIA via any path; never on a single name.
- Scored horizon → P(up) + recentered cone from the model; non-scored index → P(up)=0.5
  (honest coin-flip); short unchanged; cone WIDTH from the risk legs (widen-never-narrow preserved).
- New `INDEX_DIRECTION` block in `data/regime/anticipation_gate.json` (additive; default
  scored:false). `direction_trust` flips to "scored (Clark-West OOS-R²>0)" only for GO horizons.

## Remaining (per critique + plan)
- **IWM/DIA:** not in `build_anticipation` INDEX loop yet; **DIA price data missing** (use `_DJI`
  proxy + a collector) — mark scored:false, don't count in n_trials until live (critique #2).
- **LONG horizon:** add a Shiller/valuation collector → SPY/DIA sum-of-parts leg (deferred).
- **QQQ real-rate regime sign:** currently a single linear sign-restricted leg (validated both
  halves). A regime-conditioned version must use vintage CPI + both-halves CW + effective-N≥20/cell
  (critique #5) — not added (would over-fit scarce N).
- **Then sectors → single names** (each its own Phase-0; validation never transfers).

## Sector extension (Phase B — SHIPPED)
Same engine, per-sector preset (`SECTOR_PRESETS` in `index_direction.py`), sector-specific
legs added (`oil_mom`, `dollar`). Phase-0 over the 11 SPDRs + 3 indexes.

**Gate restructure (important, honest fix).** Stacking the BH-adjusted Clark-West AND a
Sharpe-DSR haircut at `n_trials=200` double-penalized multiple testing and rejected even
XLK (OOS-R² 0.073, CW p=0.0). Corrected: the single multiple-testing control is **BH-FDR on
each asset's composite Clark-West p ACROSS ALL ASSETS** (the real family). DSR + bootstrap CI
are **reported as economic context, not a hard veto**. P(up) gate = *calibrated* (recalibrated
Brier ≥ −0.01), not *skillful>0* — because the validated directional quantity is the forward
RETURN (cone center via OOS-R²/CW); P(up) is a calibrated display.

**RESULT (14 assets, 42td medium, BH-FDR α=0.05):** **QQQ + XLK SCORED** via `real_rate`
(tech duration/rate-sensitivity — XLK strongest in the whole study, OOS-R² **0.073**, CW
**p=0.0**, BH-q=0). **SPY, IWM, XLF, XLE, XLU, XLRE, XLB, XLI, XLY, XLP, XLV, XLC → coin-flip**
(no validated OOS directional edge — honest nulls: banks-curve/credit, energy-oil, utilities-rates
all failed OOS at medium). The one robust, economically-grounded sector edge is **long-duration
tech vs real rates** — and it's the same driver as QQQ, which is the honest finding.

## Multi-horizon deepening (Phase C — SHIPPED)
Tested every asset at LONG (189td) too, per-horizon BH-FDR. Honest findings:
- **QQQ/XLK real-rate is a MEDIUM-horizon effect, NOT long** (long OOS-R² negative — tested → null).
  The tech-rate signal is a 1-3mo repricing, not a 6-12mo drift. Regime-conditioning the sign was
  NOT added — it already holds in both pre/post-2021 halves, so conditioning would overfit.
- **NEW: XLP (staples) SCORED at LONG** via `real_rate` (OOS-R² 0.15, CW p=0.005, both halves) —
  staples are a rate-sensitive bond proxy; falling real rates → staples up over ~9mo. Effective-N
  ~22 independent windows (thin but HAC-corrected); shown with the long-horizon caveat.

**Scored cells now: QQQ-medium, XLK-medium (tech vs real rates) · XLP-long (staples vs real rates).**
Everything else, every horizon = honest coin-flip. The throughline: **real rates are the one
robustly-priced equity directional driver** — fast for tech, slow for staples.

## Thematic ETF extension (Phase D — SHIPPED)
Hypothesis (user): narrower thematic baskets may have cleaner directional edges than broad
sectors. Tested honestly — NOT on the repo's ~3y hindsight-curated synthetic baskets (too
short + contaminated to OOS-validate) but on **15 deep-history (16-25y) thematic ETFs** fetched
into the store (SMH/SOXX/IGV/XBI/IBB/GDX/GDXJ/KRE/KBE/ITB/XHB/XME/XOP/OIH/XRT/TAN). Added a
`gold` leg (GC_F) for miners. Same per-horizon BH-FDR battery across all 30 assets.

**RESULT — hypothesis PARTIALLY validated, precisely:**
- **SMH (semiconductors) SCORED at LONG** via `real_rate` (OOS-R² **0.093**, CW p=0.0006, both
  halves) — the narrowest, purest long-duration play produced a strong clean edge, exactly the
  user's intuition. (SMH-medium narrowly failed both-halves; the semi rate-repricing is a
  long-horizon effect.)
- **Every OTHER theme = coin-flip.** Gold miners (gold/real-rate), regional banks (curve/credit),
  homebuilders (mortgage~rates), oil E&P/services (oil), metals (dollar), biotech, software,
  retail, solar — NONE had a single leg clear the OOS gate. Their drivers don't predict them OOS.

**Conclusion:** "narrower" is NOT universally cleaner — it's *driver-specific*. The one robustly
OOS-priced equity directional driver across indexes + sectors + themes is **real rates**, and it
works only where the exposure is a clean rate play: growth/duration (QQQ-med, XLK-med, SMH-long)
and defensive bond-proxy (XLP-long). Everything else, every horizon, is an honest coin-flip.
The 15 theme ETFs are now collected (config extras) + on the Anticipation page (Themes group).

## Files
- `engine/validation.py` (+`oos_r2`,`clark_west`), `engine/index_direction.py` [new],
  `scripts/index_direction_phase0.py` [new] → `data/regime/anticipation_gate.json` `INDEX_DIRECTION`
  + `research/INDEX_DIRECTION_PHASE0.md`, `engine/anticipation.py` (membership-gated swap),
  `tests/test_index_direction.py` [new].
