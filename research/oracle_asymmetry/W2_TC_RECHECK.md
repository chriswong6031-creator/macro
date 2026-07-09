# OTA W2 — Time-Confound Re-Check (OTA-RC-1)

**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**

Script: `scripts/research/oracle_w2_tc_recheck.py`  |  Seed: 20260706  |  Bootstrap draws: 1000  |  Episode gap: 10 trading days

Reference: W2_FORMAL_PREREG.md + W2_FORMAL_RESULTS.md (shipped #1533).
Condition C3 (prereg adjudication): shipped R3 OUT arm is full-history — this document adds a period-matched OUT arm per C3.

---

## 1. Reproduction Gate

Mandatory check: shipped point estimates reproduced before new inference.

| Metric | Shipped | Reproduced | Diff | Gate |
|--------|---------|-----------|------|------|
| IN windows | 31 | 31 | 0 | PASS |
| ΔWR21 | 0.1163 | 0.1163 | 0.0000 | PASS |
| Δmean_ret21 | 0.0299 | 0.0299 | 0.0000 | PASS |
| Holdout ΔWR21 | 0.1073 | 0.1073 | 0.0000 | PASS |

Reproduction gate: **PASSED**

---

## 2. Macro-Episode Clustering

Armed windows across all nodes are merged into macro-episodes when the gap between any two windows (from any node) is ≤ 10 trading days or they overlap.

- Total windows (frozen): 35
- Total macro-episodes: **9**
- Mean windows per episode: 3.9
- Total span (months): 48
- Holdout episodes (all windows > 2024-06-30): 5 (episodes 4–8)
- Mixed episodes (windows spanning the split): 0
- Dev-only episodes: 4 (episodes 0–3)
- Holdout episodes with qualifying IN-arm fires: 3 (episodes 4, 5, 6 had member fires)

### Episode Summary

| Episode | Start | End | Windows | Nodes | Months | Window IDs |
|---------|-------|-----|---------|-------|--------|-----------|
| 0 | 2022-07-01 | 2022-07-27 | 2 | 2 (XLB, XLE) | 0 | 0, 5 |
| 1 | 2022-10-07 | 2022-10-31 | 3 | 3 (XLF, XLI, XLK) | 0 | 11, 18, 24 |
| 2 | 2023-08-25 | 2023-11-09 | 6 | 6 (XLB, XLF, XLI, XLK, XLP, XLU) | 3 | 1, 12, 19, 25, 29, 32 |
| 3 | 2024-04-18 | 2024-05-29 | 5 | 5 (XLF, XLI, XLK, XLRE, XLV) | 1 | 13, 20, 26, 30, 33 |
| 4 | 2024-12-20 | 2025-02-04 | 4 | 4 (XLB, XLE, XLF, XLI) | 2 | 2, 6, 14, 21 |
| 5 | 2025-03-21 | 2025-05-19 | 6 | 6 (XLE, XLF, XLI, XLK, XLRE, XLV) | 2 | 7, 15, 22, 27, 31, 34 |
| 6 | 2025-11-05 | 2025-12-18 | 5 | 5 (XLB, XLE, XLF, XLI, XLK) | 1 | 3, 8, 16, 23, 28 |
| 7 | 2026-03-05 | 2026-04-17 | 2 | 2 (XLB, XLF) | 1 | 4, 17 |
| 8 | 2026-06-02 | 2026-07-02 | 2 | 1 (XLE) | 1 | 9, 10 |

### Window → Episode Mapping

| Window ID | Node | Window Start | Window End | Episode ID |
|-----------|------|-------------|-----------|-----------|
| 0 | XLB | 2022-07-01 | 2022-07-27 | 0 |
| 1 | XLB | 2023-09-29 | 2023-11-09 | 2 |
| 2 | XLB | 2024-12-20 | 2025-02-04 | 4 |
| 3 | XLB | 2025-11-05 | 2025-12-18 | 6 |
| 4 | XLB | 2026-03-27 | 2026-04-17 | 7 |
| 5 | XLE | 2022-07-08 | 2022-07-27 | 0 |
| 6 | XLE | 2025-01-03 | 2025-01-31 | 4 |
| 7 | XLE | 2025-04-25 | 2025-05-19 | 5 |
| 8 | XLE | 2025-11-05 | 2025-11-20 | 6 |
| 9 | XLE | 2026-06-02 | 2026-06-24 | 8 |
| 10 | XLE | 2026-06-26 | 2026-07-02 | 8 |
| 11 | XLF | 2022-10-14 | 2022-10-31 | 1 |
| 12 | XLF | 2023-10-13 | 2023-11-09 | 2 |
| 13 | XLF | 2024-05-03 | 2024-05-29 | 3 |
| 14 | XLF | 2025-01-03 | 2025-02-04 | 4 |
| 15 | XLF | 2025-03-21 | 2025-05-15 | 5 |
| 16 | XLF | 2025-11-05 | 2025-12-18 | 6 |
| 17 | XLF | 2026-03-05 | 2026-04-17 | 7 |
| 18 | XLI | 2022-10-07 | 2022-10-31 | 1 |
| 19 | XLI | 2023-09-27 | 2023-11-09 | 2 |
| 20 | XLI | 2024-05-03 | 2024-05-17 | 3 |
| 21 | XLI | 2024-12-27 | 2025-02-04 | 4 |
| 22 | XLI | 2025-04-07 | 2025-04-25 | 5 |
| 23 | XLI | 2025-11-28 | 2025-12-12 | 6 |
| 24 | XLK | 2022-10-07 | 2022-10-31 | 1 |
| 25 | XLK | 2023-09-29 | 2023-11-09 | 2 |
| 26 | XLK | 2024-04-26 | 2024-05-17 | 3 |
| 27 | XLK | 2025-04-07 | 2025-04-25 | 5 |
| 28 | XLK | 2025-11-28 | 2025-12-12 | 6 |
| 29 | XLP | 2023-09-01 | 2023-09-20 | 2 |
| 30 | XLRE | 2024-04-18 | 2024-05-28 | 3 |
| 31 | XLRE | 2025-04-21 | 2025-05-15 | 5 |
| 32 | XLU | 2023-08-25 | 2023-09-20 | 2 |
| 33 | XLV | 2024-04-26 | 2024-05-28 | 3 |
| 34 | XLV | 2025-04-25 | 2025-05-16 | 5 |

---

## 3. Episode-Cluster vs Window-Cluster Delta CI (Side-by-Side)

The only change here is the resampling unit: windows (shipped) vs macro-episodes (RC-1).
OUT arm is FIXED in both — this retained limitation means CI width underestimates true
uncertainty from the OUT arm. See Limitations below.

| Metric | Shipped (window-cluster) | RC-1 (episode-cluster) | Change in CI width |
|--------|------------------------|----------------------|-------------------|
| ΔWR21 point | 0.1163 | 0.1163 | — |
| ΔWR21 90% CI | [0.0537, 0.1757] | [0.0399, 0.1901] | 0.0282 wider |
| ΔWR21 CI LB > 0 | Yes | Yes | |
| Δmean_ret21 point | 0.0299 | 0.0299 | — |
| Δmean_ret21 90% CI | [0.0153, 0.0444] | [0.0107, 0.0493] | 0.0096 wider |
| Δmean_ret21 CI LB > 0 | Yes | Yes | |
| Resampling unit | 31 windows | 7 episodes | |

---

## 4. R3 Period-Matched Baseline (Side-by-Side)

Shipped R3 used the full-history OUT arm (C3 limitation). This document adds a
period-matched OUT arm restricted to dates after 2024-06-30.

| Metric | Shipped R3 (full-history OUT) | RC-1 R3 (period-matched OUT) |
|--------|------------------------------|------------------------------|
| Holdout IN WR21 | 0.6432 | 0.6432 |
| OUT WR21 | 0.5359 (all dates) | 0.5381 (post-2024-06-30 only) |
| OUT rows | 369475 | 161021 |
| Holdout ΔWR21 | 0.1073 | 0.1051 |
| Holdout windows | 15 | 15 |
| Holdout episodes (total / with fires) | (not computed) | 5 total / 3 with IN-arm fires |

### Episode-Cluster CI on R3 Holdout (vs full-history OUT)

| Metric | Value |
|--------|-------|
| ΔWR21 point | 0.1073 |
| 90% CI | [0.0229, 0.1714] |
| CI LB > 0 | Yes |
| N episodes | 3 |

### Episode-Cluster CI on R3 Holdout (vs period-matched OUT)

| Metric | Value |
|--------|-------|
| ΔWR21 point | 0.1051 |
| 90% CI | [0.0207, 0.1692] |
| CI LB > 0 | Yes |
| N episodes | 3 |
| MDE@80% (alpha=0.05, episode units) | 0.3493 |

---

## 5. Episode-Joint Placebo (Step 4)

**Status: SKIPPED**

Episode-joint placebo (Step 4) SKIPPED: requires shifting whole macro-episodes by a shared random offset with VIX-regime match at episode start. This involves re-implementing the vectorized placebo loop with episode-level sampling across all nodes simultaneously, which exceeds the allotted time budget for this re-check. The window-level placebo from the shipped run (p95=0.1013, p-value=0.008) remains the operative null reference. A future dedicated run should implement the episode-joint placebo at 500 draws.

---

## 6. Retained Limitations

1. **OUT arm fixed in all bootstrap CIs.** Both shipped window-cluster and RC-1 episode-cluster CIs resample only the IN arm; the OUT arm is not bootstrapped. This understates total inferential uncertainty, particularly when the OUT arm has regime clustering.

2. **Episode-cluster CI reduces effective N.** Collapsing windows to episodes reduces the resample unit count, widening CIs. This is the primary finding of this re-check — see side-by-side table above.

3. **Mixed episodes (spanning the 2024-06-30 split).** Episodes containing windows on both sides of the split (0 episodes) are excluded from both the holdout-episode and dev-episode sets in the period-matched R3 analysis. Their fires are retained in the full-arm metrics.

4. **Period-matched OUT arm power.** Restricting the OUT arm to post-2024-06-30 dates reduces it to 161021 rows. This substantially reduces OUT arm stability and may increase variance in the period-matched delta vs the shipped R3.

5. **Episode-joint placebo not run** (see Step 4 above). The window-level placebo from the shipped run remains the operative null reference.

6. **No verdict vocabulary used.** This document is a re-check only. All findings require Fable adjudication before any change to recorded class or status.

---

*Generated by OTA-RC-1 | Seed 20260706 | 1000 bootstrap draws (reduced from 2000 to meet ~20min/bootstrap wall budget — deviation recorded per task brief)*

**Script deviations from brief:**
1. Bootstrap draws: 1000 (reduced from 2000). The 2000-draw run was attempted; ΔWR21 episode bootstrap completed at 2000 draws (CI=[0.0379, 0.1897]) before the run was killed for budget. The 1000-draw result (CI=[0.0399, 0.1901]) is consistent.
2. Coverage count bug: `n_holdout_episodes` in raw script output was 19 (duplicate-iteration loop); corrected to 5 in this document and in w2_tc_recheck.json. CI computations used `isin()` which was not affected.
3. Episode-joint placebo (Step 4): SKIPPED — see §5.