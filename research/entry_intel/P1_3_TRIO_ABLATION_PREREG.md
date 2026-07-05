# P1.3 Trio Ablation — PRE-REGISTRATION

**STATUS: DRAFT — PENDING FABLE APPROVAL (ruling R8: does not execute before replay golden test + PIT audit are clean)**
**Revision:** 2026-07-04 — blocking fix applied (P1.3-B1: dead 'omit dead-money' sentence deleted, m=30 unambiguous) + advisory fixes (P1.3-A1: F2 cross-reference added; P1.3-A2: RW bonus pinned to blend_sorted scale) + era law absorbed from P0_MEASUREMENT_MEMO.md v1.0; §5 conformance checklist reference added.

**Study:** P1.3 Trio Ablation. **Program:** Entry Intelligence (EI). **Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5/P1.3`. **Registered:** 2026-07-04 (before any run). **Author:** Sonnet subagent under Fable orchestration.

**Blocking gates (both must clear before execution):**
1. `data/replay/standout_replay.parquet` exists and the P0.1 golden test passes (ticker-by-ticker diff clean for latest date).
2. P0.2 Opus PIT audit memo is accepted by Fable.

**Constitution:** EI masterplan §3 (inherited law) → Setup Species constitution (SETUP_SPECIES_MASTERPLAN §1): PREREG before run; capped config grids; any post-hoc variation = new recorded trial; BH q≤0.10; both-halves sign stability; episode-clustered n floors; fills strictly after signal bar; survivor-bias stamps; verdicts on safety-net axes.

**Inherited rulings binding on this study:**
- R3: Trio promotion BLOCKED until re-ablation on **production-trigger fires** only. Weekly-trigger backtest evidence (bottom_signal_backtest, n=315 quality=82.1) is HYPOTHESIS, not validation. Any result here is independent of that prior.
- R4: No pre-commitment to gate-ification. Each factor tested as (a) hard gate AND (b) rank weight. Safety-net-axis deltas decide which, if either, survives.
- R7: Additive-lanes law — confirmation stacking raises quality labels UP; never filters board toward zero rows. Fire-rate impact table is a required deliverable.
- R8: This PREREG is DRAFT; no execution before golden test + PIT audit clean.

---

## 0. Plain-English summary

> The bottom backtest showed that cohort-washout proximity, RS-inflection, and low extension (anti-chase) were associated with better 60-day outcomes — but that test used a **weekly** MACD trigger, not the live **2D/3D** cascade that fires the board today. Before those three factors can change how the board ranks or gates stocks, they must be re-tested on actual production fires.
>
> This study does that re-test. For each trio factor we ask two questions: (1) "If we had hard-blocked fires that lacked this property, would outcomes have been better or worse?" and (2) "If we had merely ranked those fires lower, would outcomes have been better or worse?" The answer guides what role, if any, each factor earns in the live engine — while the fire-rate impact table ensures we don't accidentally shrink the board to near-zero rows.

---

## 1. Study scope and population

**Population (production-trigger fires only):** rows in `data/replay/standout_replay.parquet` where `verdict == 'fire'`. No near-misses. No rejections. This is the canonical production-trigger cohort mandated by R3.

**Era (primary window):** per `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` era table (mandatory citation). Primary verdict window = `2021-07-06 → last full replay date` — the sole verdict-grade era per the memo's STRICT-WINS ruling. The former PREREG placeholder "pre-2015 stamp" is superseded; the memo §1.2 makes clear the boundary is `2021-07-06`, not 2015. Any rows outside the primary window that appear in `data/replay/` carry a `survivor_bias_stamp` flag; those rows are EXCLUDED from primary verdict computation and INCLUDED in a labeled context appendix only ("PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE"). No EI verdict is rendered on survivor-stamped rows. If `P0_MEASUREMENT_MEMO.md` does not exist at execution time, the study **HALTS** and returns a blocker report — it does not self-select an era.

**§5 conformance checklist** (P0_MEASUREMENT_MEMO.md §5 — confirmed at run start):
- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` in preamble.
- [ ] Primary window = `2021-07-06 → last-full-replay-date`.
- [ ] Verdict-grade statistics on `survivor_bias = false` rows only.
- [ ] Confirms via per-row source stamp that unstamped rows are Massive-sourced.
- [ ] All pre-2021 rows stamped, routed to labeled context appendix, excluded from BH family, sign-stability, n-floors, and all GO/NO-GO decisions.
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately.
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] Returns INSUFFICIENT-POWER (honest null) if unstamped n floor not met.

