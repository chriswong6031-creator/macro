# W8b — Macro-Prior Prereg: AI-Capex Complex Baskets

**Status: RATIFIED 2026-07-13 — READY TO MERGE**
FT-R7 disclosed exception; operator ratification complete (see section 7).

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
| `data_center_power` | +0.5 | +0.3 | +0.2 | +0.4 | Vertiv/Eaton/GE-Vernova are Electrical-Equipment Industrials (GICS XLI), not Utilities — high-beta cyclicals with riskon 0.4; prior is an AI-capex/infrastructure hybrid, not a power_grid analogy |
| `nuclear_power` | +0.3 | +0.3 | +0.4 | +0.3 | Values chosen on their own merits: energy-scarcity narrative drives higher inflation loading (0.4); moderate growth/riskon (0.3) sits between defensive utility parents (0.1) and cyclical AI-capex entries — NOT a numeric blend of power_grid + energy_complex (both parents have riskon 0.1; no weighted average of them yields 0.3) |

**`_SECTOR_PROXY` additions** (five new entries):

| basket | ETF | reasoning |
|---|---|---|
| `ai_semiconductors` | SMH | Semiconductor ETF — direct live-RS confirmer for AI silicon demand |
| `semicap_equipment` | SMH | Same semiconductor supply-chain ecosystem; WFE names move with the complex |
| `memory_storage` | SMH | HBM/DRAM sits inside the broader semiconductor complex |
| `data_center_power` | XLI | Industrials ETF — Vertiv/Eaton/GE-Vernova are Electrical-Equipment Industrials (GICS XLI), the coherent cyclical proxy for a basket with riskon 0.4; XLU (defensive Utilities) contradicted the prior's cyclical character |
| `nuclear_power` | XLU | Nuclear operators genuinely classify within Utilities (XLU) |

**No other changes:** weights (`WEIGHTS`), leg formulas, `_label`, `_reco`, thresholds, SKIP_D,
Oracle parameters, or any other calibrated construction are untouched.

---

## 3. Delta table (run date: 2026-07-12; as_of in store: 2026-07-12)

Produced by `python -m scripts.research.w8b_macro_prior_deltas` after the operator-ratified
amendments (data_center_power proxy XLU→XLI; nuclear_power provenance wording).

```
W8b macro-prior delta table — ratification evidence (FT-R7 prereg)
==============================================================================

basket                      score_b  score_a   delta  reco_before   reco_after    changed   w8b
----------------------------------------------------------------------------------------------------
ai_agents                        47       47      +0  hold          hold               no      
ai_infra                         60       60      +0  hold          hold               no      
ai_neoclouds                     43       43      +0  avoid         avoid              no      
ai_semiconductors                58       63      +5  hold          hold               no     *
ai_software                      58       58      +0  avoid         avoid              no      
big_pharma                       60       60      +0  hold          hold               no      
critical_minerals                34       34      +0  avoid         avoid              no      
crypto                           35       35      +0  avoid         avoid              no      
crypto_rails                     41       41      +0  hold          hold               no      
cybersecurity                    63       63      +0  hold          hold               no      
data_center_power                50       52      +2  hold          hold               no     *
defense                          34       34      +0  avoid         avoid              no      
defensives                       48       48      +0  avoid         avoid              no      
energy_complex                   45       45      +0  avoid         avoid              no      
housing                          49       49      +0  hold          hold               no      
industrial_distribution          56       56      +0  avoid         avoid              no      
insurance                        67       67      +0  accumulate    accumulate         no      
mag7                             59       59      +0  enter         enter              no      
managed_care                     56       56      +0  trim          trim               no      
memory_storage                   65       70      +5  hold          hold               no     *
non_ai_software                  51       51      +0  avoid         avoid              no      
non_ai_tech                      54       54      +0  avoid         avoid              no      
nuclear_power                    43       41      -2  hold          hold               no     *
obesity_glp1                     62       62      +0  trim          trim               no      
payments_fintech                 61       61      +0  hold          hold               no      
power_grid                       49       49      +0  hold          hold               no      
quantum_computing                39       39      +0  avoid         avoid              no      
regional_banks                   60       60      +0  trim          trim               no      
reshoring                        60       60      +0  hold          hold               no      
retail                           38       38      +0  avoid         avoid              no      
robotics_automation              52       52      +0  hold          hold               no      
semicap_equipment                56       61      +5  hold          hold               no     *
space_economy                    31       31      +0  avoid         avoid              no      
travel                           59       59      +0  hold          hold               no      
uranium_miners                   35       35      +0  avoid         avoid              no      
us_sector_comm                   40       40      +0  avoid         avoid              no      
us_sector_discretionary          50       50      +0  avoid         avoid              no      
us_sector_energy                 43       43      +0  avoid         avoid              no      
us_sector_financials             61       61      +0  hold          hold               no      
us_sector_health                 62       62      +0  hold          hold               no      
us_sector_industrials            58       58      +0  hold          hold               no      
us_sector_materials              51       51      +0  hold          hold               no      
us_sector_realestate             57       57      +0  avoid         avoid              no      
us_sector_staples                53       53      +0  hold          hold               no      
us_sector_tech                   53       53      +0  avoid         avoid              no      
us_sector_utilities              61       61      +0  hold          hold               no      
----------------------------------------------------------------------------------------------------
Baskets scored: 46  |  Reco changes: 0  |  (*) = W8b new entry
```

*Note: non-W8b rows carry delta = 0 by construction (map-only change) but their absolute
scores/reco labels drift with the live store between runs; the ratification-relevant rows are
the five W8b entries and the reco-change count.*

### Recorded history: the 2026-07-10 run (pre-amendment store)

