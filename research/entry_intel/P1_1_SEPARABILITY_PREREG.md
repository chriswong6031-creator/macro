# P1.1 — Separability Study — PRE-REGISTRATION

**Program:** Entry Intelligence (research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5/P1.1)
**Study ID:** P1_1_SEPARABILITY
**Registered:** 2026-07-04 — BEFORE any run
**Author:** Sonnet subagent under Fable orchestration
**STATUS: APPROVED — Fable 2026-07-05 (see §APPROVAL at end; original draft-gate text follows) (ruling R8: does not execute before replay golden test + PIT audit are clean)**
**Revision:** 2026-07-04 — red-team fixes applied (P1.1-A1, P1.1-A2) + era law absorbed from P0_MEASUREMENT_MEMO.md v1.0; §5 conformance checklist reference added.

---

> **In plain English:** We take every entry-funnel event that the replay captures — fires, near-misses, and rejections alike — and ask whether any of the pre-recorded fields (extension grade, alignment quality, weekly phase, RS quartile, etc.) actually correlates with outcomes 21 and 63 days later. Specifically, does a high value on a given feature predict a stock going up at least a little without stopping out first (our "cushioned or clean-liftoff" definition of a good outcome)? We test each feature statistically, correct for testing multiple features at once, check that the finding holds in both halves of the data, and hand the survivors to the re-rank design team. Any feature that fails is not promoted.

---

## 1. Purpose and scope

This study measures whether the frozen set of replay-logged features **separate good outcomes from bad ones** in the pre-gate pool. The output is a ranked list of feature survivors that feed Phase 3 (P3.2 kernel-rank design) as re-rank candidates.

Scope is strictly **associative** — no causal claim, no promotion decision. Promotion of any survivor into a gate or rank weight requires its own PREREG (P1.2 for gate P&L; P2.1 for the trio ladder).

## 2. Population under study (Ruling R1 — mandatory)

**Pre-gate pool = every (ticker, date) row logged by the production replay with verdict ∈ {FIRE, NEAR_MISS, REJECTION}.**

Ruling R1 (masterplan §2): survivorship restriction of range is lethal for this question. A field used in the gate shows ZERO within-gate separability even when it works. The shipped board (survivors of the gate) is EXCLUDED as the primary dataset. It may appear only in a labeled context appendix.

Data source: `data/replay/standout_replay.parquet` (canonical checkout per ruling R9; never committed to git). The replay is the ONLY permitted data source for feature values and outcome grades. No other file may supply study-era feature observations.

## 3. Era handling

**Memo citation (mandatory):** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)`. Every run must print this citation in the preamble per §5 conformance checklist.

**Primary window:** `2021-07-06 → last-full-replay-date` — the sole verdict-grade era per the P0 Measurement Memo §1 era table (STRICT-WINS ruling; §1.2 explicitly rejects the former PREREG placeholder "2015-present"). Rows with `signal_date ≥ 2021-07-06` whose price series is Massive-sourced and whose full grading horizon falls within the replay window are UNSTAMPED (`survivor_bias = false`) and form the primary verdict population.

- UNSTAMPED rows carry full verdict weight; all BH tests, sign-stability checks, and effective-N counts run exclusively on these rows.
- Survivor-stamped rows (`survivor_bias = true`) — all rows with `signal_date < 2021-07-06` or any row whose price source cannot be confirmed as Massive-or-equivalent — are placed in a **context appendix only**, labelled **"PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE."** They are printed for transparency but excluded from every primary statistic and from BH family correction.
- The era boundary (`2021-07-06`) is taken verbatim from the measurement memo — it is NOT re-estimated here. Any re-estimation of the era boundary is a new recorded trial.
- If `P0_MEASUREMENT_MEMO.md` does not exist at execution time, this study **HALTS** and returns a blocker report. It does not self-select an era.
- The run preamble prints: memo version+date, exact primary window, count of unstamped rows, count of stamped rows excluded, and count of `horizon_censored` rows excluded per horizon.
- If the unstamped episode-clustered n floor < 50, the study returns **INSUFFICIENT-POWER** rather than borrowing pre-2021 rows.

**§5 conformance checklist** (P0_MEASUREMENT_MEMO.md §5 — each item confirmed at run start):
- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` in preamble.
- [ ] Primary window = `2021-07-06 → last-full-replay-date`.
- [ ] Verdict-grade statistics on `survivor_bias = false` rows only.
- [ ] Confirms via per-row source stamp that unstamped rows are Massive-sourced.
- [ ] All pre-2021 rows stamped, routed to labeled context appendix, excluded from BH family, sign-stability, n-floors, and GO/NO-GO decisions.
- [ ] `horizon_censored` rows excluded per-horizon, tracked separately.
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] Returns INSUFFICIENT-POWER (honest null) if unstamped n floor not met.

