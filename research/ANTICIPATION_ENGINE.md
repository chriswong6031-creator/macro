# Anticipation Engine — Design (multi-horizon probabilistic forecast)

Status: **DESIGN / pre-build.** Produced by a 16-agent research+design workflow
(6 codebase-inventory + 6 literature-research + 2 design lenses + synthesis +
adversarial critique), then corrected for the 6 issues the critique found.

> **One-line thesis.** This is **not a new model**. It is a *generalization* of
> the already-validated, already-shipped `build_vector.forward_risk` conditional
> forward-drawdown cone — lifted out of BTC, made asset-agnostic, extended to
> three horizon ranges, conditioned on a low-dimensional **confluence state**
> assembled from machinery the repo already trusts, and rendered as an asymmetric
> **fan chart**. The only genuinely net-new *factor* is a
> **velocity/acceleration-of-deterioration axis**, display-only until it earns a
> Phase-0 pass. Net-new code is small and contained; everything else is reuse.

Academic anchor: **Growth-at-Risk** (Adrian–Boyarchenko–Giannone 2019, AER) —
condition the *forward distribution's left tail* on current conditions; the
median is near-flat short-horizon, the downside is conditionally forecastable.

---

## 1. North Star & honest scope

### What it WILL claim, by horizon

| Horizon | Leads with | Direction status | Forecastable basis |
|---|---|---|---|
| **SHORT** | Conditional **drawdown band** (avg dip + p05 tail) + **vol cone** | coin-flip — `P(up)` shrunk, capped, labeled `TOSS-UP` | Vol/drawdown persist (HAR/GARCH long-memory; Hawkes self-excitation). Direction skill ≈ 0 (repo OOF Brier 0.250 vs base 0.248). |
| **MEDIUM** | Drawdown band **+ return quantile bands + validated directional tilt** | `LEAN` if leg passes Phase-0 | Momentum (12-1), PEAD/SUE (~60td), VRP — all ~50% decayed (McLean-Pontiff) → haircut. |
| **LONG** | Return drift band (**wide CI**) + trend tail-gate | `LEAN` (valuation/trend) | CAPE R²≈0.4 at 10y only (weak <3y); 200d gate halves drawdown, adds **no** mean return (US/CA hold; A-shares fail). |

### What it will EXPLICITLY REFUSE

- A confident short-horizon **direction** call.
- A dated **crash/recession** call (LPPL overfits; no OOS basis).
- An **estimated-optimal-weight** blend over ~3 cycles (forecast-combination puzzle).
- "N indicators confirm" theatre (correlated legs = illusory confluence).
- Scoring GEX / public put-call / lag-1 autocorrelation / raw VIX level as predictors.
- Treating max confluence as max conviction — **high agreement WIDENS the cone**
  (crowded one-way bet; repo D31 "everything-confirmed = late").

### Four load-bearing house rules (enforced as code invariants, §7)

1. **Phase-0 before scoring.** Display-only until a leg passes split-half +
   purged/embargoed CV + DSR + bootstrap CI in *both* halves. Default = NEUTRAL.
2. **Lead with the predictable quantity** (drawdown band); direction near
   coin-flip short-horizon.
3. **Point-in-time.** No full-sample fits, no look-ahead, no survivorship leakage
   in scored cells. FRED = revised finals (vintage caveat); breadth = current
   constituents (flag those cells lower-trust).
4. **Reuse, never duplicate.** `engine/validation.py`, `cycles.analyze`, the
   `forward_risk`/`_fwd_dd`/`_band_of`/`_cond_up_prob` kernel, `purged_folds`
   imported. Builders return 0 on engine error.

---

## 2. Horizon definitions (config `anticipation.horizons`, trading days)

Each horizon is a **direct forward window** — never sqrt/linear-scaled from
another (per `forward_risk`). Each emits a **range** and a representative window.

| Horizon | Range (td) | Rep. window | Calendar | Maps to |
|---|---|---|---|---|
| **SHORT** | **1–10** | 5td (bands at 3d & 7d) | ~½–2 wk | `cycles` D/3D ladder |
| **MEDIUM** | **21–63** | 42td | ~1–3 mo | `cycles` W ladder |
| **LONG** | **126–252** | 189td | ~6–12 mo | `cycles` M ladder |

---

## 3. Feature taxonomy (8 axes)

Tags: **[reuse]** wire existing output · **[build]** new · **[port]** lift an impl.
Predicts: **RET** (direction) · **RISK** (drawdown/tail) · **VOL** (cone width).
**The asymmetry IS the honesty:** most features condition the cone (RISK/VOL);
only a minority tilt direction (RET), confined to M/L.

