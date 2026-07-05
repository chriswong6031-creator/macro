# Factor Intelligence Program — PRE-REGISTRATION LEDGER

**Program:** Factor Intelligence
**Created:** 2026-07-04
**Status:** DRAFT — pending Fable merge. Once merged, this document is locked.
**Author:** Sonnet subagent under Fable orchestration
**Cross-reference:** research/FACTOR_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §3 (frozen definitions); masterplan rulings D-1 through D-9.

---

## §0 Lock Clause

Once this document is merged, **criteria do not move.** A gate whose success threshold, judging data, or FDR family is edited after data has been seen is void — **the edit itself is the finding** (the gate failed and someone reached for the dial).

Thresholds in this document were adversarially reviewed pre-merge and are legal to hold. Post-merge edits require a new registration with a new document name; this document is then superseded and must be cited from the new one.

The pre-bound verdict vocabulary for this program: **DISPLAY-TIER** (no gate has passed), **DISPLAY-WITH-EDGE** (month-block bootstrap CI excludes zero but effect floor or min-n not met), **GATE-PASSED** (all gates met — enables de-escalation teeth or kernel input arming as specified per hypothesis below), **NULL** (printed as null on the surface the hypothesis would have occupied). No third category may be invented post hoc. The word "validated" is never used for any outcome of this program (CI-enforced house rule per scripts/check_validated_claims.py).

**Interim rule:** Any run before the full replay artifact (data/replay/standout_replay.parquet, PR #1312) exists is labeled **PRE-FDR INTERIM** and is non-binding — EXCEPT H5, whose primary substrate is the board forward ledger (held names) by design. The PRE-FDR INTERIM label is the house convention established at PR #1339; any interim cell that prints before the trial family completes is capped at verdict ACCRUE, no BH q-values printed until the family is complete.

---

## §1 Family Declaration

**Trial family name:** `factor_intelligence_v1`

**Primary tests:** exactly 5 (H1 through H5), one primary metric + one primary horizon (21d) each.

**BH-FDR:** q = 0.10 applied across the 5 primary p-values within the `factor_intelligence_v1` family.

**Descriptive outputs** (printed, not claimed): 63d/126d horizons; per-tier (T1/T2/T3) breakdowns; per-regime cuts; frequency cost tables; per-DNA-cell tables. These are published as measured; they carry no GATE-PASSED classification and do not enter the BH family.

**Trial registration compliance:** all harnesses for this family must comply with scripts/check_trial_registration.py per the R4 compliance recipe:
1. Name the harnesses: `scripts/validate_factor_h1.py`, `scripts/validate_factor_h2.py`, `scripts/validate_factor_h3.py`, `scripts/validate_factor_h4.py`, `scripts/validate_factor_h5.py` for the five primary tests; and `scripts/validate_factor_family.py` for the single pre-committed BH runner. (All match the trigger pattern.)
2. `from engine.trial_ledger import TrialLedger` must appear before any p-value computation (these harnesses do not call `deflated_sharpe`; the import is required for auditability regardless — the gate in `scripts/check_trial_registration.py` is INERT for harnesses that never call `deflated_sharpe`, but registration is still required).
3. Before p-value computation: `ledger.log_declared_budget(5, family="factor_intelligence_v1", reason="factor_intelligence_v1 5-test family")` (positional n first — the `budget=` kwarg form is WRONG; do not use it).
4. Do NOT add any Factor Intelligence harness to LEGACY_UNREGISTERED (that list is frozen 2026-07-01).
5. BH across the five primary p-values is computed ONLY by `scripts/validate_factor_family.py`; hand-computed BH is an audit finding.
This is separate from metabolism registration (`metabolism.register_hypothesis`), which is also required.

**The five primary p-values are:**
1. H1: month-block bootstrap p for Δ P(CUSHIONED∪CLEAN_LIFTOFF,21d) on factor_annotated=True vs False
2. H2: month-block bootstrap p for Δ P(CUSHIONED∪CLEAN_LIFTOFF,21d) on high_alibi_flag=True vs False (alibi_share_20d window only; 5d/60d windows are descriptive, never claimable)
3. H3: permutation p for between-cell heterogeneity of P(STOPPED,21d) as in §3 H3
4. H4: month-block bootstrap p for Δ P(STOPPED,21d) on twin_bleed_flag=True vs False
5. H5: month-block bootstrap p for Δ P(−5% within 21d) on decay_flag=True vs False

**Effect floors:** every gate's floor is max(5pp absolute, 10% of the pooled base rate of that gate's outcome, computed on the full deduped study sample, both arms combined). No arm-specific base rate is ever the anchor. At sub-50% base rates the 5pp term binds and the 10% term is inert; it remains as a guard against high-base-rate degeneracy.

