# S-SQ Def-4 Variant (RV-Collapse-After-Drawdown Conditioning) — PRE-REGISTRATION (phase-0 variant study)

**STATUS: DRAFT — pending Fable-tier approval. This document does not authorize execution. No study code runs, no def-4-conditioned outcome number is computed or read, before a §APPROVAL block is appended by Fable/operator and committed.**

**Study:** S-SQ def-4 variant phase-0 (within-species conditioning study). **Species:** S16 — Squeeze Release (VARIANT registration; no new species number). **Program:** Entry-Stack Expansion (ESX). **Masterplan:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md` (+ Amendment 1 RUL-13/RUL-14). **Family:** `esx_sq_def4_phase0` (m = 10, §5). **Registered:** 2026-07-10 (before any run; before any def-4-conditioned split of the W2 event tape has been computed or read). **Author:** Fable (main loop), per DT-R22 dispatch. Opus red-team review mandatory before approval.

**Revision r2, 2026-07-10 (pre-PR):** Opus red-team round 1 returned **SHIP-WITH-FIXES** — all findings applied in this revision: **F2.1 (major)** positive calibration control re-sized from a 10-slot synthetic family to the real declared BH-pool size (46 cells); **F5.1** BH pool pinned — V/I trials contribute only their verdict-bearing stop5 cell (46-cell pool declared in §5); **F2.2** "verbatim reuse" of the dt_r14 time-control module corrected to a declared research-script generalization (the module hardcodes `stop5`/`_is_ssq`); **F2.3** calibration-scope note added (within-month permutation calibrates the verdict-bearing bases); **F5.2** era sign-stability denominator pinned to the four shared program eras (pre_2012 prints, DT-R16, but sits outside the denominator). Fact/law/scope categories returned CLEAN (all cited numbers verified against W2_SSQ_REPORT, registry, engine sources).

**Provenance chain (why this study exists and why now):**
1. **DT-R5** (`research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md` §3, 2026-07-06): the proposed 5-definition volatility-void-box family was **KILLED as proposed** — defs 1–2 duplicate `engine/vol_squeeze.py`; the "inside/armed" state is the BANNED arming variant (ESX §9); def 3's volume-shelf leg was routed to price-memory (DT-R7 → PM0); the uncounted multiplicity was disqualifying on its face. **Def 4 (RV-collapse-after-drawdown conditioning) and the retest/false-break state extensions were PARKED** as candidate S-SQ variants *behind* the authorized S-SQ phase-0 (RUL-P8, post-Fable queue) — clock-first: run the authorized study before inventing variants of it.
2. **S-SQ phase-0 ran and cleared.** `research/entry_stack/W2_SSQ_REPORT.md` (family `esx_sq_phase0`, budget 12): S16 transitioned phase0 → **accruing** on 2026-07-07 (Opus review + Fable sign-off; DT-R14 recomputation all-bases NON-INFERIOR). The gate condition DT-R5 set is satisfied.
3. **DT-R22** (`research/DANNYTRADES_INDICATOR_DOCKET_ADJUDICATION_2026-07-10_BY_FABLE.md`, 2026-07-10): "Per DT-R5, void-box definition 4 (RV-collapse-after-drawdown conditioning) and retest/false-break state extensions are now ELIGIBLE for registration as S-SQ variants. Not registered in this adjudication; requires its own pre-registration with family + FDR budget declared. The no-CHIP cap (RUL-P8) remains until eq_band NC-2 ships." This document is that pre-registration for **def-4 only** (§3 for what is deliberately excluded).

**Blocking gates (ALL must clear before the study executes):**
1. Fable §APPROVAL block appended to this file and committed (no execution on DRAFT).
2. Trial-ledger `declared_budget` row logged for `esx_sq_def4_phase0` (n = 10) via `engine.trial_ledger.TrialLedger.log_declared_budget` in the approval/run PR, BEFORE any compute (RUL-5 order: registration first, ledger second, study third).
3. Both calibration controls pass (§7) — negative within-month permuted labels and positive injected effect.

**Constitution:** ESX masterplan §5 protocol + Setup Species constitution (`SETUP_SPECIES_MASTERPLAN_BY_FABLE.md` §1): PREREG before run; capped config grid (this study's grid is the §5 table, complete); any post-hoc variation = new recorded trial; BH q ≤ 0.10 per declared family; era sign-stability; episode floors; T+1 fills strictly after the signal bar; survivor-bias stamps; nulls printed with equal care as wins; the word "validated" is deliberately absent from every artifact of this family (CI-enforced).

**Inherited rulings binding on this study:**
- **ESX §9 / registry rejection rule (ARMING BAN):** an "arming" variant — acting on COILED or COMPRESSED state, or any anticipatory read of an unresolved box — is BANNED from this family. The def-4 conditioning flag is *evaluated at the confirmed FIRED_UP release bar and nowhere else*; it never creates, advances, colors, or escalates any pre-release state. H2 (aged-quiet-base arming, worst stop-outs 46–48%) is the adjacent falsified relative and this distinction must hold by construction.
- **FIRED_DOWN ban:** FIRED_DOWN onsets are BANNED from this long study (S16 registry rejection rule; direction fixture carried verbatim).
- **Unresolved boxes stay non-directional** (docket Lane 3 required control): no artifact of this study assigns direction to a COILED/COMPRESSED box. Direction exists only on the confirmed release bar.
- **DT-R14 (time-confound law) — in the PRIMARY, not as a robustness pass:** this prereg is written post-DT-R14, so calendar-time control is the primary inference (§4.2), not a recomputation appendix. Verdict clauses may be met only where both time-controlled bases agree; disagreement → DEFER with both printed.
- **RUL-P8 (no-CHIP cap):** display/context tier at most; **no chip may ship from any outcome of this family until the eq_band NC-2 lookup ships**, regardless of results. Ruling-graph entry `RUL-P8` is the recorded case law.
- **DT-R11a / display-only ceiling:** nothing here promotes to rank/size/gate; the gauntlet is a promotion gate, not a build gate; survivors earn eligibility for a separate promotion prereg only.
- **RUL-1:** no volume-confirmation confirmer enters this family; volume appears only inside the S16 release confirmation, inherited unchanged.
- **RUL-2:** R1 estimator + explicit adjacency (§4.4) — a study lacking either is invalid regardless of result.
- **RUL-3:** null-competitors are the first table of the report — the W1-NC yardstick numbers are parsed from `research/entry_stack/W1_NC_REPORT.md` at runtime, never hardcoded; NC-2 marginality applies to the gatefire form.
- **RUL-9 (one grader):** all numbers via `engine.grading` `forward_metrics` / `terminal_state`; W2 numbers are cited as context, never recomputed under a different grader.
- **RUL-12:** R1 = date-FE stratified difference; FE granularity fixed at registration (fire-date FE, sector-clustered where `data/research/sector_map.csv` is present; degradation to date-only logged, W2 precedent).
- **RUL-13 / RUL-14 (Amendment 1):** primary horizons 21d; co-primaries `zone_held_21` / `stop_vol_21` (`stop_vol_21` excluded from the BH pool); `mae63` absent from verdict tables.
- **DT-R16:** no pooled multi-decade verdict without the era table.
- **DT-R20 (naming law):** no "whale"/"Danny" vocabulary in any identifier or artifact of this study; sanctioned vocabulary: squeeze release / washout context / post-drawdown conditioning. "Void-box def-4" appears in this document only as the DT-R5/DT-R22 citation key.
- **Archetype scope (inherited from S16):** US primary; HK/CA excluded; CN only via its own future prereg — unchanged here.

---

## 0. Plain-English summary

> S16 "Squeeze Release" is our measured squeeze species: a multi-week volatility compression that ends with a direction-and-volume-confirmed breakout bar. It cleared its phase-0 bar and is accruing. The DannyTrades adjudication parked one idea worth testing on top of it: maybe the squeeze releases that matter are the ones whose quiet base formed *after a washout* — realized volatility collapsing after a real drawdown (a bottoming base), rather than a sleepy consolidation near highs (a continuation pause). That is "definition 4" of the killed void-box family, now eligible per DT-R22.
>
> This study asks exactly one pre-registered question: **among confirmed S16 release bars, do the post-drawdown ones stop out less and lift off more than the rest?** The conditioning label is the repo's existing, already-computed washout-context function reused verbatim — no new squeeze machinery, no new thresholds searched. Because "buy after a drawdown" can look good for reasons that have nothing to do with squeezes (any dip-conditioned subset rides drawdown-recovery math), the design carries an identification test: the same washout conditioning is applied to the generic gate-fire control pool, and def-4 only earns its variant registration if the improvement is *squeeze-specific* (the interaction), not generic dip-buying wearing a squeeze costume. All comparisons are made with calendar-time controls in the primary statistic — the DT-R14 lesson — so "works" can never secretly mean "2020 was a washout year." Ten trials, one FDR budget, declared before anything runs. Whatever the answer, it prints: a null closes this specific construction (the label is kept as confluence context — non-standalone ≠ worthless), a win earns at most a tracked-variant registry row and the right to a separate promotion prereg. No chip ships either way until the eq_band NC-2 lookup exists (RUL-P8), and nothing here ever acts on an unresolved box.

---

## 1. Population, panels, era

**Event population (identical to W2 S-SQ, reused verbatim):** FIRED_UP state ONSETS from `engine/vol_squeeze.assess_series` under `engine/vol_squeeze.DEFAULTS` (pctile_thresh=25, min_duration=5, release_window=3, vol_confirm=1.3), one event per onset (consecutive FIRED_UP bars dedup to the first), FIRED_DOWN banned, T+1 fill, graded via `engine.grading`. The W2 event caches (`SSQ_EVENT_CACHE`) are reused — the event tape is bit-identical to the adjudicated phase-0 tape; this study adds a conditioning column, not a new event stream.

**Panels:** deep (`data/stocks/`, 224 names, 64y, full OHLCV) + baskets (`data/baskets/ohlcv/`, 2,519 names, 2014+). **DELISTED ARM: NOT APPLICABLE** — close-only panel lacks H/L for the TTM arm of the compression gate (masterplan §1 fact row 3; W2 precedent, note carried verbatim).

**Control pool:** `data/research/gate_fires_{panel}.parquet` (same control arm as W2; same grading).

**Eras (program eras, W2 verbatim):** deep {pre_2012, 2012-2015, 2016-2019, 2020-2022, 2023-2026}; baskets {2012-2015, 2016-2019, 2020-2022, 2023-2026}. Survivor-bias stamp on every absolute rate; comparisons within-era directionally valid.

**Blindness statement (registration-critical):** the W2 event tables already carry `in_washout_ctx` as an *extra-context column* (added by `label_coiled_context`; the W2 report tested only the COILED-intersection = washout AND cohort_frac ≥ 0.40). **No washout-alone outcome split has ever been computed or read.** The only published prior reads on this tape are the W2_SSQ_REPORT tables cited in §4.4. This prereg is blind to the def-4 contrast it registers.

---

## 2. Frozen definition of def-4 (single construction; nothing searched)

**Def-4 event** = an S16 FIRED_UP onset (§1) whose release bar carries **washout context**:

- `is_def4 = (in_washout_ctx == True)` where `in_washout_ctx` is `engine/coiled.washout_ctx(daily_close)` **reused verbatim** — True iff the series capitulated ≥ 15% from its 126-bar pre-capitulation high within the trailing 91 bars; requires ≥ 308 bars of history; close-only; causal by construction (data ≤ release bar).
- Evaluated **at the release bar only** (arming ban, §Inherited). The flag conditions a confirmed event; it never anticipates one.
- Events with `in_washout_ctx is None` (insufficient history) are excluded from BOTH arms of every contrast, with counts printed.
- The RV-collapse component of "RV-collapse-after-drawdown" is not a new detector: it is the S16 compression gate itself (BBWP+HVP dual percentile < 25 via `engine/entry_primitives.bbwp_series`/`hvp_series` semantics inside `vol_squeeze`, tightened by TTM where H/L exist). Def-4 = S16 ∩ post-drawdown context. **No parallel squeeze engine is built; no engine file is edited.**

**Why this operationalization (stated before results, so it cannot be accused of being chosen after):** DT-R5's def-4 is "RV-collapse-after-drawdown conditioning." The repo already owns a frozen, wave-1-era, leak-audited drawdown-context label (`washout_ctx`), already joined to every cached S-SQ event row. Reusing it verbatim (a) satisfies the no-parallel-machinery law, (b) makes def-4 mechanically distinct from the already-tested COILED-intersection form by exactly one clause (the cohort-breadth gate is dropped — §4.4), and (c) means the study introduces zero new thresholds. The 15%/126/91/308 constants are `washout_ctx`'s own frozen constants, counted once historically, not re-tuned here.

---

## 3. What is deliberately NOT in this study

- **No arming variant** (ESX §9): no trial reads COILED/COMPRESSED state as a signal, colors it by washout, or times anything off an unresolved box. Banned from the family, permanently.
- **No FIRED_DOWN / short-side trials** (S16 rejection rule; FIRED_DOWN onsets banned from long studies).
- **No retest/false-break state extensions.** DT-R22 makes them eligible, but they are a *state-machine extension* (new engine states, new event definitions), not a conditioning column — a different construction class with its own leak surface. They remain parked-eligible and require their own prereg with pre-declared states per docket Lane 3 controls ("Retest/false-break states pre-declared; unresolved boxes remain non-directional"). This family's budget does not cover them; registering them here would repeat DT-R5's uncounted-multiplicity defect.
- **No re-run of the COILED-intersection form** (already tested in `esx_sq_phase0`; failed non-inferiority; pre-declared absence, not a hidden drop).
- **No new thresholds searched** — every constant is inherited frozen (S16 DEFAULTS; washout_ctx constants; the single named sensitivity in §5 reuses the W2-registered pctile20 event grid from the existing cache).
- **No composite, no score** — `is_def4` is never fused with anything (Signal Commons R3 shape ban).
- **No chip, no gate, no rank, no board wiring, no site artifact** (RUL-P8 no-CHIP cap until eq_band NC-2 ships; display/context ceiling; survivors earn a registry row and prereg eligibility only).
- **No CN/HK/CA extension** (S16 archetype scope carried).
- **No LLM-originated numbers anywhere** (constitution; standing law).

---

## 4. Design

### 4.1 Rulers and outcomes (W2 verbatim; RUL-13/RUL-14)

Outcomes per trial, graded by `engine.grading` (RUL-9), 21d primary horizon (horizon_role: rotational — S16's declared horizon_class; verdicts only at this pre-declared ruler): `stop5` (primary endpoint; ADVERSE — more positive = worse), `fwd_mdd_21`, `rotational_liftoff` (clean8_21), `positional_liftoff`, `dead_money`, `cushion_rot`, `zone_held_21` (RUL-14 co-primary). `stop_vol_21` (mechanical mirror) and `days_to_10` (collider) print as context, excluded from the BH pool. Sign conventions W2 verbatim: stop5 non-inferiority = CI_hi < +0.01; stop5 superiority = CI_hi < 0; beneficial-outcome superiority = CI_lo > 0.

### 4.2 Estimator and time control (exact, frozen — DT-R14 primary)

- **Point estimate:** R1 date-FE stratified difference (RUL-12) on the contrast's treatment indicator; sector clustering where `sector_map.csv` is present, date-only degradation logged (W2 precedent).
- **Primary CI/p (calendar-time-controlled):** month-block bootstrap over fire months (B = 500, months resampled with replacement) of the **within-month demeaned contrast** — the F2-corrected estimand of `scripts/research/dt_r14_time_control.py` Method 1, **generalized** (outcome and treatment columns parametrized; an interaction slot added for the I-contrast — the existing module hardcodes `stop5`/`_is_ssq`, so this is a declared research-script generalization, not verbatim reuse, and never an engine change). Co-basis: within-month demeaning OLS with HC3 sandwich SEs (Method 2, same generalization). **A verdict clause is met only where BOTH bases agree; disagreement → DEFER with both printed** (DT-R14 verdict rule, promoted from robustness pass to primary law for this post-DT-R14 registration).
- **Diagnostic (labeled NOT TIME-CONTROLLED, never verdict-feeding):** the W2-style episode-block bootstrap CI, printed for comparability with the published S16 tables.
- **Seeds frozen:** bootstrap seed 20260710; all draws logged.

### 4.3 The three contrasts

- **W — within-S16 contrast (the variant question, primary):** among S16 FIRED_UP events of a panel/form, regress each outcome on `is_def4` with the §4.2 machinery (control arm = non-def-4 S16 events). Favorable direction pre-registered: stop5 / fwd_mdd_21 / dead_money more negative; liftoff / cushion / zone_held more positive.
- **V — subset-vs-control contrast (the do-no-harm question):** the def-4 subset alone vs the gate-fire control pool — the exact W2 species-bar read run on the conditioned subset. Bar: the def-4 subset must retain S16's **stop5 non-inferiority (CI_hi < +0.01)** on both time-controlled bases. A conditioning that selects a worse-than-species subset cannot register no matter what W says.
- **I — identification interaction (the confound killer):** pooled S16 events + gate-fire control pool; model `outcome ~ is_ssq + is_washout + is_ssq×is_washout` with date FE, where `is_washout` is computed for control rows by the same verbatim `washout_ctx` at the control fire date. The generic dip-buying confound lives in the `is_washout` main effect; def-4's squeeze-specific claim lives in the **interaction**. Favorable = interaction negative on stop5. Time control per §4.2. (Identification test per the measurement-lens protocol: the observable that separates "post-drawdown squeeze releases are special" from "everything post-drawdown mean-reverts" is precisely this interaction.)

### 4.4 Adjacency (RUL-2) and null-competitors (RUL-3)

**Adjacency table (nearest falsified/tested relatives, cited before any number is read):**

| Relative | Status | Mechanical distinction of def-4 |
|---|---|---|
| H2 aged-quiet-base / calm-VCP arming | FALSIFIED (worst stop-outs 46–48%) | Def-4 conditions a *confirmed release bar*; it never anticipates inside the base. Carried from S16; arming ban §9. |
| W2 COILED-intersection form (= washout_ctx AND cohort_frac ≥ 0.40) | TESTED, failed non-inferiority (deep coef +0.0080, CI_hi +0.0450, n = 461; baskets n = 257) | Def-4 drops the cohort-breadth clause: individual washout context only, expected order-larger arm. Pre-declared reading: if def-4 clears where COILED-intersection failed, the breadth gate (and its thinness) was the failure; if def-4 also fails, post-drawdown conditioning of S16 is closed at this construction. |
| Generic dip-buying (drawdown-recovery base rates) | The confound, not a relative | Killed or confirmed by the I-test interaction (§4.3); a W-win with a null interaction verdicts as CONFOUNDED-BY-GENERIC-DRAWDOWN, not as a survivor. |
| Legacy `volatility_hole` buy read (DT intake row 3) | Null as a buy (frozen version) | Context only; different construction (no release confirmation, no conditioning). |

**Null-competitor yardstick (RUL-3):** the W1-NC table (NC-1A, NC-1B, NC-2) parsed from `research/entry_stack/W1_NC_REPORT.md` at runtime appears as the first table of the report. **NC-2 marginality** (proximity-band FE added to the stop5 model, `_run_nc2_band_fe` reused verbatim) runs for the gatefire form trials — proximity confounding remains the primary alternative explanation there; NC-2 stays DESCRIPTIVE-ONLY for standalone forms (W2 precedent, PROXY-input limitation note carried).

**Independence / co-fire:** not re-tested — form-level independence was settled for S16 in phase-0 (standalone 41.9%, gatefire N/A-STRUCTURAL, ratified by Fable). Def-4 subsets inherit their form's classification; the subset's co-fire share prints as context.

### 4.5 Floors and honesty guards

- **Arm floor:** each arm of a trial needs ≥ 150 deduped events (episode floor, species constitution) — else the trial is **INSUFFICIENT-POWER**, removed from the BH family with m decremented and the decrement logged in the preamble *before any p-value is computed* (PM0 §1 precedent). No verdict language on failed floors.
- **Month floor:** < 24 qualifying fire months for a contrast → INSUFFICIENT-POWER, same handling.
- **`in_washout_ctx is None` exclusions** counted per panel/form.
- **Sequential-testing caveat (printed in the report, binding on the adjudicator):** this family re-examines the same event tape that produced the S16 verdict, under a new declared budget. BH within `esx_sq_def4_phase0` accounts for this family's multiplicity only; the adjudication must weigh the family-sequential structure (this is the second declared family on this tape) rather than reading q-values as tape-level guarantees.

---

## 5. Trial ledger (complete family `esx_sq_def4_phase0`, m = 10)

| trial | contrast | form | panel | event cfg |
|---|---|---|---|---|
| T01 | W (within-S16) | standalone | deep | DEFAULTS |
| T02 | W | standalone | baskets | DEFAULTS |
| T03 | W | gatefire-proximity | deep | DEFAULTS |
| T04 | W | gatefire-proximity | baskets | DEFAULTS |
| T05 | V (subset vs control) | standalone | deep | DEFAULTS |
| T06 | V | standalone | baskets | DEFAULTS |
| T07 | I (interaction) | standalone | deep | DEFAULTS |
| T08 | I | standalone | baskets | DEFAULTS |
| T09 | W (named sensitivity) | standalone | deep | pctile20 (W2-registered grid, cached) |
| T10 | W (named sensitivity) | standalone | baskets | pctile20 (W2-registered grid, cached) |

**m = 10 trials; one BH pass at q ≤ 0.10 over a declared pool of 46 hypothesis cells:** the six W trials (T01–T04, T09–T10) each contribute all seven BH-eligible outcomes (§4.1 exclusions: `stop_vol_21`, `days_to_10`) = 42 cells; the V trials (T05–T06) and I trials (T07–T08) each contribute **only their verdict-bearing stop5 cell** (V: subset stop5; I: stop5 interaction) = 4 cells. Non-stop5 outcomes of V/I trials print as context, never BH'd — pooling verdict-irrelevant cells would tax the W-contrast's power for no inferential gain. Floor-driven m decrements (§4.5) shrink the pool correspondingly, logged before any p-value is computed. The pctile20 sensitivity reuses the already-cached W2 sensitivity event grid — no new event definition; it asks whether the W-contrast is an artifact of the exact compression threshold. **Deliberately absent (pre-registered absences, not post-hoc drops):** COILED-intersection form (§3); relwin2/volconf15 sensitivities (W2 measured both close to defaults on this tape — volconf15 leaves the FIRED_UP event set unchanged entirely; two sensitivity trials is the declared cap); V/I on the gatefire form (proximity confound makes the subset-vs-control read uninterpretable there; NC-2 marginality on T03/T04 covers the gatefire question). Any variation beyond this table = a new recorded trial in a fresh declared family; it never joins this one retroactively.

**Order of operations (RUL-5):** this document (registration) FIRST; `declared_budget` ledger row for `esx_sq_def4_phase0` SECOND (approval/run PR, before any compute); study THIRD. The species registry is touched only at verdict time (§6/§9) — S16's own entry, bar, and accrual are not amended by this registration.

---

## 6. Pre-registered verdict criteria (checked in order, after BH)

The def-4 variant **SURVIVES phase-0** iff ALL of:
1. **W:** ≥ 1 of T01–T04 has BH-adjusted rejection on stop5 *or* one constitution axis (dead_money, cushion_rot) in the pre-registered favorable direction, agreeing on both time-controlled bases (§4.2);
2. **V:** the def-4 subset retains stop5 non-inferiority (CI_hi < +0.01, both bases) on the panel(s) supplying clause 1;
3. **I:** the stop5 interaction is favorable with CI excluding 0 on the deep panel (both bases). A null interaction with a W-win → verdict capped at **CONFOUNDED-BY-GENERIC-DRAWDOWN**: recorded as a construction-specific null (the conditioning adds nothing squeeze-specific), not a survivor and not a kill of the S-SQ search space;
4. **Era sign-stability** ≥ 3/4 program eras on every trial counted under clause 1 — the stability denominator is the four shared program eras {2012-2015, 2016-2019, 2020-2022, 2023-2026} (W2-inherited `_check_era_sign_stability` semantics); the deep panel's pre_2012 decade prints in the era table (DT-R16) but is outside the stability denominator;
5. No floor failures (§4.5) among the trials counted.

**If it survives:** def-4 is recorded as a **tracked variant of S16** in `data/species/registry.json` (S15 `tracked_variants` precedent; accruing, display/context tier), and earns eligibility for exactly one thing more: its own promotion prereg (P2.1-style, own family and budget) — which cannot produce a chip before eq_band NC-2 ships (RUL-P8) and cannot produce a gate/rank effect without clearing the full promotion gauntlet.

**If it does not survive:** the verdict is recorded against *this construction* (S16 ∩ washout_ctx as registered). `in_washout_ctx` is retained on the event tables as a **confluence-context input** (standing law: null-as-standalone → retained as confluence input; non-standalone ≠ worthless); the kill closes this conditioning, not the search for a squeeze-context ranker. S16 base accrual is unaffected either way.

---

## 7. Calibration controls (both blocking; run before any real trial is read)

Convention and thresholds per P2.5 §7 / PM0 §7 (no study reports statistics from an uncalibrated instrument):

- **7.1 Negative — permuted labels:** instrument = T01 (deep, standalone, W-contrast). 200 draws, seed 777: `is_def4` permuted across events **within each calendar month** (events are deduped episodes on this tape, W2 precedent; full-window permutation would be the exact control-that-cannot-inject-the-confound defect DT-R14 documents). Full primary machinery rerun per draw. PASS requires: rejection rate at α = 0.05 ≤ 0.12; mean and median p within 0.5 ± 0.1; KS-uniformity p ≥ 0.05. *Calibration-scope note:* the within-month class calibrates the **verdict-bearing month-demeaned bases** (§4.2); the date-FE point estimate has finer stratification and is a location descriptor here, not the verdict instrument.
- **7.2 Positive — injected effect:** on a disposable copy, relabel 5pp of the def-4 arm's stop5=1 rows to stop5=0 (whole episodes, drawn uniformly across qualifying months, seed 4242); the primary pipeline must detect it with BH-adjusted p ≤ 0.10 inside a synthetic family of **the real declared BH-pool size (46 cells at registration; the post-floor pool size if decrements occur)** — calibrating detection at a smaller multiplicity than the study applies would overstate instrument power.

Either failure ⇒ the study is INVALID before it starts; blocker report to Fable; no real p-values are examined.

---

## 8. Context-only outputs (printed, never verdict-feeding, never BH'd)

- Def-4 share of S16 events per panel/form/era; `in_washout_ctx is None` counts; overlap of the def-4 subset with the W2 COILED-intersection subset (how much of the failed form lives inside def-4).
- Washout-depth (`dd_at_capit`) deciles of def-4 events — descriptive texture only (no depth threshold is tested; a depth-conditioned variant would be a new family).
- Control-arm washout read (the I-test main effect) — the measured size of generic dip-buying on this tape, printed either way.
- Def-4 subset species-bar table (W2 format) for the V trials.
- Volume-confirmed (mechanism-faithful) share within the def-4 arm vs the non-def-4 arm (diagnostic; the registered event set remains all FIRED_UP, W2 convention).
- Sequential-testing caveat (§4.5).

---

## 9. Report contract and execution routing

**Harness:** `scripts/research/run_ssq_def4.py` (new, research-only, never on any render path; offline on the Mac Studio host). It **imports** the W2 machinery — event builders + `SSQ_EVENT_CACHE` caches + `label_coiled_context` + form labeling from `scripts/research/run_w2_ssq.py`; NC-2 band FE from `run_w2_sur.py`; time-control machinery following `scripts/research/dt_r14_time_control.py` with the §4.2 declared generalization (parametrized outcome/treatment columns + interaction slot; research-script only); grading via `engine.grading`; squeeze semantics exclusively via `engine/vol_squeeze.py` (+ `engine/entry_primitives.bbwp_series`/`hvp_series` semantics already inside it); conditioning exclusively via `engine/coiled.washout_ctx`. **It builds no parallel squeeze engine and edits no engine file.** Control-row washout labels are computed with the same verbatim function from the same panel OHLCV stores.

**Report:** `research/entry_stack/SSQ_DEF4_REPORT.md` (W2_SSQ_REPORT format). Fails its gate if any section is absent: (1) preamble — cache paths, event counts, None-exclusions, floors + any m decrement, frozen constants restated, calibration outcomes, m = 10 declared; (2) NC yardstick first table (RUL-3, runtime-parsed); (3) per-trial tables — R1 point estimate, both time-controlled bases, episode-bootstrap diagnostic (labeled), BH q, era tables; (4) NC-2 marginality for T03/T04; (5) species-bar table for V trials; (6) I-test table with main effects + interaction; (7) verdict per §6 with explicit clause citations; (8) context appendix (§8); (9) registry/ledger row texts (applied only per §6 outcome); (10) plain-English box. No promotion language; "validated" absent; survivor-bias stamps on all absolutes.

**Delegation (masterplan §6 routing):** Sonnet (`builder`) builds and runs; Opus (`reviewer`) conformance-reviews; Fable adjudicates the verdict. Deviation from this document = new recorded trial; ambiguity = blocker report to Fable, never improvisation. **This registration does not dispatch the run** — execution awaits the §APPROVAL block and its ledger row (Blocking gates).

---

## 10. Standing prohibitions carried by every descendant of this family

No arming variant, ever (ESX §9). No FIRED_DOWN long study. No direction from unresolved boxes. No chip before eq_band NC-2 ships (RUL-P8), and none after without its own promotion prereg + Fable ruling. No gate/rank/size authority from any outcome of this family without the full promotion gauntlet. No composite/fused score containing `is_def4`. No price-level trade-instruction fields (DT-R2/DT-R7 vocabulary ban). No "whale"/"Danny" identifiers (DT-R20). LLMs may only ever de-escalate on any calibrated key that eventually ships — never originate, score, or escalate.

---

*Registered 2026-07-10 per DT-R22. Immutable after Fable approval commit; results go to the report only; this document is never edited to accommodate observed outcomes. Retest/false-break state extensions remain parked-eligible (DT-R22) and are NOT consumed by this registration.*