**Data source (strict):** `data/replay/standout_replay.parquet` artifact ONLY. No live price queries, no re-computation of signals, no supplemental data fetches. All study features must be columns already present in the replay artifact (frozen at signal-bar time per P0.1 design contract). If a needed column is absent, that is a blocker (stop and report — do not recompute signals outside the replay).

**Required replay columns (must exist before execution; check at startup and halt if absent):**
- `ticker`, `signal_date`, `verdict`, `entry_date`, `entry_price`
- `ext_z` (anti-chase proxy: extension z-score)
- `rs_vs_sector_quartile` (or equivalent RS-vs-sector column)
- `cohort_washout_proximity` (or equivalent washout-proximity metric)
- `episode_cluster_id`
- Terminal-state partition: `terminal_state` ∈ {`stopped`, `dead_money`, `cushioned`, `clean_liftoff`}
- Forward returns at 21d and 63d: `fwd_21d`, `fwd_63d`
- `survivor_bias_stamp` (bool)

If the exact column name differs from the above (artifact may use snake_case variants), the run script resolves by name mapping logged to a preamble file before any computation. Name-mapping is fixed pre-run; no post-hoc adjustment.

**Episode-cluster n floor:** A factor verdict that is based on fewer than 25 independent episode clusters (unique `episode_cluster_id` values in the subgroup) is labeled **THIN** and cannot promote. The thin-cell label is printed in every table row. Promotion requires n_clusters ≥ 25.

---

## 2. Trio factors under test

Three factors, each tested in two design modes (§3). Features are frozen to replay-artifact columns; no re-computation.

### F1 — Cohort-washout proximity

**Mechanism:** a fire that occurs while the stock is still within the "washout window" (recently underwent a forced seller flush) is hypothesized to have better forward cushion and lower stop-out than a fire with no recent washout. The bottom backtest provided supporting mechanism evidence on a different trigger; this ablation re-tests on the production trigger.

**Operationalization (frozen):** use the replay column `cohort_washout_proximity` as-is. The column encodes proximity (e.g. days since washout event, or a binary in-window flag) per the P0.1 design contract. If the column is a continuous proximity score, the hard-gate split is at the median of the fire population (pre-specified: median split, not data-adaptive). If the column is a binary in-window flag, the split is the flag value. The exact encoding is logged from the artifact schema before any computation.

**Hard-gate definition (F1-HG):** fire must have `cohort_washout_proximity` in the favorable half (in-window / above-median proximity). Fires outside = rejected by this gate (counterfactual).

**Rank-weight definition (F1-RW):** washout proximity enters as an additive rank bonus; magnitude pre-registered as +0.10 fractional rank points normalized within the daily fire pool on the `blend_sorted` 0..1 scale. +0.10 is intentionally sized at approximately one cascade tier (≈ `tier_frac` in species constitution §1.4), so it moves a fire up by roughly one tier without silently dominating or vanishing against the scale. This magnitude is logged and confirmed against the measured `tier_frac` in the run preamble. The exact weighting formula is logged before run (no post-hoc tuning of the weight).

### F2 — RS-inflection

**Mechanism:** a fire where the stock's relative strength vs its sector has recently inflected upward (RS turning, not extended) is hypothesized to outperform a fire where RS is already extended or declining.

**Operationalization (frozen):** use the replay column `rs_vs_sector_quartile`. A RS-inflection indicator is defined as: the stock is in quartile 2 or 3 of RS vs sector (middle two quartiles — not the extended top, not the lagging bottom) at signal time. This is the "turning but not extended" hypothesis. Pre-registered: Q2 and Q3 = favorable; Q1 and Q4 = unfavorable. Note: P1.1 tests this same column monotonically (higher quartile → better outcome); P1.3 tests the non-monotone inflection recode (Q2∪Q3 favorable). Both are registered hypotheses on disjoint families — they are different questions, not a contradiction.

