# Cycle Intelligence Masterplan — PRE-REGISTRATION LEDGER

**Created:** 2026-07-02 (Wave W0.4 — the keystone gate). **Status:** the anti-p-hacking
contract. Once this document is merged, **criteria do not move.** A gate whose success
threshold, judging data, or FDR family is edited after data has been seen is void — the
edit itself is the finding (the gate failed and someone reached for the dial).

**Provenance.** Every gate below is extracted verbatim-in-spirit from
`research/CYCLE_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §4 (the wave table + acceptance
column) and the pillar designs `D5_PREDICTION.md` (§1.7 skill gate, §1.8 cone coverage,
§4 lead-lag, §5 novel-feature gates), `D2_MEASUREMENT.md` (§3 promise-graders, §4 binding
calibration), and the red-team rulings A2/A7/A14/A15 (`§1` of the masterplan). Masterplan
ruling **A15** mandates this single ledger with BH-FDR applied *within* gate families and
a family-stratified KM baseline (anti-gaming).

---

## 0 · Doctrine for reading this ledger

- **"Expected pass probability under null"** = the chance the gate fires by luck if the
  underlying claim is false, given the test's power and the data on hand. It is the
  budget A15 warns about: ~20 pre-registered gates at α≈0.10 ⇒ ~2 pass by chance. BH-FDR
  *within each family* controls that; the KM baseline (not a coin flip) raises the bar so
  a gate can't pass by beating a straw man.
- **Every gate names the exact data that judges it** — an artifact path or a computed
  statistic. A gate without a runnable judge does not ship (masterplan §5).
- **Risk levers are not return levers** (doctrine #9): a drawdown-reduction gate may size;
  it may never be repurposed to vote direction after the fact.
- **Two cohorts never blend** (doctrine #7): `BACKTEST n=` flips to `LIVE n=` only when the
  prospective cohort matures. A gate judged on TR-v0 backfill (epoch `tr_v0`) is
  research-only and can never promote a user-facing badge (ruling A1).
- **BH-FDR families** are declared per gate. FDR is applied *within* a family at q shown;
  a cell "passes" only if it survives BH at its family's q AND its own CI criterion.

---

## 1 · The keystone gate (W0.4 — THIS wave, already judged)

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **KG-1** | Position deciles carry forward drawdown-adjusted signal | monotone/near-monotone dd-adj score across deciles AND ≥1 extreme-decile gap CI (month-block bootstrap, resample months) excludes 0 at 95% | `data/research/keystone_tr0/study_tables.json` → `full.{h}.position_deciles[*].ret_gap_ci / p10_dd_gap_ci` | ~0.15 (10 deciles × 3 h, but correlated) | `keystone` (q=0.10) |
| **KG-2** | Phases carry forward drawdown-adjusted signal | ≥1 phase's dd-adj gap-vs-base CI excludes 0 at 95%, sign consistent across ≥2 horizons | same → `full.{h}.phases[*].p10_dd_gap_ci` | ~0.20 (5 phases × 3 h) | `keystone` (q=0.10) |
| **KG-3** | The LADDER inversion (low-pos/DECLINE out-performs high-pos/FRESH-BUY) | inversion `verdict == inversion_confirmed` (low-minus-high gap CI excludes 0 on the low side) on ≥2 horizons | same → `full.{h}.inversion.verdict` | ~0.05 (directional, one-sided) | `keystone` (q=0.10) |
| **KG-4** | Signal (BUY/SELL transition badge) precedes its promised move | BUY: fwd-ret hit-gap CI > 0; SELL: fwd-maxdd p10 gap CI < 0 (deeper), both ≥2 horizons | same → `full.{h}.signal[*]` | ~0.10 | `keystone` (q=0.10) |
| **KG-5** | Walk-forward stability | the sign of any KG-1/2 effect that passes on `full` also holds (same sign) on BOTH `pre_2018` and `post_2018` sub-panels | same → `pre_2018.*` / `post_2018.*` | ~0.25 (sign agreement by chance) | `keystone` (q=0.10) |

**This wave's verdict** is recorded in `W04_KEYSTONE_VERDICT.md`. KG-3's result **steers the
scope of Phase 4** (masterplan §6 risk #1): a NO-EDGE keystone shrinks Phases 3-5 to
tripwires + regime context + measurement; a GO expands the hazard/conditional stack.

---

## 2 · Hazard-model skill gates (D5 §1.7, Waves W4.1–W4.3)

The bar is the **age-only Kaplan-Meier hazard**, family-stratified (A15 anti-gaming), NOT a
coin flip. A (direction, horizon) cell ships MODEL output only if it clears its gate; else
the KM PRIOR ships, badged `PRIOR`.

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **HZ-up-1m** | peak-hazard 1m beats KM | OOS Brier(model) < Brier(KM) with month-block bootstrap 90% CI on paired ΔBrier excluding 0 | `data/cycle_hazard/model.json` → `ledger.up.1m.{skill_vs_km, ci90, pass}` | 0.05 | `hazard` (q=0.10) |
| **HZ-up-3m** | peak-hazard 3m beats KM | same, horizon 3m | `ledger.up.3m` | 0.05 | `hazard` (q=0.10) |
| **HZ-up-6m** | peak-hazard 6m beats KM | same, horizon 6m | `ledger.up.6m` | 0.05 | `hazard` (q=0.10) |
| **HZ-dn-1m** | trough-hazard 1m beats KM | same, direction down | `ledger.down.1m` | 0.05 | `hazard` (q=0.10) |
| **HZ-dn-3m** | trough-hazard 3m beats KM | same | `ledger.down.3m` | 0.05 | `hazard` (q=0.10) |
| **HZ-dn-6m** | trough-hazard 6m beats KM | same | `ledger.down.6m` | 0.05 | `hazard` (q=0.10) |

**Power caveat (masterplan §6 risk #2 / R1):** absolute Brier gaps are ~0.011 at ~90
effective blocks — **most cells will likely ship PRIOR initially.** That is a disclosed
prior, not a failure: the KM prior is itself a large upgrade over the re-anchoring median
projection. FDR: BH at q=0.10 across the 6-cell `hazard` family.

**Regime-feature sub-gates (A14):** each regime feature (quad_Q2..Q4, liq, breadth_div)
must clear its own coefficient CI (month-block bootstrap) or it is **dropped** from the
panel. The quad-conditioned skill is labeled *revision-optimistic* until D6 vintages land;
a lagged-quad (+1m) robustness refit is itself a gate: `model.json.sensitivity.quad_lag1_delta_brier`
must be small (< 0.005) or the macro-derived quad is dropped and market-price features kept.

### HZ results (W4.2, 2026-07-03 — criteria above UNCHANGED)

Fit artifact: `data/hazard/model_price_c4414dcb.json` (the actual path; the `judged by`
column's `data/cycle_hazard/model.json` is the planned rename — the `ledger.<dir>.<h>`
sub-keys match). Epoch corrected to **price-basis** turns first (see
`W42_HAZARD_VERDICT.md §0`; y1 events 7,496 → 7,774). Gate scored on **leak-free
out-of-fold** calibrated predictions vs the correctly-specified family-stratified KM
(both a prior strawman-KM and a calibration-on-eval leak were caught and fixed).

| id | result | date |
|---|---|---|
| **HZ-up-1m** | **PASS** — ΔBrier +0.0140, 90% CI [+0.0068, +0.0209], boot p=0.0012, sign 14/17 yrs, survives BH. Robust. | 2026-07-03 |
| **HZ-up-3m** | **PRIOR** — ΔBrier +0.0071, CI [−0.0003, +0.0143] (touches 0), p=0.061. KM prior ships. | 2026-07-03 |
| **HZ-up-6m** | **PRIOR** — ΔBrier +0.0002, CI [−0.0057, +0.0062], p=0.52 (no skill). KM prior ships. | 2026-07-03 |
| **HZ-dn-1m** | **PASS** — ΔBrier +0.0141, CI [+0.0034, +0.0247], p=0.018, sign 11/17, BH. Solid. | 2026-07-03 |
| **HZ-dn-3m** | **PASS (marginal)** — ΔBrier +0.0078, CI [+0.0005, +0.0155], p=0.036, sign 13/17, BH. | 2026-07-03 |
| **HZ-dn-6m** | **PASS (marginal)** — ΔBrier +0.0042, CI [+0.0005, +0.0079], p=0.024, sign 12/17, BH. | 2026-07-03 |

**Summary: 4 of 6 PASS, 2 PRIOR** — lands close to the pre-registered "most cells ship PRIOR"
expectation; the 1-month cells are the robust wins. **Regime sub-gate:** `breadth_div`
dropped for *absence* (not computed in the W4.1 panel); `quad_Q2`/`quad_Q4` (up) and
`quad_Q3`/`liq_expanding` (down) fail their coefficient CI and are flagged DROP; zeroing them
leaves the passing 1m cells unchanged (edge is not regime-carried). **Quad-lag robustness:**
`quad_lag1_delta_brier` = 0.0002 (up) / 0.0029 (down), both < 0.005 → macro quad retained,
quad-conditioned skill labeled *revision-optimistic* (P-D5-1). See `W42_HAZARD_VERDICT.md`.

---

## 3 · Cone-coverage / calibration gates (D2 §3.2–3.3, D5 §1.8, Wave W2.4)

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **CC-1** | the hazard cone's stated band is calibrated | empirical coverage of the S∈[0.25,0.75] band within Wilson CI of the 50% nominal (i.e. |coverage − 0.50| not significant), per direction | `data/cycle_hazard/scorecard.json` / `data/<engine>/cone_coverage.json` → `{empirical, ci, nominal}` | n/a (calibration, not skill) | `calibration` (report-only) |
| **CC-2** | reliability: probabilities are honest | Brier skill_score vs per-instrument base rate > 0 with n≥30; ECE reported | `data/<engine>/reliability.json` → `{skill_score, ece, n}` | 0.10 | `calibration` (q=0.10) |
| **CC-3** | turn precision/recall is factual, not circular | precision & recall Wilson-lo > 0.5 on n_eff≥40, graded against **independent realized-extrema truth** (A6), not the same detector | `data/<engine>/turn_pr.json` → `pooled.{precision_ci, recall_ci, n_eff}` | 0.15 | `turn_pr` (q=0.10) |

Cone half-width is **recalibrated** from the realized timing-error distribution
(`quantile(|timing_err|, nominal)`), replacing `lerp(1.5,13)`; the recalibration is a
stored calibration artifact, not a hand constant (D2 §3.2 / §4). CC gates are
*calibration* (coverage ≈ nominal), not *skill* — a well-calibrated 50% cone that covers
50% PASSES; it is not trying to beat a baseline.

---

## 4 · Binding-calibration gate (D2 §4, Wave W4.6)

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **BC-1** | LADDER_SCORE / tier cuts / stance matrix are earned, not asserted | artifact `validated==true` ⇔ every fit cell n_eff≥40 AND train→holdout rank-corr of the risk-adjusted score >0.5 AND cell survives `fdr_adjust` AND block-bootstrap CI excludes null | `data/calibration/*.json` → `{validated, holdout_check.rank_corr_train_vs_holdout, fdr_passed_cells}` | ~0.10 | `calibration` (q=0.10) |
| **BC-2** | the word "validated" requires a stored artifact | `tests/test_no_unearned_validated.py` greps EN+zh+generated JS for "validated"/"已验证"; fails if the token appears without a backing artifact whose `validated==true` | the test itself (CI hard step) | 0 (mechanical) | n/a (guard) |

The binding metric is the **drawdown lens** — `score_metric(state) = mean_fwd_ret(state) /
|dd_p10(state)|` (return per unit tail risk), fit walk-forward. This is where the keystone
gate's KG-3 result is operationalized: if DECLINE's return-per-tail genuinely ranks above
FRESH-BUY out-of-sample, BC-1 encodes it; if the keystone said NO-EDGE, BC-1 fails and the
ladder ships as FRAME context, not a fitted score.

**RESULTS (W4.6, 2026-07-03 — appended per A15; criteria above were NOT moved):**

| id | criterion (verbatim, frozen) | result | judged by | date |
|---|---|---|---|---|
| **BC-1** | train→holdout rank-corr of the risk-adjusted score >0.5 AND n_eff≥40 AND FDR-survived AND CI excludes null | **FAIL** — train→holdout rank-corr of `mean_fwd_ret/\|dd_p10\|` per state = **−0.119** (bar >0.5; *negative* — the return-per-tail ordering INVERTS out-of-sample). Exactly the §6.5 pre-committed expectation. `validated=false`; the ladder ships as FRAME context, not a fitted score. | `data/regime/ladder_risk_calibration.json` → `bc1.{verdict,rank_corr_train_vs_holdout}` | 2026-07-03 |
| **BC-2** | grep EN+zh+generated JS for "validated"/"已验证"; fail if the token appears without a backing artifact whose `validated==true` | **WIRED + PASSING** — implemented as `scripts/check_validated_claims.py` (+ `data/regime/validated_claims_allowlist.json`, 166 justified entries) rather than `test_no_unearned_validated.py`; runs as a HARD abort-lane step in `cycle-calibration.yml`. Whole-tree scan clean; selftest proves it fires on a synthetic unearned claim in EN and zh. NO unearned uses were found in the existing corpus (it was already disciplined). | the gate + its `--selftest` (CI hard step) | 2026-07-03 |

**The re-scope actually applied (D2 §4.1 metric replaced per §6.5 item 2).** The `mean_fwd_ret/|dd_p10|`
metric is denominator-dominated (ranks states by ambient vol). W4.6 re-scoped to the RISK channel:
the binding metric is the **vol-residualized forward drawdown** `rdd = fwd_maxdd / trailing_63d_vol`,
and the binding value is a **SIZE multiplier in [0.5,1.5]** (never a directional score). The disciplined
verdict: after vol-residualization, **0 of 48 (state × family × horizon) cells survive BH-FDR q=0.10**
within the `calibration` family (2 nominal pre-FDR hits = the ~2–3-by-luck rate this ledger fences).
**Every cell ships `risk_size_mult=1.0` — there is no risk-sizing signal.** The raw
`ladder_calibration.json` drawdown ordering was ambient-vol clustering. The directional `LADDER_SCORE`
is UNTOUCHED this wave (its axis-flip is W4.7's question). Full verdict:
`research/cycle_masterplan/W46_BINDING_CALIBRATION_VERDICT.md`.

---

## 5 · Lead-lag two-stage gate (D5 §4, Waves W5.1–W5.2)

**Two-commit discipline:** the pre-registration block is written into
`data/cycle_hazard/leadlag_phase0.json` **before** Stage B runs (criteria commit, then
results commit). The STOP rule is binding and written before the run.

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **LL-A** | some ordered pair's lagged Δphase-position leads | ≥1 pair×lag survives BH-FDR q=0.10 across ALL pairs×lags on the ≤2017 TRAIN cross-correlation (Δosc, block-bootstrap null band) | `leadlag_phase0.json` → `stageA.fdr_survivors` | 0.10 (FDR-controlled by construction) | `leadlag_A` (q=0.10) |
| **LL-B** | knowing the leader's turn improves the follower's OOS hazard | for the frozen top-K=20 pairs: pooled OOS 3m Brier improvement ≥ 2% AND positive in ≥2/3 walk-forward year-blocks AND paired month-block bootstrap 90% CI on ΔBrier excludes 0 | `leadlag_phase0.json` → `stageB.{rel_brier_improvement, year_block_signs, ci90}` | ~0.05 | `leadlag_B` (q=0.10) |

### W5.1 results (2026-07-03 — criteria above UNCHANGED, two-commit discipline observed)

| id | criterion (verbatim, frozen) | result | judged by | date |
|---|---|---|---|---|
| **LL-A** | ≥1 pair×lag survives BH-FDR q=0.10 on ≤2017 TRAIN cross-correlation | **PASS** — 136 of 8,253 pair×lag tests survive BH-FDR (q=0.10). Top-20 frozen to `data/leadlag/frozen_pairs.json`. Stage A gate passes; proceed to Stage B. | `leadlag_phase0.json` → `stageA.n_fdr_survivors=136` | 2026-07-03 |
| **LL-B** | pooled OOS 3m Brier improvement ≥ 2% AND positive in ≥2/3 year-blocks AND CI₉₀ excludes 0 | **NO-GO** — all three sub-criteria fail: rel improvement = +0.029% (bar ≥2%), CI₉₀ = [−0.261%, +0.288%] (includes 0), 3 of 9 year-blocks positive (bar ≥6). Verdict: STOP. Fallback: sync gauge shipped on `measurement.html` (T7). | `leadlag_phase0.json` → `stageB.pooled.{rel_brier_improvement=0.00029, n_year_blocks_positive=3, ci90=[-0.002607,0.002882]}` | 2026-07-03 |

**STOP rule:** if LL-A yields no survivors OR LL-B fails → `verdict: NO-GO`, **do not build
the interaction layer.** Ship instead the measured synchronization statistic (`sync = 1 −
circ_var(2π·pos/100)`) validated as a conditioning state via the conditional-cell machinery
under the same shrinkage/effective-n rules, replacing markets.html's fake convergence bands.

---

## 6 · Decision-linkage gates (A7 — the anti-"build with no payoff" contract)

Ruling A7: the hazard/conditional stack is the biggest build with the weakest
decision-linkage. Each D5 output must move a *named decision*, or it ships as a research
surface only.

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **DL-1** | the hazard cone earns its place over the IQR band | walk-forward entry-sizing on the hazard cone improves drawdown-adjusted outcomes vs the current median-half-cycle IQR band, CI excluding 0 | a walk-forward sizing backtest artifact (W4.2 acceptance) | 0.10 | `decision` (q=0.10) |
| **DL-2** | conditional phase×quad cells earn a conviction tilt | the fitted `tilt_config.json` tilt improves sector_central walk-forward drawdown-adjusted conviction ordering vs the flat map, CI excluding 0 | `data/cond_forward/tilt_config.json` + a walk-forward conviction backtest | 0.10 | `decision` (q=0.10) |

Until DL-1/DL-2 pass, the corresponding outputs ship **as a research surface** (measurement
page), never as a badge that sizes a position. D5-W8 novel features (provisional-turn
classifier, leg-velocity) are **cut to research backlog** unless their own §7 gate passes.

### DL-2 results (W4.4, 2026-07-03 — criteria above UNCHANGED)

| id | criterion (verbatim, frozen) | result | judged by | date |
|---|---|---|---|---|
| **DL-2** | the fitted tilt improves sector_central walk-forward drawdown-adjusted conviction ordering vs the flat map, CI excluding 0 | **NOT RUN** — W4.4 delivers the cell estimates and CIs (research surface); the walk-forward conviction backtest is a downstream wave. Prerequisite met: 7 cells in fwd_ret/63d and 11 in fwd_ret/126d have CIs excluding the phase-pooled mean. All are `revision_optimistic=True` (P-D5-1). Ruling A7: cells ship as research surface on `measurement.html` only. No `tilt_config.json` is produced this wave. | `data/cycle_ontology/conditional_cells_20260703.json` → `verdict_summary` | 2026-07-03 |

---

## 7 · Proxy-fitness gates (D3 §, Wave W3.1)

MEASURED-proxy series (a substitute standing in for an unobservable cycle) must earn the
substitution by a turn-match fitness bar, Wilson-bounded (A6/R1).

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **PX-MU** | MU (memory maker) tracks the DRAM cycle's turns | turn-match precision & recall Wilson-lo > 0.5 vs the reference DRAM-ASP turn series | proxy registry fitness artifact → `bands[*].fitness` | 0.15 | `proxy` (q=0.10) |
| **PX-CCJ** | CCJ tracks the uranium (U₃O₈) cycle's turns | same, vs the U₃O₈ spot turn series | same | 0.15 | `proxy` (q=0.10) |

A proxy that fails its fitness gate ships as **FRAME** (timing-only, position gauge
suppressed — ruling A17), never as a MEASURED position.

---

## 8 · Novel-feature gates (D5 §5, Wave W4.x/W5)

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **NF-provturn** | P(provisional pivot survives to confirmation) is skillful | OOS AUC ≥ 0.60 AND calibrated-Brier beats base rate with CI excluding 0 | `data/cycle_hazard/provturn_phase0.json` | 0.10 | `novel` (q=0.10) |
| **NF-velocity** | abnormally fast legs die young (leg-velocity feature) | coefficient sign stable across ALL walk-forward folds AND pooled OOS Brier improves | `model.json.sensitivity.velocity` | 0.15 | `novel` (q=0.10) |

Failures are **recorded, not deleted** (the artifact stores the failing verdict); the
feature simply does not ship.

---

## 9 · Program-level FDR budget (A15)

- **Families and their sizes:** `keystone` (5), `hazard` (6), `calibration` (CC-1..3 +
  BC-1..2), `turn_pr` (1 pooled + per-instrument as a sub-family), `leadlag_A` (all
  pairs×lags), `leadlag_B` (1 pooled), `decision` (2), `proxy` (2), `novel` (2).
- **BH-FDR is applied WITHIN each family** at the q shown (0.10 unless noted). No claim is
  reported "earning"/"validated" unless it survives BH within its family AND its own CI
  criterion.
- **Naive expectation under global null:** summing E[pass|null] across ~28 independent-ish
  gates ⇒ **~2–3 pass by luck** if every underlying claim is false. That is the p-hacking
  surface this ledger fences. A result is only believed if it (a) survives its family's BH,
  (b) holds sign out-of-sample (KG-5 / the walk-forward requirement baked into each skill
  gate), and (c) is not the *only* survivor in a large family (a lone survivor in
  `leadlag_A` across ~1,500 pairs×lags is treated as FDR noise per the STOP rule).
- **KM baseline is family-stratified** (A15 anti-gaming): the skill bar is computed per
  family (`us_sector`/`country`/`cn_sector`) so a model can't "win" by beating a pooled KM
  that a single high-turn family (EWZ) distorts.

---

## 10 · Amendment log (append-only; an entry here is itself a finding)

- 2026-07-02 — Ledger created at W0.4. KG-1..5 judged this wave (see
  `W04_KEYSTONE_VERDICT.md`); all downstream gates registered, criteria frozen. No
  amendments.
- 2026-07-03 — **W4.4 results appended** (DL-2 gate status recorded; §6 results block).
  DL-2 criterion unchanged. Implementation note: the conditional-cell builder derives `phase_v2`
  from `pos_osc` + `direction` (using D1's ZONE_EHI/ZONE_ELO boundaries) since MTF MACD votes
  are not available in the monthly panel. This is a PIT-pure simplification relative to the
  full `classify_phase()`; future waves may upgrade to full phase classification if panel is
  enriched. All 39 winning cells are `revision_optimistic=True` (P-D5-1).
- 2026-07-03 — **W4.6 results appended** (BC-1 FAIL, BC-2 wired+passing; §4 results block).
  No success criterion was moved. Two honest implementation notes recorded as findings, not
  silent changes: (1) BC-1's *binding metric* was re-scoped per §6.5 item 2 from the
  denominator-dominated `mean_fwd_ret/|dd_p10|` to the vol-residualized `fwd_maxdd/trailing_vol`
  (the SUCCESS CRITERION — rank-corr>0.5, n_eff≥40, FDR, CI-excludes-null — was applied
  unchanged; the return-channel metric was ALSO evaluated verbatim and recorded as FAIL). (2)
  BC-2 was implemented as `scripts/check_validated_claims.py` + a justified allowlist rather
  than the placeholder filename `tests/test_no_unearned_validated.py` named in the criterion;
  the MECHANISM (grep EN+zh+generated JS; fail on an unbacked 'validated') is identical.

---

## 11 · W2.5 Collinearity gate (post-registration, 2026-07-02)

**Honestly labeled post-registration entry.** This gate was not in the original
ledger (W0.4 was focused on predictive-power; W2.5 was a measurement/prerequisite
wave added after the keystone re-steer §6.5). It is added here as a results-only
entry: the criteria were defined in the W2.5 wave prompt and in R4 §U2 (BEFORE the
study ran), and are reported below as-found with no post-hoc adjustment.

| id | claim | pre-registered criterion | judged by | result | date |
|---|---|---|---|---|---|
| **CL-1** | state_score and pos_osc are redundant (near-collinear price transforms) | pooled \|rho\| > 0.80 OR VIF > 5.0 | `data/cycle_ontology/collinearity_phase0.json` → `verdict.redundant_pairs` + `verdict.high_vif_legs` | **CONFIRMED** — rho(state_score, pos_osc) = −0.968; VIF(pos_osc) = 29.8, VIF(state_score) = 25.8 | 2026-07-02 |
| **CL-2** | at least one leg carries independent risk-channel information (partial-corr CI excludes 0) | ≥1 leg's partial-corr with forward max-drawdown has bootstrapped 95% CI excluding 0 on ≥1 horizon | same artifact → `verdict.risk_channel_survivors` | **CONFIRMED** — 4 survivors: trend_pass_f, mom_score, rs_63d_f, vol_pctile (63d horizon) | 2026-07-02 |
| **CL-3** | 90% of variance captured by fewer PCs than legs (dimension reduction justified) | n_pcs_for_90pct < n_legs (8) | same artifact → `pooled.pca.n_pcs_for_90pct` | **CONFIRMED** — 5 PCs (of 8 legs) explain 91.2% of variance | 2026-07-02 |

**Binding consequence (gates W4.2 and W4.6):** W4.2 (hazard fit) and W4.6 (binding
calibration) MUST NOT include both `state_score` and `pos_osc` as separate features.
The de-duplicated feature set is: ONE representative from the collinear pair (use
`pos_osc` as the simpler representative) + `trend_pass_f` + `mom_score` +
`rs_63d_f` + `vol_pctile` + `amp_proxy` (low VIF=1.1, retained) + `osc_slope_f`
(low VIF=1.7, retained) + macro-regime axis (non-price, assumed orthogonal — to be
measured when PIT regime backfill exists). If PCA orthogonalization is preferred,
use the top 5 loadings stored as a committed artifact.

**Study details:** 12,504 pooled PIT monthly stamps (11 US sectors, 31 country ETFs,
31 China Shenwan sectors; 2010-12-31 → 2026-06-30). Month-block bootstrap, 800 draws,
seed=7. Script: `scripts/collinearity_phase0.py`. Full tables in artifact JSON.

**Skipped legs (disclosed):** macro-regime quad/liquidity (no PIT backfill; P-D5-1
revision leak); age-in-phase (deferred to D5-W1 hazard panel).

---

## 12 · CPI feature-trial gates — family `cycle_pattern_ft` (registered 2026-07-06, PRE-RUN)

**Two-commit discipline (as W5.1):** this section + the frozen runner
(`scripts/build_cycle_pattern_ft_phase0.py`) + the trial-budget declaration are committed BEFORE the
study runs. The results commit appends a results block below WITHOUT moving any criterion. Program
context: masterplan §4 (the information program) — the CPI thesis that new orthogonal covariates,
not deeper mining of existing columns, move turn-prediction accuracy.

**Design (frozen).** Harness = the W4.2 harness verbatim: discrete-time L2 logistic per direction on
the person-period panel `data/hazard/panel_price_c4414dcb.parquet`, expanding-origin ANNUAL date-block
walk-forward (first test year 2010, 6-month embargo), leak-free out-of-fold PAV calibration, paired
ΔBrier month-block bootstrap (800 draws, seed 7), BH-FDR q=0.10 within the family. **Baseline = the
current shipped W2.5-bound feature set refit under the identical folds inside this runner** — NOT the
KM prior: a covariate block must add information beyond what already ships. **Holdout embargo:** rows
with date ≥ 2024-01-01 are excluded from all fitting AND from the gate (stricter than W4.2's own span;
preserves the untouched confirmatory window; test years 2010–2023, 14 blocks). Sign-stability bar:
ΔBrier(base − base+X) > 0 in ≥ 60% of test years (≥ 9 of 14).

**Frozen feature blocks — no per-feature selection permitted after this commit:**

- **FT-1 breadth block** (4 features, PIT-pure from member tapes of the instrument's own panel family):
  `fam_pct_above_200d`, `fam_pct_above_50d`, `breadth_div_own` (= fam_pct_above_200d − own
  above-200d indicator), `breadth_thrust_3m` (= Δ over 3 month-ends of fam_pct_above_50d).
- **FT-4 structure block** (4 features, PIT-pure from the panel cross-section at t):
  `sync_family` (= 1 − circular variance of family `pos_osc`, the W5.1 statistic), `phase_breadth_late`
  (fraction of family members with pos_osc ≥ 70), `phase_breadth_early` (fraction ≤ 30),
  `pos_dispersion` (cross-sectional std of family pos_osc / 100).

Continuous features standardized by train-fold mean/sd, as W4.2.

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **FT1-{up,dn}-{1m,3m,6m}** | the breadth block adds OOS turn-hazard skill beyond the shipped feature set | paired ΔBrier(base − base+block) month-block bootstrap 90% CI excludes 0 on the positive side AND survives BH-FDR q=0.10 within `cycle_pattern_ft` AND sign-stability ≥ 9/14 years | `data/cycle_pattern/ft_trials/ft1_breadth.json` → `ledger.<dir>.<h>` | 0.05/cell | `cycle_pattern_ft` (q=0.10) |
| **FT4-{up,dn}-{1m,3m,6m}** | the cross-entity structure block adds OOS turn-hazard skill beyond the shipped feature set | same | `data/cycle_pattern/ft_trials/ft4_structure.json` → `ledger.<dir>.<h>` | 0.05/cell | `cycle_pattern_ft` (q=0.10) |

**Trial budget:** 12 cells (2 blocks × 2 directions × 3 horizons), declared as family
`rf.cycle_pattern.ft_v0` in `data/trial_ledger.jsonl` at criteria-commit time. No other cells, blocks,
horizons, or feature substitutions may be evaluated under this registration.

**Outcome handling (frozen):** failing cells → the block does NOT enter the shipped model; a null
truth artifact scoped to the block is appended to `data/cycle_pattern/truths.jsonl`. Passing cells →
eligibility for a shipped-model refit is a SEPARATE follow-on wave (promotion still requires the truth
layer + Signal Bus notes); no page/UI change this wave regardless of outcome. The stated bounty is the
up-3m/up-6m PRIOR cells: any block that unlocks multi-month peak hazard matters more than any lattice cell.
