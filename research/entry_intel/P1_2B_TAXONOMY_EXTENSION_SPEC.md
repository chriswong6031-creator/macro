# P1.2b — Taxonomy Extension Spec: Replay-Harness Re-tag + Mini-PREREG

**STATUS: APPROVED — Fable 2026-07-05 (red-team P2_REDTEAM.md blocking fixes applied; Fable rulings R-P2.1 flip-floor=100 clusters+2 quarters, R-P2.2 single concordance authority = P2.1b §3.3)**

**Document type:** Engineering spec + mini-PREREG (hybrid; design doc with falsifiable acceptance criteria and a plain-English box per house form)
**Study:** P1.2b — replay-harness taxonomy extension (re-tag pass + matched-design re-run on two new rejection-reason codes)
**Program:** Entry Intelligence (EI)
**Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §5/P1.2` (this document extends P1.2, not replaces it)
**Triggered by:** P1.2 structural blocker + Opus review D1 (`p1_runs/P1_2/REVIEW.md`)
**Registered:** 2026-07-05 (before any re-tag or re-run)
**Author:** Sonnet subagent under Fable orchestration
**Constitution:** EI masterplan §3 (inherited law) → Setup Species constitution §1. All P1.2 inherited rulings apply (R1–R10, R4 no pre-commitment, R7 additive-lanes law). Era law: `P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments (2026-07-05)`.

---

## 0. Plain-English box

> The P1.2 study asked: for each reason the board says "no" to a stock, do those rejected names actually perform worse afterwards? It ran across nine testable rejection codes — but when results came back, four of those codes showed **zero rows** in the replay data. Two of them (the "stale signal" and "T4 tier" reasons) turned out not to be absent at all — they were *there* in the substrate, just not tagged with their own distinct label. The harness had been silently folding them into neighbouring codes.
>
> This document does two things. First, it specifies the surgery on the replay harness to carve those two reasons out as properly labelled rows — without touching the fire or near-miss verdicts that everything downstream depends on. Second, it registers a mini re-run of the P1.2 matched design on just those two new codes, fixing a separate problem: the original run accidentally compared board-demoted names against the very pool they were demoted from (which guarantees near-zero differences). The re-run is cleaner — rejected rows are matched against gate-passing rows only, not the demoted-fire pool.
>
> The two other "missing" codes (earnings blackout and cohort-null) genuinely do not exist in the current data collection and are documented as such; no re-tag will produce them.

---

## §1 Background: the structural blocker

### §1.1 P1.2 taxonomy gap — evidence

The P1.2 run (`p1_runs/P1_2/RESULTS.md`, 2026-07-05) found the following row counts in the verdict-grade primary substrate (`data/replay/replay_boarded.parquet`, 961,656 rows):

| Registered reason code | n (verdict-grade rows) | P1.2 status |
|---|---|---|
| `not_topped_veto` | 92,715 | TESTABLE — KEEP verdict |
| `board_rank_cutoff` | 13,676 | TESTABLE — KEEP verdict |
| `extension_demote` | 9,638 | TESTABLE (board-level label) — KEEP verdict (non-informative per D2) |
| `knife_demote` | 20,696 | TESTABLE (board-level label) — KEEP verdict (non-informative per D2) |
| `sector_cap_displaced` | 8,536 | TESTABLE (board-level label) — KEEP verdict (non-informative per D2) |
| `hygiene_screen` | 8,464 | EXCLUDED (R10, graded for coverage only) |
| **`freshness_expired`** | **0** | **INSUFFICIENT_N — labelled "absent"** |
| **`tier_cutoff`** | **0** | **INSUFFICIENT_N — labelled "absent"** |
| `event_blackout` | 0 | INSUFFICIENT_N — genuinely absent |
| `cohort_null` | 0 | INSUFFICIENT_N — genuinely absent |

The Opus reviewer (REVIEW.md §D1 — ADVISORY) confirmed that **two of the four zero-row codes are semantically present in the substrate but untagged as distinct `rejection_reason` values**:

- **`freshness_expired`**: The `gate_reason` free-text field carries the exact FRESH-window semantics. Rows with `verdict_type=near_miss` and `rejection_reason=nan` include 15,022 with "no longer a fresh entry" text variants. The signal_gate source confirms this path: `engine/signal_gate.py` L195 and L210 both write `v["near_miss_reason"] = "freshness_expired"` in the gate function, but this field was not being promoted into the replay's canonical `rejection_reason` column at log time. The `not_topped_veto` cohort (92,715 rows) represents the "exactly-one-failure: topped" branch of the same logic; `freshness_expired` is the "exactly-one-failure: stale" branch. They are two halves of the same near-miss gate and should be tagged separately.

- **`tier_cutoff`**: The `gate_reason` field carries `tier T2/T3/T4 (weight …)` for 10,569 rows. Specifically, **`tier T4 (weight 0.4)` = ~131 rows** with `verdict_type ∈ {rejection (~100), near_miss (~31)}`. `engine/signal_gate.py` L79–81 documents that T4 is *deliberately excluded* from `BUYABLE_TIERS = ("T1", "T2", "T3")` because it fires off the 2D StochRSI rather than the 3D. When a T4-tier name reaches the gate, it is eligible in confluence_tiers but not admitted by signal_gate — this is the `tier_cutoff` semantic. At ~131 rows it is above the n≥10 INCONCLUSIVE floor (and near the n≥25 DEMOTE floor) and was **testable**, not absent. The runner's "0 rows / INSUFFICIENT_N" label for this code is inaccurate.

### §1.2 Board-demotion confound — evidence

The Opus reviewer (REVIEW.md §D2 — BLOCKING for interpretability) confirmed a second structural problem with the three board-level demotion codes (`extension_demote`, `knife_demote`, `sector_cap_displaced`): the matched fired cohort was the **union of all fire rows**, which includes `board_rejection` (demoted) fires as well as `board_fire` (accepted) fires. The demoted fires are a subset of their own matched cohort — the counterfactual is contaminated. The reviewer measured: of 10,365 matchable fire rows, 7,894 are `board_rejection` (demoted) and only 2,471 are `board_fire` (accepted), making the knife_demote cohort **~49.9% of its own matched pool**. The near-zero deltas for all three board-level codes are mechanically induced by this design. Their KEEP verdicts carry no counterfactual information and should be treated as INCONCLUSIVE.

The runner correctly declined to improvise a fix under §APPROVAL clause 4 ambiguity and escalated; P1.2b is Fable's scoped response.

### §1.3 Genuinely absent codes — rationale for NOT-AVAILABLE-IN-SUBSTRATE status

- **`event_blackout`**: Reviewer confirmed 0 token hits in any free-text or code field. The earnings-proximity exclusion referenced in `engine/grading.py REJECTION_TAXONOMY` L109 is described as "where wired" — it is not yet wired in the replay substrate. No re-tag can produce rows that do not exist. **Status: NOT-AVAILABLE-IN-SUBSTRATE** (engineering not yet implemented).

- **`cohort_null`**: The §3.3 coverage law (`coverage_pct < 70%`) referenced in the taxonomy describes a mechanism that requires per-name PIT membership coverage computation. Reviewer confirmed 0 rows; the coverage gate either passes all names in the verdict window or is not applied in the replay path. **Status: NOT-AVAILABLE-IN-SUBSTRATE** (gating logic not plumbed into the replay substrate).

Both absent codes remain in the `REJECTION_TAXONOMY` frozenset (no silent removal per grading.py L99–100 governance rule). When the relevant substrate changes (event blackout wired; cohort-null gate plumbed), a new §8 entry opens a fresh P1.2c or amends this spec. No P1.2b work addresses them.

---

## §2 Harness change specification

### §2.1 What changes

The replay harness (`scripts/replay_standout_pipeline.py`) currently writes gate-stage rejection information into `gate_reason` as free-text and does NOT reliably propagate the `near_miss_reason` field from `signal_gate.gate()` into the replay's canonical `rejection_reason` column. Two new structured codes must be carved out.

The pattern to follow is the **near-miss annotation** in `signal_gate.py` (L187–210): the gate already sets `v["near_miss_reason"]` with the exact code strings `"freshness_expired"` and `"not_topped_veto"`. The harness must read this field and write it to the canonical `rejection_reason` column at log time, rather than leaving `rejection_reason` as null.

**Change 1 — `freshness_expired` tagging:**

At the point in the replay harness where each candidate's gate verdict is logged, add:

```python
# Promote the signal_gate near_miss_reason to the canonical rejection_reason
# for freshness-expired rows (gate.py L195, L210 — "freshness_expired" branch of
# the exactly-one-failure not-topped veto logic).
if verdict.get("near_miss_reason") == "freshness_expired":
    row["rejection_reason"] = "freshness_expired"
