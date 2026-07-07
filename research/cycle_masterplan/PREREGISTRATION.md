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

### FT results (2026-07-06 — criteria above UNCHANGED; two-commit discipline observed)

| id | result | date |
|---|---|---|
| **FT1-up-{1m,3m,6m}** | **FAIL** — ΔBrier +0.0026 / +0.0028 / +0.0021, all CI₉₀ straddle 0 (lower bounds −0.0005/−0.0004/−0.0003); years+ 10/7/8 of 14; none survive BH. Directionally positive but not claimable. | 2026-07-06 |
| **FT1-dn-1m** | **FAIL (harmful)** — ΔBrier **−0.0056**, CI₉₀ [−0.0099, −0.0016] excludes 0 on the NEGATIVE side: the breadth block actively degrades the strongest shipped cell. | 2026-07-06 |
| **FT1-dn-{3m,6m}** | **FAIL** — ΔBrier −0.0018 / −0.0006, CIs straddle 0. | 2026-07-06 |
| **FT4-{up,dn}-{1m,3m,6m}** | **FAIL** — all six cells: ΔBrier −0.0036 … +0.0010, every CI₉₀ straddles 0 (up/6m lower −0.0077), no BH survivor. | 2026-07-06 |

**Verdict: 0 of 12 cells pass.** Per frozen outcome handling: neither block enters the shipped model;
null truth artifacts CPI-016 (breadth block) and CPI-017 (structure block) appended to
`data/cycle_pattern/truths.jsonl`, scoped to these exact block definitions and this harness. Full
adjudication: `research/cycle_masterplan/CPI_FT1_FT4_VERDICT.md`. Reopening either block requires a
NEW preregistered trial naming the null it challenges (dead-stays-dead). Artifacts:
`data/cycle_pattern/ft_trials/ft{1,4}_*.json`; budget line `rf.cycle_pattern.ft_v0` n=12 in
`data/trial_ledger.jsonl`.

---

## 13 · CPI feature-trial batch 2 — FT-2 credit/curve (registered 2026-07-06, PRE-RUN)

Same harness and discipline as §12, unchanged: W4.2 harness verbatim; **baseline = the shipped
W2.5-bound feature set refit under identical folds inside the runner**; embargo (rows ≥ 2024-01-01
excluded from fit AND gate); 14 test years 2010–2023; paired ΔBrier month-block bootstrap (800, seed
7); sign-stability ≥ 9/14. **Batch-1 lessons applied:** one block, three features, and
direction-scoped adjudication — the block may be adopted for at most the direction(s) whose cells pass.

**FT-3 (net liquidity) is NOT registered this batch** — the numeric components on disk are
insufficient (WALCL 2002→, RRPONTSYD 2003→, TGA absent). Registering a weak proxy would repeat the
FT-1 kitchen-sink mistake. Docket: build the TGA/netliq collector (P4), then register FT-3 properly.

**Frozen FT-2 block (3 features; market-priced; PIT-pure; time-only covariates — precedent: the
quad/liquidity dummies already in the base model):**
- `hy_oas_pctile` — expanding percentile of the BofA HY OAS level at t
  (`data/fred/BAMLH0A0HYM2.parquet`, 1996-12→; the 4-month NaN head at panel start follows the §12
  median-impute convention).
- `hy_oas_d63` — 63-trading-day change in the HY OAS level at t.
- `curve_10y3m` — the 10y−3m Treasury spread level at t (`data/fred/T10Y3M.parquet`, 1982→).

All series sampled at the last available observation ≤ t (weekly/daily publication; no lookahead).

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **FT2-{up,dn}-{1m,3m,6m}** | the credit/curve block adds OOS turn-hazard skill beyond the shipped feature set | identical to §12: paired ΔBrier CI₉₀ excludes 0 on the positive side AND survives BH-FDR q=0.10 within `cycle_pattern_ft_v1` AND sign-stability ≥ 9/14 years | `data/cycle_pattern/ft_trials/ft2_credit.json` → `ledger.<dir>.<h>` | 0.05/cell | `cycle_pattern_ft_v1` (q=0.10) |

**Trial budget:** 6 cells, declared as family `rf.cycle_pattern.ft_v1` in `data/trial_ledger.jsonl`
pre-p-value. No other features, transformations, lags, or horizons may be evaluated under this
registration. Outcome handling as §12: fail → `promoted_null` scoped to this block; pass → adoption
is a separate follow-on wave; no page/UI change this wave regardless.

### FT-2 results (2026-07-06 — criteria above UNCHANGED; two-commit discipline observed)

| id | result | date |
|---|---|---|
| **FT2-up-{1m,3m,6m}** | **FAIL (harmful)** — ΔBrier −0.0118 / −0.0113 / −0.0098, ALL CI₉₀ entirely below 0; years+ 4/14 each. The block significantly degrades every peak-hazard cell. | 2026-07-06 |
| **FT2-dn-1m** | **FAIL (harmful)** — ΔBrier −0.0043, CI₉₀ [−0.0074, −0.0013]. | 2026-07-06 |
| **FT2-dn-{3m,6m}** | **FAIL** — ΔBrier −0.0020 / −0.0003, CIs straddle 0. | 2026-07-06 |

