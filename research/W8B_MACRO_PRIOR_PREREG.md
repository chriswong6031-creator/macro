# W8b — Macro-Prior Prereg: AI-Capex Complex Baskets

**Status: AWAITING OPERATOR RATIFICATION — DO NOT MERGE**
FT-R7 disclosed exception. See checkbox at bottom.

---

## 1. Hypothesis

`engine/theme_scoring.py` weights the macro leg at 0.18.  When a basket has **no entry** in
`_MACRO_PRIOR` / `_SECTOR_PROXY`, `_macro_leg()` returns `None` and the caller renormalises
that 0.18 weight out of the composite — the basket is scored **macro-blind**, not
macro-dragged. (Source: `engine/theme_scoring.py:229-263`, comment at line 232-235.)

Five AI-capex complex baskets (`ai_semiconductors`, `semicap_equipment`, `memory_storage`,
`data_center_power`, `nuclear_power`) had no entries.  These are the baskets whose demand pool
tracks the hyperscaler capex wave — the same wave whose rapid acceleration triggered the
2026-07-08 Iran-semis incident (FTR masterplan §1 recon).

**Hypothesis:** macro-blindness understates recos for these baskets in macro tailwind regimes
(growth-on / easing Fed / risk-on conditions) and overstates them in macro headwind regimes —
a systematic miscalibration proportional to the basket's true macro sensitivity.

---

## 2. Exact change (map additions only)

**File:** `engine/theme_scoring.py`

**`_MACRO_PRIOR` additions** (five new entries only; all existing entries byte-identical):

| basket | growth | rates | inflation | riskon | analogy |
|---|---|---|---|---|---|
| `ai_semiconductors` | +0.7 | +0.3 | -0.1 | +0.9 | `ai_infra` (same hyperscaler demand pool; slightly higher rates sensitivity for pure-play semis) |
| `semicap_equipment` | +0.6 | +0.1 | +0.1 | +0.6 | `ai_infra` scaled back for upstream/lagged equipment cycles; more industrial, less rates-sensitive |
| `memory_storage` | +0.6 | +0.2 | 0.0 | +0.7 | `ai_semiconductors` with slightly lower risk-on (memory is commodity-like vs accelerator) |
| `data_center_power` | +0.5 | +0.3 | +0.2 | +0.4 | `power_grid` (physical infrastructure build-out; positive inflation leg for equipment pricing) |
| `nuclear_power` | +0.3 | +0.3 | +0.4 | +0.3 | `power_grid` + `energy_complex` blend (energy scarcity narrative + long-duration capital) |

**`_SECTOR_PROXY` additions** (five new entries):

| basket | ETF | reasoning |
|---|---|---|
| `ai_semiconductors` | SMH | Semiconductor ETF — direct live-RS confirmer for AI silicon demand |
| `semicap_equipment` | SMH | Same semiconductor supply-chain ecosystem; WFE names move with the complex |
| `memory_storage` | SMH | HBM/DRAM sits inside the broader semiconductor complex |
| `data_center_power` | XLU | Power/utilities ETF — closest sector proxy for the power-infra buildout |
| `nuclear_power` | XLU | Nuclear operators classified within XLU |

**No other changes:** weights (`WEIGHTS`), leg formulas, `_label`, `_reco`, thresholds, SKIP_D,
Oracle parameters, or any other calibrated construction are untouched.

---

## 3. Delta table (run date: 2026-07-10; as_of in store: 2026-07-09)

Produced by `python -m scripts.research.w8b_macro_prior_deltas` on the current committed store.

```
W8b macro-prior delta table — ratification evidence (FT-R7 prereg)
==============================================================================

basket                      score_b  score_a   delta  reco_before   reco_after    changed   w8b
----------------------------------------------------------------------------------------------------
ai_agents                        53       53      +0  hold          hold               no
ai_infra                         60       60      +0  hold          hold               no
ai_neoclouds                     47       47      +0  avoid         avoid              no
ai_semiconductors                55       60      +5  avoid         avoid              no     *
ai_software                      63       63      +0  accumulate    accumulate         no
big_pharma                       64       64      +0  accumulate    accumulate         no
critical_minerals                35       35      +0  avoid         avoid              no
crypto                           38       38      +0  avoid         avoid              no
crypto_rails                     43       43      +0  hold          hold               no
cybersecurity                    74       74      +0  hold          hold               no
data_center_power                47       46      -1  trim          trim               no     *
defense                          36       36      +0  avoid         avoid              no
defensives                       46       46      +0  avoid         avoid              no
energy_complex                   49       49      +0  hold          hold               no
housing                          46       46      +0  avoid         avoid              no
industrial_distribution          52       52      +0  avoid         avoid              no
insurance                        70       70      +0  accumulate    accumulate         no
mag7                             56       56      +0  avoid         avoid              no
managed_care                     59       59      +0  trim          trim               no
memory_storage                   62       67      +5  trim          trim               no     *
non_ai_software                  58       58      +0  hold          hold               no
non_ai_tech                      55       55      +0  avoid         avoid              no
nuclear_power                    43       41      -2  hold          hold               no     *
obesity_glp1                     66       66      +0  hold          hold               no
payments_fintech                 62       62      +0  hold          hold               no
power_grid                       51       51      +0  hold          hold               no
quantum_computing                41       41      +0  avoid         avoid              no
regional_banks                   61       61      +0  trim          trim               no
reshoring                        54       54      +0  avoid         avoid              no
retail                           35       35      +0  avoid         avoid              no
robotics_automation              47       47      +0  avoid         avoid              no
semicap_equipment                58       63      +5  hold          trim              YES     *
space_economy                    32       32      +0  avoid         avoid              no
travel                           60       60      +0  hold          hold               no
uranium_miners                   33       33      +0  avoid         avoid              no
us_sector_comm                   40       40      +0  avoid         avoid              no
us_sector_discretionary          48       48      +0  avoid         avoid              no
us_sector_energy                 46       46      +0  avoid         avoid              no
us_sector_financials             63       63      +0  accumulate    accumulate         no
us_sector_health                 64       64      +0  hold          hold               no
us_sector_industrials            58       58      +0  avoid         avoid              no
us_sector_materials              47       47      +0  avoid         avoid              no
us_sector_realestate             57       57      +0  avoid         avoid              no
us_sector_staples                53       53      +0  avoid         avoid              no
us_sector_tech                   55       55      +0  avoid         avoid              no
us_sector_utilities              63       63      +0  accumulate    accumulate         no
----------------------------------------------------------------------------------------------------
Baskets scored: 46  |  Reco changes: 1  |  (*) = W8b new entry
```