The initial prereg table (run 2026-07-10, store as_of 2026-07-09) showed **one reco change:
`semicap_equipment` HOLD→TRIM** via the rollover guard. The macro leg pushed score 58→63; at
score ≥ 62 with `delta_5d = -0.1415` (the Iran/semis incident ~14% drawdown over 5 days) and
`net_nh = 0`, the rollover-guard condition fired → label `fading` → reco `trim`. The basket
was in a genuinely deteriorating technical state; the guard doing its job, not a spurious flip.

**That reco change dissolved by 2026-07-12.** By the time the 07-12 store was read,
`semicap_equipment`'s score_after was 61 (not 63) — the 5-day Iran drawdown window had rolled
out of the lookback, removing the trigger delta_5d condition. `score 61 < 62` means the
rollover guard does not fire; reco stays `hold`. This is recorded history, not a recalibration:
the guard fired correctly on 07-09 data and released correctly on 07-12 data.

### Delta interpretation (2026-07-12 run, post-amendment)

**Invariance confirmed:** all 41 non-W8b baskets show delta=0, reco unchanged. The change is
exactly as narrow as declared.

**`data_center_power` delta: +2 (50→52).** Switching the sector proxy from XLU to XLI raises
the score by 2 points relative to the 07-10 run (which showed −1 with XLU). The XLI live-RS
confirmer is currently stronger than XLU — consistent with the industrial/cyclical character of
Vertiv/Eaton/GE-Vernova. The reco stays `hold`; the +2 delta reflects the coherent alignment
of a cyclical prior with a cyclical proxy. Under the old XLU routing the macro leg was being
partially suppressed by a defensive-utility confirmer that contradicted the prior's riskon 0.4.

**`nuclear_power` delta: −2 (43→41).** Unchanged from 07-10. The macro prior for nuclear_power
carries moderate growth/riskon (0.3) but the current store is mildly risk-cautious; the prior's
higher inflation loading (0.4) is partially offset. Score decreases slightly; reco unchanged
(`hold`). XLU proxy confirmed correct for nuclear operators.

**`ai_semiconductors`, `semicap_equipment`, `memory_storage` deltas: +5, +5, +5.** Score
improvements from adding the macro leg in a macro-tailwind state (growth-on, easing-leaning
Fed). No reco changes for any of these baskets on 07-12 data; `semicap_equipment` at 61 is
just below the ≥62 rollover-guard threshold.

### Score ≥ 62 threshold disclosure

The score ≥ 62 threshold governs **two** paths in `_label()` / `_reco()`:

1. **Rollover-guard → FADING (risk-reducing):** `score >= 62 AND falling AND delta_5d <=
   −0.015 AND net_nh <= 0`. When this fires, a technically deteriorating basket is labeled
   `fading` → reco `trim` or `sell`. Disclosed in detail above for `semicap_equipment`.

2. **DOMINANT → ACCUMULATE escalation (risk-increasing):** `score >= 62` is also the gate that
   allows a basket already labeled `dominant` to escalate its reco to `accumulate`
   (`engine/theme_scoring.py` ~line 498). Under a macro tailwind that pushes a healthy-technical
   basket above 62, this escalation path can fire — meaning a basket that was holding a strong
   technical position at score 58–61 could receive a more aggressive reco if the macro leg
   carries it across the threshold. No basket flipped to a more aggressive reco in the current
   07-12 snapshot (no W8b basket is in `dominant` state), but operators should be aware that
   the same +macro-leg lift that guards against fading tape can also escalate a strong basket
   when conditions align.

---

## 4. Falsification plan

Forward-grading at the existing theme ledger horizons (matching `grade_thematic` conventions):

- **Target:** all five W8b baskets graded vs counterfactual recos (pre-change reco as the
  null). The `semicap_equipment` HOLD→TRIM reco flip documented in the 07-10 run dissolved
  pre-merge (score 61 < 62 threshold on 07-12 data; see section 3 recorded history). No
  reco-flip target remains — grade all five baskets on whether the added macro leg (positive
  for the semi/storage complex, negative for nuclear_power) is informative vs SPY.
- **Null:** per-basket forward realized return (equal-weight level) vs SPY, measured at the
  theme ledger horizons (21d, 42d), graded vs counterfactual (pre-change reco). A macro-lifted
  basket (ai_semiconductors, semicap_equipment, memory_storage) that outperforms SPY confirms
  the macro leg was informative; underperformance is evidence against. For nuclear_power (score
  reduced −2), SPY outperformance relative to the null reco confirms informativeness.
- **Grading convention:** PIT — use the score/reco as of the amended-merge date
  (2026-07-13); forward window is purely out-of-sample from that date. No backfill.
- **Clock:** first read 2026-08-03 (21d from merge), final read 2026-08-24 (42d from merge).

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

- [x] **OPERATOR RATIFICATION REQUIRED BEFORE MERGE**

The operator must review the delta table above (section 3) — which post-amendment shows
**zero reco changes** (the 07-10 `semicap_equipment` HOLD→TRIM flip dissolved pre-merge; see
the recorded history in section 3) — and check this box before the PR is merged. Merging
without this checkbox checked violates FT-R7.

Ratification confirms:
1. The hypothesis in section 1 is accepted as a legitimate structural repair.
2. The exact changes in section 2 are approved.
3. The delta table in section 3 has been reviewed (zero reco changes post-amendment; the
   dissolved 07-10 semicap flip is recorded as history there).
4. The falsification plan in section 4 will be graded at the stated clocks.

**Ratified 2026-07-13** by operator (session decision; amendments applied at ratification
review: data_center_power proxy XLU→XLI, nuclear_power provenance wording, fresh delta table
on the 2026-07-12 store, CI whitelist wiring). Falsification clocks in section 4 restart from
the amended-merge date: first read 21d, final read 42d from merge.
