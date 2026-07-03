# W4.2 Hazard Fit — BINDING VERDICT (honesty ledger)
**Fit date:** 2026-07-03
**Branch:** wave/w4-2-hazard-fit
**Gates:** PREREGISTRATION.md §2 — HZ-{up,dn}-{1m,3m,6m} (the 6-cell `hazard` family, BH-FDR q=0.10)
**Status:** COMPLETE — see `data/hazard/model_price_c4414dcb.json`
**Epoch:** `price_c4414dcb` (corrected — see §0)

---

## 0. Epoch sanity check — THE PANEL WAS ON THE WRONG BASIS, and was rebuilt

The W4.1 panel was stamped `tr_4d5643ac`. Inspection of `scripts/build_hazard_panel.py`
confirmed the turn definitions (leg/age/label construction) were detected on **total-return
closes** (`_detect_turns_for_instrument(..., basis="close_tr")`, and `turn_epoch(basis="close_tr")`).
That violates the **D4_SUBSTRATE §1 contract** (lines 84, 88): *structure math — ZigZag turns,
age, invalidation — consumes the `price` basis (split-adjusted, dividend-UNadjusted); only
return/momentum/RS math consumes `tr`.* Dividends inject spurious drift into a total-return
tape, which moves ZigZag pivot dates and therefore moves every leg boundary, age, and label.

**The dual-basis store (T5) has landed** — `data/yahoo/*.parquet` carries a `close_price`
column (verified XLK/SPY/EWJ). The Shenwan CN sector `close` is *already* a price-basis
custodian index (D4 §1.54/§175), so CN needed no change. The fix was therefore surgical:
detect turns on `close_price` for yahoo instruments (keeping the TR `close` for RS/momentum
features), label the epoch `price_*`, and rebuild.

**Event-count diff (the honest artifact):**

| Metric | TR epoch `tr_4d5643ac` | PRICE epoch `price_c4414dcb` | Δ |
|---|---|---|---|
| Total person-period rows | 18,526 | 18,619 | +93 (+0.5%) |
| y1 events | 7,496 | 7,774 | **+278 (+3.7%)** |
| us_sector up / down events | (part of 574/…) | 616 / 376 | — |
| country up / down events | — | 2,322 / 1,506 | — |
| cn_sector up / down events | — | 1,749 / 1,205 | — |

Per-instrument turn-count shifts confirmed the mechanism (14% ZigZag, confirmed turns):
XLK +2, XLE −4, EWZ +2, XLF/EWJ/FXI unchanged — dividend drift moves pivots most on
high-yield tapes (energy, financials). The stale `tr_*` panel + KM baseline were removed
(no code/doc/config referenced them; the regenerated `W41_PANEL_CENSUS.md` and `rho_hat.json`
now reflect the price epoch). **The fit below was run only on the price-basis panel.**

---

## 1. What this fit is

Two discrete-time logistic hazards (Allison person-period form), one per direction
d ∈ {up→peak, down→trough}: λ(t) = sigmoid(β₀ + β·x_t). Hand-rolled numpy L2 logistic
(NO sklearn/statsmodels/lifelines — D5 §1.9; the fit module has a test asserting the ban).
Walk-forward by **DATE blocks** (annual, expanding origin, first test year 2010, 6-month
embargo; blocks by date, never by instrument). Continuous features standardized by
train-fold mean/sd (stored in the artifact). Calibration is PAV isotonic.

**Feature set (W2.5-bound §6.6 + own/family-normalized age):**
`age_b1..b5`, `log_age_ratio`, `amp_proxy`, `pos_osc/100`, `osc_slope/10`, `trend_pass`,
`mom_score`, `rs_63d`, `vol_pctile`, regime `quad_Q2..Q4` + `liq_expanding`,
family dummies `fam_country`/`fam_cn` (us_sector & Q1 & non-expanding-liq are reference levels).

**Features dropped, disclosed:**
- `state_score` — DEAD (ρ=−0.968 with pos_osc, VIF~30; W2.5). Absent from the panel.
- `breadth_div` / `breadth_missing` — **the W4.1 panel does not compute a cross-sectional
  breadth column**, so this regime feature is *dropped for absence*, not for a failed CI.
  Honest consequence: the breadth axis of the regime block is simply not in this fit.