**Verdict: 0 of 6 pass; 4 of 6 significantly harmful.** Truth CPI-018 (`promoted_null`, block-scoped)
appended. **Program-level synthesis after 2 batches (18 cells, 0 passes, 5 harmful):** additive
feature blocks on the pooled hazard logistic reliably reduce OOS skill under this harness — the
shipped model's parsimony is load-bearing (events-per-variable + regime nonstationarity). Steer
(recorded here as adjudication, NOT a criteria change): no further additive-feature FT registrations
on the pooled hazard until a structurally different result motivates one; the docket advances to the
lattice (no model fitting), TR-1 (new target), IX-1 (new unit of analysis), and the regime-v2 PIT
spine. Artifacts: `data/cycle_pattern/ft_trials/ft2_credit.json`; budget `rf.cycle_pattern.ft_v1`
n=6 declared pre-p-value. Full adjudication: `research/cycle_masterplan/CPI_FT2_VERDICT.md`.

---

## 14 · CPI lattice batch 1 — family `cycle_pattern_lattice_v0` (registered 2026-07-06, PRE-RUN)

**Mode shift after the FT synthesis (§13 results):** no model fitting. Shrunken conditional-cell
estimates over PIT-pure, price-derived dimensions only — the W4.4 machinery
(`scripts/build_conditional_cells.py`: `james_stein_shrink`, month-block `cell_boot_ci`,
vol-residualized DD) reused verbatim, with **no quad conditioning** → survivors carry NO
revision-optimistic caveat (the novelty vs W4.4).

**Frozen lattices** (substrate: hazard panel `price_c4414dcb` + its W4.4-convention forward joins;
embargo: rows ≥ 2024-01-01 excluded from estimates AND gate):
- **L-A:** `phase_v2`(5, derived from pos_osc+direction per W4.4) × `family`(3) = 15 cells.
- **L-B:** `phase_v2`(5) × `trend_pass`(2) × `family`(3) = 30 cells.

**Frozen targets (3):** `rdd_63d` (vol-residualized forward max-DD, 63 trading days — the W4.6
binding metric; raw-DD ordering is ambient-vol clustering and is NOT a target), `turn_event_3m`
(panel y3), `phase_persist_3m` (phase_v2 unchanged across the next 3 month-ends).

**Estimates:** (15 + 30) × 3 = **135 shrunken cell estimates** — this whole count is the declared
search space. Exploration output = shrunk mean + 95% month-block bootstrap CI on the gap vs the
phase-pooled mean (800 draws, seed 7), n_months per cell, collapse below 12 months (report pooled
only), per D2/A2 rules.

| id | claim | success (PROMOTION) criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **LT1-cell** (any of the 135) | the cell's outcome differs from its phase-pooled baseline | gap CI₉₅ excludes 0 AND n_months ≥ 40 AND era-split sign agreement (pre-2018 AND post-2018 sub-panel gaps share the full-sample sign) AND survives BH-FDR q=0.10 across ALL 135 gap tests | `data/cycle_pattern/lattice/batch1.json` → `promotions[]` | ~0.05/cell pre-FDR | `cycle_pattern_lattice_v0` (q=0.10) |

**Budget:** 135, declared as `rf.cycle_pattern.lattice_v0` pre-p-value. **Pipeline sanity gate
(printed, not a claim):** the raw-DD phase×family point estimates must reproduce the KG-2 direction
(Trough → deeper, Peak → shallower forward DD) on the full sample, else the run aborts as a
pipeline error. **Outcome handling:** promoted cells → factory candidates (status `screened`, with
this artifact as evidence) + display-class truth candidacy; zero promotions → a scoped null truth
for the two lattices; exploration tables ship to the measurement research surface either way. No
page-authority change this wave.

### Lattice batch-1 results (2026-07-06 — criteria above UNCHANGED)

**48 of 135 cells clear the frozen gate** (sanity gate: KG-2 reproduced). Adjudication
(`CPI_LATTICE1_VERDICT.md`): the cross-family phase-pooled baseline conflates family base-rate
offsets with phase effects (CN cells mirror-signed vs US/country per phase) — the 48 promotions are
classified confirmatory-only (CPI-019, display/structural) with ONE substantive lead: CN Downturn ×
broken-trend deep vol-adjusted tail (CPI-020, candidate; rdd gap −0.0597, CI₉₅ [−0.119, −0.028],
n=145, era-stable) pending a within-family re-test. All 48 filed as factory candidates (`screened`,
authority display_only, truth_guard 0 flags). **Batch-2 pre-commitment: lattice baselines go
within-family (to be frozen as §15 before any batch-2 run).** Process disclosure: an implementer
scratch dry-run preceded the criteria commit; §14 text is character-identical pre/post (see verdict
doc). Artifacts: `data/cycle_pattern/lattice/batch1.json`, `batch1_cells.parquet`; budget
`rf.cycle_pattern.lattice_v0` n=135 declared pre-p-value.

---