## 4. Outcome definitions (frozen)

Two binary outcome labels, computed from the replay grading columns (terminal-state partition at the declared horizons):

| Label | Definition | Horizon classes |
|---|---|---|
| `good_21d` | terminal_state ∈ {cushioned, clean_liftoff} at the 21-day horizon | 21d |
| `good_63d` | terminal_state ∈ {cushioned, clean_liftoff} at the 63-day horizon | 63d |

- **Cushioned:** price at horizon ≥ entry close AND never triggered the stop-out rule within the horizon (MAE < stop threshold as defined in the replay grader).
- **Clean liftoff:** price at horizon ≥ entry close + species-constitution MFE threshold AND no stop-out.
- Rows where the outcome is **unresolvable** (delisted mid-horizon with ambiguous final price, or horizon not yet elapsed) are excluded from that horizon's family and counted in a coverage table printed in the report. Exclusion is applied before any statistical test — it is not a modeling decision.

Both `good_21d` and `good_63d` are tested. They share one BH family (§6 below). The 63d horizon is the longer-lookback counterpart; a feature that survives only at 63d but not 21d is noted and flagged for the P3 team as longer-horizon-only evidence.

## 5. Frozen feature list (trial grid — capped)

The feature list is **frozen to the columns logged by the replay harness (P0.1 design contract, §4)**. No feature outside this list may be tested within this study. Any additional feature constitutes a new recorded trial and requires its own PREREG entry before running.

| # | Feature column | Type | Direction hypothesis |
|---|---|---|---|
| 1 | `ext_z` | continuous | lower → better (less extended = lower stop-out risk) |
| 2 | `ext_atr` | continuous | lower → better |
| 3 | `knife_z` | continuous | lower → better (less knife-catch signal) |
| 4 | `alignment_quality` | continuous | higher → better (stronger multi-timeframe alignment) |
| 5 | `alignment_tier` | ordinal (PRIME=2, ARMED=1, APPROACHING=0) | higher → better |
| 6 | `weekly_phase` | ordinal/categorical (0–7 or labeled buckets) | hypothesis: earlier phase → better; treated as ordinal rank |
| 7 | `dist_52wh` | continuous | lower → better (closer to 52-week high = less overhead supply) |
| 8 | `rs_vs_sector_quartile` | ordinal (1–4) | higher → better (stronger relative strength within sector) |
| 9 | `side_200dma` | binary (above=1, below=0) | above → better |
| 10 | `adv_dollar_21d` | continuous | direction not pre-committed (liquidity as hygiene check only per R10; tested for information, verdict never promotes to rank) |
| 11 | `cohort_washout_proximity` | continuous (where non-null) | lower → better (closer to washout = better entry context) |

**m = 11 features × 2 horizons = 22 tests in the BH family.**

Feature #10 (`adv_dollar_21d`) is tested for completeness of the census. Per ruling R10 (masterplan §2), any association it shows is hygiene/display information only — it CANNOT be promoted to rank power without its own independent PREREG. Its BH-adjusted result is printed but its verdict is labeled HYGIENE-ONLY regardless of outcome.

Feature #11 (`cohort_washout_proximity`) has partial coverage (computed only where the washout algorithm can define proximity). Rows with null values for this feature are excluded from its sub-family only; the remaining features are tested on their own non-null coverage sets. Coverage counts are printed per feature.

**No other column from the replay parquet is tested.** If the replay harness ships additional columns not listed above, they are available for a subsequent registered trial with a new PREREG.

## 6. Statistics and thresholds (exact, frozen)

### 6.1 Per-feature association statistics

For each feature × outcome horizon pair, compute:

1. **Spearman rank correlation** (ρ) of the feature vs the binary outcome label (0/1). Point estimate + two-sided p-value. Used for all continuous and ordinal features.

2. **AUC (AUROC)** of the feature as a single predictor of the binary outcome label. Point estimate + permutation p-value (n_permutations = 10,000; seed = 42, frozen). AUC > 0.5 in the pre-registered direction is the expected signal; AUC ≈ 0.5 = no information.