- `amp_ratio` (D5's median-normalized amplitude) is not in the panel; the shipped W2.5
  `amp_proxy` (bounded 0–1 expanding pctile) is used in its place.

---

## 2. THE VERDICT — 4 of 6 cells PASS, 2 ship PRIOR

Gate (frozen, PREREG §2): a cell PASSES only if **OOS Brier(model) < Brier(family-stratified
KM)** with a **month-block bootstrap 90% CI on the paired ΔBrier excluding 0**, AND it
survives **BH-FDR at q=0.10** across the 6-cell family. Failing cells ship the KM PRIOR.

Two corrections were required for the gate to be honest (both caught and fixed before the
verdict — see §2.1):

| cell | Brier model | Brier KM | ΔBrier (KM−model) | 90% CI | boot p | yrs gap>0 | BH | **verdict** |
|---|---|---|---|---|---|---|---|---|
| **up/1m** | 0.2216 | 0.2394 | **+0.0140** | [+0.0068, +0.0209] | 0.0012 | 14/17 | ✓ | **PASS** |
| up/3m | 0.2492 | 0.2563 | +0.0071 | [−0.0003, +0.0143] | 0.061 | 11/17 | ✓ | **PRIOR** |
| up/6m | 0.2431 | 0.2433 | +0.0002 | [−0.0057, +0.0062] | 0.522 | 10/17 | ✗ | **PRIOR** |
| **down/1m** | 0.2308 | 0.2449 | **+0.0141** | [+0.0034, +0.0247] | 0.018 | 11/17 | ✓ | **PASS** |
| **down/3m** | 0.1765 | 0.1843 | **+0.0078** | [+0.0005, +0.0155] | 0.036 | 13/17 | ✓ | **PASS** (marginal) |
| **down/6m** | 0.1046 | 0.1088 | **+0.0042** | [+0.0005, +0.0079] | 0.024 | 12/17 | ✓ | **PASS** (marginal) |

**Headline:** The two **1-month** cells (up & down) are the robust wins — near-term turn
hazard is genuinely and reliably more predictable than the age-only family KM. The
**down-side 3m/6m** cells pass by the letter of the pre-registration (CI excludes 0, survive
BH) but are **marginal** (lower CI bounds of +0.0005 — a hair above zero) and are flagged
as such. **up/3m and up/6m ship PRIOR**: up/3m's CI touches zero (p=0.061); up/6m has
essentially **no skill** (gap ≈ 0, p=0.52). This lands close to the pre-registered
expectation ("most cells will likely ship PRIOR initially… a disclosed prior, not a failure").

### 2.1 Two gate-integrity fixes (why an initial 6/6 was verification theater)

A first pass reported **6/6 PASS** with 3m/6m gaps of 0.06–0.095. That was wrong, twice:

1. **Strawman KM baseline.** Compounding a single age-bucket's 1-month hazard geometrically
   to 6 months (`1−(1−λ)^h`) made the KM Brier *worse than the naive base rate* (e.g. up/6m
   KM 0.330 vs base 0.240) — an instrument ages into *other* buckets over the horizon, so
   the single-bucket compounding is a poor multi-month predictor. **Fix:** the family-
   stratified KM now predicts the **train-fold empirical horizon-h rate** by (family,
   direction, age_bucket) directly — the correctly-specified KM survival integrated to h,
   never worse than the base rate (there is a test for this).

2. **Calibration-on-eval leak.** The PAV isotonic was fit on the *pooled OOS* predictions
   and then scored on the *same* rows — the calibration map saw the eval labels, rescuing
   the mis-compounded 3m/6m raw predictions. On **raw** (leak-free) predictions the 3m/6m
   model was actually *worse* than KM (up/6m raw gap −0.060). **Fix:** the skill gate is now
   scored on **out-of-fold** calibrated predictions — a PAV isotonic fit per fold on the
   fold's **train** predictions only, applied to that fold's OOS. The pooled-OOS isotonic is
   retained *only* as the shipped live-calibration map, never for the gate.

The 4/6 verdict above is the leak-free result.

---

## 3. Feature coefficient table (final expanding fold; standardized continuous)

**Up-leg → peak hazard** (economically coherent):

| feature | coef | reading |
|---|---|---|
| log_age_ratio | +0.050 | older up-legs → higher peak hazard (cycle mean-reversion) |
| pos_osc/100 | −0.527 | high oscillator → lower imminent-top hazard (trend persists) |
| osc_slope/10 | −0.218 | rising oscillator → lower top hazard |
| trend_pass | −0.355 | above 200-DMA → lower near-term top hazard |
| mom_score | +0.248 | elevated 6m−1m momentum → higher near-term reversal risk |
| rs_63d | +0.138 | strong RS → higher near-term reversal risk |
| vol_pctile | +0.103 | high realized vol → higher top hazard |

**Down-leg → trough hazard:**

| feature | coef | reading |
|---|---|---|
| vol_pctile | +0.473 | high vol → higher trough hazard (capitulation) |
| trend_pass | +0.423 | reclaiming trend → higher trough hazard (bottom reclaim) |
| pos_osc/100 | +0.275 | oscillator lifting off lows → trough forming |
| log_age_ratio | +0.182 | older down-legs → higher trough hazard |

### 3.1 Regime sub-gate (A14) — each regime feature's own coefficient CI (month-block bootstrap, 90%)

| direction | feature | coef | 90% CI | clears (CI∌0)? |
|---|---|---|---|---|
| up | quad_Q2 | −0.048 | [−0.241, +0.139] | **NO → DROP** |
| up | quad_Q3 | +0.278 | [+0.079, +0.496] | yes |
| up | quad_Q4 | +0.008 | [−0.174, +0.184] | **NO → DROP** |
| up | liq_expanding | −0.254 | [−0.446, −0.058] | yes |
| down | quad_Q2 | +0.459 | [+0.271, +0.652] | yes |
| down | quad_Q3 | −0.021 | [−0.261, +0.228] | **NO → DROP** |
| down | quad_Q4 | +0.338 | [+0.095, +0.600] | yes |
| down | liq_expanding | +0.225 | [−0.013, +0.502] | **NO → DROP** |

**Immateriality check (important):** zeroing each direction's non-clearing regime dummies
leaves the passing **1-month** cells unchanged — up/1m gap 0.0140 → 0.0149; down/1m 0.0141
→ 0.0158 (if anything marginally stronger). **The passing edge does not lean on the regime
block** — it is carried by age/oscillator/momentum structure. That materially *reduces* this
result's exposure to the P-D5-1 revision leak.

### 3.2 Lagged-quad robustness (P-D5-1) — quad-conditioned results are REVISION-OPTIMISTIC

Refitting with quad/liquidity dummies lagged +1 month (a proxy for known-vintage quad):
`quad_lag1_delta_brier` = **0.0002 (up)**, **0.0029 (down)** — both **< 0.005**, so the
macro-derived quad is *not* dropped wholesale by the robustness gate. **However**, the
macro quad/liquidity series have **no PIT vintage backfill** (P-D5-1), so any skill that
*does* lean on quad coefficients is labeled **revision-optimistic** until D6 vintages land.
Given §3.1's immateriality result, the passing 1m cells are largely insulated from this,
but the caveat is recorded and the model artifact carries `revision_optimistic: true`.

---

## 4. Cross-check vs the keystone / W4.6 phase-keyed drawdown structure — CONVERGENT

The W4.6 phase-keyed DD artifact has **not landed on origin/main** yet, so this cross-check
is against the **keystone verdict** (`W04_KEYSTONE_VERDICT.md §2.2`), the canonical DD-by-
phase finding: *Peak phase → **shallower** forward drawdowns (63d p10-DD gap-vs-base CI
[+1.2%, +5.0%]); Trough phase → **deeper** (CI [−10.0%, −1.9%]) — and the Peak→shallow
signal **decays out of sample** (significant pre-2018, straddles zero post-2018).*

The hazard fit and the keystone measure different things (turn-timing Brier vs drawdown-
magnitude gap) on the same substrate, and they **converge**:

- The hazard's one strong, sign-stable win is **near a cycle peak** (up/1m PASS, sign 14/17
  years) — the same region the keystone singles out as structurally distinct on the DD lens.