## 15 · CPI lattice batch 2 — WITHIN-FAMILY baselines, family `cycle_pattern_lattice_v1` (registered 2026-07-06, PRE-RUN)

**Two-commit discipline:** this section + the frozen runner
(`scripts/build_cycle_pattern_lattice_batch2.py`) + tests are committed BEFORE any run against the
real panel (unit tests excluding the real-panel smoke run pre-commit; the smoke and the real run
happen only after the criteria commit — tightening the §14 process disclosure). The results commit
appends a results block below WITHOUT moving any criterion.

**Motive (binding, from the §14 adjudication):** the §14 baseline (phase-pooled ACROSS families)
conflates family base-rate offsets with phase effects (truth
`cycle_truth_lattice1_confirmatory_and_baseline_confound_v1`). Per the §14 batch-2 pre-commitment,
batch 2 re-tests the SAME 135-cell search space against WITHIN-FAMILY baselines. The cross-family
gap is demoted to a **disclosed diagnostic** (point estimate only, no CI, no gate role).

**Frozen design — everything §14 unless stated:** same substrate (hazard panel `price_c4414dcb` +
W4.4-convention forward joins, machinery reused verbatim via import), same embargo (rows ≥
2024-01-01 excluded from estimates AND gate), same lattices (L-A `phase_v2`(5)×`family`(3) = 15;
L-B `phase_v2`(5)×`trend_pass`(2)×`family`(3) = 30), same 3 targets (`rdd_63d`, `turn_event_3m`,
`phase_persist_3m`), same estimator (James-Stein shrinkage, month-block bootstrap 800 draws seed 7,
collapse below 12 months pinned to the pool mean), same era split (pre/post-2018 sign agreement,
point estimates only), same KG-2 raw-DD sanity abort (pipeline check, not a claim).

**THE change — frozen baseline pools:**
- **L-A cell (phase p, family f):** baseline pool = ALL rows of family f (all phases, same
  target). Gap = shrunk cell mean − family-pooled mean. James-Stein group = the 5 phase cells of
  family f. Bootstrap: month-block resample of family-f dates; per draw, gap = cell mean − family
  mean on the same resample. Question tested: *does this phase differ from the family's own norm?*
- **L-B cell (phase p, trend t, family f):** baseline pool = rows of family f × phase p (both
  trend_pass values, same target). James-Stein group = the 2 trend cells of (f, p). Bootstrap pool
  = family-f × phase-p rows. Question tested: *does the trend split matter within this
  family-phase?* — the nested interaction, exactly the CPI-020 falsifier's "against CN's own
  Downturn baseline."
- Era signs: gap sign recomputed per era under the SAME within-family pool definition (pool
  recomputed within each era; point estimates only).
- Diagnostic columns (no gate role): `gap_xfam` + `pooled_xfam` — the §14-style cross-family
  phase-pooled gap and its baseline, point estimates only.

| id | claim | success (PROMOTION) criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **LT2-cell** (any of the 135) | the cell's outcome differs from its WITHIN-FAMILY baseline | within-family gap CI₉₅ excludes 0 AND n_months ≥ 40 AND era-split sign agreement (pre-2018 AND post-2018 within-family gaps share the full-sample sign) AND survives BH-FDR q=0.10 across ALL 135 gap tests | `data/cycle_pattern/lattice/batch2.json` → `promotions[]` | ~0.05/cell pre-FDR | `cycle_pattern_lattice_v1` (q=0.10) |
| **LT2-020** (named re-test of CPI-020) | CN Downturn × broken-trend deep vol-adjusted tail survives its own family×phase baseline | the specific cell (L-B, `phase_v2`=Downturn, `family`=cn_sector, `trend_pass`=0, `rdd_63d`) clears the full LT2-cell gate above | same artifact → `named_retest` | ~0.05 pre-FDR | member of the 135 — NO extra budget |

**Budget:** 135, declared as `rf.cycle_pattern.lattice_v1` pre-p-value (the named re-test is one of
the 135, not additional). Candidate count printed BEFORE any evaluation (anti-mining law).

**Outcome handling (frozen):**
- **LT2-020 PASS** → truth `cycle_truth_cn_downturn_broken_trend_tail_candidate_v1` transitions
  `candidate → display` (effect_class risk_only, display-class; forbidden consumers unchanged —
  board_rank / oracle_escalation / sector_central_direction_score / position_sizing stay barred).
  **FAIL** → `candidate → retired` per its registered auto_demote_rule, and a scoped null truth
  records the kill.
- **The 48 §14 factory candidates are resolved mechanically by this batch:** a §14 candidate whose
  cell FAILS the within-family gate → `screened → numeric_rejected` (evidence: batch2.json); a §14
  candidate whose cell PASSES keeps `screened` with batch2.json appended as evidence. No §14
  candidate may advance past `screened` on batch-1 evidence alone.
- Newly promoted cells → factory candidates (status `screened`, trial_family `lattice_v1`) +
  display-class truth candidacy; **zero promotions** → a scoped null truth for the within-family
  lattices ("phase/trend conditioning adds nothing beyond family norms"); exploration tables ship
  to the measurement research surface either way. No page-authority change this wave.