**State column (21d partition):** the 21d terminal-state partition for H1–H4 IS the replay column `state_8_21` (parameterisation clean8_21: LIFTOFF_8 = +8%, horizon 21d). CUSHIONED∪CLEAN_LIFTOFF ≡ state_8_21 ∈ {CUSHIONED, CLEAN_LIFTOFF}; STOPPED ≡ state_8_21 = STOPPED. No alternative 21d partition (e.g. one built from fwd_mfe_21 with a +5% liftoff) may be substituted. `fwd_ret_21`, `fwd_mdd_21`, and `fwd_mfe_21` are used for descriptives and H5-style path checks only.

**Written ban:** No descriptive output (other windows, other horizons, kernel cells, contradiction promotions, per-class cuts) may be re-designated a primary finding; a claim on any of them requires a new pre-registration. Kernel style_regime cells and the borrowed_strength contradiction promotion are explicitly OUTSIDE this family (kernel discrimination is judged at the standing kernel-FDR checkpoint 2026-10).

**Worked example — H2 metabolism registration payload:**
```python
metabolism.register_hypothesis(
    hypothesis="H2: high_alibi_flag fires have lower P(CUSHIONED∪CLEAN_LIFTOFF,21d) than non-flagged fires",
    claim_shape="conditional_regime",
    spine_query={
        "feature": "high_alibi_flag",
        "window_d": 20,
        "source": "factor_panel"
        # no cortex_attention or reflex.cortex_attention refs
    },
    horizon_d=21,
    pre_committed_gate={
        "metric": "delta_P_cushioned_liftoff",
        "threshold": -0.05,  # effect ≤ −5pp
        "min_n": 25,          # metabolism row floor (distinct from month-block floors: ≥10 months AND ≥150 deduped fires/arm)
        "horizon_d": 21
    }
)
```
Note: `min_n=25` here is metabolism's row floor (the `_HOUSE_MIN_N` in metabolism.py). The month-block inference floors (≥10 contributing months AND ≥150 deduped fires per arm) are separate and set ex ante in this pre-registration. Both must be met for GATE-PASSED.

**Metabolism registration honesty note:** The worked payload above is illustrative, not locked. `metabolism.register_hypothesis` hard-wires `fdr_family='cortex'` and clamps `min_n` to ≥25 — the machine registration is context-only and does NOT participate in this document's 5-way BH family (no double-counting: a metabolism pass is never cited as the BH pass). At P2 registration time the `metric` string must match the evaluator's accepted set; if `delta_P_cushioned_liftoff` is not accepted, the nearest accepted metric is used and the mapping is noted in the registration — the gate numbers in this document do not move.

**Expected FDR reality, stated in advance:** with 5 primary tests at q=0.10, approximately 0.5 tests pass by chance under the global null. H3 (discrimination test) has the most power because it tests heterogeneity, not a direction; H4 (twin-bleed) has the lowest expected n in the early accrual window. Null results on H2 or H4 would be correct behavior, not failure.

---

## §2 Substrate, Clustering, and Grading

### 2.1 Primary substrate

