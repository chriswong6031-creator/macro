# P1.1 Separability Study — Results

**VERDICT: SURVIVORS-FOUND**

5 feature(s) survive BH + sign stability. Ranked list forwarded to P3.2.

**Study ID:** P1_1_SEPARABILITY
**Run timestamp:** 2026-07-05T09:27:49Z
**Memo citation:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)
**PREREG:** research/entry_intel/P1_1_SEPARABILITY_PREREG.md

---

## In plain English

We asked whether any pre-recorded field — extension grade, alignment quality, weekly phase, relative strength quartile, proximity to a cohort washout, and so on — can predict whether a stock goes up without stopping out, measured at both 21 and 63 calendar days after the entry signal. We tested all 11 registered features on the full pre-gate pool (fires, near-misses, and rejections alike — 834,267 rows spanning 184 distinct weeks). We corrected for testing 22 feature-horizon pairs at once (Benjamini-Hochberg, FDR ≤ 10%), and required that any finding hold in both the earlier and later halves of the data.

**Result: SURVIVORS-FOUND. 5 feature(s) survive BH + sign stability. Ranked list forwarded to P3.2.**

> Technical note: p-values use cluster-robust standard errors (CR1 sandwich at the week-cluster level), which is the pre-registered equivalent to block bootstrap. AUC p-values use the analytical Mann-Whitney U (exact equivalent to permutation AUC for large N); AUC is supplemental only and not used for BH correction.

---

## Era and Population

| Item | Value |
|------|-------|
| Memo | P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) |
| Effective verdict window (v1.1 Amendment 1) | 2022-06-30 → 2026-07-02 |
| Primary population | 834,267 rows (verdict_grade=True, horizon_censored=False) |
| **Effective-N** | **184 week clusters** |
| Unstamped rows (verdict-grade) | 834,267 (survivor_bias=False throughout) |
| Stamped rows excluded | 127,389 |
| horizon_censored excluded | 127,389 |
| good_21d base rate | 0.4137 (41.4%) |
| good_63d base rate | 0.3539 (35.4%) |
| Pre-gate pool: fires | 49,939 |
| Pre-gate pool: near_misses | 15,053 |
| Pre-gate pool: rejections | 769,275 |

**SURVIVOR-BIAS STAMP (P0_MEASUREMENT_MEMO.md §2.3):** survivor-biased panel: 0% of member-months lack price history for the 2022–2026 verdict era; delisted-name recall verified via Massive store (100%/17 probe); results are VERDICT-GRADE.

**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE:** Not applicable (0 stamped rows in this replay snapshot).

---

## §5 Conformance Checklist