**Alternative operationalization (if `rs_vs_sector_quartile` is absent but a continuous RS z-score column is present):** inflection = RS z-score in [-0.5, +1.0] range at signal time (registered fallback; logged in preamble if used; not a post-hoc choice).

**Hard-gate definition (F2-HG):** fire must have RS in the favorable zone (Q2 or Q3 of sector-relative RS).

**Rank-weight definition (F2-RW):** RS-inflection bonus of +0.10 fractional rank points for fires in the favorable zone on the `blend_sorted` 0..1 scale (≈ one cascade tier; same sizing rationale as F1-RW; confirmed against measured `tier_frac` in the run preamble). Same normalization as F1-RW.

### F3 — Anti-chase (ext_z)

**Mechanism:** a fire where the stock is not already price-extended (low ext_z at signal time) is hypothesized to have lower stop-out and better forward cushion than a chase entry into an already-extended name. The extension grade is display-only today (§1 masterplan note "never touches score") — this ablation tests whether it should remain display-only or earn rank/gate power.

**Operationalization (frozen):** use the replay column `ext_z`. Hard-gate threshold: fires with `ext_z > +2.0` are classified as "extended/chase" and excluded by this gate (counterfactual). The +2.0 threshold is pre-registered; no search across thresholds.

**Rank-weight definition (F3-RW):** anti-chase bonus is a monotone decreasing function of ext_z, capped. Pre-registered formula: `bonus = max(0, (2.0 - ext_z) / 2.0) * 0.10` fractional rank points (normalized within day). Fires with ext_z ≥ 2.0 receive zero bonus. Formula is logged before run.

---

## 3. Design modes

Each factor F1/F2/F3 is tested in exactly two modes. Both modes use the same underlying population (all production-trigger fires in the primary era, excluding survivor-stamped rows).

### Mode A — Hard gate (counterfactual comparison)

**Construction:** split the production-trigger fire population into:
- **"Would-pass"** subgroup: fires that satisfy the gate condition.
- **"Would-block"** subgroup: fires that do NOT satisfy the gate condition (counterfactual blocked).

**Primary comparison:** terminal-state distribution (stop-out %, dead-money %, cushioned %, clean-liftoff %) at 21d and 63d horizons for would-pass vs would-block. Delta = would-pass rate minus would-block rate for each terminal state.

**BH-corrected test per (factor, terminal-state, horizon):** Mann-Whitney U on the underlying forward return distributions (not just state counts), with episode-cluster bootstrap for the p-value (resample at the episode-cluster level to respect within-cluster correlation). FDR correction (BH, q≤0.10) applied across the full Mode-A trial family (enumerated in §4).

**Fire-rate impact:** count rows in would-block / total fires = fraction of board eliminated by this gate. Reported as `gate_fire_rate_impact_pct`.

### Mode B — Rank weight (within-fire re-ranking)

**Construction:** within the same fire population, apply the factor's rank bonus formula. Re-rank the fire pool by (incumbent_rank_score + factor_bonus) within each calendar day. This is a within-day re-rank — no fires are removed.

**Primary comparison:** compare outcomes of fires that move UP in rank vs fires that move DOWN in rank (or stay flat). "Moved up" = rank improved by ≥ 1 position within the day. This partitions the fire population post-hoc on rank direction, which is a function of the bonus formula (fully deterministic from replay data).

**BH-corrected test:** same Mann-Whitney U + episode-cluster bootstrap, across the Mode-B trial family (§4). BH q≤0.10.

**Fire-rate impact:** zero by construction (R7 additive-lanes law — rank weight never removes fires). Reported as `gate_fire_rate_impact_pct = 0.0` in the impact table.

---

## 4. Trial ledger (capped; family `P1_3_trio_ablation`)

The following trials are pre-registered and constitute the complete family for BH correction. Any variation explored after observing data is a NEW recorded trial in `engine/trial_ledger` and triggers a separate §8 entry.