### Delta interpretation

**Invariance confirmed:** all 41 non-W8b baskets show delta=0, reco unchanged. The change is
exactly as narrow as declared.

**`semicap_equipment` reco change (HOLD → TRIM):** This is the one reco change and warrants
explicit explanation. The macro leg added a +0.571 value (macro tailwind per the growth/risk-on
prior × current state), pushing score 58→63. At score 63, the **rollover guard** in `_label()`
fires (threshold: `score >= 62 AND falling AND delta_5d <= -0.015 AND net_nh <= 0 AND mom_pos
AND breadth_ok AND not long_dn`). As of the run date, `semicap_equipment` had:

- `delta_5d = -0.1415` (the WFE basket fell ~14% in 5 days — the Iran/semis incident)
- `net_nh = 0` (no net new highs)
- `score = 63 >= 62` (newly triggered by macro leg)
- `mom_pos` True (20d rel = +2.86%)
- `breadth_ok` True (pct50 = 0.5)
- `long_sign` not negative

Previously at score=58 the `score >= 62` threshold was NOT met, so the rollover guard did not
fire and the label stayed `neutral` → reco `hold`. With the macro leg, the guard fires →
label `fading` → reco `trim`. The basket is in fact in a technically deteriorating state; the
macro leg revealing this is the guard doing its job, not a spurious reco flip.

**`data_center_power` and `nuclear_power` deltas are negative (-1, -2):** These baskets have a
moderately negative macro component under current conditions (the macro prior for
`data_center_power` has `riskon=0.4` but current conditions are risk-cautious; for
`nuclear_power` with lower growth/risk-on weights the current macro state is mildly headwind).
Scores decrease slightly; recos are unchanged.

---

## 4. Falsification plan

Forward-grading at the existing theme ledger horizons (matching `grade_thematic` conventions):

- **Target:** reco-flipped basket (`semicap_equipment` HOLD→TRIM) and all five W8b baskets.
- **Null:** per-basket forward realized return (equal-weight level) vs SPY, measured at the
  theme ledger horizons (21d, 42d), graded vs counterfactual (the pre-change reco). A trim
  that is followed by further underperformance vs SPY confirms the added macro leg was
  informative. A trim followed by outperformance is evidence against.
- **Grading convention:** PIT — use the score/reco as of the run date (2026-07-10); forward
  window is purely out-of-sample from that date. No backfill.
- **Clock:** first read 2026-09-10 (21d from run date), final read 2026-10-10 (42d).

---

## 5. Rollback

Delete the five new entries from `_MACRO_PRIOR` and the five new entries from `_SECTOR_PROXY`
in `engine/theme_scoring.py`. No other files are affected.

---

## 6. FT-R7 citation

> **FT-R7 — No silent recalibration.** Adding a macro prior for semicap-class baskets changes
> the calibrated score (the score renormalises over available legs — an added leg is a new
> input, not a repaired one) and is therefore W8b: a separate pre-registered trial with
> per-basket before/after score deltas printed.

Source: `research/FAST_TURN_TWO_SPEED_TAPE_MASTERPLAN_BY_FABLE.md`, §4 rulings table, FT-R7.

---

## 7. Operator ratification

- [ ] **OPERATOR RATIFICATION REQUIRED BEFORE MERGE**

The operator must review the delta table above (section 3), confirm the `semicap_equipment`
reco change is acceptable given its technical state (section 3 interpretation), and check this
box before the PR is merged. Merging without this checkbox checked violates FT-R7.

Ratification confirms:
1. The hypothesis in section 1 is accepted as a legitimate structural repair.
2. The exact changes in section 2 are approved.
3. The delta table in section 3 has been reviewed, including the one reco change.
4. The falsification plan in section 4 will be graded at the stated clocks.