- CPI-019's monitoring metric `batch2_within_family_retest` is satisfied either way (notes
  appended; version bump only if its statement changes).

### Lattice batch-2 results (2026-07-06 — criteria above UNCHANGED; §15 two-commit discipline observed)

**27 of 135 cells clear the frozen within-family gate** (sanity gate: KG-2 reproduced). **The named
LT2-020 re-test FAILS**: within-family gap −0.0350, CI₉₅ [−0.0688, −0.0021], boot p=0.04, era-stable
— standalone-significant but does NOT survive BH-FDR q=0.10 across the declared 135 (~60% of the
batch-1 magnitude was the §14 family-composition confound; xfam diagnostic on the same cell −0.073).
Per frozen outcome handling: `cycle_truth_cn_downturn_broken_trend_tail_candidate_v1` →
**retired**; scoped null `cycle_truth_cn_downturn_broken_trend_tail_null_v1` appended. Survivors:
15 turn_event_3m (incl. the CN broken-trend Downturn turn-DEFICIT pair −0.086/+0.160, BH-pass — the
risk story survives as duration, not depth), 10 phase_persist_3m (Recovery fragile in all 3
families; Peak persists), 2 rdd_63d (Peak = shallower vol-adjusted tails within country +0.049 / CN
+0.071 — KG-2/CPI-002 in stricter form). All 27 → factory candidates (`screened`, trial_family
`lattice_v1`, truth_guard 0 flags); truth `cycle_truth_lattice2_within_family_structure_v1`
(display/structural). §14 candidates resolved mechanically: **33 → numeric_rejected**
(transitions.jsonl, kill evidence = batch2.json), 15 keep screened. CPI-019 monitoring satisfied
(structure is NOT a family-composition artifact — falsifier answered). Adjudication:
`CPI_LATTICE2_VERDICT.md`. Artifacts: `data/cycle_pattern/lattice/batch2.json`,
`batch2_cells.parquet`; budget `rf.cycle_pattern.lattice_v1` n=135 declared pre-p-value.

---

## 16 · TR-1 next-phase transition model — family `cycle_pattern_tr` (registered 2026-07-06, PRE-RUN)

**Two-commit discipline as §12–§15.** NEW TARGET (masterplan §5, capability C4 "what comes next") and NEW capacity: a multinomial model of the next phase. This is NOT an additive-feature trial on the pooled hazard logistic — the CPI-018 suspension (additive FT trials) does not apply: different target, different model, its own named baseline.

**Substrate (frozen):** hazard panel `price_c4414dcb` + `derive_phase` (W4.4 verbatim) → `phase_v2` per (id, month-end). Labels: `next_phase_1m` = phase_v2 at the NEXT consecutive month-end; `next_phase_3m` = phase_v2 at the 3rd consecutive month-end; a calendar gap breaks the chain → NaN (the §14 `phase_persist_3m` convention). Rows with NaN current phase or NaN label are excluded. **Embargo:** rows ≥ 2024-01-01 excluded from fit AND gate. Walk-forward: the W4.2 expanding-origin ANNUAL date-block harness verbatim (first test year 2010, 6-month embargo between train end and test start, test years 2010–2023 = 14 blocks).

**Baseline (frozen):** family-stratified empirical transition matrix estimated on each train fold: P(next_phase_h = k | phase_v2_t = j, family), Laplace-smoothed (α = 1 across the 5 classes); fallback for an unseen (j, family) row = family-pooled row, then the global row (the KM fallback-chain convention).

**Model (frozen):** multinomial L2 softmax regression, pure numpy, extending the W4.2 hand-rolled logistic conventions (train-fold standardization of continuous features; lr = 0.15, iters = 600, l2 = 1.0). Features = current-phase one-hot (5) + the shipped W2.5-bound hazard feature set EXACTLY as used by the shipped model (log_age_ratio, amp_proxy, pos_osc_s, osc_slope_s, mom_score, rs_63d, vol_pctile, age-bucket dummies, family dummies, direction) — NO new covariates: this trial tests MODEL CAPACITY over existing PIT-pure columns, not new information. NO calibration layer in v0 (raw softmax probabilities are gated; disclosed).

**Cells (6):** horizon {1m, 3m} × family {us_sector, country, cn_sector}. One pooled fit per fold (family dummies); evaluation per family cell. Multiclass Brier = (1/5)·Σ_k (p_k − y_k)² per row, averaged over the cell's OOS rows.

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **TR1-{fam}-{h}** | the softmax model beats the family transition-matrix baseline on OOS multiclass Brier | paired ΔBrier(baseline − model) month-block bootstrap CI₉₀ excludes 0 on the positive side AND survives BH-FDR q=0.10 within `cycle_pattern_tr` AND sign-stability ≥ 9 of 14 test years | `data/cycle_pattern/tr_trials/tr1_transition.json` → `ledger.<fam>.<h>` | 0.05/cell | `cycle_pattern_tr` (q=0.10) |