- The hazard's **multi-month up-side washes out** (up/3m, up/6m PRIOR) — mirroring the
  keystone's own finding that the Peak-DD signal **decays** and does not extend cleanly.
- The **down-side** carries a weaker but more horizon-persistent hazard signal (down/1m/3m/6m
  all pass, though 3m/6m are marginal), consistent with the keystone's Trough→deeper-DD being
  its more robust phase result.

Two independent analyses agree: **the neighborhood of a cycle turn — especially the peak —
is a small, real, but short-horizon and possibly-decaying edge; longer horizons revert to
the KM prior.** Convergent evidence, not a single-method artifact.

---

## 5. DL-1 decision linkage — what each PASSING cell could move (and what W4.3 may wire)

DL-1 (PREREG §6) binds the hazard outputs to a *named decision* or they ship as a research
surface only: *"walk-forward entry-sizing on the hazard cone improves drawdown-adjusted
outcomes vs the current median-half-cycle IQR band, CI excluding 0."* **DL-1 is NOT tested
here** (W4.2 fits the model; the sizing backtest is DL-1's own W4.2/W4.3 acceptance). Until
DL-1 passes, everything below ships **as a research surface, never as a badge that sizes a
position.**

**PASSING CELLS ONLY** — the candidate decisions:

- **up/1m (peak-hazard, robust):** could sharpen the *near-term top-risk* read on a running
  up-leg — a de-escalation/trim tripwire when the 1-month peak hazard runs materially above
  the KM prior. This is the cell W4.3 is most justified in wiring into a research surface.
- **down/1m (trough-hazard, solid):** could sharpen a *near-term bottom-forming* read on a
  down-leg — a "washout maturing" context flag (not a buy signal on its own).
- **down/3m, down/6m (marginal):** persistence of the trough signal to 3–6 months is *just*
  significant; **do not wire to sizing** on this evidence — carry as a low-weight research
  context only, re-examine when n grows (the panel matures monthly).

**What W4.3 may wire:** a *research-surface* hazard-cone panel keyed on the two 1-month cells,
badged with the KM prior for the PRIOR cells, and explicitly labeled revision-optimistic
where any quad coefficient contributes. No position sizing until DL-1's own gate passes.

---

## 6. Reproduce

```
python -m scripts.build_hazard_panel          # rebuild the price-basis panel (epoch price_c4414dcb)
python -m scripts.fit_cycle_hazard            # fit + gate → data/hazard/model_price_c4414dcb.json
python -m pytest tests/test_cycle_hazard_fit.py tests/test_hazard_panel.py -q
```

Artifact: `data/hazard/model_price_c4414dcb.json` (coefficients, per-fold fits, calibration
maps, per-cell ledger with verdicts, regime CI + quad-lag sensitivity block, versioned).