| trial_id | factor | mode | horizon | primary terminal state | BH family slot |
|---|---|---|---|---|---|
| T01 | F1 (washout) | HG | 21d | stop-out | yes |
| T02 | F1 (washout) | HG | 21d | dead-money | yes |
| T03 | F1 (washout) | HG | 21d | cushioned | yes |
| T04 | F1 (washout) | HG | 63d | stop-out | yes |
| T05 | F1 (washout) | HG | 63d | dead-money | yes |
| T06 | F1 (washout) | HG | 63d | cushioned | yes |
| T07 | F1 (washout) | RW | 21d | stop-out | yes |
| T08 | F1 (washout) | RW | 21d | cushioned | yes |
| T09 | F1 (washout) | RW | 63d | stop-out | yes |
| T10 | F1 (washout) | RW | 63d | cushioned | yes |
| T11 | F2 (RS-inflect) | HG | 21d | stop-out | yes |
| T12 | F2 (RS-inflect) | HG | 21d | dead-money | yes |
| T13 | F2 (RS-inflect) | HG | 21d | cushioned | yes |
| T14 | F2 (RS-inflect) | HG | 63d | stop-out | yes |
| T15 | F2 (RS-inflect) | HG | 63d | dead-money | yes |
| T16 | F2 (RS-inflect) | HG | 63d | cushioned | yes |
| T17 | F2 (RS-inflect) | RW | 21d | stop-out | yes |
| T18 | F2 (RS-inflect) | RW | 21d | cushioned | yes |
| T19 | F2 (RS-inflect) | RW | 63d | stop-out | yes |
| T20 | F2 (RS-inflect) | RW | 63d | cushioned | yes |
| T21 | F3 (anti-chase) | HG | 21d | stop-out | yes |
| T22 | F3 (anti-chase) | HG | 21d | dead-money | yes |
| T23 | F3 (anti-chase) | HG | 21d | cushioned | yes |
| T24 | F3 (anti-chase) | HG | 63d | stop-out | yes |
| T25 | F3 (anti-chase) | HG | 63d | dead-money | yes |
| T26 | F3 (anti-chase) | HG | 63d | cushioned | yes |
| T27 | F3 (anti-chase) | RW | 21d | stop-out | yes |
| T28 | F3 (anti-chase) | RW | 21d | cushioned | yes |
| T29 | F3 (anti-chase) | RW | 63d | stop-out | yes |
| T30 | F3 (anti-chase) | RW | 63d | cushioned | yes |

**m = 30 pre-registered trials.** BH correction applied across all 30 simultaneously. `deflated_sharpe` is not the primary metric here (this is a classification study on terminal-state deltas, not a return-stream study); DSR does not apply. The BH q≤0.10 family correction IS the multiplicity control.

**Design note (dead-money and Mode-B):** Mode-B (rank weight) does not remove fires; the dead-money rate across the full fire pool is therefore unaffected by re-ranking. Dead-money delta is a hard-gate (Mode-A) metric only. The trial table above already reflects this: Mode-B rows (T07–T10, T17–T20, T27–T30) carry only stop-out and cushioned terminal states, as shown. The family count m = 30 is complete as enumerated in the table above.

---

## 5. Primary verdict statistics (exact, frozen)

### 5.1 Terminal-state delta

For each trial Txx:
- **Statistic:** delta in terminal-state incidence rate (fraction of fires) between the two groups, expressed in percentage points (pp).
- **Positive direction:** favorable for the hypothesis = would-pass/rank-up has LOWER stop-out, LOWER dead-money, and HIGHER cushioned + clean-liftoff.
- **Test:** Mann-Whitney U on the underlying 21d or 63d forward return distributions (continuous, not the discretized state). This avoids 2×2 chi-squared power problems on thin cells.
- **Episode-cluster bootstrap:** resample episode_cluster_id with replacement, N=5,000 bootstrap resamples. The bootstrap p-value is the primary p-value fed into BH. Parametric p-value printed as a secondary diagnostic.
- **Effect size:** rank-biserial correlation r (from Mann-Whitney U) printed alongside each p-value.
- **BH correction:** applied at q=0.10 across all 30 trials simultaneously. A trial "survives BH" if its BH-adjusted p ≤ 0.10.

### 5.2 Both-halves sign stability