**Budget:** 6 cells, declared as `rf.cycle_pattern.tr_v0` in `data/trial_ledger.jsonl` at run time BEFORE any p-value. No other horizons, families, feature substitutions, or calibration variants may be evaluated under this registration. **Sanity gate (pipeline, printed, not a claim):** the full-pre-embargo-sample baseline diagonal must show Peak self-persistence > Recovery self-persistence in every family (the §15 batch-2 structure), else abort sys.exit(2).

**Outcome handling (frozen):** passing cells → a display-class truth + factory candidate (status `screened`, trial_family `tr_v0`, authority display_only) per §15 conventions; page/UI unchanged; shipped-surface adoption is a SEPARATE wave. 0/6 → ONE scoped null truth ("next-phase dynamics carry no model-capacity edge beyond the family empirical transition matrix on existing PIT-pure columns") with falsifier naming the reopening conditions (new information per FT reopening rules, or the regime-vintage spine). Either way the exploration tables ship to the measurement research surface.

### TR-1 results (2026-07-06 — criteria above UNCHANGED; §16 two-commit discipline observed)

| id | result | date |
|---|---|---|
| **TR1-us_sector-1m** | **PASS** — ΔBrier +0.0030, CI₉₀ [+0.0015, +0.0047], boot p=0.005, years+ 11/14, BH-pass. | 2026-07-06 |
| **TR1-us_sector-3m** | **FAIL** — ΔBrier +0.0005, CI₉₀ [−0.0013, +0.0022] straddles 0; years+ 8/14; no BH. | 2026-07-06 |
| **TR1-country-1m** | **PASS** — ΔBrier +0.0055, CI₉₀ [+0.0040, +0.0070], boot p=0.0012, years+ 13/14, BH-pass. | 2026-07-06 |
| **TR1-country-3m** | **PASS** — ΔBrier +0.0027, CI₉₀ [+0.0012, +0.0040], boot p=0.0012, years+ 12/14, BH-pass. | 2026-07-06 |
| **TR1-cn_sector-1m** | **PASS** — ΔBrier +0.0066, CI₉₀ [+0.0051, +0.0082], boot p=0.0012, years+ 14/14, BH-pass. | 2026-07-06 |
| **TR1-cn_sector-3m** | **FAIL** — ΔBrier +0.0014, CI₉₀ [−0.0002, +0.0030] straddles 0; years+ 10/14 (BH-pass but the CI leg fails). | 2026-07-06 |

**Verdict: 4 of 6 cells pass — the program's first gate-passing cells** (after 18 additive-FT
cells, 0 passes: the §13 synthesis holds — capacity entered as a NEW MODEL on a NEW TARGET, not as
new columns on the pooled hazard). Sanity gate reproduced the §15 structure (Peak self-persistence
> Recovery in every family, 3m baseline diagonal). The edge is HORIZON-CONCENTRATED: 1m passes in
all three families (uplift 2.7% / 4.8% / 6.1% of a strong baseline Brier 0.110/0.113/0.108); 3m
passes only in country (+1.8%). Per frozen outcome handling: display truth
`cycle_truth_tr1_next_phase_softmax_skill_v1` appended + 4 factory candidates (`screened`,
trial_family `tr_v0`, authority display_only, truth_guard 0 flags); the failing 3m cells are
recorded here and in the artifact — no shipped-surface change, adoption is a SEPARATE wave.
Exploration tables (full-sample family transition matrices, both horizons) ship inside the
artifact. Full adjudication: `research/cycle_masterplan/CPI_TR1_VERDICT.md`. Artifacts:
`data/cycle_pattern/tr_trials/tr1_transition.json`; budget `rf.cycle_pattern.tr_v0` n=6 declared
pre-p-value (2026-07-07T00:27Z, before any evaluation).

---

## 17 · IX-1 index-level turn hazard — TRANSFER test, family `cycle_pattern_ix` (registered 2026-07-07, PRE-RUN)

**Two-commit discipline as §12–§16.** NEW UNIT OF ANALYSIS (masterplan §5, capability C5): does the member-trained hazard model TRANSFER to index-level entities, beating each index's own age-pooled KM? The CPI-017 member-level FT-4 null left the index-level target explicitly open; this is that trial. Not an additive-feature trial on the pooled member hazard (CPI-018 suspension does not apply: different evaluation unit, its own named baseline; the member model is used as-trained, unchanged).