Both statistics are computed for all 11 features. The primary test statistic for BH correction is the **Spearman p-value** (one-tailed in the pre-registered direction per feature). AUC is a confirmatory statistic printed alongside but NOT used for BH correction — it is supplemental evidence. A feature whose observed association is significant in the direction OPPOSITE its §5 hypothesis is printed with an INVERTED-SIGN flag and referred to Fable; the one-tailed direction is never re-chosen post-hoc.

For `side_200dma` (binary feature), the Spearman is equivalent to a point-biserial correlation; AUC is the C-statistic. Both computed identically.

For `alignment_tier` (ordinal), treated as numeric rank (0/1/2) for Spearman. For `weekly_phase` (categorical), if labeled as non-ordinal buckets, a Kruskal–Wallis H-test replaces the Spearman for that feature; this substitution is pre-registered here and does not constitute an additional trial.

### 6.2 Episode clustering (mandatory, inherited from species constitution §3)

Observations are NOT independent (same-date cross-section; rolling same-name events). Episode clusters are defined as groups of rows sharing the same calendar week (Monday–Sunday of signal date). All p-values are computed with **cluster-robust standard errors at the week-cluster level** OR equivalently with a block bootstrap (block = week cluster, n_boot = 5,000, seed = 42). The specific implementation chosen (cluster-robust SE vs block bootstrap) is declared at run time and applied uniformly to all 22 tests. This is not an additional degree of freedom — both are pre-registered as equivalent implementations of the same clustering intent.

**Effective-N = number of distinct week clusters in the primary window, not row count.** Effective-N is printed next to every statistic.

### 6.3 Benjamini–Hochberg family correction

**One BH family** across all 22 tests (11 features × 2 horizons). Family-wise FDR q ≤ 0.10. The 22 unadjusted p-values are sorted ascending; each is compared to its BH threshold (rank/22) × 0.10. Feature × horizon pairs with BH-adjusted q ≤ 0.10 are designated **survivors**. All 22 results are printed; passing/failing status is shown for each.

Feature #10 (`adv_dollar_21d`) participates in the BH family for multiplicity bookkeeping, but its pass/fail verdict is overridden to HYGIENE-ONLY (R10) regardless of the BH outcome.

### 6.4 Both-halves sign stability (mandatory)

For each BH survivor: split the primary-window rows chronologically at the midpoint (first half = earlier dates, second half = later dates). Compute the Spearman ρ in each half independently. **Sign stability requirement:** the point estimate of ρ must be in the same direction (same sign) in both halves. A survivor that flips sign in either half is reclassified as UNSTABLE — it is noted in the output table, excluded from the survivor list passed to P3, and flagged for investigation (e.g., regime conditioning, era break).

For `weekly_phase` when the Kruskal–Wallis branch fires (§6.1): sign stability is evaluated as the sign of the rank-mean difference between the best-performing bucket and the worst-performing bucket, where the bucket ordering is fixed at registration (ascending phase order, pre-registered). This proxy for directionality must agree in sign in both halves; a flip disqualifies `weekly_phase` from the survivor list in the same way as a Spearman sign flip.

Both-halves stability is a binary gate, not a graded metric. No further tuning of the split point is permitted.

## 7. Output contract (feeds P3 re-rank candidates)

The study produces one structured output table:

| Feature | Direction | ρ (full) | AUC (full) | BH-adj q (21d) | BH-adj q (63d) | Sign-stable? | Verdict |
|---|---|---|---|---|---|---|---|

**Verdict values:**
- `SURVIVOR`: BH q ≤ 0.10 in at least one horizon AND sign-stable in both halves.
- `HYGIENE-ONLY`: applies to `adv_dollar_21d` regardless of BH outcome (R10).
- `UNSTABLE`: BH passes but sign flips — excluded from P3.
- `NO-SIGNAL`: BH q > 0.10 at both horizons.

The ranked survivor list (by Spearman ρ magnitude, descending, primary horizon 21d first) is the direct input to the P3.2 kernel-rank design. P3.2 is separately PREREG'd; this study hands off the list only.

## 8. What result kills vs ships

| Condition | Consequence |
|---|---|
| Zero features survive BH at q ≤ 0.10 in either horizon | Study verdict = NO-SURVIVORS. Report is published. P3.2 kernel re-rank receives a null list; hand-formula continues as the incumbent. Status logged in §9 of the masterplan. |
| ≥ 1 survivor passes BH + sign stability | Study verdict = SURVIVORS-FOUND. Ranked list forwarded to P3.2. Each survivor requires its own PREREG before any gate/rank deployment (P1.2 for gate P&L, P2.1 for promotion). |
| Sign-flip rate > 50% of BH-passing features | Flag posted to Fable: evidence of era non-stationarity or regime interaction; P1.5 continuation-partition results consulted before P3 design. |
| Effective-N (week clusters) < 50 | Study paused; coverage printed; Fable re-scopes on era extension or granularity change. |

