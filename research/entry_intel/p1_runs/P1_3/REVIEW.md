# P1.3 Trio Ablation — CONFORMANCE REVIEW (Opus reviewer, skeptical default)

**Reviewer:** Opus conformance subagent, Entry Intelligence program
**Date:** 2026-07-05
**Artifacts audited:** `run_P1_3.py`, `RESULTS.md`, `results.json` in `research/entry_intel/p1_runs/P1_3/`
**Substrate recomputed against:** `data/replay/replay_boarded.parquet` (MD5 `906175f9eb8caa351ed6d7d5c56265d3` — matches results.json)

---

## FINAL VERDICT: **DEVIATIONS — DO NOT ACCEPT THE NO-GO VERDICT**

The population, era discipline, BH family size, fire-rate table, sign-stability halves, and n-floors are all implemented correctly and recompute exactly. **However, the primary inference statistic — the episode-clustered bootstrap p-value — is statistically invalid.** It returns ≈0.50 for every trial *by construction*, independent of the true effect. Because every GO/NO-GO decision, the BH family, and the headline ("zero of 30 survive; min BH-adj p = 0.53") are all downstream of this broken statistic, the whole-study verdict is **not supported by the evidence**. This is a BLOCKING defect.

The correct interpretation is NOT "the trio is confirmed" — it is "the trio ablation has not been validly tested." At least F1 and F3 have effect-size confidence intervals that exclude zero; F2 is genuinely near-null. A corrected re-run is required before any NO-GO can be registered as `falsified`.

---

## The blocking defect, in detail (BLOCKING)

`episode_bootstrap_mwu` (run_P1_3.py L238–304) resamples episodes **from within each observed group** (A resampled from A, B resampled from B) and then compares:

```
obs_dev  = |obs_U - expected_U|          # expected_U = n_a*n_b/2  (null center)
boot_dev = |boot_U - expected_U|
boot_p   = mean(boot_dev >= obs_dev)
```

A within-group resample produces bootstrap U statistics centered at the **observed** U, not at the null `expected_U`. I reproduced the runner's exact function on T01:

- `obs_U = 348,340,866`; `expected_U (null) = 309,728,955`; `obs_dev = 38,611,911`
- bootstrap `U` mean = **348,323,334** (≈ obs_U, NOT ≈ null), std ≈ 3.48M
- therefore `boot_dev` centers at ≈38.5M ≈ `obs_dev` → `P(boot_dev ≥ obs_dev) ≈ 0.48–0.50`

This is why all 30 boot_p values cluster in [0.4918, 0.5328] regardless of effect size. It is a mis-specified test: a percentile/CI-inversion bootstrap of the **effect** (or a label-permutation null) is required; comparing the resampled deviation against the observed deviation using the same center is guaranteed to yield ~0.5.

### Consequence: real effects were masked

I ran a **correct** episode-clustered bootstrap (resample episodes, recompute rank-biserial r, 95% percentile CI):

| Trial | Effect (r) | Correct cluster-boot 95% CI | CI excludes 0? | Runner boot_p | Runner verdict |
|---|---|---|---|---|---|
| T01 (F1 HG 21d stop) | -0.1247 | [-0.1415, -0.1078] | **YES** | 0.5032 | no survive |
| T04 (F1 HG 63d stop) | -0.0978 | [-0.1141, -0.0809] | **YES** | 0.4972 | no survive |
| T24 (F3 HG 63d stop) | -0.0379 | [-0.0730, -0.0015] | **YES** | 0.4936 | no survive |
| T11 (F2 HG 21d stop) | +0.0117 | [-0.0045, +0.0277] | no (genuinely null) | 0.5328 | no survive |

The correct method separates real effects (F1, F3) from the genuine null (F2). The runner's broken bootstrap flattened all of them to ~0.50. The parametric MWU (printed only as a "secondary diagnostic") for T01 is p = 8.68e-128 — a 128-orders-of-magnitude divergence from the primary boot_p of 0.50 that should itself have tripped a sanity gate in the runner and was not flagged.

**Note on direction (not exculpatory for conformance):** some detected effects are directionally *unfavorable* or ambiguous (T01: washout-pass has HIGHER 21d stop-out, +2.4pp; T04: washout-pass has LOWER 63d stop-out, favorable). The point stands regardless: the primary statistic is broken, so no valid favorable/unfavorable GO/NO-GO adjudication has occurred. The NO-GO for F2 may survive a correct re-run; the NO-GO for F1 and F3 rests on a statistic that demonstrably could not detect their (real) effects.

---

## Per-check findings

### CHECK 1 — Trial-grid adherence: **PASS**
All 30 executed trials (T01–T30) map exactly to the PREREG §4 ledger; factor/mode/horizon/terminal-state tuples match line-for-line. m=30 asserted in code (L427) and in BH. Mode-B rows correctly carry only stop-out + cushioned (no dead-money), per PREREG design note §4. No unregistered trial is presented as primary. No post-hoc trials recorded or needed.