The primary era is split at its midpoint by date. Each trial Txx is computed independently on each half. Sign stability = the sign of the terminal-state delta (favorable vs unfavorable direction) is the same in both halves. A trial that survives BH but fails sign stability is labeled UNSTABLE and cannot promote.

### 5.3 Fire-rate impact table (mandatory, R7 additive-lanes law)

A required deliverable independent of the BH outcome. For each factor, Mode-A (hard gate) reports:
- `n_fires_total`: total production-trigger fires in primary era.
- `n_would_block`: fires that would be eliminated by the gate.
- `gate_fire_rate_impact_pct`: n_would_block / n_fires_total as a percentage.
- `n_clusters_would_block`: episode clusters in the would-block group (thin-cell check).

For Mode-B (rank weight), `gate_fire_rate_impact_pct = 0.0` by construction.

The table is printed regardless of study outcome. Even if all factors fail BH, the fire-rate table is a standalone deliverable.

---

## 6. Pre-registered kill and ship criteria (checked in order)

These criteria are applied AFTER BH correction. No factor-level decision is made before looking at all 30 BH-adjusted p-values.

### 6.1 What kills a factor

A factor (F1, F2, or F3) is marked **NO-GO** if BOTH of the following hold:
- In Mode-A (hard gate): the BH-adjusted p-value for stop-out delta at BOTH 21d and 63d exceeds 0.10 (i.e. no significant stop-out reduction survives BH), AND
- In Mode-B (rank weight): the BH-adjusted p-value for cushioned delta at BOTH 21d and 63d exceeds 0.10 (i.e. no significant cushion improvement survives BH).

A NO-GO factor does not promote in any form. It is recorded in §8 of the masterplan with the verdict. Display-only status (current status of all three factors) remains unchanged.

### 6.2 What kills the gate design specifically

A factor's Mode-A (hard gate) design is marked **GATE-REJECT** if the gate fire-rate impact exceeds 40% (i.e. the gate would eliminate more than 40% of board rows) AND the BH-adjusted p for stop-out delta at 21d does not survive (q > 0.10). A gate that kills 40%+ of board flow must earn its bar; if it cannot clear BH at 21d it does not proceed as a gate. The R7 additive-lanes law demands this check.

A factor can be GATE-REJECT but still proceed as a rank weight if Mode-B survives BH.

### 6.3 What ships

A factor (F1, F2, or F3) earns the right to proceed to P2.1 promotion if:
- At least one of Mode-A or Mode-B has a BH-adjusted p ≤ 0.10 for the pre-specified favorable direction in stop-out or cushioned at 21d or 63d, AND
- Both-halves sign stability holds for the surviving trial(s), AND
- The episode-cluster n floor ≥ 25 in the relevant subgroup (not THIN).

**Ship design is the mode (HG or RW) that survives.** If both modes survive, BOTH are forwarded to P2.1 and Fable decides which design to promote first (shadow-first per R6). If only Mode-B (rank weight) survives, the factor ships as rank weight only — no gate. If only Mode-A (hard gate) survives AND gate fire-rate impact < 40%, the factor ships as gate; if fire-rate impact ≥ 40%, Fable is flagged before any promotion.

### 6.4 Whole-study kill

If all three factors return NO-GO, the trio ablation is CLOSED (registry records all three as `phase0: falsified`). The program then proceeds without trio confirmation in the rank/gate stack; the factors remain display-only indefinitely (or until a new PREREG re-approaches from a different angle). This outcome does not block other P1 studies.

---

## 7. Context-only outputs (not verdict-grade)

The following outputs are computed and printed in the report but do NOT feed the GO/NO-GO verdict and are NOT FDR-corrected against the primary family:

- **Clean-liftoff delta** (by factor, by mode, by horizon): printed as a descriptive complement to the stop-out/cushioned deltas. Not a hypothesis test.
- **MAE at 21d by gate subgroup**: median MAE for would-pass vs would-block per factor. Printed as risk context.
- **Sector breakdown of would-block subgroup (Mode-A)**: frequency of would-block fires by sector. Printed to check for sector concentration bias (e.g. if the gate disproportionately blocks one sector).
- **Pre-2021 survivor-stamped rows**: computed separately and printed in a labeled context appendix ("PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE"). Never mixed with primary verdicts.
- **Weekly-trigger bottom backtest comparison (R3 context):** the prior n=315 result (quality=82.1, 64.1% durable) is printed in a context box with the explicit label "HYPOTHESIS — DIFFERENT TRIGGER — NOT VALIDATION." The direction of any agreement or disagreement with the current production-trigger result is noted without being used as confirmatory evidence.

