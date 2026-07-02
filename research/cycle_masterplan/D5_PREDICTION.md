# PILLAR D5 — THE PREDICTION LAYER
## Hazard model · conditional forward distributions · regime prior · lead-lag phase-0

*Design doc for the cycle-platform solution masterplan. Author: principal quant-systems designer (Fable session, 2026-07-02). All paths relative to canonical main checkout `/tmp/macro-cycle-fable-main/` unless noted. Ground truth: audit `research/CYCLE_INTELLIGENCE_PROBLEM_AUDIT_FOR_FABLE.md` (findings H/I/J/K + Part II), scout notes S1–S5 in `/tmp/cycle_masterplan_designs/`, and code read this session.*

---

## 0. Executive thesis

The platform's current "prediction" is a median-half-cycle arithmetic projection (`sector_cycles._project_next`, lines 192–215) that (a) uses only the instrument's own tiny turn history, (b) conditions on nothing (no regime, no amplitude, no position), (c) **floors the central date at +0.05y from today** (`central = base_x + max(0.05, med - since)`) so an overdue cycle is silently redrawn as "imminent" forever, and (d) has never been graded against a realized turn. Meanwhile the flagship pages hand-type cones with `lerp(1.5,13)` amplitudes that no code has ever scored (audit K-3).

The upgrade is a **discrete-time logistic hazard model**: for every MEASURED instrument in a leg (up-leg awaiting a peak, down-leg awaiting a trough), predict the per-month probability the leg ends, conditioned on age, amplitude, position, RS, regime quad, liquidity, and vol regime — pooled across ~66 instruments and ~30 years. I verified the raw material exists **today**: running `_detect_swings` at the production 14% threshold over the current `data/yahoo` parquets yields **1,883 confirmed turns across just the 35 US-sector + country ETFs** (XLK 51, EWZ 112, … XLC 7); adding the 31 Shenwan L1 sectors (1999→, 18–25% thresholds) brings the event count to ≈2,400–2,600 with ≈25–30k instrument-month at-risk rows. Split into peak-hazard and trough-hazard models that is ~1,200 events per model against ~15 features — events-per-variable ≈ 80, comfortably estimable with a **hand-rolled L2 logistic (no sklearn in the render path, per the house "no scipy/sklearn" doctrine verified in S5)**.

Three honesty principles are load-bearing and non-negotiable:

1. **The bar is the age-only hazard, not the coin flip.** A Kaplan-Meier-style empirical hazard by age-bucket *is* the median-half-cycle prior, formalized. The model earns the right to draw a cone only if its walk-forward OOS Brier beats that baseline — otherwise "hazard model" is repackaged age and we ship the prior, labeled as a prior.
2. **Every probability shipped is isotonic-calibrated on pooled OOS predictions and carries a Brier ledger** (vs base-rate AND vs age-only), registered in the admin Experiments tracker (N4) with a come-back date.
3. **The event definition is versioned** (`turn_def_version`), because Pillar D1/D2's price-basis + ZigZag-threshold fixes will re-date turns (N2). Model artifacts, panels, and grades are keyed by that version; a re-key triggers a re-fit, never a silent re-grade.

Downstream of the hazard core, this pillar ships: (2) **phase×regime conditional forward-return cells with James-Stein shrinkage** replacing both the raw small-n Wilson cells and the hand-typed `lift*6.0` tilt maps; (3) **one `engine/regime_prior.py`** consumed by every cycle page, with reconciliation banners; (4) a **pre-registered lead-lag phase-0** with a hard STOP rule; (5) two novel evidence-gated features — leg-velocity ("blow-off speed") and a **provisional-turn survival classifier** that directly monetizes the repaint problem the audit flagged (H-4).

---

## 1. THE HAZARD MODEL (T3 — adopted, refined)

### 1.1 Verdict on T3

**ADOPT, with four refinements.**

- **Refinement 1 — two models, not one.** Peak-hazard (rows where the instrument is in an up-leg) and trough-hazard (down-leg) are fit separately. Cycle asymmetry is real and first-order: down-legs are shorter and sharper (verifiable from the backfilled leg-duration distribution before fitting; the panel builder emits this diagnostic). Interacting one model with direction costs the same parameters and reads worse.
- **Refinement 2 — family fixed effects + own-history normalization, not hierarchical Bayes.** Fable's "per-family shrinkage" is right in spirit; full hierarchical shrinkage (random effects) needs bespoke EM code we shouldn't hand-roll. Equivalent effect, simpler machinery: (a) family dummies (`us_sector`, `country`, `cn_sector`), (b) the age feature is a **ratio to the instrument's own expanding-median half-cycle** (blended with the family median for thin histories — an explicit prior-blend, formula §1.5), which is itself an implicit per-instrument shrinkage. With ~1,200 events per model, family dummies + normalized features capture what a hierarchy would, at zero new-dependency cost.
- **Refinement 3 — the fallback is a first-class output, not an error path.** Instruments below data floors, structural frames (T1), and any horizon where the model fails its skill gate ship the **age-only empirical hazard (the formalized median-half-cycle prior)**, badged `PRIOR` vs `MODEL`. The UI never shows an unlabeled number.
- **Refinement 4 — monthly-frequency panel only in v1.** N1's monthly-kernel flagship cycles (Case-Shiller, DRAM ASP, ISM) join in v2 once the proxy registry exists (that's Pillar D3/N1 scope); the hazard architecture is frequency-agnostic by design (the panel row is "instrument-period", period = month), so v2 is a data add, not a redesign.

### 1.2 Event definition

**Event = a confirmed ZigZag pivot on the canonical turn primitive** (Pillar D1's ontology contract; today `sector_cycles._detect_swings`, lines 106–157), computed on the **`close_price` basis** (split-adjusted, dividend-unadjusted — T5; until D2's dual-basis collector lands, v0 panels are built on the existing TR closes with `basis:'tr'` stamped, and re-built under `turn_def_version` bump when `close_price` lands — see migration §1.10).