- [x] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` in preamble.
- [x] Primary window = `2022-06-30 → 2026-07-02` (v1.1 effective; 250-bar MTF warmup applied).
- [x] Verdict-grade statistics on `survivor_bias = false` rows only (all 834,267 primary rows).
- [x] Source confirmation: all rows Massive-sourced per replay provenance (survivor_bias=False throughout).
- [x] Pre-2021 rows: none in dataset. Context appendix: not applicable.
- [x] `horizon_censored` rows excluded (127,389 rows).
- [x] Stamp text printed with era census missing-fraction (0% for Massive-sourced 2022+ window).
- [x] Effective-N = 184 week clusters ≥ 50 minimum — POWER THRESHOLD MET.

---

## BH Family — Full 22-Row Table

| #   | Feature                          | Hor   | rho      | AUC      | p_one       | BH_adj_q   | BH     | Verdict          | Flags                |
|-----|----------------------------------|-------|----------|----------|-------------|------------|--------|------------------|----------------------|
| 1   | ext_z                            | 21d   | -0.0707  | 0.4585   | 0.000002    | 0.0000     | PASS   | SURVIVOR         |                      |
| 2   | ext_z                            | 63d   | -0.0501  | 0.4698   | 0.000277    | 0.0009     | PASS   | SURVIVOR         |                      |
| 3   | ext_atr                          | 21d   | -0.0593  | 0.4653   | 0.000040    | 0.0001     | PASS   | SURVIVOR         |                      |
| 4   | ext_atr                          | 63d   | -0.0148  | 0.4911   | 0.135343    | 0.2127     | ---    | SURVIVOR         |                      |
| 5   | knife_z                          | 21d   | 0.0660   | 0.5351   | 0.999997    | 1.0000     | ---    | NO-SIGNAL        | INVERTED-SIGN        |
| 6   | knife_z                          | 63d   | 0.0245   | 0.5134   | 0.964293    | 1.0000     | ---    | NO-SIGNAL        | INVERTED-SIGN        |
| 7   | alignment_quality                | 21d   | 0.0327   | 0.5190   | 0.019802    | 0.0436     | PASS   | UNSTABLE         |                      |
| 8   | alignment_quality                | 63d   | 0.0405   | 0.5242   | 0.005202    | 0.0143     | PASS   | UNSTABLE         |                      |
| 9   | alignment_tier                   | 21d   | 0.0043   | 0.5023   | 0.347086    | 0.4772     | ---    | NO-SIGNAL        |                      |
| 10  | alignment_tier                   | 63d   | 0.0114   | 0.5062   | 0.120710    | 0.2043     | ---    | NO-SIGNAL        |                      |
| 11  | weekly_phase                     | 21d   | N/A      | 0.4895   | 0.000000    | 0.0000     | PASS   | SURVIVOR         |                      |
| 12  | weekly_phase                     | 63d   | N/A      | 0.4862   | 0.000000    | 0.0000     | PASS   | SURVIVOR         |                      |
| 13  | dist_52wh                        | 21d   | -0.0845  | 0.4505   | 0.000000    | 0.0000     | PASS   | SURVIVOR         |                      |
| 14  | dist_52wh                        | 63d   | -0.0056  | 0.4966   | 0.339717    | 0.4772     | ---    | SURVIVOR         |                      |
| 15  | rs_vs_sector_quartile            | 21d   | -0.0160  | 0.4909   | 0.999594    | 1.0000     | ---    | NO-SIGNAL        | INVERTED-SIGN        |
| 16  | rs_vs_sector_quartile            | 63d   | -0.0048  | 0.4972   | 0.871699    | 1.0000     | ---    | NO-SIGNAL        | INVERTED-SIGN        |
| 17  | side_200dma                      | 21d   | -0.0541  | 0.4728   | 0.999972    | 1.0000     | ---    | NO-SIGNAL        | INVERTED-SIGN        |
| 18  | side_200dma                      | 63d   | -0.0160  | 0.4917   | 0.905811    | 1.0000     | ---    | NO-SIGNAL        | INVERTED-SIGN        |
| 19  | adv_dollar_21d                   | 21d   | -0.0171  | 0.4900   | 0.016088    | 0.0393     | HYG    | HYGIENE-ONLY     | HYGIENE-ONLY         |
| 20  | adv_dollar_21d                   | 63d   | -0.0105  | 0.4937   | 0.068901    | 0.1378     | ---    | HYGIENE-ONLY     | HYGIENE-ONLY         |
| 21  | cohort_washout_proximity         | 21d   | 0.0773   | 0.5364   | 0.000000    | 0.0000     | PASS   | SURVIVOR         |                      |
| 22  | cohort_washout_proximity         | 63d   | 0.0178   | 0.5086   | 0.101568    | 0.1862     | ---    | SURVIVOR         |                      |


*Notes: rho = Spearman rank correlation. AUC via roc_auc_score. p_one = one-tailed in pre-registered direction (two-sided for HYGIENE-ONLY). BH_adj_q computed over m=22 tests. `weekly_phase` p_one = KW p (non-directional; used as-is). HYGIENE-ONLY = adv_dollar_21d per R10.*

---

## Per-Feature Coverage

| Feature                          | n_21d      | excl_21d   | n_63d      | excl_63d   |
|----------------------------------|------------|------------|------------|------------|
| ext_z                            | 834,267    | 0          | 834,267    | 0          |
| ext_atr                          | 834,267    | 0          | 834,267    | 0          |
| knife_z                          | 834,267    | 0          | 834,267    | 0          |
| alignment_quality                | 834,267    | 0          | 834,267    | 0          |
| alignment_tier                   | 110,392    | 723,875    | 110,392    | 723,875    |
| weekly_phase                     | 834,267    | 0          | 834,267    | 0          |
| dist_52wh                        | 834,267    | 0          | 834,267    | 0          |
| rs_vs_sector_quartile            | 776,439    | 57,828     | 776,439    | 57,828     |
| side_200dma                      | 834,267    | 0          | 834,267    | 0          |
| adv_dollar_21d                   | 834,267    | 0          | 834,267    | 0          |
| cohort_washout_proximity         | 834,267    | 0          | 834,267    | 0          |


*Note: cohort_washout_proximity is a bool (True=near washout, False=not). The PREREG §5 feature #11 is labeled "continuous (where non-null)" but the replay encodes it as a binary proximity flag. Null count = 0 (bool); "excluded" here means rows where the signal is False (not near washout) — included in the test since False=0 is a valid observation.*

---

## Both-Halves ρ Table (BH survivors)

Split point: 2024-W13 / 2024-W14 (H1: 92 weeks, H2: 92 weeks, chronological split)

| Feature                          | Hor   | rho_h1     | rho_h2     | Sign-stable  |
|----------------------------------|-------|------------|------------|--------------|
| ext_z                            | 21d   | -0.0976    | -0.0481    | True         |
| ext_z                            | 63d   | -0.0850    | -0.0160    | True         |
| ext_atr                          | 21d   | -0.0794    | -0.0384    | True         |
| ext_atr                          | 63d   | -0.0376    | 0.0055     | False        |
| alignment_quality                | 21d   | 0.0802     | -0.0113    | False        |
| alignment_quality                | 63d   | 0.0882     | -0.0059    | False        |
| weekly_phase                     | 21d   | -0.0370    | -0.0054    | True         |
| weekly_phase                     | 63d   | -0.0427    | -0.0102    | True         |
| dist_52wh                        | 21d   | -0.0943    | -0.0740    | True         |
| dist_52wh                        | 63d   | -0.0177    | 0.0052     | False        |
| cohort_washout_proximity         | 21d   | 0.1026     | 0.0494     | True         |
| cohort_washout_proximity         | 63d   | 0.0383     | -0.0034    | False        |


---

## Survivor List (P3.2 Re-rank Candidates)

Ranked by |ρ| at 21d horizon (descending), primary horizon first.

| Rank  | Feature                          | Direction        | rho_21d   | AUC_21d   | BHq_21d   | BHq_63d   | Stbl21    | Stbl63    |
|-------|----------------------------------|------------------|-----------|-----------|-----------|-----------|-----------|-----------|
| 1     | dist_52wh                        | lower→better     | -0.0845   | 0.4505    | 0.0000    | 0.4772    | True      | False     |
| 2     | cohort_washout_proximity         | near_washout→better | 0.0773    | 0.5364    | 0.0000    | 0.1862    | True      | False     |
| 3     | ext_z                            | lower→better     | -0.0707   | 0.4585    | 0.0000    | 0.0009    | True      | True      |
| 4     | ext_atr                          | lower→better     | -0.0593   | 0.4653    | 0.0001    | 0.2127    | True      | False     |
| 5     | weekly_phase                     | earlier→better   | N/A       | 0.4895    | 0.0000    | 0.0000    | True      | True      |


---

## HYGIENE-ONLY Annotation

`adv_dollar_21d` — Ruling R10 (masterplan §2): liquidity fields are hygiene/display only. Any association found cannot be promoted to rank power without its own independent PREREG. Its BH-adjusted result is printed but verdict is overridden to HYGIENE-ONLY regardless of BH outcome.

---

## weekly_phase — Kruskal-Wallis Branch

The PREREG §6.1 pre-registers a Kruskal-Wallis H-test (non-directional) for `weekly_phase` (categorical). The KW p-value enters the BH family. Sign-stability uses the Spearman ρ of the ordinal proxy (basing=0…falling=5) in each chronological half. Bucket outcome means are reported in results.json.

---

## Computational Implementation (declared at runtime per PREREG §6.2)

The PREREG §6.2 pre-registers **either** cluster-robust SE **or** block bootstrap (seed=42, n_boot=5000) as equivalent implementations. This run uses **CR1 cluster-robust SE** (sandwich estimator at the week-cluster level, t-distribution with G-1 degrees of freedom, CR1 small-sample correction). Block bootstrap at n_boot=5000 would require ~3 hours for 22 tests on 834k rows; CR1 SE yields the same clustering correction in seconds. The choice is declared here and applied uniformly across all 22 tests.

AUC p-value: analytical Mann-Whitney U (mathematically equivalent to permutation AUC in expectation). The registered n_perm=10,000 permutation would require ~7 hours for 22 tests; MWU is the standard analytical substitute. AUC is supplemental only and NOT used for BH correction — this substitution does not affect any primary verdict.

---

## Leak Audit

1. All feature values read from `replay_boarded.parquet` at the row's `signal_date` (PIT-stamped by the P0.1 replay harness per its design contract).
2. Fill rule: entry = first close strictly after `signal_date`. Inherited from replay grader; not re-estimated here.
3. No feature is a transformation of `state_8_21` or `state_15_126` (the outcome labels). Features are pre-signal attributes logged at signal time.
4. `adv_dollar_21d_proxy` and `washout_proximity_proxy` stamps retained in parquet — these flag proxy-sourced values in the replay; study uses the underlying feature column values, not the proxy flags.
5. `align_tier_enc` is a fixed ordinal encoding (APPROACHING=0, ARMED=1, PRIME=2), pre-registered in §6.1; not fitted from data.
6. `weekly_phase_ord` ordinal mapping is fixed at registration (basing=0, bear_recovering=1, turning=2, rising=3, rolling=4, falling=5, unknown=NaN); not fitted from data.

---

## Sign-Flip Rate

BH-passing features (excl. hygiene): 6
UNSTABLE (sign flip): 1
Rate: 1/6 = 16.7%
OK: flip rate within tolerance (≤50%).

---

## Masterplan §9 Status Entry

| Study | Run date | Verdict | Survivors |
|-------|----------|---------|-----------|
| P1.1 Separability | 2026-07-05 | SURVIVORS-FOUND | ext_z, ext_atr, weekly_phase, dist_52wh, cohort_washout_proximity |

---

*PREREG: research/entry_intel/P1_1_SEPARABILITY_PREREG.md (immutable; this report does not modify it)*
*This report is immutable once committed.*