---

## 8. Data and era handling

**Data source (strict):** `data/replay/standout_replay.parquet`. No other sources. The replay artifact was produced by `scripts/replay_standout_pipeline.py` using the production code path (P0.1 design contract). The script was run on the canonical `data/` store, not a worktree checkout.

**Era handling clause:** Primary window = `2021-07-06 → last-full-replay-date` per `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)`. Rows with `survivor_bias_stamp == True` are excluded from all primary verdict computations. Those rows appear in a context appendix labeled "PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE." The context appendix prints the terminal-state distribution for survivor-stamped rows alongside the primary-era table, labeled clearly. No BH correction applied to context-appendix rows; no GO/NO-GO language used for them.

**Feature freeze (PIT honesty):** all study features (ext_z, rs_vs_sector_quartile, cohort_washout_proximity) are the values frozen at signal time in the replay artifact. The replay harness enforced point-in-time slicing per P0.1 contract. This study does not re-compute any feature; it reads frozen values only. Any misalignment between the replay column and the live production value at the same signal date is a P0.1 artifact defect, not a P1.3 problem — if detected during startup checks, halt and report to Fable.

**Forward-return construction:** entry price = `entry_price` column (first close strictly after signal date per P0.1 fill rule). Forward return at horizon h = `fwd_{h}d` column from the replay artifact. No re-computation. A named match between `entry_date` and the declared fill rule is logged in the preamble.

---

## 9. Report contract

Report file: `research/entry_intel/P1_3_TRIO_ABLATION_REPORT.md`

Required sections (report fails gate if any are absent):
1. **Preamble:** exact artifact path + hash, column-name mapping log, era table citation (P0_MEASUREMENT_MEMO.md version + date), n fires total, n episode clusters total, survivor-stamped row count.
2. **Per-factor results table (Modes A and B):** terminal-state deltas at 21d/63d, raw p, BH-adjusted p, effect size r, sign-stability flag, n_clusters, THIN flag if applicable.
3. **Fire-rate impact table** (all three factors, Mode-A and Mode-B — mandatory regardless of BH outcome).
4. **Both-halves sign stability table.**
5. **Verdict per factor** (NO-GO / GATE-REJECT + ship-as-RW / ships-as-HG / ships-as-HG+RW) with explicit BH threshold citation.
6. **Whole-study verdict** (trio closed / partial survivors forwarded to P2.1).
7. **Context appendix:** survivor-stamped rows; weekly-trigger bottom backtest comparison box (labeled HYPOTHESIS).
8. **Leak audit section:** fill rule confirmation (next-bar, not same-bar), feature freeze confirmation (signal-time PIT), era boundary confirmation, sector-map non-PIT disclosure if applicable, any survivor-bias bound re-statement.
9. **§8 entry row** for each factor (registry update, `validation_status` transition).
10. **Plain-English box** (one paragraph; required by §3 plain-language law).

---

## 10. Downstream routing

**If any factor ships:**
- Forward to P2.1 (species promotion ladder). The replay evidence is the same evidence class as the pre-validated seeding precedent (production-trigger fires, PIT era, BH-corrected). Ships shadow-first per R6.
- Species registry: new entry per factor with `validation_status: phase0_passed` and the trial evidence attached.
- P2.1 PREREG is a separate registered document; this PREREG does not authorize any board wiring.

**If all factors NO-GO:**
- Registry: all three marked `validation_status: falsified`.
- §8 masterplan entry: trio ablation closed; trio factors remain display-only; no rank/gate integration authorized.
- No impact on P1.1, P1.2, P1.4, P1.5 (those are independent study families).

---

*Registered 2026-07-04. Immutable after Fable approval commit. Results added to REPORT file only; this document is never edited to accommodate observed outcomes (species README convention).*