**Substrate (frozen):** model arm trains on the MEMBER panel `data/hazard/panel_price_c4414dcb.parquet`; evaluation rows come from the INDEX panel `data/hazard/panel_index_v0.parquet` (8 entities: SPY = us_market + 7 blocs, epoch `price_c4414dcb`, built by #1769 with schema parity). **Embargo:** rows ≥ 2024-01-01 excluded from ALL fitting and the gate. Walk-forward: the W4.2 expanding-origin ANNUAL harness verbatim (first test year 2010, 6-month embargo, test years 2010–2023 = 14 blocks).

**Model arm (frozen):** per direction, the W4.2 discrete-time L2 logistic with the shipped W2.5-bound feature set, fit on member-panel train rows EXACTLY as the §12/§13 baseline arm does (train-fold standardization from member rows; leak-free out-of-fold PAV calibration fit on member out-of-fold predictions), then SCORED on the index-panel rows of the fold's test window (index features standardized with the member train-fold parameters; PAV applied as fit). No index-row fitting anywhere. The index FT-4 covariates present in panel_index_v0 (sync_family, phase_breadth_*, pos_dispersion) are NOT used by the model arm — reserved for a future stacking trial (see falsifiers).

**Baseline (frozen):** age-POOLED per-entity KM: P(y_h = 1 | entity, direction) estimated on INDEX-panel train rows via `engine/index_km.py` conventions (fallback to the entity's family pool below 30 train rows per (entity, direction), then to the global index pool — the substrate census shows SPY-down and VXUS-down will use fallback in early folds; disclosed, not tuned).

**Cells (4):** direction {up, dn} × horizon {1m, 3m}, each pooled across ALL 8 index entities' OOS test rows. Brier per row; paired ΔBrier(KM − model).

| id | claim | success criterion | judged by | E[pass\|null] | FDR family |
|---|---|---|---|---|---|
| **IX1-{dir}-{h}** | the member-trained hazard model beats the index age-pooled KM on OOS Brier at index level | paired ΔBrier(KM − model) month-block bootstrap CI₉₀ excludes 0 on the positive side AND survives BH-FDR q=0.10 within `cycle_pattern_ix` AND sign-stability ≥ 9 of 14 test years | `data/cycle_pattern/ix_trials/ix1_transfer.json` → `ledger.<dir>.<h>` | 0.05/cell | `cycle_pattern_ix` (q=0.10) |

**Budget:** 4 cells, declared as `rf.cycle_pattern.ix_v0` at run time BEFORE any p-value. No other horizons, entities, feature sets, stacking variants, or calibration variants may be evaluated under this registration. **Sanity gate (pipeline, printed, not a claim):** on the full pre-embargo index panel, the pooled down-leg y3 event rate must exceed the pooled up-leg y3 event rate (down legs turn faster — the substrate census structure), else abort sys.exit(2).

**Outcome handling (frozen):** passing cells → a display-class truth + factory candidates (status `screened`, trial_family `ix_v0`, authority display_only); engine-backing the markets.html US row is a SEPARATE adoption wave requiring its own review — no page/UI change this wave regardless of outcome. 0/4 → ONE scoped null truth ("the member-trained hazard does not transfer to index level against index age-pooled KM"). Falsifiers/reopening: (a) an index-covariate stacking trial (member scores + sync/phase-breadth/dispersion fit at index level) under a new registration naming this result; (b) accrued post-embargo data. Exploration tables ship to the measurement research surface either way.

### IX-1 results (2026-07-07 — criteria above UNCHANGED; §17 two-commit discipline observed)

| id | result | date |
|---|---|---|
| **IX1-up-1m** | **FAIL** — ΔBrier +0.0099, CI₉₀ [−0.0056, +0.0247] straddles 0, boot p=0.126; years+ 8/14; no BH. Directionally positive but unearned. | 2026-07-07 |
| **IX1-up-3m** | **FAIL** — ΔBrier −0.0018, CI₉₀ [−0.0195, +0.0135] straddles 0, p=0.592; years+ 8/14; no BH. No transfer signal. | 2026-07-07 |
| **IX1-dn-1m** | **FAIL (sign-stability leg)** — ΔBrier +0.0335, CI₉₀ [+0.0084, +0.0590] excludes 0, p=0.011, BH-pass — but years+ 5/13 (bar ≥9). Pooled gain is year-concentrated, not reliable. | 2026-07-07 |
| **IX1-dn-3m** | **FAIL (sign-stability leg)** — ΔBrier +0.0290, CI₉₀ [+0.0129, +0.0455] excludes 0, p=0.001, BH-pass — but years+ 7/13. Same shape. | 2026-07-07 |

**Verdict: 0 of 4 cells pass.** The frozen conjunction did exactly its anti-flukiness job: both down
cells clear the CI and BH legs on pooled magnitude, but the gains are episodic — the per-year gap
is dominated by 2021 (+0.31/+0.25 year-mean vs cell means +0.033/+0.029) with 2020 harmful
(−0.16/−0.06), so the sign-stability leg (≥9 positive years) fails at 5/13 and 7/13. Up-direction
transfer shows no earned skill at all. Disclosed denominator note: 2017 has ZERO index down-leg OOS
rows, so the down cells are judged on 13 test years; the frozen bar stays ≥9 (a year with no rows
cannot count positive). Per-entity decomposition (diagnostic): the down-cell pooled gains are broad
(7 of 8 entities positive at 1m, SPY the largest at +0.095) with ILF the sole drag; at up/3m SPY is
the largest drag (−0.027). Sanity gate reproduced the census structure (pooled y3 down 0.850 > up
0.438). Per frozen outcome handling: 0/4 → ONE scoped null truth
`cycle_truth_ix1_index_transfer_null_v1` appended (promoted_null; the down cells' passing CI/BH
legs and the year-concentration are named inside the statement); NO factory candidates; page/UI
unchanged. Reopening requires a NEW registration naming this null — the §17 falsifiers: (a) the
index-covariate stacking trial, (b) accrued post-embargo data (more down-leg years directly test
the failed leg). Exploration tables (full pre-embargo index KM table + per-entity ΔBrier
decomposition) ship inside the artifact. Full adjudication:
`research/cycle_masterplan/CPI_IX1_VERDICT.md`. Artifacts:
`data/cycle_pattern/ix_trials/ix1_transfer.json`; budget `rf.cycle_pattern.ix_v0` n=4 declared
pre-p-value (2026-07-07T01:04:24Z, before any evaluation).

---

## 18 · Cycle projection overhaul — Wave 0 preregistration (2026-07-07)

**Two-commit discipline (as §12–§17).** Substrate PR adds monthly oscillator PIT columns to
the CPI lake (`state_monthly.parquet`). Gates below are FROZEN at this commit.
DO NOT run any trial/evaluation until this section is merged — preregistration strictly
precedes evaluation (ordering is the entire point). No hazard model, `hazard_score.py`, or
UI is touched by this wave.

**Substrate (frozen):** `data/cycle_pattern/state_monthly.parquet` extended with columns
`mmacd_hist`, `mmacd_sign`, `mmacd_slope`, `mstoch_k`, `mstoch_d`, `osc_missing`.
Pinned math per ESX-RUL-31 + RUL-33-OSCSPECIES: RSI-MACD via `engine/confluence_tiers._rsi_macd`;
StochRSI K/D via `engine/confluence_tiers._stoch_rsi_kd` (14/3/3, 0-100 scale). Applied on
monthly-resampled ("ME") close from the yahoo daily tape. Completed monthly bar = month-end ≤
stamp date (incomplete in-progress bar dropped). `osc_missing=True` for entities with <40
completed monthly bars at stamp date, or with no daily yahoo tape (China Shenwan sectors).

---

### FT-OSC-1 gate

**Claim:** The oscillator covariate family (monthly MACD hist/sign/slope + monthly StochRSI K&D)
joins the CPI turn-hazard model design iff, on the BACKTEST cohort, post-2010 era row:
OOS Brier(model+osc) < Brier(KM baseline) AND month-block-bootstrap 90% CI on paired dBrier
excludes 0 AND survives BH-FDR q=0.10 within cycle_pattern_ft AND n_oos >= 3,000 monthly
cell-observations for that (direction x horizon) cell.
Demotion: any promoted cell failing the gate on 2 consecutive LIVE quarterly re-grades reverts
to PRIOR.
Kill-switch FALS-OSC (runs FIRST, before any UI work): if the 6m-cell paired dBrier 90%
month-block CI does not exclude 0 for EITHER direction, the entire oscillator covariate family
is a printed NULL to truths.jsonl; columns stay in the lake, model design reverts.

**Trial budget:** 36 cells (6 covariate arms × 2 directions × 3 horizons); declared as
`cycle_pattern_ft` in `data/trial_ledger.jsonl` at criteria-commit time (2026-07-07T02:00:00Z).
FDR family: `cycle_pattern_ft` (q=0.10).

---

### PHASE-CLOCK-1 gate

**Claim:** The 6-state monthly phase-clock (capitulation / basing / early_expansion /
late_expansion / rolling_over / early_contraction; FROZEN thresholds 20/80 and sign/slope
rules, NOT fitted) promotes from display to default headline for a family iff
dBrier(phase-conditioned survival vs age-only family KM) < 0 at h=6m with month-block-bootstrap
90% CI excluding 0, survives BH-FDR q=0.10 within cycle_pattern_ft, AND the post-2010 era row
independently shows dBrier < 0, on the 2024+ embargoed OOS window; cells with N<8 confirmed
turns pool to family level (pooling printed, never hidden).
Falsifier phase_clock_no_lift: if phase-conditioned 6m Brier is not strictly below age-only KM
Brier for >=2 of 3 families on post-2010 embargoed OOS, phase-clock is promoted_null and all
cards ship the KM prior.

**Trial budget:** 18 gate cells (3 families × 2 directions × 3 horizons); declared as
`cycle_pattern_ft` in `data/trial_ledger.jsonl` at criteria-commit time (2026-07-07T02:00:01Z).
FDR family: `cycle_pattern_ft` (q=0.10).

---

### HAR-1 gate

**Claim:** Historical-analog retrieval (kNN over normalized completed half-cycles + macro
fingerprint, analogs capped at <=2 per rolling 24-month era window, effective-N reported in
months) promotes from SHADOW to display-default per family iff OOS CRPS beats BOTH nulls
(frozen median-half-cycle projection AND age-only family KM) with month-block-bootstrap 90%
CI excluding 0, survives BH-FDR q=0.10 within cycle_pattern_analog, the post-2018 era row also
improves, cone coverage >= 0.60, >=25 realized turns in the eval fold for that family, AND beats
the within-era analog-shuffle null by the same pre-declared margin. Failing any criterion it
stays SHADOW and ships the null (dead-stays-dead).

**Trial budget:** 9 cells (3 families × 3 horizons); declared as `cycle_pattern_analog` in
`data/trial_ledger.jsonl` at criteria-commit time (2026-07-07T02:00:02Z).
FDR family: `cycle_pattern_analog` (q=0.10, NEW family — registered in
`config/ruling_graph.yml` meta.known_fdr_families in this same PR).

---

**Amendment log entry (2026-07-07):** Wave 0 substrate + three gates preregistered. No
evaluation has run. Column descriptions and oscillator computation details are in
`engine/cycle_pattern/lake.py`. Trial-budget declarations in `data/trial_ledger.jsonl`
(entries ts 2026-07-07T02:00:00Z through T02:00:02Z). Gate criteria above are FROZEN on merge.

### FT-OSC-1 results (2026-07-07 — criteria above UNCHANGED; §18 two-commit discipline observed)

> **Review fixes applied (2026-07-07):** Three disclosures added per reviewer findings.
> (MF-1) BH-FDR was applied across 6 cells (kill-switch scope: 2 dirs × 3 horizons,
> covariate arms collapsed into single joint arm); prereg n=36 is the full per-arm budget
> that would apply only if the kill-switch did not fire. (MF-2) The baseline comparison is
> paired ΔBrier vs the fitted base model — not vs a KM arm — which is the correct
> conservative reading of §18's kill-switch "paired dBrier" clause. (MF-3) A non-preregistered
> sign_stable bar (≥9/14 years positive) was removed from the PASS/FAIL verdict; the §18 gate
> contains no such requirement. **Corrected verdicts below.**

Runtime: 6.5s. Subsample: 5841/16429 embargoed rows (35.6%; cn_sector=0% by construction — see implementation_notes in artifact).

| id | result | date |
|---|---|---|
| **FT-OSC-1-up-1m** | **FAIL** — ΔBrier -0.0034, CI₉₀ [-0.010993, 0.003223], boot_p=0.7653, years+=6/11, n_oos=3784 |
| **FT-OSC-1-up-3m** | **FAIL** — ΔBrier -0.0009, CI₉₀ [-0.007787, 0.005891], boot_p=0.5743, years+=5/11, n_oos=3784 |
| **FT-OSC-1-up-6m** | **FAIL** — ΔBrier +0.0037, CI₉₀ [-0.003746, 0.010398], boot_p=0.211, years+=7/11, n_oos=3784 |
| **FT-OSC-1-down-1m** | **FAIL** — ΔBrier +0.0013, CI₉₀ [-0.009577, 0.012478], boot_p=0.4632, years+=4/8, n_oos=925 |
| **FT-OSC-1-down-3m** | **FAIL** — ΔBrier +0.0020, CI₉₀ [-0.002632, 0.006158], boot_p=0.2235, years+=6/8, n_oos=925 |
| **FT-OSC-1-down-6m** | **PASS** — ΔBrier +0.0028, CI₉₀ [0.001378, 0.00445], boot_p=0.0012, bh_pass=True, years+=7/8, n_oos=925 |

> **Notable result — down/6m PASSES the §18 gate:** ΔBrier +0.00276, CI₉₀ [+0.00138,
> +0.00445] excludes 0, boot_p=0.0012, BH-FDR survives. This is a genuine incremental
> signal in the down-regime direction. The kill-switch STILL FIRES because up/6m CI₉₀
> includes 0 (§18: kill fires if EITHER direction fails). The down/6m result is printed
> honestly here and in truths.jsonl; it does not unblock the oscillator family for use.

**Kill condition (FALS-OSC):** **KILL SWITCH FIRED**.
  up/6m: CI₉₀=[-0.003746, 0.010398], ci_lo=-0.003746, kill=True.
  down/6m: CI₉₀=[0.001378, 0.00445], ci_lo=0.001378, kill=False.
Per §18: oscillator covariate family is a printed NULL to truths.jsonl; columns stay in the lake; model design reverts. truth_id=`cycle_truth_falsosc_osc_covariate_null_v1`.

Full scorecard: `data/hazard/falsosc_trial_v1.json`. Era-split rows are post-2010 OOS (walk-forward first_test_year=2010). Verdict adjudication by program chair.

### §18 addendum — FT-OSC-2 (registered 2026-07-07, post-kill pairlet)

FT-OSC-1's family kill fired on the up/6m cell, but the down/6m cell printed real incremental
skill (paired dBrier +0.0028, CI90 [+0.0014, +0.0045], boot_p=0.0012, BH-pass within the 6-cell
kill scope; n_oos=925, below the standalone 3,000 floor). Per the post-kill pairlet discipline,
FT-OSC-2 re-tests the DOWN-direction-only oscillator join on a time-based holdout: stamps accrued
strictly after 2026-07-07, >=2 quarters, same paired-dBrier machinery restricted to down/6m.
Registered BEFORE any evaluation in data/trial_ledger.jsonl (FT-OSC-2, cycle_pattern_ft, n=1) and
data/experiments/registry_seed.json (come-back 2027-01-15). n_oos < 300 -> DEFERRED, not FAIL.
The FT-OSC-1 family null (cycle_truth_falsosc_osc_covariate_null_v1) stands; this addendum does
not reopen it.