The study does NOT decide promotions. It identifies which features carry associative signal. Every deployment decision requires a separate PREREG.

## 9. What this study does NOT do

- Does not test gate P&L (that is P1.2).
- Does not ablate the trio (that is P1.3).
- Does not measure recall (that is P1.4).
- Does not partition continuation vs reversal fires (that is P1.5).
- Does not promote any feature to a gate or rank weight.
- Does not run on the shipped-board survivors alone (R1 prohibition — repeated here for emphasis).
- Does not test any feature not listed in the frozen feature list (§5). Any addition = new recorded trial.
- Does not use data outside `data/replay/` for primary feature values.
- Does not test interaction terms or multivariate models. Those are P3-layer decisions with their own PREREG.

## 10. Report contract

`research/entry_intel/P1_1_SEPARABILITY_REPORT.md` (written after results, never before) must include:

- Full 22-row BH table with all statistics and verdicts.
- Per-feature coverage counts (rows tested, excluded, reason for exclusion).
- Both-halves ρ table for all BH survivors.
- Effective-N (week clusters) printed prominently.
- Era boundary applied (from measurement memo, with the memo's version/date cited).
- Survivor list in rank order.
- Leak-audit section: confirm feature values were read from replay rows (PIT-stamped signal-date observation), not from look-ahead columns; confirm fill rule (entry = first close strictly after signal date, inherited from replay grader); confirm no feature is a transformation of the outcome label.
- HYGIENE-ONLY annotation on `adv_dollar_21d`.
- Sign-flip flags on any UNSTABLE features.
- Masterplan §9 status row entry.

The report is immutable once committed. The pre-registration (this file) is never edited to accommodate results.

## 11. Gating condition (R8 — hard stop)

**This study does not execute until:**
1. `data/replay/standout_replay.parquet` exists and the golden test (P0.1 design contract) has PASSED (ticker-by-ticker diff clean).
2. The Opus PIT audit has cleared the replay harness (no historical lookahead detected).
3. The P0 Measurement Memo exists at `research/entry_intel/P0_MEASUREMENT_MEMO.md` with an era table.

All three gates must be clean before the first line of study code runs. Fable approves this PREREG after verifying gate status. A subagent that runs the study before all three conditions are met is in violation of R8.

## 12. Trial ledger entry

Family ID: `p1_1_separability`
Registered trial count: m = 22 (11 features × 2 horizons)
Any post-hoc variation (new feature, new horizon, new outcome definition, interaction term) = new recorded trial requiring a new PREREG before running.

---

## §APPROVAL — Fable, 2026-07-05

**STATUS: APPROVED FOR EXECUTION** (supersedes the DRAFT header above; R8 gates cleared: replay golden exact-match on full ledger + PIT re-audit CLEAN).

Binding v1.1 conformance (P0_MEASUREMENT_MEMO §6, in addition to the v1.0 checklist):
1. Effective verdict window = **2022-06-30 → 2026-07-02** (250-bar Massive warmup; the nominal 2021-07-06 window does not exist in the ledger).
2. Canonical input = `data/replay/replay_boarded.parquet` ONLY. Never read the `replay_2*.parquet` parts glob.
3. Frozen substrate reference (post PR #1466 sector backfill): 961,656 rows; 57,640 fires (49,939 verdict-grade); 17,587 near-misses; 886,429 rejections; 25,783 fire episodes; rs_sector_quartile fill 92% on fires (current-GICS snapshot, 928-label constituents map). Baseline terminal states on verdict-grade fires: STOPPED 31,372 / CLEAN_LIFTOFF 16,549 / CUSHIONED 1,975 / DEAD_MONEY 43.
4. `board_rank_unresolved` rows receive descriptive treatment only — never keep/demote/flip verdicts (memo §6.3).
5. Any concordance citation uses the on-disk 98.5%/12-name value (memo §6.4).

Execution contract: outputs to `research/entry_intel/p1_runs/<study_id>/` (analysis script + RESULTS.md + results.json). Deviation from the registered grid = new recorded trial per species law; ambiguity = blocker report to Fable, never improvisation.