- **A. Trend/Momentum (multi-TF)** — `cycles.mtf_snapshot`/`ladder_state`/`signal_age`,
  `predictive_signals.PRICE_LEGS` (12-1, FIP), `residual_alpha` (US/CA). [reuse]
  S/M/L · RET(M/L, decayed)→mostly RISK.
- **B. Velocity/Acceleration of deterioration ← THE GAP** — `vel_z = slope_z(...)`
  (1st-deriv of breadth%/RS/ladder-score), `accel = rolling_slope(vel_z)` (2nd-deriv),
  ported price-only `impulse` (z-MACD-hist × Kaufman ER), realized-variance velocity.
  `engine/velocity.py` [build/port]. S/M · **RISK/VOL only** (see honesty gate).
  Optional Gettleman–Marks cross-sectional price-acceleration as a *separate* RET candidate.
- **C. Volatility/Options/GEX** — HAR realized-vol forecast (cone-width anchor) +
  VRP (index/sector only) in `engine/vol_forecast.py` [build]; VIX/VVIX/MOVE vs mean,
  VIX term structure, CBOE SKEW− [reuse]; **GEX = cone-width/fragility chip ONLY**
  (`gex_engine`, coincident, failed repo's own de-risk Phase-0, never per-name directional).
- **D. Cross-asset/Macro/Credit/Rates/Dollar** — `dislocation` Fed-put switch (validated),
  `conditions` drawdown_risk/`dd10_prob_pct`, EBP (Phase-0 candidate), yield curve
  (re-steepening), broad dollar (asset-specific), HY OAS/copper-gold/net-liquidity
  (coincident → cone-width gate). [reuse + 1 build]
- **E. Valuation/Extension/Bubble** — `extension.extension_signals` (ext_z, parabolic
  grade −94% dd tail, cohort_stretch), valuation-vs-own-history, CAPE-style (LONG only). [reuse]
- **F. Positioning/Crowding** — COT spec washout (es_spx/gold/oil/btc/fx, validated,
  index/cmdty/btc only), `theme_crowding`, `crowding.compute_fragility`, NAAIM/put-call
  extremes. **No validated single-stock leading PIT source → texture/tail-width only for names.** [reuse]
- **G. Breadth/Liquidity** — %>50/200, NH-NL, A-D + breadth **velocity** (Axis B),
  breadth thrust (rare, tiny-N), net liquidity. [reuse + build] **survivorship-flagged.**
- **H. Geopolitical/Uncertainty** — GPR threat/act (1985+ daily), EPU, event proximity
  (FOMC/CPI/NFP/opex), `turning_point` fragility. **All display/overlay → scale cone
  WIDTH, never push direction. Never auto-fade a geopolitical spike** (acts → +1mo rise;
  Fed-put guard). [reuse-validate]

**Hard honesty gate on Axis B:** `residual_alpha` already tested + dropped
velocity/acceleration of residual momentum as *anti-predictive for cross-sectional
return*. So Axis B may **only** feed RISK/VOL (cone width) — never `P(up)` — except
the separate Gettleman–Marks RET tilt, which must pass its own per-market Phase-0.
Axis B is regime-gated: at washout + Fed-put, "accelerating down" → *fragile/two-sided*,
not "more downside." `lag1_autocorr` is **explicitly NOT built** (fails in markets, Guttal 2016).

---

## 4. The new ideas — each with expected Phase-0 outcome

- **(a) Velocity/acceleration of deterioration** → `engine/velocity.py`. Expected:
  **PARTIAL / RISK-side only.** RET form expected FAIL (residual_alpha proved the dead end);
  RISK/VOL widener expected PASS-as-display-then-gated; Gettleman–Marks RET tilt expected MARGINAL.
- **(b) Confluence-intensity without double-counting.** Collapse correlated legs within
  each axis to one representative (`vif`/`top_correlated_pairs`/`resid_z`/`factor_orthogonal`);
  confluence = count of **independent axes agreeing**, equal-weighted. Expected: **KEEP-HEURISTIC**
  (1/N beats learned weights on ~3 cycles; repo's own ensemble Phase-0 confirms). **High agreement WIDENS the cone.**
- **(c) Critical-slowing-down early warning.** Admit rising realized-variance / vol-of-vol
  velocity; **exclude lag-1 autocorrelation.** Expected: variance-velocity PASS-with-caveats
  (Guttal 2016: 0 false-negatives but ~7 false alarms/115y → print the false-alarm rate),
  lag-1-AC NOT BUILT.
- **(d) Analog / conditional-distribution multi-horizon forecaster** → `engine/anticipation.py`.
  Generalize `_fwd_dd`/`_band_of` to emit per asset × horizon the empirical forward
  return quantiles (p05/p25/p50/p75/p95) + forward max-drawdown conditioned on the live
  confluence cell, with empirical-Bayes shrinkage of thin cells. Expected: **PASS**
  (zero fitted weights; the repo's proven, both-halves-stable quantity).

---

## 5. Forecasting + calibration method

### 5.1 Primary — conditional empirical analog distribution (Growth-at-Risk)
For asset `a`, horizon `h`:
1. **Confluence state `S(a,t)` — LOW-dimensional** (the one genuine design choice).
   A 1-D `anticipation_index ∈ [0,100]` band, or at most 2-D `momentum_state × risk_regime`
   (what `build_vector` already uses). **Every Axis A–H feature folds INTO the composite
   index as a validated, orthogonalized z-leg — NOT as a new conditioning dimension**
   (anti-shatter rule → keeps cell counts adequate). Unvalidated axes (B velocity, GPR)
   contribute to the index **only on the RISK/VOL side** and only after Phase-0; until
   then carried as display drivers.
2. **Conditional sample → distribution.** Empirical forward return quantiles + forward
   max-drawdown (`_fwd_dd`: avg dip, p05 tail) over window `h` from historical dates where
   `S(a,·)` matched. Empirical quantiles cannot cross.
3. **Vol cone width** = HAR forecast at `h`, widened by event-proximity, backwardation,
   turning-point fragility, variance-velocity.
4. **`P(up)`** = empirical-Bayes shrunk to marginal, nudged by validated tilts, **capped to
   the empirically-observed reliable band (~[0.43,0.58], config)** — *not* the loose [0.30,0.70]
   the first draft used (critique fix #5). Thin cell (n<min) → marginal. **Short horizon forced
   to TOSS-UP.**
5. **Conviction tier** = TOSS-UP/LEAN/EDGE from |p−50|, gated by **cell sample size** (n<300
   can never print EDGE); orthogonal tape vote can only **demote**.

### 5.2 Overlapping-label leakage fix (the core hazard — corrected per critique #4)
- **CV split BY CALENDAR DATE, globally.** Assign whole calendar blocks (≥ max-horizon apart)
  to folds so **no date appears in both train and test for ANY name** — a per-name embargo
  does *not* remove cross-sectional contemporaneous overlap (two tickers same date share the
  market factor). Embargo on the **date axis**, not per-series row index.
- `purged_folds` with **embargo = max horizon** (long-horizon window in td).
- Embargo the pre-half's last max(horizons) rows before any split (the documented
  `calibrate_vector` fix; a bare `split_date` leaks).
- `fold_robust`: full-sample sign == want, zero fold flips, all-but-one folds agree.
- **Effective-N, not raw eval count** = non-overlapping count (history_td / horizon_td);
  cluster overlapping evals by calendar; Newey-West HAC t-stats; judge ordering/sign/
  monotonicity, never magnitudes.
- Test: `test_no_calendar_leakage_cross_name`.

### 5.3 Calibration (LEVEL check, on OOF predictions)
`brier_reliability` + `platt_fit` (Platt, not isotonic — isotonic overfits few cycles) +
**`crps`** (the **one** net-new validation primitive — scipy-free `E|X−y| − ½E|X−X′|`,
scores the *full distribution*; Brier is binary-only). Reliability curve ships as a UI trust badge.

### 5.4 Optional ML layer (shadow, behind promotion gate, never default-on)
**Conformalized Quantile Regression** (Romano-Patterson-Candès 2019; split-conformal → finite-sample
coverage, fixes quantile-crossing) over a quantile-GBM base. **Shadow/display-only until it beats
BOTH the empirical-analog baseline AND the best single leg on OOS CRPS + interval coverage in BOTH
split-halves across purged folds.** On ~3 cycles, expected to fail → stays shadow. Raw,
non-conformalized intervals never ship.

---

## 6. Output JSON schema + illustration

Per-asset JSON attached as `rec['anticipation']` in `build_stock_library._one`; index-level
into `latest.json`. Keys: `asset`, `asset_class`, `as_of`, `trust{tier,gate,scored,n_cell,thin,
split_stable,survivorship_flag,vintage_flag}`, `anticipation_index`, `index_band`,
`confluence{axes[],n_agree,n_axes_independent,dispersion,main_contradiction{en,zh}}`,
`horizons{short,medium,long}` each with `range_td`, `window_td`, `direction`, `p_up`, `conviction`,
`drawdown{avg_dip_pct,p05_tail_pct,base_dip_pct,n}`, `ret_quantiles{p05,p25,p50,p75,p95}`,
`vol_cone{har_vol_ann,width_mult,wideners[]}`, `cell_n`, `thin`, `stability`,
`calibration{brier_skill,platt_a,crps}`, `headline{en,zh}`, plus `directional_tilt`/`trend_gate`/
`valuation_band` on M/L; `drivers[]` (signed, scored vs display_only), `caveats[]`, `guards{}`,
`guard_flags[]`.

**Illustration** (client-side; per-asset panel in `stockdata.js`, standalone page later):
1. **Fan/cone chart** (Bank-of-England style) — nested asymmetric bands (p05/p25/p50/p75/p95)
   across the three horizon **ranges** on one inline **SVG** (no Plotly dep). Downside emphasized;
   median dashed/grey when coin-flip.
2. **Confluence radar** — 8-axis spider; spoke color = dir, length = |z|; `risk_only`/`width_only`/
   unscored axes rendered **hollow/dashed/grey** so the user sees direction came from few axes.
3. **Driver attribution bars** — signed, weight-sized; scored vs display-only visually distinct.
4. **Trust badges** — n_cell, thin/split-stable/survivorship/vintage; thin/unstable greyed/widened.
5. **Reliability mini-plot** when a track record exists.
6. **Honesty banner**: "Short-term direction not forecastable — showing risk distribution."

i18n gotcha honored: `t()`/`td()` return span Markup — **never** inside an HTML `title=` attribute.

---

## 7. Phase-0 protocol + honesty guards

### 7.1 `scripts/anticipation_phase0.py` (mirrors `calibrate_vector.py` + `sector_bottom_phase0.py`)
A leg is declared in a `SIGNALS` dict (bands + labels + `want` sign + optional `shape='extremes'`)
so it auto-rides every gate. **Gauges judged on forward DRAWDOWN at SHORT; return-predictors at LONG.**
Gates (all from `engine/validation.py`): (1) walk-forward PIT (state at `i` from `close[i-600:i+1]`,
outcomes `close[i+1:i+1+h]`); (2) split-half with embargo; (3) purged+embargoed CV + `fold_robust`;
(4) monotonicity (`rank_trend` |ρ|>0.6) OR `_extremes_verdict` for U-shapes — never `rank_trend` on a
U-shape; (5) DSR haircut with honest `n_trials` = (#states × #legs × #horizons); (6) block-bootstrap CI
(lower bound excludes 0); (7) distribution calibration (`brier_reliability` + `platt_fit` + `crps`,
must beat climatology); (8) cross-sectional family control (`rank_ic` + Newey-West + BH-FDR, t>3); (9)
PIT recompute test; (10) **power guard** → shallow/survivorship-inflated data ⇒ FORCED NEUTRAL.

Writes `data/regime/anticipation_gate.json = {asset_class:{leg: GO|NEUTRAL}}`, overwritten only on a
clean run. The cone RANK/headline **always uses the validated empirical baseline** unless a leg is GO.
A composite/ML layer is GO only if it beats BOTH the empirical baseline AND the best single leg on OOS
CRPS + coverage in BOTH halves — else KEEP-HEURISTIC.

### 7.2 Invariants (tests in `tests/test_anticipation.py` unless noted)
never-a-crash-call · short-direction-is-coinflip (P(up) clamp; short can't exceed TOSS-UP) ·
cone-widens-with-horizon · downside-cone-wider-under-stress · display-only-until-GO (source-grep:
scoring engines don't import velocity/anticipation as a scored leg) · missing-axis-recorded-not-neutral ·
confluence-no-double-count · full-agreement-widens-cone · acceleration-signflip-at-washout ·
gex-width-only · thin-cell-falls-back-to-marginal · PIT (`test_anticipation_pit.py`) ·
axis-B-never-directional · builder-returns-zero-on-error · bilingual · no-cross-class-transfer ·
**no-calendar-leakage-cross-name** (critique #4).

---

## 8. Shared-core + per-asset-class parameterization

One pure core `engine/anticipation.py::anticipate(close, high, *, preset, feature_frame, vix_ctx,
macro_ctx, gate) -> dict`. Asset class enters **only via a preset** (mirrors `cycles.CYCLE_PRESETS`
+ `baskets_region`). Per-class: `feature_manifest`, `cycle_preset`, `horizons`, `cost_bps`,
`trading_year`, `directional_prior` (US trend validated; commodity/FX **none**; BTC cycle-conditioned),
`calibration_target` (fwd dd + ret quantiles), `survivorship_flag`.

**Hard cross-class rules:** no global momentum prior; **GEX never in the core**; **re-run Phase-0 per
class** (validation does NOT transfer — A-shares mean-revert, HK no edge, commodity mtf inverts oil/gold
→ read polarity live, FX no momentum prior). Each class reads its own gate block; unvalidated class
defaults NEUTRAL/display-only.

---

## 9. Phased plan (corrected per critique)

**MVP asset class = US stocks + 11 SPDR sectors + SPY/QQQ** — richest data (deep PIT OHLCV in
`data/stocks`, VIX/SKEW/COT/breadth/FRED). Sector ETFs are "just price series" (proven by `sector_bottom`).

**Substrate correction (critique #1):** the real calibration substrate is the **per-name OHLCV in
`data/stocks` walked PIT** inside `build_stock_library` (exactly as `forward_risk` already does) — NOT
`_conviction_features.parquet` (no date/ticker, medium-horizon only → unusable for the analog method,
calendar CV, or short/long cones). Any harness panel is rebuilt with date+ticker+all-three-horizon
(1-10 / 21-63 / 126-252d) MAE/MFE/ret labels.

**Per-name LONG under-power (critique #2):** compute cell adequacy on **effective-N** (= history_td /
horizon_td), not raw rows. The per-name LONG cone is **structurally under-powered** → falls back to the
index/sector cone (or marginal) with a forced-thin badge; **never a per-name LONG direction.** Per-name
cones are reliable at SHORT/MEDIUM.

- **Phase 1 — velocity + vol forecast (display-only) · ~M.** `engine/velocity.py` [new],
  `engine/vol_forecast.py` [new], `validation.crps()` [edit]; tests incl. PIT recompute.
- **Phase 2 — shared kernel + core engine + Phase-0 harness (display-only) · ~L.**
  **MANDATORY (critique #3):** lift `_fwd_dd`/`_band_of`/`_cond_up_prob`/`oof_cell_probs` into a shared
  `engine/forward_dist.py` (oof_cell_probs currently lives in the `calibrate_vector` script, not the
  engine), **keeping `build_vector` byte-identical under a golden test**; parameterize the split date
  per asset class (no hard-coded 2021). `engine/anticipation.py` [new], `scripts/anticipation_phase0.py`
  [new], `config.yml` `anticipation:` block [edit]; invariant + PIT tests.
- **Phase 3 — per-asset compute at scale + integration · ~M.** Call `anticipate()` inside
  `build_stock_library._one` (rides the existing ProcessPool); index/macro leaf in `engine/run.py` →
  `latest.json`. **Benchmark `_one` incremental cost on the deepest name first (critique #6); LONG
  per-name off by default; heavy Phase-0 in its own parallel CI job.**
- **Phase 4 — illustration · ~M.** `stockdata.js` `panel_anticipation` (SVG fan + radar + driver bars +
  trust/reliability badges), `stock.html.j2` shell, `build_site.py` sector/index view, `i18n.py` lexicon;
  optional standalone `templates/anticipation.html.j2`.
- **Phase 5 — promotion review + cross-asset port · ~M/class.** Only GO legs score (expect KEEP-HEURISTIC
  on ~3 cycles). Port preset to sector/index → commodity (add `CYCLE_PRESETS["commodity"]`, read polarity
  live) → BTC (reuse native `impulse`). Per-class Phase-0 each (expect NEUTRAL/display-only on shallow non-US).
- **Phase 6 — optional ML shadow · ~L.** CQR/quantile-GBM behind `ensemble_promotion`.

**CI:** engine job ~42m against 70m timeout → forecast must ride inside `build_stock_library`'s pool
(HAR/velocity vectorized, cheap incremental); no heavy serial step; Phase-0 its own parallel job; builders
try/except → return 0.

---

## 10. Open decisions for the user

1. **Starting target** — US per-stock cones first, or index/macro (SPY leaf in `run.py`) first (faster
   to a visible result, single leaf, but no per-name cone)?
2. **Page surface** — per-asset panel on existing stock pages, a dedicated standalone illustrated
   "Anticipation" page, or both?
3. **ML** — defer to a gated Phase-6 shadow (recommended; will likely fail the gate on ~3 cycles), or
   build the CQR scaffold earlier?
4. **GPR/EPU/EBP** — build as display-only drivers + Phase-0 candidates now (recommended), or pure display?
5. **Velocity scope** — RISK/VOL-only + regime-gated (recommended), plus optionally re-test the RET tilt?
6. **Shared-kernel refactor** — mandatory per critique (one source of truth, golden-tested) vs duplicate.
7. **Non-US** — ship as honest display-only cones with "not validated for this market" badges vs restrict
   to US/BTC until deeper data accrues.
