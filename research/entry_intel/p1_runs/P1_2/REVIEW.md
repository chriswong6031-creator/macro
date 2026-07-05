# P1.2 Gate P&L — CONFORMANCE REVIEW (Opus reviewer)

**Reviewer stance:** default skeptical; audited artifacts (RESULTS.md / results.json / run_P1_2.py) against the PREREG grid and independently recomputed ≥3 headline numbers against `data/replay/replay_boarded.parquet`.
**Review date:** 2026-07-05
**Verdict:** **CONFORMANT WITH DEVIATIONS** — the executed statistics are faithful and reproduce exactly; the headline KEEP/INCONCLUSIVE verdicts are arithmetically forced and correctly reported. However, one substantive DEVIATION exists: the runner declares 2 of the 4 "absent" reasons (`freshness_expired`, `tier_cutoff`) as *not present in the data* when their **semantic cohorts ARE discoverable** in the substrate (via `gate_reason` free-text and the `tier T4` gate_reason). This does not change any verdict (they would still be INCONCLUSIVE or KEEP), but the honesty surface overstates substrate absence. All findings below are tagged BLOCKING / ADVISORY.

---

## Independent recomputation (Check 3)

Recomputed directly from `replay_boarded.parquet` (never touched `replay_2*.parquet`). Every headline number reproduced to the digit:

| Headline statistic | Runner report | My recompute | Match |
|---|---|---|---|
| Primary rows (vg==True & in-era) | 834,267 | 834,267 | EXACT |
| Verdict-grade fires | 49,939 | 49,939 | EXACT |
| Episode clusters (21d windows) | 44 | 44 | EXACT |
| hygiene_screen rows | 8,464 | 8,464 | EXACT |
| board_rank_unresolved fires | 11,069 | 11,069 | EXACT |
| not_topped_veto matchable | 4,342 | 4,342 | EXACT |
| not_topped_veto survived (Step 3) | 3,503 | 3,503 | EXACT |
| not_topped_veto fire matched | 7,225 | 7,225 | EXACT |
| ntv Δ_stop 21d | +0.001 | +0.0007 | EXACT |
| ntv Δ_stop 63d | −0.008 | −0.0080 | EXACT |
| BH m / valid pvals | 72 / 40 | 72 / 40 | EXACT |

No mismatch > 1% on any recomputed number. The matching pipeline (episode-cluster assignment, Step-3 ≥3-distinct-ticker gate, Step-4 union cohort, 63d state derivation) is a faithful implementation of the PREREG algorithm.

---

## Per-check findings

### Check 1 — Trial-grid adherence — **PASS**
- 18 registered cells (9 reasons × 2 horizons), m=72 (× 4 axes). Confirmed: `(5 testable + 4 absent) × 2 × 4 = 72`; 40 valid p-values (5 testable × 2 × 4), 32 nan slots (4 absent × 2 × 4). Arithmetic exact.
- No unregistered trial is presented as primary. The two post-hoc adaptations (taxonomy source-column remap; align_tier=NaN exclusion) are disclosed inline and in `post_hoc_trials_recorded`, not laundered into the primary grid.

### Check 2 — Era / stamp discipline — **PASS**
- Primary stats filtered to `verdict_grade==True` (confirmed: `terminal_state_rates` runs only on `primary` = vg==True subset).
- Effective window `2022-06-30 → 2026-07-02` stated in preamble, results.json, and RESULTS.md; matches §APPROVAL clause 1.
- Note (not a defect): `survivor_bias` is `False` for **all** 961,656 rows, and **all** vg==True rows already fall inside the window (recomputed: 0 vg rows outside era). So the "0 stamped rows excluded" and the survivor-appendix "no stamped rows to route" statements are literally correct for this substrate, not an omission.

### Check 3 — Independent recompute — **PASS** (see table above)

### Check 4 — BH family — **PASS**
- Family size m=72 as registered; p-value pooling is across all 18 cells × 4 axes simultaneously (single family `ei_gate_pnl`), matching the PREREG definition.
- BH step-up + right-to-left monotonicity implemented correctly. Since min raw p = 0.4749 and 0.10/72 = 0.00139, `n_significant = 0` is arithmetically forced and correctly reported.
- Sign-stability halves executed (midpoint 2024-05-01) and printed per reason as registered.

### Check 5 — n-floors / INSUFFICIENT-POWER — **PASS (with ADVISORY, see D1)**
- INCONCLUSIVE returned for the 4 zero-row reasons; no borrowing of pre-2021 or cross-reason rows. n-floor logic (INCONCLUSIVE<10, DEMOTE≥25, FLIP≥50) matches PREREG §Primary statistics.
- All 4 absent reasons retained in the BH family (counted in m) rather than dropped — correct per PREREG §178.

### Check 6 — Honesty surface — **PASS (with DEVIATION, see D1)**
- RESULTS.md leads with verdict; plain-English box present; mandatory stamp text present; `board_rank_unresolved` treated descriptively-only per §APPROVAL clause 4. Leak-audit section present with the required GICS-reclassification disclosure.
- DEVIATION: the "not present in replay data (0 rows)" framing for `freshness_expired` and `tier_cutoff` is column-literal but semantically incomplete (D1).