Primary substrate: `data/replay/standout_replay.parquet` (the replay artifact from PR #1312, schema frozen there; never committed to git per R2-data-plane law). JOINed to the factor panel (`data/factordata/panel/`, v1, partitioned by month) on **(ticker, signal_date)** — the canonical join keys from the replay schema.

Row grain of the replay (verbatim from PR #1312): one row per (ticker, signal_date) candidate evaluated by the production gate. Verdict types: `fire`, `near_miss`, `rejection` (closed set).

For H1, population is `verdict_type = 'fire'` rows with `tier_cascade ∈ {T1, T2}` (T3 and T4 excluded per production gate). For H2, H3, and H4, population is all `fire` rows (any tier the production gate emits as buyable). For H5, substrate is the board forward ledger (see §2.4).

### 2.2 Inference frame (month-block bootstrap)

**Inference frame (month-block bootstrap):** The resampling unit is the calendar month. Each resample draws months with replacement from the pool of months containing at least one qualifying observation; all fires within a drawn month move together. This captures both same-date cross-sectional correlation AND the ~21-shared-forward-bars overlap of nearby fires. Resamples: ≥2000. Seed: declared in harness preamble (recommended: 20260704). House standard: see research/cycle_masterplan/PREREGISTRATION.md convention.

**Bootstrap specification (pre-committed):** CI = percentile method (one-sided gate uses the 5th or 95th percentile bound in the registered direction). One-sided p = share of resamples whose effect lies on the null side of 0. Each resample draws m months with replacement where m = the number of qualifying months (m-out-of-m block bootstrap). Ticker-week dedup is applied ONCE, before resampling, never re-applied inside resamples. A resample yielding an empty arm is recomputed on the non-empty months (drop-and-renormalize); if >5% of resamples produce an empty arm, the harness prints a fragility warning alongside the result.

The per-ticker ISO-week `episode_id` (from `scripts/replay_standout_pipeline.py` on branch `origin/ei/p0-1-replay-harness`) is retained as a de-duplication key only: before the study joins to the factor panel, the replay rows are deduplicated to one row per (ticker, ISO-week) — the row with the highest `tier_cascade` rank is retained. The episode_id is never the resampling unit.

### 2.3 Terminal state definitions (verbatim from PR #1312 / engine/grading.py)

Barriers are relative to **fill-bar close** (entry = first close strictly after signal_date, fill_offset=1, next-bar convention). Applied on dividend-adjusted total-return series throughout.

| State | Definition |
|---|---|
| `STOPPED` | close ≤ entry × 0.95 STRICTLY BEFORE close ≥ entry × 1.05 |
| `DEAD_MONEY` | never hit ±8% band AND ret_at_read < +5% at the read |
| `CUSHIONED` | hit +5% before −5%; no liftoff |
| `CLEAN_LIFTOFF` | hit the liftoff barrier before −5% |

Named parameterisations used in this family:
- `clean15_126` — positional primary: LIFTOFF_15 (+15%), horizon 126d; output column `state_15_126`
- `clean8_21` — rotational primary: LIFTOFF_8 (+8%), horizon 21d; output column `state_8_21`

Tie rule (pre-registered): stop wins on a straddle bar (conservative). Forward-metric columns used: `fwd_ret_21`, `fwd_mdd_21`, `fwd_mfe_21` at the 21d primary horizon — these are used for descriptives and H5-style path checks only; they do not substitute for `state_8_21` in H1–H4 terminal-state classification.

**Partition pin:** the 21d terminal-state partition for H1–H4 IS `state_8_21` (parameterisation clean8_21: LIFTOFF_8 = +8%, horizon 21d). CUSHIONED∪CLEAN_LIFTOFF ≡ state_8_21 ∈ {CUSHIONED, CLEAN_LIFTOFF}; STOPPED ≡ state_8_21 = STOPPED. No alternative 21d partition may be substituted.

### 2.4 H5 substrate: board forward ledger

H5 uses the US board forward ledger (`data/us_board_ledger/retro_grades.parquet`) as its primary substrate, supplemented with factor panel columns joined on (ticker, as_of).

**Known schema state (R4 reality check):** As of 2026-07-04, the ledger has only 7 distinct as_of dates (2026-06-15 to 2026-06-24) with 950 total rows; 21d horizons have zero matured rows. `tier_cascade` is NULL on all historical rows (lives only in today's signal_gate.json). `hold_days` is NULL. `signal_quality` is NULL.

**Minimal logging additions required before H5's clock starts:** the board grader must begin stamping `tier_cascade` and `hold_days` on each new board date (these fields exist in the signal_gate.json at emission time and need only be joined into the ledger write). H5's clock starts on the first board date where these fields are non-null and at least one 21d horizon has matured. This is estimated to be approximately 2026-09-01 (see §4).

**H5 episode cluster:** flag-date cohort (all names on the board with `decay_flag = True` on the same evaluation date form one cluster).

### 2.5 PIT guards

(a) `style_regime[t]` is a pure function of data ≤ t, stored once, never rewritten on re-render (an idempotence assertion enforced in the P1 test suite). (b) Every percentile/quintile breakpoint used for cohort assignment — including alibi Q80, DNA Block-B percentiles, and `alpha_z_house` quintiles — is computed on a trailing 252d cross-sectional window as of t, never panel-global. The breakpoint window for all quantile computations in this program is: trailing 252 calendar days as of signal_date.

---

## §3 The Five Hypotheses

---

### H1 — Factor-Adjusted Confluence Annotation

**Motivation:** The residual_alpha study (research/RESIDUAL_ALPHA_MOMENTUM.md) found that residual-series momentum (sector-neutral) modestly outperforms total-return momentum on modern data, and that PIT-debiased IC is weak but positive (0.0124, phase 2). If the production gate fires on raw-series oscillator crossings, a fire where the same signal pattern also appeared on the stock's residual return series (market+sector neutralized) would represent "genuine idiosyncratic motion rather than market carried." We test whether annotating such fires as residual-led identifies a subpopulation with better outcomes — an annotation, not a harder gate.

**Population:** T1/T2 fires in the replay artifact (verdict_type='fire', tier_cascade ∈ {T1, T2}).

**Feature definitions (deterministic, PIT):**

`sector_rel_cross` — binary: the same entry oscillators (RSI-MACD or StochRSI cross on the 2D/3D grid) also fired on the stock/sector-ETF ratio series within the backward-only window [t−3, t] bars of the raw fire date (a cross after the raw fire date is not knowable at t and never counts). Sector-ETF is the name's GICS sector SPDR ETF (from the `sector` replay column). Ratio cross computed from the same close-only price store; the backward-only window is pre-committed.

`resid_led` — binary: the residual-series cross date (Block-A market+sector neutralized series) is ≤ the raw cross date (the residual move preceded or coincided with the raw move). Residual series computed from Block-A betas lagged 1 day with 252d window per D-2.

**Annotation flag:** `factor_annotated` = `sector_rel_cross OR resid_led`. The two sub-flags are descriptive; only the union enters the primary test.

**Primary metric:** Δ P(CUSHIONED ∪ CLEAN_LIFTOFF at 21d) — `factor_annotated=True` vs `factor_annotated=False`. Sign direction: positive means annotated fires have better outcomes.

**Gate:** month-block bootstrap 95% CI of the risk difference (factor_annotated=True minus factor_annotated=False) excludes 0 on the positive side AND |effect| ≥ max(5pp absolute, 10% of the pooled base rate of P(CUSHIONED ∪ CLEAN_LIFTOFF), computed on the full deduped study sample, both arms combined). One-sided p from month-block bootstrap enters the `factor_intelligence_v1` BH family at q=0.10.
- Min n: ≥10 contributing months AND ≥150 deduped fires **per arm** (annotated and not-annotated separately).
- Frequency cost (share of fires annotated) must be printed alongside the p-value. A finding where 95% of fires are annotated has no selectivity value.

**Mandated ablation (DESCRIPTIVE, not in BH family):** effect size within each quintile of `align_quality` (the alignment quality score in the replay schema, range 0–100), to expose circularity with the rank key. If the entire H1 effect is concentrated in the top align_quality quintile, the annotation adds nothing that align_quality alone does not capture. This ablation is DESCRIPTIVE only — it is not a gate clause.

**Naming reconciliation note:** the replay schema emits `align_quality` and `align_tier` (not `alignment_quality`/`alignment_tier` as named in some masterplan sections). Harnesses must use the emitted names.

**What GATE-PASSED unlocks:** factor annotation becomes a logged field on every fire for the thesis-decay track (H5); it does not affect gate decisions, board ordering, or allocation. De-escalation reflex: none on day 1. Future P2 round may propose annotation-based rank weight after n matures.

**Null action:** annotation field is computed and displayed as a descriptive column; no behavioral consequence; null printed on the surface it would have occupied.

---

### H2 — Borrowed-Strength (Alibi) Veto Validity

**Motivation:** The Factor Intelligence thesis (Fable ruling D-3) defines `alibi_share_W` = Σ|contrib_W| / (Σ|contrib_W| + |resid_ret_W|) — the fraction of a name's realized return magnitude explained by factor streams rather than its own idiosyncratic residual. A high alibi share means the name's return was largely borrowed from macro/sector tailwinds, not earned. The hypothesis: fires where a name's 20d alibi share is in the top quintile (most "borrowed") have worse outcomes — the gain is explained away, not earned. This is the primary FAST-lane veto mechanism (Article 3, A3 target: existing clamp mechanisms only).

**Population:** All fires in the replay artifact (verdict_type='fire').

**Feature definition (deterministic, PIT):**

`alibi_share_20d` = `Σ|contrib_20d| / (Σ|contrib_20d| + |resid_ret_20d|)`, bounded [0,1] by construction, no clipping. From the factor panel column of the same name, value at signal_date (PIT: factor panel is keyed by (ticker, date) and uses betas estimated from the 252d window ending at t−1).

`high_alibi_flag` = `alibi_share_20d ≥ Q80` where Q80 is the trailing 252d cross-sectional 80th percentile breakpoint (PIT: computed on cross-section as of t, not panel-global). Breakpoint window: trailing 252 calendar days as of signal_date. The 5d/60d alibi_share windows are descriptive only — never claimable under this family.

**Primary metric:** Δ P(CUSHIONED ∪ CLEAN_LIFTOFF at 21d) — high_alibi_flag=True vs high_alibi_flag=False (bottom half, Q0–Q50). Sign direction: negative means high-alibi fires have worse outcomes. The gate is one-sided in the expected-harm direction.

**Gate:** month-block bootstrap 95% CI of the risk difference (high_alibi_flag=True minus False) excludes 0 on the negative side AND |effect| ≥ max(5pp absolute, 10% of the pooled base rate of P(CUSHIONED ∪ CLEAN_LIFTOFF), computed on the full deduped study sample, both arms combined). One-sided p from month-block bootstrap enters the BH family. GATE-PASSED requires BH survival + floor met.
- Min n: ≥10 contributing months AND ≥150 deduped fires per arm (high-alibi fires and not-high-alibi fires separately).
- Split-half stability check (descriptive, not blocking): the sign of the effect must hold in both the earlier half and later half of the fire-date sample. A sign flip between halves is printed as a stability warning; it does not automatically null the gate but is a mandatory narrative caveat.

**Second gate clause (pre-committed):** The alibi effect must also survive within-`alpha_z_house`-quintile stratification. Stratification variable = `alpha_z_house` (the sector-neutral residual-momentum z from `engine/residual_alpha.py`, carried as a factor-panel column at signal_date, PIT — computed from data ≤ t). Quintile breakpoints follow the §2.5 trailing-252d rule (trailing 252 calendar days as of signal_date, cross-sectional; alpha_z quintile breakpoints are computed on the same trailing-252d cross-sectional window as other quantile breakpoints in this program). Pooling = stratum-size-weighted (n-weighted) risk difference across the five quintile strata. Pass condition = the pooled one-sided month-block-bootstrap 95% CI excludes 0 on the harm side. The max(5pp, 10%) floor applies to the PRIMARY unstratified effect only, not the pooled clause. Both clauses must pass for GATE-PASSED. Note: Block-A residuals come from a richer stream set (market+sector+size+growth+rates+dollar+AI-theme) than residual_alpha.py's two-factor (market+sector-orthogonalized) residual behind alpha_z_house — related but not identical; the stratified clause is the guard against the residual_alpha.py confound.

**Prior that must be printed:** the crowding phase-0 (reports/fund-crowding-phase0.md) found that a three-leg fragility criterion (crowded + shorted + extended, all ≥ P80 simultaneously) had 21d forward excess return sign-flip between halves (H1: −0.12pp, H2: +0.32pp). The alibi share is a different construct (factor-attribution, not price/short-interest), but the phase-0 failure is the prior and must be cited in the results doc.

**What GATE-PASSED unlocks:** the alibi veto becomes a logged de-escalation candidate. GATE-PASSED does not immediately give the veto teeth. Per D-7: de-escalation teeth (Article 3, A3 targets) come only after the relevant hypothesis passes its gate AND is wired to an existing clamp mechanism (e.g., altdata/narrative _reconcile clamp). The next registration step is a shadow ledger documenting would-have-fired vetoes vs realized outcomes before the clamp is activated.

**Null action:** alibi_share_20d is displayed as an informational column; the veto fires as a logged warning only; null printed where the veto flag would have occupied a de-escalation surface.

---

### H3 — Drawdown Discrimination of DNA × Style-Regime Cells

**Motivation:** D-5 defines eight DNA classes (quality_growth, high_beta_liquidity, cyclical_value, defensive_quality, rate_duration_sensitive, china_crypto_proxy, small_spec, mixed) and D-6 defines five style_regime states (growth_momentum, quality_defense, value_cyclical, junk_rally, mixed). The hypothesis is that P(STOPPED) is heterogeneous across DNA × style_regime cells — specifically that cells where a DNA class is "in-regime" (e.g., quality_growth in quality_defense) have lower stop-out rates than cells where the DNA class is "out-of-regime." This is a discrimination claim, NOT a direction-alpha claim.

**Population:** All fires in the replay artifact with a non-null DNA class and non-null style_regime (fires where either is `mixed` are included — `mixed` is a valid cell label per D-5 and D-6).

**Feature definitions (deterministic, PIT):**

`dna_class` — from factor panel Block-B percentiles via the D-5 threshold cascade, evaluated at signal_date. Deterministic priority-ordered cascade over Block-B percentiles + Block-A betas; 'mixed' is the honest default.

`style_regime` — from the D-6 classifier at signal_date. Deterministic inputs only from existing series (factor_series long/short 20d+60d returns, etf_pulse ratios, factor_series._rotation() confirmed leader). Flip rule: state change requires 2 consecutive daily confirms; 'mixed' is default. Emitted as a world_state lobe + panel column.

**Cell formation:** the Cartesian product `dna_class × style_regime` yields up to 40 cells (8 × 5). Cells with fewer than ≥30 fires after ticker-week dedup are excluded from the primary test (too sparse); they are printed as descriptive only.

**Primary metric:** P(STOPPED at 21d) between-cell heterogeneity across cells that meet the ≥30 fires floor.

**Primary test:** statistic = Pearson χ² over the qualifying-cell × {STOPPED, not-STOPPED} contingency table, computed on deduped fire rows. The qualifying-cell set (≥30 deduped fires) is FROZEN at the observed partition and held fixed across all permutations — only cell labels are permuted; the permutation unit is the deduped fire row. Null distribution: permute cell labels across deduped fire rows WITHIN each calendar month (≥2000 permutations). p = share of permuted statistics ≥ observed. GATE-PASSED: p < q_BH (q=0.10) from the `factor_intelligence_v1` BH family. "Wilson bounds are display descriptives; the test statistic uses raw rates."

**Descriptive output (not in BH family):** full cell table of P(STOPPED) with Wilson lower bounds (Wilson CI at z=1.645 per house standard), printed for all cells regardless of cluster count. The cell table is display-tier.

**What GATE-PASSED unlocks:** cells become named coordinates in the world_state lobe (D-6 style_regime is already display-tier; H3 passage adds the DNA × regime discrimination observation to the lobe's descriptive text). No behavioral consequence on day 1. Per D-7, Article-2 surfaces (board_ordering, allocations, banner escalations) are untouched through P1-P3. The cell table is an input to the shadow kernel (D-6 "classifier is a coordinate, not a prior").

**Null action:** cell table published as display-tier with a null banner; no routing change.

---

### H4 — Twin-Bleed Veto Validity

**Motivation:** D-4 defines a twin basket (same GICS industry, size band ±1 tercile, top-12 peers by 252d residual-return correlation). The `twin_bleed_flag` marks fires where the twin basket is deteriorating at entry: twin 20d return is negative AND the twin is below its own 20d high by more than its trailing median pullback. The hypothesis: such fires have higher stop-out rates (the peer deterioration predicts contagion). This is a FAST-lane de-escalation signal — if it works, it justifies withholding a fire from the board (display-tier logging only, then de-escalation teeth after passage).

**Population:** All fires in the replay artifact where the name has a valid twin basket (≥ 8 peers, meeting the D-4 min-peers floor). Fires with fewer than 8 peers fall back to industry EW basket; if neither produces ≥ 8 peers, the row is excluded from H4 (not from the broader program).

**Feature definition (deterministic, PIT):**

`twin_bleed_flag` — binary, as defined in D-4 (deterministic formalization required by the drafter before harness build): twin basket 20d return < 0 **AND** twin basket is below its own 20d rolling high by more than its trailing median pullback depth (computed from the prior 60d of twin basket daily returns, using the rolling 20d drawdown from 20d high distribution). All twin basket inputs are PIT: the 252d residual-return correlation window ends at t−1; membership is frozen on the first trading day of the month.

Twin selection uses Block-A residual correlations; `twin_bleed` is a return-level condition on the twin basket, not the candidate's own residual — no self-conditioning.

**Primary metric:** Δ P(STOPPED at 21d) — twin_bleed_flag=True vs twin_bleed_flag=False. Sign direction: positive means flagged fires have higher stop-out rates.

**Gate:** month-block bootstrap 95% CI of the risk difference (twin_bleed_flag=True minus False) excludes 0 on the positive side AND |effect| ≥ max(5pp absolute, 10% of the pooled base rate of P(STOPPED), computed on the full deduped study sample, both arms combined).
- One-sided p from month-block bootstrap enters the BH family.
- Min n: ≥10 months AND ≥60 flagged fires (SLOW-ACCRUAL; estimated 12–18 months post replay merge).

**What GATE-PASSED unlocks:** twin_bleed_flag becomes a logged FAST-lane de-escalation candidate. Same path as H2: shadow ledger of would-have-fired vetoes before any teeth. GATE-PASSED does not immediately suppress any fire.

**Null action:** twin_bleed_flag logged as informational; null printed where the veto surface would have appeared.

---

### H5 — Thesis-Decay in Held Names

**Motivation:** The EMA8/EXIT rule is a confirmed NO-GO (research/LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md line 122; research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md line 267): mechanically-acting exit cuts are whipsaw-prone on held-out data. H5 is a **different object** — not a price rule, but a factor-attribution observation. The decay_flag fires when a name's residual return has gone negative over 20d while its raw return remained positive AND its alibi share has been rising (factor tailwinds increasing, idiosyncratic edge declining). The hypothesis: such names are more likely to give back gains over the next 21d from the flag date.

**Population:** fixed cohort of all names present on the standout/board ledger at flag-evaluation date t with ≥10 trading days on board. One observation per (ticker, flag-date); if a name sits in multiple lanes on the same date, the buy-lane row is used (priority: buy > watch > laggard). "≥10 trading days on board" = on-board tenure measured as the count of consecutive prior as_of dates on which the ticker appears in any lane — explicitly NOT `hold.days_basing` (which measures basing length, a different quantity). Outcomes = forward price path from flag-date close, computed for EVERY cohort member regardless of later board membership (no survivorship bias). 'In profit at t' (raw_ret_from_entry > 0) is a pre-registered STRATIFICATION only: the primary test runs on the full cohort regardless of profit status; the in-profit stratum is printed as a descriptive sub-analysis. A name may contribute multiple flag-dates to the sample (each date is a separate observation; clustering = flag-date cohort).

**Feature definition (deterministic, PIT):**

`decay_flag` = ALL THREE of:
1. `resid_ret_20d < 0` — the Block-A residual return over the past 20d is negative (name's idiosyncratic performance has turned negative while overall return may still be positive)
2. `raw_20d_return > 0` — the raw total return over the same 20d window is positive (the name is superficially "working")
3. `alibi_share_20d` has increased over the prior 10d (the factor-attribution share is rising — the name is increasingly relying on macro/sector tailwinds)

All three inputs are from the factor panel joined to the board ledger on (ticker, as_of). PIT: factor panel betas estimated from 252d window ending at t−1.

**Primary metric:** Δ P(hit −5% from flag-date price within 21d after flag) — decay_flag=True vs decay_flag=False. This is NOT a terminal state from the replay; it is a forward path computed from the price series starting at the flag date. Stop-out barrier = −5% from the price on the flag evaluation date (same conservative barrier as the replay grading).

**Gate:** month-block bootstrap 95% CI of the risk difference (decay_flag=True minus False) excludes 0 on the positive side AND |effect| ≥ max(5pp absolute, 10% of the pooled base rate of P(−5% within 21d), computed on the full deduped study sample, both arms combined). One-sided p from month-block bootstrap enters the BH family.
- Min n: ≥10 months of flag evaluations AND ≥40 flagged names (SLOW-ACCRUAL; clock-gated stamp; earliest gauntlet 2027-Q1).
- **H5's clock does not start until:** `tier_cascade` and `hold_days` are non-null on at least one board date AND at least one 21d horizon has matured in the ledger. Estimated start: 2026-09-01 (see §4 power analysis).

**Note on the NO-GO prior:** the EMA8 exit-rule NO-GO verdict means price-based mechanical cuts are not pursued. H5 is not a price rule — it does not propose cutting a position when the flag fires. H5 proposes only that the board surface display a "thesis quality declining" annotation, logged to the forward ledger, to be studied prospectively. If GATE-PASSED, the annotation becomes a displayed warning. De-escalation teeth (e.g., downweighting in the allocation clamp) require a further shadow ledger + registration per D-7.

**What GATE-PASSED unlocks:** thesis-decay annotation becomes a displayed field on held names (world_state lobe). No allocation consequence on day 1. Shadow ledger phase begins.

**Null action:** decay_flag computed and logged; no display annotation; null printed.

---

## §4 Power and n-Floor Realism

**Pre-run descriptive note:** The first descriptive run prints the empirical base P(CUSHIONED ∪ CLEAN_LIFTOFF) and P(STOPPED) as PRE-FDR INTERIM descriptives. Note: the ANTICIPATION_PHASE0 up-rates (0.531 base rate at short horizon, 0.606 at medium) are direction up-rates, a different quantity from stop-out rates and liftoff rates — they are not directly the gate base rates.

**Power table (pre-committed n-floors):**

| H | Expected fresh fires/month | Expected months to n-floor | SLOW-ACCRUAL? | Not-before date |
|---|---|---|---|---|
| H1 | ~15–25 T-tier fires/month | ~6–10 months per arm (≥150 deduped fires) | No (replay bottleneck) | replay artifact merge + 6 months |
| H2 | ~15–25 T-tier fires/month | ~6–10 months (≥150 deduped fires per arm) | No (replay bottleneck) | replay artifact merge + 6 months |
| H3 | ~15–25 fresh fires/month (all tiers) | ≥12 months for dense cell coverage | SLOW-ACCRUAL | replay merge + 12 months |
| H4 | ~2–5 flagged fires/month (10–20% of fires) | ~12–18 months (≥60 flagged fires) | SLOW-ACCRUAL | replay merge + 12–18 months |
| H5 | ~3–6 flagged names/month (after field stamp) | ~10–15 months (≥40 flagged names) | SLOW-ACCRUAL | 2027-Q1 |

**Minority-arm rule (pre-committed):** the min-n clock is governed by the minority arm; if either arm's share of deduped fires falls outside [10%, 90%], the hypothesis's SLOW-ACCRUAL flag flips on automatically and the share is printed. No gate number moves.

**Note:** BH run is withheld until all 5 primary p-values exist. Interim results for H1–H3 may print PRE-FDR INTERIM. The family BH run is explicitly withheld until H4 and H5 reach their respective floors, unless the family is split with a documented rationale pre-registered before data is seen.

R4 measured the following from the actual ledger and signal_gate.json as of 2026-07-04:

| Source | Observation |
|---|---|
| US board ledger (retro_grades.parquet) | 7 distinct as_of dates; 950 total rows; 5d/10d matured, 21d = 0 matured. **Not viable for any gauntlet yet.** |
| US board buy-lane | ~20–30 names/day current regime (peak was ~87/day, now ~24/day) |
| T-tier fires/month | ~3–4 names/day × 21 trading days ≈ 63–84 T-tier board appearances; ~15–25 FRESH T-tier fires/month |
| Oracle corpus | 749 episodes (357/392), 1999–2026 — the only adequately powered corpus today |

**H1 and H2 (replay-based, all fires):** The replay artifact (PR #1312, not yet merged as of 2026-07-04) does not exist in the worktree. Once it exists and covers multiple years, the episode count will be large (thousands of rows; fires are a subset). The ~15–25 fresh T-tier fires/month translates to roughly 6–10 months to reach ≥150 deduped fires per arm, so the H1/H2 floor is within 1 quarter to 2 quarters of replay artifact merge. **Not SLOW-ACCRUAL** — the replay is the bottleneck, not fire frequency.

**H3 (DNA × style_regime discrimination):** The cell-level ≥30 fires after ticker-week dedup floor per cell is the constraint. With 40 possible cells and ~20–30 fires/day, many cells will be thin (DNA=china_crypto_proxy in a growth_momentum regime is rare). Expect 8–15 cells meeting the floor within 12 months of replay availability. **SLOW-ACCRUAL** for dense cell coverage; primary test requires ≥12 contributing months AND ≥8 qualifying cells.

**H4 (twin-bleed):** twin_bleed_flag is expected to fire on a minority of fires (names without valid twins excluded; flag condition is dual-threshold). Estimated flag frequency: 10–20% of fires. With ~15–25 fresh T-tier fires/month, expect ~2–5 flagged fires/month. **Time to ≥60 flagged fires: approximately 12–18 months post replay merge.** This is the slowest hypothesis. **H4 is marked SLOW-ACCRUAL.** Interim prints are labeled PRE-FDR INTERIM throughout; the family BH run is withheld until H4 reaches its floor (or the family is explicitly split with a documented rationale registered before data is seen).

**H5 (thesis-decay, board ledger):** primary blocker is the missing `tier_cascade`/`hold_days` fields and zero matured 21d rows. Once the fields are stamped (est. 2026-07-10 if the board grader is patched promptly) and 21d horizons begin maturing (~21 trading days later, est. 2026-08-07), accrual begins. With 20–30 names/day ≥10 hold days, and decay_flag expected to fire on 10–20% of qualifying names, expect ~3–6 flagged names/month. **Time to ≥40 flagged names: approximately 10–15 months post field-stamp.** **H5 is marked SLOW-ACCRUAL.** H5 clock starts at the first board date with non-null `tier_cascade`, `hold_days`, and at least one matured 21d row. Estimated earliest honest gauntlet run for H5: **2027-Q1**.

**n-floor for an honest Factor Intelligence phase-0 gauntlet on board-level data: approximately November 2026** for H1/H2/H3 (replay-based), **mid-2027 for H4 and H5**. These dates are printed, not hidden.

---

## §5 What This Pre-Registration Does NOT Cover

- **Kernel coordinate discrimination at the 2026-10 kernel-FDR checkpoint.** That is a separate standing clock with its own registration. H3's cell table is an input (as described in D-6), but the kernel checkpoint is not pre-registered here.
- **Any international port of the factor panel.** The panel is built on US names only in v1 (Block-A uses US ETF proxies). A China/HK/Canada port requires a new registration.
- **Any Article-2 flip** (board_ordering, allocations, banner escalations). Those get their own pre-registered shadow ledgers per the EI R6 precedent (shadow forward ledger beats incumbent at episode-clustered n floor, n ≥ 25 date clusters, Wilson(z=1.645) lift > 1.25, freshness ≤ 120d).
- **A7 actions (origination of signals, scores, or escalations).** Banned unconditionally per constitution Article 1. No hypothesis here proposes any LLM-authored confidence number; claims carry calibrated Wilson bounds from graded history or no number.
- **Kernel-rank shadow ledger (P3.2 EI spec).** That is a downstream phase registered separately when H1/H2 survivors exist and the replay artifact has matured to the required cluster floor.
- **Species desk adapter (P4 EI spec).** Registered separately when P3.2 matures.

---

## §6 Gate Summary Table

| H | Feature | Primary metric | Threshold | Min n | Status |
|---|---|---|---|---|---|
| H1 | `factor_annotated` (sector_rel_cross OR resid_led) | Δ P(CUSHIONED ∪ CLEAN_LIFTOFF, 21d) | month-block bootstrap 95% CI excludes 0 (positive); effect ≥ max(5pp, 10% pooled base rate); p < q_BH | ≥10 contributing months AND ≥150 deduped fires/arm | awaits replay artifact |
| H2 | `high_alibi_flag` (alibi_share_20d ≥ Q80) | Δ P(CUSHIONED ∪ CLEAN_LIFTOFF, 21d) | month-block bootstrap 95% CI excludes 0 (negative); effect ≥ max(5pp, 10% pooled base rate); p < q_BH; + alpha_z_house-stratified clause | ≥10 contributing months AND ≥150 deduped fires/arm | awaits replay artifact |
| H3 | `dna_class × style_regime` cells | P(STOPPED, 21d) between-cell heterogeneity (Pearson χ² permutation p) | permutation p < q_BH; ≥8 qualifying cells | ≥30 fires/cell after dedup; ≥8 qualifying cells AND ≥12 contributing months | SLOW-ACCRUAL (cell + month coverage) |
| H4 | `twin_bleed_flag` | Δ P(STOPPED, 21d) | month-block bootstrap 95% CI excludes 0 (positive); effect ≥ max(5pp, 10% pooled base rate); p < q_BH | ≥10 months AND ≥60 flagged fires | SLOW-ACCRUAL (~12–18 mo) |
| H5 | `decay_flag` (thesis decay, board ledger) | Δ P(−5% within 21d of flag) | month-block bootstrap 95% CI excludes 0 (positive); effect ≥ max(5pp, 10% pooled base rate); p < q_BH | ≥10 months AND ≥40 flagged names | SLOW-ACCRUAL; clock starts at first non-null tier_cascade board date |

**BH-FDR family:** `factor_intelligence_v1`, q = 0.10, across H1–H5 primary p-values. BH run is withheld until all 5 primary p-values exist (i.e., until H4 and H5 each reach their cluster floor). Interim results for H1–H3 may print labeled PRE-FDR INTERIM.

---

*Registration locked at merge. Results docs must link back here. Any deviation between harness and this text is an audit finding, not an interpretation choice.*