- **Event time** = the pivot **extremum date** (the `date` field `_detect_swings` emits), *not* the confirmation date. Rationale: the platform's promise is "when does the market turn," and grading against the extremum is the honest reading of that promise. The confirmation lag (time from extremum to the ≥14% reversal that confirms it) is **measured and reported separately** as `confirm_lag` in the panel diagnostics — it is the irreducible detection latency the UI must disclose (it is why live cards carry `provisional` flags).
- **Leg** = the interval between consecutive confirmed pivots. An instrument-month row at time t belongs to the leg whose opening pivot is the last pivot **confirmed by t** (PIT: features may only see turns confirmed ≤ t; the still-open leg's running extreme is feature material, its eventual pivot date is label material).
- **Label** `y_h(t) = 1` iff a confirmed pivot of the leg-ending kind has extremum date in `(t, t+h]` (h in months). For the person-period hazard model the primitive label is `y_1` (leg ends within the next month); multi-horizon probabilities come from compounding the hazard curve (§1.7), and `y_3`/`y_6` are used directly for calibration/grading of the compounded outputs.
- **Censoring**: the currently-open leg at panel-build time is right-censored at the last bar — rows are kept with `y=0` up to `last_date − max_h` and dropped after (no peeking at an unconfirmed future pivot).
- **`turn_def_version`** = hash of `{detector: 'zigzag', pct_threshold(s), basis, min_bars}`. Stored in every panel row, model artifact, and grade row. **This is the N2 answer for the prediction layer**: when D1/D2 re-key turns, the panel is rebuilt under a new version, the model refit, and old grades archived under the old version — never silently re-marked.

### 1.3 Panel construction

**New file: `engine/cycle_hazard_panel.py`**

```python
def build_panel(*, families: dict[str, list[str]] | None = None,
                asof: str | None = None,
                freq: str = "M",
                turn_def_version: str | None = None) -> pd.DataFrame:
    """Instrument-period at-risk panel for the discrete-time hazard model.

    One row per (instrument, month-end t) where the instrument is inside a leg.
    All features causal at t (tape <= t; turns confirmed <= t). Labels look
    forward. Returns the panel; scripts/build_hazard_panel.py persists it.
    """
```

**Universe v1** (all daily tapes, no basket-membership PIT blocker — S2 confirmed baskets are excluded until `pit=True` membership exists):

| family | instruments | source | zz pct | history |
|---|---|---|---|---|
| `us_sector` | 11 SPDR (XLK…XLC) | `data/yahoo` | 14 | 1998→ |
| `country` | 24 country ETFs + 7 blocs | `data/yahoo` | vol-scaled `_zz_pct_for` (per D1 contract) | 1996→ |
| `cn_sector` | 31 Shenwan L1 | `data/china_sectors` (price-basis already — S1) | 18–25 per D1 | 1999→ |

**Row schema** (`data/cycle_hazard/panel.parquet`):

```
date            month-end timestamp t
id              instrument id (ticker / shenwan code)
family          us_sector | country | cn_sector
direction       up | down            (leg direction; selects which model)
turn_def_version
# --- survival bookkeeping ---
age_m           months since leg-opening pivot extremum
y1, y3, y6      leg-ending pivot extremum within (t, t+h]   (0/1; NaN if censored)
event_date      extremum date of the ending pivot (label; NaT if censored)
# --- features (all causal at t) ---
log_age_ratio   ln(age_m / half_med_blend)                  §1.5
amp_ratio       |running-extreme/leg-open − 1| / med_leg_mag (expanding, own+family blend)
pos             detrended osc 0-100 at t (existing _detrended_osc, PIT per S2)
osc_slope       osc 21d slope at t
rs_63           63d return vs family benchmark (SPY / ACWX / 000300) — TR basis, labeled
vol_pctile      expanding percentile of 63d realized vol (NOT VIX — see §1.4 note)
quad_Q1..Q4     regime quad dummies at t (regime_history.parquet)
liq_expanding   liquidity overlay dummy at t (same file)
breadth_div     family breadth (pct members >200d) minus own >200d indicator; NaN-tolerant
age_b1..b5      age-bucket dummies (baseline hazard shape): age_ratio in
                [0,.5), [.5,.8), [.8,1.1), [1.1,1.5), [1.5,inf)
```

**Sizing (measured, not guessed):** 1,883 confirmed turns exist right now across the 35 US+country tickers at 14%; Shenwan adds an estimated ~500–700 (verify at panel build — acceptance gate). Rows ≈ 35×~300 + 31×~320 ≈ **20–30k**; events per direction-model ≈ **1,100–1,300**.

**Dependency:** the panel needs the D4 PIT backfill only for *grading the platform's historical stamps*; the panel itself is buildable **today** directly from the tapes (turn detection is a pure function of price, S2). So D5-W1 can start in parallel with D4, sharing the same `turn_def_version` contract from D1.

**Compute:** turn detection + feature build over 66 series ≈ single-digit minutes offline (S2 measured 56ms/call for the far heavier `_record_core`; the panel builder calls only `_detect_swings` + rolling stats). Runs in `scripts/build_hazard_panel.py`, **outside the 67-min render** (weekly cron alongside the nightly-calibration family, like `regime_hmm`).

### 1.4 Features — sourcing decisions and two new problems

- **Regime quad + liquidity**: `data/regime/regime_history.parquet` — verified this session: daily 1971-01-04 → 2026-07-01, 14,478 rows, columns incl. `quad`, `liquidity`, `cycle`, `transition_state`. This is the feature source for BOTH backfill and live (same file → live==backtest by construction).
  - **NEW PROBLEM (P-D5-1, medium):** `regime_history.parquet` is built from *revised* macro series (payrolls_trend, indpro_trend feed the growth axis — `data/regime/latest.json` `confirming` list) with no ALFRED vintages, so historical quad labels carry a revision leak of the same class the audit flagged for `business_cycle` (I-2). Mitigation, not solution, for v1: (a) document the leak in the model card; (b) run a **sensitivity fit with quads lagged +1 month** — if coefficients/skill move materially, drop the macro-derived quad and keep only the market-price-derived features. Full vintage fix belongs to the macro-regime pillar.
- **Vol regime = expanding percentile of 63d realized vol**, NOT VIX and NOT `engine/vol_regime.py`.
  - **NEW PROBLEM (P-D5-2, low):** the validated vol-regime engine is US-index-only; China/Shenwan has no VIX. A cross-family model needs one uniformly-computable vol feature; realized-vol percentile is causal, universal, and instrument-specific. `vol_regime`'s verdict remains a display prior via `regime_prior` (§3), not a model feature.
- **market_state verdict is NOT a feature.**
  - **NEW PROBLEM (P-D5-3, high, design-constraining):** `market_state` persists only `data/market_state/latest.json` (overwritten nightly; S2 confirmed the overlay layers aren't archived). There is **no PIT history**, so it cannot appear in a backfilled panel without leaking. It stays a *display-time* prior in `regime_prior` with an explicit `not_a_model_input: true` flag. If a future wave starts archiving daily market_state snapshots, it can be promoted after 2+ years of accrual.
- **Breadth divergence**: computable from the closes panels alone (pct of family members above their 200d MA) — PIT-pure; NaN before family coverage exists (model handles via missing-indicator column, §1.6).

### 1.5 The age feature — explicit shrinkage formula

`half_med_blend` for instrument i at time t:

```
half_med_blend(i,t) = (n_i · med_i(t) + k · med_F(t)) / (n_i + k),   k = 6
```

where `med_i(t)` = expanding median of instrument i's confirmed half-cycle durations using turns confirmed ≤ t, `n_i` = count of those, `med_F(t)` = same for the whole family pooled. `k=6` means an instrument's own history dominates once it has ~6 confirmed legs (XLC with 7 turns sits at the crossover; EWZ with 112 is fully self-normalized). This constant is **pre-registered, not tuned** (sensitivity check k∈{3,6,12} in the fit report; if OOS skill is materially k-sensitive, that is itself a red flag reported in the ledger).

### 1.6 Model form and fitting

**Discrete-time logistic hazard (Allison person-period form)** — per direction d ∈ {up→peak, down→trough}:

```
λ(t) = P(y1=1 | x_t) = sigmoid(β₀ + β·x_t)
x_t = [age_b1..b5, log_age_ratio, amp_ratio, pos/100, osc_slope/10,
       rs_63, vol_pctile, quad_Q2, quad_Q3, quad_Q4, liq_expanding,
       breadth_div, breadth_missing, fam_country, fam_cn]
```

(Q1 and `us_sector` are reference levels; `breadth_missing` is the missing-indicator with `breadth_div` zero-filled when missing.)

**Fitting: hand-rolled numpy logistic with L2**, in the pattern of `scripts/calibrate_baskets._fit_logistic_signed` and `engine/validation.platt_fit` (both verified pure-numpy, S5). Newton or gradient descent, `l2=1.0` on non-intercept, non-age-bucket coefficients; standardize continuous features by **train-fold** mean/sd (stored in the artifact for live scoring).

**New file: `engine/cycle_hazard.py`**

```python
def fit_hazard(panel: pd.DataFrame, *, direction: str,
               l2: float = 1.0, iters: int = 500, lr: float = 0.1) -> dict:
    """Fit one direction's logistic hazard on the full train slice.
    Returns {'coefs': {...}, 'feat_means': {...}, 'feat_sds': {...},
             'n_rows': int, 'n_events': int}."""

def walk_forward(panel: pd.DataFrame, *, direction: str,
                 first_test_year: int = 2010, embargo_m: int = 6) -> pd.DataFrame:
    """Annual date-block walk-forward: for each test year Y >= first_test_year,
    fit on rows with date <= Dec(Y-1) - embargo, predict rows in year Y.
    Returns OOS predictions frame [date,id,direction,p1_raw,y1,y3,y6,...].
    Blocks are by DATE, never by instrument (all instruments share dates)."""

def km_age_hazard(panel: pd.DataFrame, *, direction: str) -> dict:
    """Empirical age-bucket hazard (the formalized median-half-cycle prior):
    lambda_b = events_b / at_risk_b per age bucket, with Wilson CIs
    (grading_stats.wilson). THE baseline the model must beat."""

def hazard_curve(model: dict, x_now: dict, *, months: int = 12) -> list[float]:
    """Forward per-month hazards advancing ONLY age (age_b*, log_age_ratio);
    all other features frozen at current values. Documented as
    'current-conditions cone'."""

def survival_summary(lams: list[float]) -> dict:
    """S(k)=prod(1-lam_j). Returns {'p_turn_1m','p_turn_3m','p_turn_6m',
    'central_m': first k with S<=0.5, 'lo_m': S<=0.75, 'hi_m': S<=0.25}."""

def score_live(model_art: dict, records: list[dict]) -> None:
    """Attach hazard block to each live cycle record (mutates in place).
    Pure arithmetic — safe inside the render path."""
```

**Why walk-forward-by-year rather than `validation.purged_folds`:** the target horizon is up to 6 months; annual blocks with a 6-month embargo give clean separation, match how the model will be operated (refit yearly/quarterly on schedule), and produce an interpretable per-year skill series ("was the model good in 2015? in 2020?") that the honesty ledger reports. `purged_folds` remains available for the novel-feature gates (§5).

### 1.7 Calibration and outputs

1. Pool all OOS `p1_raw` from `walk_forward`; compound to `p3_raw`, `p6_raw` via each row's forward hazard curve evaluated with OOS coefficients.
2. Fit **isotonic** per horizon on OOS (validation.isotonic_calibration — pure-numpy PAV, verified S5): `iso_h = isotonic_calibration(p_h_raw, y_h)`.
3. **Skill gate (BINDING):** per horizon h and direction d, compute Brier of (a) calibrated model, (b) constant base-rate, (c) age-only KM hazard (compounded the same way). Ship the model for (d,h) **only if** `brier_model < brier_km` with a date-block-bootstrapped 90% CI excluding zero on the paired difference (use `grading_stats.boot_gap_ci` ported per T4). Failing cells ship the KM prior, badged.

**Model artifact `data/cycle_hazard/model.json`:**

```json
{
  "schema": 1, "fitted_at": "2026-07-10", "turn_def_version": "zz14tr-v0",
  "train_span": ["1996-01","2025-12"], "panel_rows": 27412,
  "models": {
    "up":   {"coefs": {...}, "feat_means": {...}, "feat_sds": {...},
             "n_events": 1240, "iso": {"1m": {...}, "3m": {...}, "6m": {...}}},
    "down": {...}
  },
  "km_baseline": {"up": {"lambda_by_bucket": [...], "wilson": [...]}, "down": {...}},
  "ledger": {
    "up": {"3m": {"brier": 0.148, "brier_base": 0.171, "brier_km": 0.159,
                   "skill_vs_km": 0.069, "ci90": [0.021, 0.114], "pass": true,
                   "reliability": [{"bin":..., "pred":..., "obs":..., "n":...}]},
           "1m": {...}, "6m": {...}},
    "down": {...}
  },
  "sensitivity": {"quad_lag1_delta_brier": 0.002, "k_blend": {"3": ..., "6": ..., "12": ...}}
}
```

**Per-instrument live output** — attached by `score_live` into every `_record_core`-family record (and therefore into `sector_cycles.js` / `country_cycles_data.js` / CN equivalents):

```json
"hazard": {
  "src": "model",                       // "model" | "prior" (KM) | null (structural frame)
  "model_version": "zz14tr-v0/2026-07-10",
  "p_turn": {"1m": 0.09, "3m": 0.31, "6m": 0.62},
  "cone": {"central": "2026-11", "lo": "2026-09", "hi": "2027-02"},
  "skill": {"3m_brier_skill_vs_prior": 0.069},   // shown in tooltip; null for prior
  "provisional_leg": false               // true when the open leg's extreme is < confirm threshold away
}
```

The cone replaces `_project_next`'s output on hazard-eligible instruments; `_project_next` remains as the `prior` fallback **with its `max(0.05, …)` floor removed** (see P-D5-4 below) so overdueness is visible: a prior cone whose central is in the past renders as "OVERDUE (median half-cycle elapsed N m ago)".

**NEW PROBLEM (P-D5-4, medium):** `sector_cycles._project_next` (line ~207) computes `central = base_x + max(0.05, med - since)` — the floor converts any overdue cycle into "turn ~18 days out", permanently, and re-anchors from *today* every build so the projection **walks forward daily and can never be graded as missed**. Evidence: `engine/sector_cycles.py:192-215`. This is why cone-coverage grading (T4) would be vacuous against the current projection — the fix (remove floor, project from the pivot, expose overdue state) must land with W3.

### 1.8 Grading the hazard (N3 answer)

Phase-appropriate, not 21d-fixed:

- **Event-window grading:** for each historical stamp (from the D4 backfill and the live forward log), grade `p_turn_h` against `y_h` — Brier + reliability per (direction, h, family). This is the native calibration-window grading N3 asks for.
- **Cone coverage:** new shared primitive (S5 identified it as missing repo-wide):

```python
# engine/grading_stats.py
def cone_coverage(events: pd.DataFrame, *, nominal: float = 0.5) -> dict:
    """events: one row per resolved leg with [central_m, lo_m, hi_m, realized_m].
    Returns {'n', 'coverage': frac(lo_m <= realized_m <= hi_m),
             'wilson': (lo,hi), 'median_abs_err_m', 'nominal'}."""
```

  The hazard cone's stated band is the S∈[0.25,0.75] interquartile window → nominal coverage 50%. Grade it, print `coverage 54% [46,62] vs nominal 50%`.
- **Ledger cadence:** `scripts/fit_cycle_hazard.py` refits quarterly (cron), regrades monthly; scorecard JSON `data/cycle_hazard/scorecard.json` rendered on the cycle pages' methodology drawer. Registered in `data/experiments/registry_seed.json` with `maturation: "n_matured>=60 AND brier_skill_vs_km>0 at 3m"` and a come-back date (N4).

### 1.9 Library constraint (settled)

Hand-rolled numpy logistic + PAV isotonic + Wilson + date-block bootstrap — **all already exist in-repo** (`validation.platt_fit` pattern, `validation.isotonic_calibration`, `china_sector_pathway._wilson`, `china_sector_cycles_grader._boot_gap_ci`). **No sklearn, no statsmodels, no lifelines.** sklearn stays optional-off (meta_label precedent); statsmodels is not a declared dep and is not introduced. Survival libraries are unnecessary: discrete-time hazard *is* logistic regression on person-period rows.

### 1.10 Migration steps

1. **v0 (now):** panel + model on existing TR closes, `turn_def_version = zz14tr-v0`. Everything runs; grades accrue; UI ships behind the skill gate.
2. **When D2's dual-basis (`close_price`) lands:** rebuild panel as `zzXXpx-v1` (threshold per D1's re-derivation), refit, re-run skill gates. v0 artifacts archived under version key; narrative re-keying handled by D1/N2's nearest-turn matcher — the hazard layer only ever references turns by `(id, turn_def_version, extremum_date)`.
3. **When N1's monthly proxy registry lands (Pillar D3):** append monthly-frequency instrument rows (family `flagship_monthly`) with per-cycle turn params from the registry; refit as v2. The person-period design needs no structural change.

---

## 2. CONDITIONAL FORWARD-RETURN DISTRIBUTIONS (phase × regime, shrunk)

### 2.1 What it replaces

- China pathway's 4-sector Wilson cells on overlapping windows with raw n (audit II-5: CI ~2.4× too narrow, banks n_eff≈6).
- The China tilt maps `lift*6.0`, `n/60` (audit F/G findings) and sector_central's per-phase hand dict.
- The FWER-failing pretense: Phase-0 already proved no single China driver clears strict FWER (`china_sector_pathway.py` header). We do NOT resurrect per-cell significance claims. The honest product is a **shrunken estimate with an honest interval**, presented as conditioning context.

### 2.2 The estimator

**New file: `engine/cond_forward.py`**

```python
def cell_table(panel: pd.DataFrame, *, h_m: int, outcome: str = "fwd_ret") -> pd.DataFrame:
    """panel: the hazard panel joined with h-month forward TR returns (labeled basis='tr').
    Cells: master_phase (5, from D1 ontology) x quad (4) x family (3).
    Emits per cell: n, n_eff = n / h_m  (overlap deflation),
    raw_mean, raw_pos_rate, shrunk_mean, shrink_w, wilson_lo/hi on n_eff."""
```

**James-Stein / empirical-Bayes shrinkage toward the phase-pooled mean** (pooling over quads within a phase×family):

```
tau2   = max(0, Var_c(m_c) - mean_c(s2_c / n_eff_c))      # between-cell variance, method of moments
w_c    = tau2 / (tau2 + s2_c / n_eff_c)                   # shrink weight for cell c
shrunk = w_c * m_c + (1 - w_c) * m_phase_pooled
```

where `m_c` = raw cell mean, `s2_c` = within-cell variance, both on **month-end stamps** with `n_eff = n/h` (h-month overlapping windows share h−1 months; this is the audit's effective-n discipline made mechanical). Same shrinkage applied to `pos_rate` via logit-space shrink; Wilson interval computed at `n_eff`, never raw n.

### 2.3 Presentation contract (the honest generalization of the pathway layer)

Every rendered cell shows, verbatim structure:

> **When {phase} met {quad-name} ({family}), the {h}-month forward return was positive {shrunk_pos_rate}% (raw {raw}%, shrunk {100·(1−w_c)}% toward the phase average; n_eff≈{n_eff} of n={n} overlapping months) vs base {base}%.**

with dual-span i18n and the standing footer: *"Conditioning context, not a forecast; no cell clears a family-wise significance bar"* / zh equivalent. Cells with `n_eff < 12` render the pooled phase row only. There is **no BUY/SELL derived from a cell** — cells tilt conviction (below) and inform prose, nothing else.

### 2.4 Where it feeds

1. **sector_central conviction tilt (US + CN):** replace the hand `lift*6.0`/`n/60` map with
   `tilt = clip(round(12 * shrunk_lift / 0.10), -12, +12) if n_eff >= 30 else 0`
   where `shrunk_lift = shrunk_pos_rate − base_rate` at h=3m. The ±12 cap matches the existing overlay scale; the 0.10 normalizer means a full ±12 tilt requires a shrunken 10-pt lift on 30+ effective months — rare by construction. The tilt constant set is stored in `data/cond_forward/tilt_config.json` and versioned (calibration BINDS, T4).
2. **China pathway page:** the 4-sector layer becomes a view over the same `cell_table` restricted to `cn_sector` — one estimator, one honesty contract, no bespoke Wilson-on-raw-n path left alive.
3. **Hazard cone annotation:** the cone tooltip cites the current cell ("historically, turns from Peak×Q3 resolved down 63% of the time") — display join only.

Artifact: `data/cond_forward/cells_{h}m.json`, rebuilt monthly in the same cron as the hazard refit; render-path cost is a JSON read.

---

## 3. THE REGIME PRIOR SERVICE (`engine/regime_prior.py`)

### 3.1 Contract

One module, one artifact, consumed by **all** cycle pages (cycle, markets, country_cycles, sector_cycles×2, sector_central×2), replacing: the hand-typed `CYCLE_META.regime` block (audit I-1), per-page regime anchors (`sector_central._regime_anchor` reading `data/regime/latest.json` directly), and any page-local quad prose.

```python
# engine/regime_prior.py
def regime_prior(asof: str | None = None) -> dict:
    """Single conditioning prior for all cycle pages. Merges:
       - data/regime/latest.json          (quad, liquidity, cycle_tag, transition, flip_condition)
       - business_cycle_snapshot()         (bc phase, leading mom6, diffusion)
       - data/market_state/latest.json     (verdict, score)  [display-only, not_a_model_input]
       - vol regime verdict                 (display-only)
    Every source carries its own asof; status = 'fresh' | 'stale' | 'partial'.
    STALENESS RULE: any source asof > 3 trading days old => that source status
    'stale' and the merged status degrades; consumers MUST render the banner."""
```

**Artifact `site/regimedata/regime_prior.json`** (written by `engine/run.py` build step; JS pages fetch it — static-site constraint respected):

```json
{
  "schema": 1, "asof": "2026-07-02", "status": "fresh",
  "quad": "Q1", "quad_name_en": "Goldilocks", "quad_name_zh": "金发姑娘",
  "liquidity": "expanding", "cycle_tag": "mid", "transition_state": "STABLE",
  "bc_phase": "expansion", "market_state": {"verdict": "MIXED", "score": 50,
                                             "not_a_model_input": true},
  "vol_regime": "normal",
  "flip_condition": {...},
  "sources": {"regime": "2026-07-01", "market_state": "2026-07-01",
              "business_cycle": "2026-07-01"},
  "hazard_model_version": "zz14tr-v0/2026-07-10"
}
```

### 3.2 Reconciliation banner (the audit I-1 fix)

Narrative overlays (post-T6 `narratives.json` schema, owned by Pillar D-narrative) may declare a machine-readable claim:

```json
"regime_claim": {"quad": "Q3", "risk": "off", "as_of": "2026-06-25"}
```

Build-time check in the shared build path (one function, `regime_prior.check_claims(narratives) -> list[dict]`): if `claim.quad != prior.quad` or claimed risk direction contradicts `market_state.verdict`, the page data gets `"regime_disagreement": {"claimed": ..., "engine": ..., "engine_asof": ...}` and the JS renders a banner — dual-span:

> EN: "Page narrative says {claimed}; the live regime engine reads {engine} (as of {date})."
> ZH: "页面叙述为 {claimed}；实时体制引擎读数为 {engine}（截至 {date}）。"

No `t()` in attributes; banner is body-copy spans per the i18n house rule. A `scripts/check_regime_claims.py` guard (pattern: `check_nav_mega`) fails the build if any page consumes regime prose without either a `regime_claim` or an explicit `"regime_claim": null` opt-out — so hand-typed regime text can never again ship unreconciled.

### 3.3 What this does NOT do

It does not make market_state or vol_regime hazard features (P-D5-3), does not recompute anything (pure merge+freshness), and does not add render cost beyond one JSON write.

---

## 4. LEAD-LAG PHASE-0 (T7 — adopted with a hard STOP rule)

### 4.1 Verdict on T7

**ADOPT.** The audit is right that the interaction layer is asserted, not measured (Part I-7, Part V). The phase-0 below is pre-registered, uses the backfilled canonical turns, and has a decision-relevant primary endpoint: **does knowing the leader's recent turn improve the follower's hazard forecast out-of-sample?** — because that is the only form in which a lead-lag would actually be *used* by this platform.

### 4.2 Study design (`scripts/leadlag_phase0.py`, verdict artifact `data/cycle_hazard/leadlag_phase0.json`)

**Inputs:** the hazard panel (§1.3) + canonical confirmed turns, all under one `turn_def_version`.

**Stage A — screening (in TRAIN period only, ≤2017-12):**
- Candidate pairs: all ordered pairs within {11 US sectors}, within {24 countries}, within {31 CN sectors}, plus the 3 cross-family block pairs (US-sector→country, US-sector→CN-sector, country→CN-sector) at the family-aggregate level. That is ~110 + ~550 + ~930 within-family pairs — screened, not tested.
- Statistic: cross-correlation of monthly Δphase-position (first difference of the detrended osc, which whitens the series — raw osc levels are near-integrated and would fabricate correlation) at lags 1..6 months; block-bootstrap (21d blocks, B=2000, `validation.block_bootstrap_ci`) for the null band; **BH-FDR at q=0.10 across all pairs×lags** (port `grading_stats.fdr_bh` — T4).
- Also: turn-date event study — for each surviving pair, distribution of (follower turn date − nearest leader turn date), sign test with date-block bootstrap. Effective-n = number of *follower turns*, not months (this is the effective-n discipline: EWZ has 112 turns, XLC has 7 — pairs into XLC are near-untestable and reported as such).
- Output: top-K (K=20) pairs by FDR-surviving lagged correlation, frozen into the pre-registration.

**Stage B — primary endpoint (OOS 2018→):**
- Add one feature to the follower's hazard row: `leader_turned_3m ∈ {0,1}` (leader printed a confirmed opposite-leg pivot, confirmed ≤ t, extremum within last 3m).
- Refit the hazard walk-forward (§1.6) with this feature for the K pairs' followers; compare pooled OOS Brier at 3m vs the no-leader model.
- **Pre-registered success criterion:** relative Brier improvement ≥ 2% pooled, AND positive in ≥ 2/3 of walk-forward year blocks, AND the paired date-block-bootstrap 90% CI on ΔBrier excludes 0.

**STOP rule (binding, written into the artifact before the run):**
- If Stage A yields no FDR survivors, or Stage B fails the criterion → **verdict `NO-GO`: do not build the interaction layer.** Ship instead the measured **synchronization statistic**: per family, the cross-sectional dispersion of phase position, `sync = 1 − circ_var(2π·pos/100)` monthly; validate it as a *conditioning state* via `cond_forward.cell_table` (sync tercile × forward family return) under the same shrinkage/effective-n rules; display on the family pages as a measured gauge replacing markets.html's fake convergence bands. And stop there.
- Registry entry either way (N4): `id: leadlag-phase0`, `come_back_on: fit+3m`, maturation criteria = the success criterion verbatim.

---

## 5. NOVEL EVIDENCE-GATED ADDITIONS (nobody asked; each with a falsifiable phase-0 gate)

### 5.1 Provisional-turn survival classifier ("will this low hold?") — highest value

The repaint problem (audit H-4/H-7: a fresh low is invisible 10 days–6 weeks; the ZigZag's last pivot is `provisional`) is currently pure liability. Turn it into the platform's most actionable prediction: **P(the current provisional pivot survives to confirmation without a lower low)**.

- Panel: every historical provisional-pivot episode from the backfilled turns (each confirmed pivot was once provisional; each *failed* candidate — running extreme later exceeded before the reversal threshold — is a negative). Label: survived → confirmed as-is (1) vs extended (0). Features at candidate time: reversal-so-far / threshold ratio, volume ratio vs 21d (where volume exists — `data/yahoo` has it), breadth thrust (family pct-above-20d jump), vol_pctile, pos, quad.
- Same hand-rolled logistic + isotonic + walk-forward machinery (reuse §1.6 code paths).
- **Gate:** OOS AUC ≥ 0.60 AND calibrated-Brier beats base rate with CI excluding 0. Pass → ships as `provisional.p_hold` on the card's provisional badge. Fail → badge stays qualitative, artifact records the failure.

### 5.2 Leg-velocity ("blow-off speed") hazard feature

`vel_ratio = (leg return so far / age_m) / instrument's expanding median leg velocity`. Hypothesis: abnormally fast legs die young (climax behavior). **Gate:** added to the hazard model, coefficient sign stable across all walk-forward folds AND pooled OOS Brier improves; else dropped (recorded in `model.json.sensitivity`).

### 5.3 Cross-frequency confirmation (deferred hook)

Daily-phase vs monthly-kernel-phase agreement as a hazard feature — **explicitly deferred** until N1's monthly kernel exists (Pillar D3); the panel schema reserves the column (`xfreq_agree`, NaN v1) so v2 is additive. No gate spec until the data exists (pre-registering a gate on unbuilt data is theater).

---

## 6. NEW PROBLEMS DISCOVERED (beyond the 89 + N1-N4)

| id | severity | claim | evidence |
|---|---|---|---|
| P-D5-1 | medium | `regime_history.parquet` quad labels carry macro-revision leak (payrolls/indpro components, no vintages) — any backfilled model conditioning on quad inherits it | `data/regime/regime_history.parquet` (1971→, verified); `data/regime/latest.json` confirming list includes `growth_payrolls_trend`, `growth_indpro_trend`; no ALFRED vintage path in `engine/regime.py` |
| P-D5-2 | low | vol-regime engine is US-index-only; no uniform vol feature exists for a cross-family model (CN has no VIX) | `engine/vol_regime.py` scope; `data/china_sectors` has no implied-vol source (S1) |
| P-D5-3 | high | `market_state` has **no PIT history** (latest.json overwritten nightly) → the site-wide "single source of truth" verdict can never be a backfilled model feature or a graded conditioning state until archiving starts | `engine/market_state.py:780-814` (persist/load, no history write); S2 scout: overlay files not archived |
| P-D5-4 | medium | `_project_next` floors the central turn at +0.05y from *today* and re-anchors daily — overdue cycles render as perpetually "imminent" and the projection can never be graded as missed | `engine/sector_cycles.py:192-215`: `central = base_x + max(0.05, med - since)` with `base_x = _yf(last_ts)` |
| P-D5-5 | medium | Turn-count heterogeneity is extreme (XLC 7, XLRE 15, INDA 20 vs EWZ 112 confirmed turns at 14%) — any per-instrument statistic (median half-cycle, pathway cell, lead-lag pair) involving the thin names is noise; fixed thresholds on TR-adjusted deep history also inflate counts for high-vol EM tapes | measured this session: `_detect_swings(close,14.0)` over `data/yahoo` — full per-ticker table in §0/§1.3; motivates the k=6 blend (§1.5) and per-pair effective-n reporting (§4.2) |

---

## 7. VERDICTS ON THE FABLE THESES (this pillar's scope)

- **T3 — ADOPT, refined** (§1.1): two direction-models; family dummies + own-history-normalized age instead of hierarchical Bayes; the binding skill gate is vs the **age-only KM hazard**, not the coin flip; fallback (median-half-cycle prior) is a first-class, badged output. Realistic n verified empirically: ~2,400–2,600 events → the model is estimable, Fable's tiny-n fear is solved by pooling exactly as staked.
- **T7 — ADOPT** (§4): pre-registered two-stage design; the primary endpoint is hazard-Brier lift (the only decision-relevant form); hard STOP rule ships the sync/dispersion statistic and nothing more.
- **T4 — ADOPT** (dependency): hazard grading and cone coverage are the "grade the actual promises" primitives; `grading_stats.py` gains `cone_coverage` + `fdr_bh` (both currently missing repo-wide, S5).
- **T5 — ADOPT with staging**: v0 panel on TR closes with `basis:'tr'` stamped + version-keyed rebuild when `close_price` lands (§1.10). Refusing to start until the dual-basis collector ships would idle the highest-value work for no honesty gain — the version key preserves honesty.
- **T1 — ADOPT**: hazard applies to MEASURED cycles only; structural frames get `hazard: null` and their tripwire DSL (other pillar) — no probability theater on n≈2 secular clocks.
- **T2 — ADOPT**: the `hazard` block and `regime_prior` schema are declared in the ontology contract so JS cannot drift.
- **N1 — deferred by design** (§1.10 step 3, §5.3): person-period architecture is frequency-agnostic; monthly instruments are a v2 data add once the proxy registry exists.
- **N2 — answered for this pillar** via `turn_def_version` keying of panel/model/grades (§1.2, §1.10).
- **N3 — answered**: event-window Brier + cone coverage replace fixed-21d grading for turn calls (§1.8).
- **N4 — answered**: hazard scorecard and lead-lag phase-0 both register in the experiments tracker with maturation criteria and come-back dates.

---

## 8. WAVES

Cross-pillar dependencies referenced abstractly: **D1 = ontology/turn-contract pillar, D2 = data-basis pillar, D4 = backfill/measurement pillar** (whatever their final wave ids, the named artifacts are: canonical turn primitive + `turn_def_version`; `close_price` column; PIT backfill stamps + shared `grading_stats.py` seed).

### D5-W1 — Panel + baselines + shared stats additions
- **Tier: sonnet.** Depends on: D1's turn contract merged (needs `turn_def_version` definition); can run parallel to D4 (panel builds from tapes directly).
- Files: `engine/cycle_hazard_panel.py` (new), `engine/grading_stats.py` (add `cone_coverage`, `fdr_bh`; Wilson/boot ports land here if D4 hasn't already), `scripts/build_hazard_panel.py` (new, cron-tier), `data/cycle_hazard/panel.parquet`, `engine/cycle_hazard.py::km_age_hazard`.
- Acceptance: panel ≥ 20k rows, ≥ 1,800 events total (≥ 500 CN — verify the Shenwan estimate); zero rows where any feature uses data > t (spot-audit script re-computing 50 random rows with truncated tapes); KM hazard artifact with Wilson CIs per age bucket per direction; leg-duration + confirm-lag diagnostics emitted; experiments-registry entry created; runs outside render (cron), < 10 min.

### D5-W2 — Hazard fit, walk-forward, calibration, honesty ledger
- **Tier: opus** (modeling judgment: feature pruning, sensitivity reads, gate adjudication). Depends: D5-W1.
- Files: `engine/cycle_hazard.py` (fit/walk_forward/hazard_curve/survival_summary), `scripts/fit_cycle_hazard.py`, `data/cycle_hazard/model.json`, `data/cycle_hazard/oos_predictions.parquet`.
- Acceptance: per (direction,horizon) ledger with Brier vs base vs KM + bootstrap CI; isotonic reliability curves stored; quad-lag and k-blend sensitivity blocks present; skill-gate verdict recorded per cell; NO ship decision here (W3 gates on this artifact); pure-numpy (CI check: no sklearn/statsmodels import).

### D5-W3 — Wire hazard into records + cones + fallback + i18n
- **Tier: sonnet.** Depends: D5-W2 artifact with ≥1 passing cell; D1's record-schema wave for field placement.
- Files: `engine/sector_cycles.py` (`score_live` call in compute; `_project_next` floor removal + overdue state), `engine/country_cycles.py`/`china_sector_cycles.py` (inherit via kernel), templates/JS for the three engine page families, LEX additions (`HAZARD-BACKED`/`PRIOR ONLY`/`OVERDUE` dual-span), `scripts/fit_cycle_hazard.py` staleness guard.
- Acceptance: every engine-page record carries `hazard` block or explicit `src:'prior'`; failing-gate cells render prior with badge; model.json missing/stale (> 100 days) → all cards degrade to prior + build warning; overdue prior renders elapsed months; zh up/down color flip respected; render-time delta < 2 min; no `t()` in attributes.

### D5-W4 — Conditional forward-return cells + shrinkage + sector_central binding
- **Tier: sonnet.** Depends: D5-W1 (panel), D4's forward-return join conventions.
- Files: `engine/cond_forward.py` (new), `data/cond_forward/cells_{1,3,6}m.json`, `data/cond_forward/tilt_config.json`, `engine/sector_central.py` + `china_sector_central.py` (tilt swap), `engine/china_sector_pathway.py` (re-route cells through cond_forward), page templates for the presentation contract.
- Acceptance: every cell shows n, n_eff = n/h, shrink weight, Wilson at n_eff; no raw-n Wilson path remains (grep gate); hand tilt maps (`lift*6.0`, `n/60`) deleted, tilt sourced from `tilt_config.json`; cells with n_eff < 12 collapse to pooled row; FWER-honesty footer on every surface, dual-span.

### D5-W5 — Regime prior service + reconciliation banners
- **Tier: sonnet.** Independent of W1-W4 (can ship first).
- Files: `engine/regime_prior.py` (new), `site/regimedata/regime_prior.json` write in `engine/run.py`, `scripts/check_regime_claims.py` (build guard), page JS consumption on all 5+ cycle surfaces, `narratives.json` schema addition (`regime_claim`), banner strings in LEX.
- Acceptance: all cycle pages read the one artifact (grep: no page-local `data/regime/latest.json` read left in cycle-page builders); staleness (> 3 trading days) renders banner; a seeded disagreeing `regime_claim` in a test narrative triggers the banner in a render test; guard fails build on unreconciled regime prose; market_state carries `not_a_model_input: true`.

### D5-W6 — Lead-lag phase-0 (pre-registered)
- **Tier: opus.** Depends: D5-W1 + D5-W2 (needs the hazard walk-forward harness).
- Files: `scripts/leadlag_phase0.py`, pre-registration block written into `data/cycle_hazard/leadlag_phase0.json` BEFORE Stage B runs (two-commit discipline: register, then run), registry entry.
- Acceptance: Stage A FDR table over all pairs; frozen top-K; Stage B pooled ΔBrier with CI and per-year signs; explicit `verdict: GO|NO-GO` per the §4.2 criterion; NO interaction code shipped in this wave regardless of verdict.

### D5-W7 — Interaction feature OR synchronization gauge (conditional on W6)
- **Tier: sonnet.** Depends: D5-W6 verdict.
- GO path: `leader_turned_3m` feature into the production model for the surviving pairs (refit via W2 harness, ledger updated); NO-GO path: `sync` statistic in `engine/cond_forward.py`, family-page gauge replacing markets.html convergence bands, graded as a conditioning state.
- Acceptance (GO): production ledger shows the ΔBrier holding on the refit; (NO-GO): sync gauge rendered with its own cell_table validation, dual-span, and the fake convergence bands removed.

### D5-W8 — Novel feature gates (provisional-turn classifier + leg-velocity)
- **Tier: sonnet.** Depends: D5-W2 (harness reuse).
- Files: `engine/provisional_turn.py` (new, reuses cycle_hazard fitting), phase-0 artifacts `data/cycle_hazard/provturn_phase0.json` + velocity block in `model.json.sensitivity`; UI `p_hold` badge only on gate pass.
- Acceptance: each feature has a stored pass/fail artifact against its pre-registered gate (§5.1 AUC ≥ 0.60 + Brier CI; §5.2 sign-stability + Brier); failures recorded, not deleted; registry entries with come-back dates.

**Sequencing summary:** W5 anytime; W1 → W2 → {W3, W4, W6} → W7/W8. All fitting/panel work lives in cron scripts outside the 67-min render; render-path additions are JSON reads + arithmetic scoring (bounded, measured in W3's acceptance).

---

## 9. Open questions for Fable

1. Should the hazard cone REPLACE the median-half-cycle cone on passing instruments, or render both (model + prior) for a transparency period? (Design assumes replace-with-badge; dual-render costs card space.)
2. `k=6` blend constant and the ±12 tilt cap are pre-registered rather than fit — acceptable, or should W2 grid them under the walk-forward (at multiple-testing cost)?
3. Blocs (EFA/EEM/…) are in the country family for the panel; should they be excluded as redundant composites of members (they mechanically correlate with member turns and could distort the lead-lag screen)? Design currently keeps them in the hazard panel but EXCLUDES them from lead-lag Stage A.
4. Does the D4 backfill stamp cadence (month-end) match this panel's month-end convention exactly? It must — one `PANEL_FREQ` constant should be shared.