---

## Deviations & findings

### D1 — DEVIATION (ADVISORY, does not change any verdict): 2 of 4 "absent" reasons have discoverable semantic cohorts
The runner reports `freshness_expired`, `tier_cutoff`, `event_blackout`, `cohort_null` as "not present in replay data (0 rows)." True at the `rejection_reason`/`board_reason` **column** level. But my recompute shows:
- **`freshness_expired`**: `gate_reason` free-text carries the exact FRESH-window semantics. Within the era, the "…no longer a fresh entry" text with `verdict_type=near_miss` and `rejection_reason=nan` (15,022 rows) is present but untagged; the "cross 2+ ticks ago — no longer a fresh entry" (7,319) and "forming master already topping" (4,960) variants exist in the broader frame. The topped variant (92,715) is 1:1 the `not_topped_veto` cohort, so freshness is partly **conflated into** not_topped_veto, not absent.
- **`tier_cutoff`**: `gate_reason` carries `tier T2/T3/T4 (weight …)` for 10,569 rows; specifically **`tier T4 (weight 0.4)` = 131 rows** with `verdict_type ∈ {rejection(100), near_miss(31)}` — this is exactly the PREREG's "confluence_tiers T4-excluded / below-tier threshold." A T4 cohort of ~100 rejection rows is **above the n≥10 INCONCLUSIVE floor and near the n≥25 DEMOTE floor** — it was testable, not absent.

**Impact:** Neither would flip the headline. `tier_cutoff` at n≈100 could have produced a genuine (non-nan) p-value instead of a nan slot; had it been non-significant (overwhelmingly likely given every other cohort sits at raw-p≈0.48), the verdict stays KEEP and `n_significant` stays 0. So the **scientific conclusion is unchanged**, but the RESULTS.md "0 rows / INSUFFICIENT_N" honesty statement for these two reasons is **inaccurate** and should read "not tagged as a distinct `rejection_reason` code; semantic cohort recoverable via `gate_reason` free-text (freshness) / `tier T4` gate_reason (tier_cutoff) — deferred pending a structured taxonomy tag." `event_blackout` and `cohort_null` I confirmed genuinely absent (0 token hits anywhere). This is ADVISORY, not BLOCKING, because it does not alter a verdict — but it is a real overstatement of substrate absence and the re-run recommendation to Fable should name freshness/tier as *recoverable-now*, not *TBD*.

### D2 — DESIGN LIMITATION confirmed and, if anything, UNDERSTATED (BLOCKING for the 3 board-demotion verdicts' interpretability)
The runner flags that board-level demotions are matched back into the fire population they were drawn from. My recompute shows this is more severe than stated: the **entire matchable fire pool is only 10,365 rows**, composed of 7,894 `board_rejection` (demoted) + 2,471 `board_fire` (accepted). The genuine counterfactual (demoted vs accepted) is diluted to **~24%** of the comparison; knife_demote alone is **49.9%** of its own matched pool. The near-zero deltas for extension/knife/sector_cap are therefore **mechanically induced**, and their KEEP verdicts carry **no counterfactual information** — they should be read as "test not identified," effectively INCONCLUSIVE, not KEEP. The runner's blocker text says "near-zero by construction"; the review confirms the mechanism and rates the three board-demotion KEEP labels as **non-informative**. Because `board_fire` rows (2,471 matchable) DO exist, a within-fire demoted-vs-accepted design was constructible; the runner correctly declined to improvise it under §APPROVAL clause 4 ambiguity and raised it as a blocker to Fable — that escalation is **conformant behavior**.

### D3 — ADVISORY: align_tier coverage collapse
Recomputed align_tier non-null coverage in primary = **13.2%** overall; not_topped_veto = **5.1%** (report says 4.7%; my 5.1% is on all-primary ntv vs the report's within-window slice — within <1% tolerance and directionally identical). The matched cohort is a heavily selected 5% sub-population. The runner discloses this inline and as a blocker. Verdict interpretability for not_topped_veto is bounded accordingly; correctly surfaced, no concealment.

---

## Final reviewer verdict

**CONFORMANT WITH DEVIATIONS.** The study is statistically faithful (every recomputed headline exact), the BH family and n-floor discipline are correct, INSUFFICIENT-POWER is returned honestly rather than borrowed, and the two structural blockers (taxonomy mismatch, board-demotion confound) are real and correctly escalated to Fable rather than papered over. Two deviations temper the honesty surface: (D1) `freshness_expired`/`tier_cutoff` are mislabeled "absent" when their cohorts are recoverable — ADVISORY, no verdict change; (D2) the three board-demotion KEEP verdicts are non-informative by construction and should be treated as INCONCLUSIVE — BLOCKING for their interpretation but already flagged by the runner. **No verdict in the report is overturned by this review.** Recommend Fable (a) correct the RESULTS.md "0 rows" language for freshness/tier to "untagged, recoverable via gate_reason," (b) re-cast the three board-demotion KEEPs as INCONCLUSIVE pending a demoted-vs-`board_fire` re-design, and (c) extend the replay harness to emit structured `rejection_reason` codes for freshness_expired and tier_cutoff before P1.2 re-run.