### CHECK 2 — Era / stamp discipline: **PASS**
Primary population filtered to `verdict_type=='fire' & verdict_grade==True` (L118–119). Effective window stated as 2022-06-30 → 2025-12-29 (the on-disk max; the §APPROVAL "→2026-07-02" nominal is the entitlement ceiling, actual ledger ends 2025-12-29 — correctly disclosed). survivor_bias all False; horizon_censored (7,701) pre-excluded via verdict_grade. Stamp text present. `fill_offset` uniformly +1 (next-bar fill) — recomputed and confirmed.
*ADVISORY:* the §APPROVAL clause 1 window literal is "2022-06-30 → 2026-07-02"; RESULTS states the effective realized window 2022-06-30 → 2025-12-29. Consistent and honestly explained, but the run_P1_3.py docstring L14 still says "→ 2026-07-02" — cosmetic.

### CHECK 3 — Independent recompute (≥3 headline numbers): **PASS on descriptives, FAIL on the top-line verdict statistic**
Recomputed and matched exactly: n_vg_fires 49,939; episode clusters 22,295; n_stamped 0; era 2022-06-30→2025-12-29; washout 22,965/26,974; ext_z>2.0 = 2,299; RS quartiles (13016/12632/11101/9362); Q2+Q3 23,733 / Q1+Q4 22,378. Trial descriptives matched exactly: T01 delta +2.405pp, T02 -13.194pp (`T02_notable_dead_money_delta_pp`), T04 -5.206pp (`F1_63d_stop_delta_pp`), r=-0.1247 (`F1_r_biserial_21d`). Fire-rate 54.0% / 48.5% / 4.6% all reproduce.
**FAIL:** the headline verdict statistic `min_boot_p / min_bh_adj_p = 0.53` does NOT survive independent recompute — a correct episode-clustered bootstrap yields effect CIs excluding zero for T01/T04/T24. The >1% mismatch here is categorical (0.50 vs true significant), not marginal.

### CHECK 4 — BH family: **PASS (mechanics), TAINTED (inputs)**
BH implemented correctly: m=30, standard step-up with monotonicity enforcement (L307–323); I reproduced min BH-adj = 0.5328 and n_survive=0 from the runner's own p-vector. Sign-stability halves executed as registered (midpoint ~2024-02-28, n≈24,932 / 25,007). The family is correctly *sized and pooled* — but it is fed 30 invalid p-values, so the correction is operating on garbage. Not a BH-mechanics fault; a p-value-source fault (see Check 3 / blocking defect).

### CHECK 5 — n-floors / INSUFFICIENT-POWER: **PASS**
THIN floor = 25 episode clusters honored; smallest cell (F3 would-block: 1,270 clusters) is well above floor, correctly labeled OK, not borrowed. No cell falsely promoted or falsely thinned. `insufficient_power_cells: []` is correct on the n-floor axis. (Caveat: the *right* honest-null call here is not "insufficient power" but "invalid statistic" — a different failure than the floor logic covers.)

### CHECK 6 — Honesty surface: **PASS with ADVISORY**
RESULTS.md leads with the verdict; plain-English box present; proxy stamps present (rs_sector_quartile current-GICS non-PIT disclosed, 3,828 nulls excluded); leak audit, fire-rate table, sign-stability table, context appendices A/B/C all present. board_rank_unresolved not applicable to this study (descriptive treatment N/A).
*ADVISORY (doc error, non-computational):* RESULTS.md L61 states washout "19,003 True / 30,936 False" for vg_fires — both wrong (actual 22,965 / 26,974; "30,936" is the all-fires False count). The trial math used the correct counts (matches n_A/n_B and fire_rate_impact), so this is a cosmetic transcription error in the preamble only. It should be corrected so a future reader does not distrust the (correct) downstream numbers.

---

## Recommended remediation (for the Fable orchestrator)

1. **BLOCKING:** Replace `episode_bootstrap_mwu` with a valid clustered inference — either (a) percentile/BCa CI of the effect (rank-biserial r or median-difference) from the episode-resampled distribution, with a two-sided p via CI inversion; or (b) an episode-label permutation null. Add a sanity gate: if parametric p and bootstrap p diverge by orders of magnitude, HALT.
2. Re-run all 30 trials, re-apply BH, re-adjudicate §6 criteria. The corrected result may still land some/all factors at NO-GO on **direction** or BH grounds (F2 plausibly stays NO-GO), but the current NO-GO for F1 and F3 is not defensible on the present statistic.
3. Fix the RESULTS.md L61 washout count transcription (advisory).
4. Do not register F1/F2/F3 as `validation_status: falsified` until the corrected re-run lands.

**No git operations performed. This review is data for the Fable orchestrator.**