```

This is the only change needed for `freshness_expired`. The `not_topped_veto` code is already present in the substrate (92,715 rows) via the parallel branch; this change completes the pair.

**Change 2 — `tier_cutoff` tagging:**

The T4 rejection happens at `signal_gate.gate()` via the `BUYABLE_TIERS` check. Currently the reason surfaces only in the `gate_reason` free-text field as `tier T4 (weight 0.4)`. Add an explicit check in the harness:

```python
# Tag T4-excluded rows as tier_cutoff (signal_gate BUYABLE_TIERS excludes T4;
# see signal_gate.py L79-81 — T4 is the below-tier exclusion reason).
if (verdict.get("tier_cascade") == "T4"
        and not verdict.get("eligible", False)
        and row.get("verdict_type") in ("rejection", "near_miss")):
    row["rejection_reason"] = "tier_cutoff"
```

**Priority ordering:** if `rejection_reason` is already non-null from another path, do not overwrite — the first-assigned reason wins. The above assignments only apply when `rejection_reason` is null or absent.

### §2.2 What does NOT change

- **Verdicts and fires are byte-identical.** The re-tag pass only reclassifies rows where `rejection_reason` was null or generic into one of the two new structured codes. No `verdict_type`, `terminal_state`, `fwd_ret_*`, `survivor_bias`, or `episode_id` field changes. Fire rows (verdict_type='fire') are never re-tagged — the re-tag targets only rows with `verdict_type ∈ {'rejection', 'near_miss'}` and `rejection_reason` currently null.

- **No full re-run.** The re-tag is a surgical post-pass that reads the existing `data/replay/replay_boarded.parquet`, adds or corrects the `rejection_reason` column for the two new codes, and writes a new artifact `data/replay/replay_boarded_p12b.parquet`. The full price-series grading, terminal-state computation, episode clustering, and survivor-bias stamps are unchanged.

### §2.3 Validation requirement (byte-identity of fire/near-miss sets)

Before the re-tagged artifact is used for any verdict computation, the following validation must pass and be reported in the P1.2b results preamble:

**Gate V1 — Fire set byte-identity:**
```
assert (
    replay_boarded_p12b[replay_boarded_p12b["verdict_type"] == "fire"]
    .sort_values(["ticker", "signal_date"])
    .reset_index(drop=True)
    .equals(
        replay_boarded[replay_boarded["verdict_type"] == "fire"]
        .sort_values(["ticker", "signal_date"])
        .reset_index(drop=True)
    )
)
```
If this assertion fails, halt and return a blocker report. The re-tag has contaminated a fire row.

**Gate V2 — Near-miss set identity (row-level, not count-only):**
The near-miss set must be byte-identical between the original and re-tagged artifacts on all columns EXCEPT `rejection_reason` (which is the column being re-tagged). A swap bug — promoting one near-miss row while demoting another — conserves count but corrupts the set; count conservation alone does not catch it.
```python
# Drop the re-tagged column, sort on stable keys, and assert full set equality
_nm_orig = (
    replay_boarded[replay_boarded["verdict_type"] == "near_miss"]
    .drop(columns=["rejection_reason"])
    .sort_values(["ticker", "signal_date"])
    .reset_index(drop=True)
)
_nm_p12b = (
    replay_boarded_p12b[replay_boarded_p12b["verdict_type"] == "near_miss"]
    .drop(columns=["rejection_reason"])
    .sort_values(["ticker", "signal_date"])
    .reset_index(drop=True)
)
assert _nm_orig.equals(_nm_p12b), (
    "V2 FAIL: near-miss row set is not byte-identical (excluding rejection_reason). "
    "A near-miss row was added, removed, or had a non-rejection_reason column changed."
)
```

**Gate V2b — Whole-frame verdict_type byte-identity:**
The `verdict_type` column across the entire frame must be byte-identical between the original and re-tagged artifacts — guaranteeing no fire↔near_miss↔rejection migration anywhere.
```python
assert (
    replay_boarded_p12b["verdict_type"].reset_index(drop=True)
    .equals(replay_boarded["verdict_type"].reset_index(drop=True))
), "V2b FAIL: verdict_type column differs — a row migrated across verdict_type categories."
```

**Gate V3 — New code coverage plausibility:**
Print the row counts for the two new codes after re-tag. The expected range is:
- `freshness_expired`: 1,000–30,000 rows (the semantic cohort from the reviewer's analysis was ~15,022 in the near-miss near_miss_reason field; some may not have a recoverable near_miss_reason in the parquet-serialised form).
- `tier_cutoff`: 50–400 rows (reviewer found ~131 matching `tier T4` gate_reason).

If either code returns 0 rows after re-tag, the harness change did not fire — return a blocker report with the column inspection.

### §2.4 NOT-AVAILABLE-IN-SUBSTRATE documentation (required output)

The P1.2b results preamble must include the following text verbatim:

> **`event_blackout` — NOT-AVAILABLE-IN-SUBSTRATE.** The earnings-proximity exclusion gate is defined in `engine/grading.py REJECTION_TAXONOMY` but is annotated "where wired." As of the current replay substrate, no rows carry this rejection reason or its semantic equivalent in any free-text column (0 token hits confirmed by Opus review 2026-07-05). This code requires new data plumbing in the replay harness before it becomes testable. No re-tag action is possible. Deferred to a future P1.2c amendment when the gate is wired.
>
> **`cohort_null` — NOT-AVAILABLE-IN-SUBSTRATE.** The §3.3 coverage-law gate (coverage_pct < 70%) is defined in the taxonomy but not applied in the current replay substrate (0 rows). This code requires the per-name PIT membership coverage computation to be plumbed into the replay gate path. Deferred to a future P1.2c amendment.

---

## §3 P1.2b Mini-PREREG

**Family ID (BH FDR):** `ei_gate_pnl_p12b` — a NEW, separate BH family. It is NOT merged with the original `ei_gate_pnl` family (m=72). This keeps the two studies' type-I error control independent; a combined post-hoc BH family would violate the species-constitution pre-registration law.

**Blocking gate:** P1.2b does not execute before the re-tag validation gates V1/V2/V3 all pass.

**Input artifact:** `data/replay/replay_boarded_p12b.parquet` (the re-tagged output of §2). Never reads the original `replay_boarded.parquet` or the per-year parts glob (P0_MEASUREMENT_MEMO §6 v1.1 clause 2).

### §3.1 Population

**Rejection cohorts (two new codes):**
- Rows with `rejection_reason == "freshness_expired"` and `verdict_grade == True`.
- Rows with `rejection_reason == "tier_cutoff"` and `verdict_grade == True`.

**Matched fired cohort (confound fix):**

The P1.2 original design matched rejections against the union of all fire rows (including board-demoted fires). For the three board-level demotion codes (`extension_demote`, `knife_demote`, `sector_cap_displaced`), this created a mechanical near-zero confound (D2). `freshness_expired` and `tier_cutoff` are **gate-stage rejections**, not board-level demotions — the confound does not apply to them in the same way. However, to prevent any residual contamination and to establish a cleaner design:

**The matched fired cohort for P1.2b is restricted to `board_fire` rows only** — rows with `verdict_type == 'fire'` AND `board_verdict == 'board_fire'` (i.e., rows that passed the gate AND were accepted by the board). Board-rejected fires (`board_verdict == 'board_rejection'`) are excluded from the match pool.

This is the correct counterfactual: a gate-stage rejection is compared against names that cleared the gate AND made the board, not names that cleared the gate but were then demoted for a different reason.

### §3.2 Matching algorithm (inherits P1.2 §Matching algorithm, one modification)

Steps 1–4 of the P1.2 matching algorithm apply unchanged, with one stated modification:

- **Step 2 (exact matching):** match on `(episode_cluster_id, gics_sector, alignment_tier)` — identical to P1.2.
- **Step 3 (pool size gate):** matching pool must contain ≥ 3 distinct `board_fire` rows (distinct by ticker) — identical threshold, but pool is now restricted to `board_fire` rows only.
- **Step 4 (matched cohort construction):** the matched fired cohort is the union of `board_fire` rows appearing in at least one rejection row's matching pool.

### §3.3 Trial ledger (pre-registered; family `ei_gate_pnl_p12b`)

**m = 2 reasons × 2 horizons × 4 axes = 16.** BH correction applied across all 16 simultaneously.

| trial | rejection_reason | primary verdict horizon | axis | BH slot |
|---|---|---|---|---|
| B01 | `freshness_expired` | 21d | Δ_stop_out | yes |
| B02 | `freshness_expired` | 21d | Δ_dead_money | yes |
| B03 | `freshness_expired` | 21d | Δ_cushion | yes |
| B04 | `freshness_expired` | 21d | Δ_clean_lift | yes |
| B05 | `freshness_expired` | 63d | Δ_stop_out | yes |
| B06 | `freshness_expired` | 63d | Δ_dead_money | yes |
| B07 | `freshness_expired` | 63d | Δ_cushion | yes |
| B08 | `freshness_expired` | 63d | Δ_clean_lift | yes |
| B09 | `tier_cutoff` | 21d | Δ_stop_out | yes |
| B10 | `tier_cutoff` | 21d | Δ_dead_money | yes |
| B11 | `tier_cutoff` | 21d | Δ_cushion | yes |
| B12 | `tier_cutoff` | 21d | Δ_clean_lift | yes |
| B13 | `tier_cutoff` | 63d | Δ_stop_out | yes |
| B14 | `tier_cutoff` | 63d | Δ_dead_money | yes |
| B15 | `tier_cutoff` | 63d | Δ_cushion | yes |
| B16 | `tier_cutoff` | 63d | Δ_clean_lift | yes |

m = 16 pre-registered trials. Any post-hoc variation (alternative horizon, alternative matching key, alternative code parsing) = new recorded trial in `engine/trial_ledger` before running. The 126d context grid (printed where n ≥ 10 at 126d) is not counted in the BH family.

### §3.4 Primary statistics (exact, frozen)

Inherited from P1.2 §Primary statistics and thresholds exactly:
- **Primary statistic:** the four safety-net axis deltas (Δ_stop_out, Δ_dead_money, Δ_cushion, Δ_clean_lift) at the declared horizon, expressed as rejection-cohort rate minus matched-fired-cohort rate.
- **Episode-clustered p-value:** block-bootstrap (B = 10,000 draws), blocks = episode_cluster_ids. One p-value per (reason, horizon, axis). BH at q ≤ 0.10 across all 16.
- **Wilson lower bounds:** printed beside every rate (z = 1.645, one-sided 95%).
- **n floor for verdict eligibility:** INCONCLUSIVE if n_rejection < 10 after Step 3 pruning; DEMOTE n ≥ 25; FLIP n ≥ 50. Thin-cell flag printed in every table row.

**POWER NOTE:** `tier_cutoff` at ~131 verdict-grade rows is above the INCONCLUSIVE floor (n=10) and near the DEMOTE floor (n=25). Given the short matched window, it may fall below the FLIP floor (n=50). If n < 25 after Step 3 pruning: print rates, print the raw delta and Wilson bounds, return INCONCLUSIVE and label THIN. Do NOT borrow rows from outside the p12b artifact or from pre-2021 stamped rows to reach a floor.

### §3.5 Verdict thresholds (inherited from P1.2 §Pre-registered verdict thresholds per gate)

The KEEP / DEMOTE-TO-PENALTY / FLIP decision rules from P1.2 apply unchanged, using the B01–B16 family. The one modification: FLIP requires both-halves sign stability on Δ_stop_out AND Δ_cushion; if the primary era is too short to split (fewer than 2 episode clusters in each half), both-halves is reported as INCONCLUSIVE and a FLIP verdict cannot be issued regardless of the BH outcome.

### §3.6 Era handling clause (binding)

- **Era memo:** `P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments (2026-07-05)`.
- **Effective verdict window:** `2022-06-30 → last-full-replay-date` (250-bar MTF warmup per §6.1 amendment; the nominal 2021-07-06 window does not exist in the ledger).
- **Canonical input:** `data/replay/replay_boarded_p12b.parquet` ONLY.
- All v1.0 §5 checklist items and all v1.1 §6 amendments apply. Primary verdict statistics on `verdict_grade == True` rows only. Stamped rows (if any exist post-re-tag) routed to context appendix.
- If `P0_MEASUREMENT_MEMO.md` does not exist at execution time, the study **HALTS**.

### §3.7 Acceptance criteria (falsifiable)

The following criteria are stated before any run. They are not adjusted post-hoc.

**AC-1 (harness change correctness):** Validation gates V1, V2, and V3 all pass. The re-tagged artifact has ≥ 50 `freshness_expired` rows and ≥ 50 `tier_cutoff` rows in the verdict-grade window. Below 50 on either code: blocker, halt, report.

**AC-2 (no verdict contamination):** The five testable verdicts from the original P1.2 run (`not_topped_veto`: KEEP; `extension_demote`, `knife_demote`, `sector_cap_displaced`, `board_rank_cutoff`: KEEP/non-informative) are NOT re-opened in P1.2b. This study produces verdicts only for `freshness_expired` and `tier_cutoff`. Findings on the other codes are unchanged.

**AC-3 (INCONCLUSIVE is an honest result):** If `tier_cutoff` n_rejection < 10 after Step 3 pruning, the result is returned as INCONCLUSIVE. This is a valid outcome. It updates the RESULTS.md "0 rows / absent" language to "present but thin" and feeds a recommendation to extend the replay window before a verdict-grade claim is attempted.

**AC-4 (BH discipline):** The 16-trial family is the entire family. No p-value from this run enters the original `ei_gate_pnl` BH family (m=72). No p-value is laundered across families. If a BH-significant finding arises for `freshness_expired` or `tier_cutoff`, it feeds the P2.2 candidate list as a new entry — with explicit labelling that it comes from the `ei_gate_pnl_p12b` family at q≤0.10.

**AC-5 (board-demotion confound remains open):** The three board-demotion KEEP verdicts (`extension_demote`, `knife_demote`, `sector_cap_displaced`) from P1.2 are NOT re-tested in P1.2b. Their KEEP labels are re-cast as non-informative per the Opus D2 finding. A future P1.2c or P2.2 scoping should design a demoted-vs-`board_fire` counterfactual using the existing substrate. P1.2b does not attempt this; its scope is the gate-stage re-tag only.

---

## §4 P1.3 evidence context (required citation — three independent effects)

Per the masterplan §9 review advisory, downstream documents citing P1.3 must use the independent-effect count (~3 factors, ~10 independent forward-return tests), NOT "22/30 trials" (which duplicates p-values across terminal states within each (factor, mode, horizon) cell — P1.3 REVIEW_v2.md ADVISORY-2, confirmed by reviewer).

The three independent P1.3 effects relevant as context for gate-design decisions:

1. **F1 — cohort-washout proximity** (SHIPS-AS-RANK-WEIGHT): near-washout fires show −13.19pp dead-money at 21d (T02, perm_p=0.0002, BH_p=0.0006, r=−0.1247, sign-stable) and −5.21pp stop-out at 63d (T04, perm_p=0.0002, BH_p=0.0006, r=−0.0978, sign-stable). This is a strong, horizon-dependent effect; washout proximity meaningfully reduces dead-money outcomes even though it does not reduce 21d stop-outs (T01: +2.41pp, unfavorable, same perm_p — the same continuous distribution drives all terminal states in a cell). Gate-rejected at 54.0% board impact.

2. **F3 — anti-chase (ext_z ≤ 2.0)** (SHIPS-AS-HARD-GATE): extended fires (ext_z > 2.0) show higher stop-outs (T21: −0.43pp reduction for would-pass vs would-block at 21d, perm_p=0.0026, BH_p=0.0060, r=−0.0612, sign-stable; T24: −5.00pp at 63d, perm_p=0.0648, BH_p=0.0933, sign-stable) and higher dead-money (T22: −3.63pp at 21d, BH_p=0.0060, sign-stable). Gate admitted at 4.6% board impact — the one factor with a viable gate design. This corroborates the gate-design intuition for `freshness_expired` (stale entries share the "chasing" risk profile) without being confirmatory evidence for it.

3. **F2 — RS-inflection (Q2∪Q3)** (SHIPS-AS-RANK-WEIGHT): genuinely weak (|r| ≈ 0.01–0.02; RW 21d cushioned T18 perm_p=0.0684, BH_p=0.0933; RW 63d cushioned T20 perm_p=0.0426, BH_p=0.0752); sign-stable on the shipping legs; 48.5% board impact if used as a hard gate. Context only: the RS-inflection signal does not directly bear on freshness or tier-cutoff gate design; cited for completeness.

These three effects are cited for context only. They do not constitute confirmatory evidence for P1.2b verdicts — per R3 (applied by analogy), evidence from a different study family transfers as hypothesis, not validation.

---

## §5 Report contract

Output file: `research/entry_intel/p1_runs/P1_2B/RESULTS.md` (plus `results.json` and the run script `run_P1_2B.py`).

Required sections (report fails gate if absent):

1. **Re-tag preamble:** re-tagged artifact path + MD5, original artifact MD5 (must differ on the `rejection_reason` column only), V1/V2/V3 validation gate results, row counts for the two new codes before/after re-tag, NOT-AVAILABLE-IN-SUBSTRATE text verbatim (§2.4).
2. **Era coverage statement:** memo citation (v1.0 + §6 v1.1), effective window, n verdict-grade rows, n episode clusters, n stamped rows (expected 0), n horizon_censored excluded.
3. **Coverage table (two new codes):** n_rejection_total, n_matchable, n_survived (Step 3), prune_rate, n_board_fire_matched (the new pool restriction is explicit).
4. **Primary verdict table (B01–B16):** Δ per axis per (reason, horizon), Wilson bounds, raw block-bootstrap p, BH q-value, verdict (KEEP / DEMOTE-TO-PENALTY / FLIP / INCONCLUSIVE / THIN).
5. **BH family audit:** m=16 registered before run, all 16 raw p-values, q-values, rejection threshold, n significant.
6. **P2.2 candidate list:** all DEMOTE or FLIP verdicts with full evidence, formatted for Fable review.
7. **Board-demotion confound status note:** explicit statement that the D2 confound (extension/knife/sector_cap) is NOT addressed in this run; verdicts for those three codes remain non-informative per the Opus review and are deferred to a future P1.2c or P2.2 scoping.
8. **Leak audit section:** fill rule, feature freeze, era boundary, gics_sector non-PIT disclosure, survivor bias.
9. **§8 masterplan entry rows** for each new code with verdict and transition to `validation_status`.
10. **In plain English box** (§0 above serves as the registered version; the report may reprint it or provide a tailored update — it must be present).

---

## §6 §8 status rows (to be filled post-run)

| date | wave | status | code | notes | PR |
|---|---|---|---|---|---|
| (pending) | P1.2b | DRAFT | `freshness_expired` | PREREG registered 2026-07-05; awaiting re-tag validation + run | — |
| (pending) | P1.2b | DRAFT | `tier_cutoff` | PREREG registered 2026-07-05; awaiting re-tag validation + run | — |
| 2026-07-05 | P1.2b | NOT-AVAILABLE | `event_blackout` | Genuinely absent in substrate; earnings-proximity gate not wired in replay; deferred to P1.2c | — |
| 2026-07-05 | P1.2b | NOT-AVAILABLE | `cohort_null` | Genuinely absent in substrate; §3.3 coverage gate not plumbed into replay path; deferred to P1.2c | — |

---

*Registered 2026-07-05. Immutable after Fable approval. Results added to RESULTS file only; this document is never edited to accommodate observed outcomes (species README convention).*

*2026-07-05 — red-team blocking fixes applied (P2_REDTEAM.md) incl. Fable rulings R-P2.1 (flip floor 100 clusters + 2 quarters) and R-P2.2 (single concordance authority).*
