# REVIEW — P3 Kernel-Rank Shadow

**Branch reviewed:** `origin/ei/p3-kernel-shadow` (PR #1473)
**Base:** `origin/ei/p2-board-stack` (merge-base `09767d54`)
**Spec:** `research/entry_intel/P3_KERNEL_RANK_PREREG.md` (APPROVED Fable 2026-07-05)
**Reviewer:** EI Phase-2 review subagent under Fable orchestration
**Date:** 2026-07-05
**Method:** cumulative PR diff via `git show origin/ei/p3-kernel-shadow:<path>` (no shared checkout); independent recomputation of cell posteriors, per-fire scores, base rates, breakpoints from `data/replay/replay_boarded.parquet`; artifact inspection of the R9 outputs.

**VERDICT: CLEAN — stage may be built upon.**

The build faithfully implements P3_KERNEL_RANK_PREREG.md. Every registered numeric decision was re-derived independently and matches. The washout-omitted fallback branch is correctly triggered by the absent concordance artifact. Zero board/user-visible wiring. Two ADVISORY findings, none blocking.

---

## Diff surface

Only 3 files added, all under `research/entry_intel/p3_runs/`:
- `build_kernel_rank_shadow.py` (1,023 lines)
- `P3_KERNEL_RANK_BUILD_REPORT.md` (201 lines)
- `build_meta.json` (90 lines)

No `site/`, `templates/`, `engine/`, or board-pipeline file is touched. R9 data parquets (`data/replay/kernel_rank_shadow.parquet`, `data/signal_archive/kernel_rank_cells.parquet`, `data/signal_archive/kernel_rank_ledger.parquet`) are written to disk and correctly NOT committed. Confirmed no import of any Neural Web money-path consumer; the only `reorder`/`kernel_rank` matches in the diff are comment/log lines asserting "never used to reorder."

---

## Per-AC results

| # | Acceptance criterion (prereg) | Result | Evidence |
|---|---|---|---|
| 1 | Cites P0_MEASUREMENT_MEMO v1.0 + §6 v1.1; primary window 2022-06-30 → last-full-replay | PASS | preamble + build; era recomputed 2022-06-30 → 2025-12-29 |
| 2 | Replay MD5 gate `906175f9…265d3` | PASS | recomputed MD5 matches; artifact present |
| 3 | Population = fire ∧ verdict_grade ∧ ¬survivor_bias = 49,939 fires / 22,295 episodes | PASS | independently recomputed: 49,939 fires, 22,295 episodes, 0 pre-2021 rows |
| 4 | Base rates 21d/63d | PASS | recomputed 0.439396 / 0.370933 — matches meta to 6 dp |
| 5 | Breakpoints (dist_52wh, ext_z, ext_atr quartiles) | PASS | recomputed identical to meta (dist −0.2779/−0.1644/−0.0701; ext_z −1.05/−0.26/0.72; ext_atr −4.693/−0.764/4.292) |
| 6 | Washout binary split NEAR/NOT_NEAR (22,965 / 26,974) | PASS | recomputed 22,965 / 26,974 exactly |
| 7 | K_SHRINK=10, two-tier shrink toward parent→grandparent→global base rate | PASS | 5 independent cell recomputes match shrunken_p to 4 dp |
| 8 | Wilson lower bound, z=1.645, n_eff_effective = n_eff+K | PASS | 5 independent wilson_lo recomputes match to 4 dp |
| 9 | Episode-clustered n_eff (co-firing collapse) | PASS | `drop_duplicates(episode_id)`; recomputed n_eff match |
| 10 | THIN threshold 25 episode clusters, parent fallback | PASS (vacuous) | code path correct; 0 THIN cells in this historical build (all cells well above 25) — consistent with 22,295 episodes over a shallow grid |
| 11 | Concordance gate reads `p1_runs/P1_3/concordance_check.json`; absent → omit-and-renormalize fallback (Σw=0.86, 3 features) | PASS | file confirmed ABSENT at build time; branch took fallback; `weights_sum=0.86`, `active_features=[dist_52wh, ext_z, ext_atr]`, no proxy dims |
| 12 | Combination formula = weighted mean of Wilson LBs, weights 0.34/0.28/0.24, denom 0.86 | PASS | 3 sample fires recomputed to <1e-4 (residual = stored-breakpoint float rounding) |
| 13 | weekly_phase weight 0.00 (excluded from combination, retained as conditioning cell) | PASS | not in active_features; source-cell strings carry only the 3 weighted features |
| 14 | All 49,939 fires scored at both 21d and 63d | PASS | shadow parquet: 49,939 scored, 0 missing, both horizons |
| 15 | Directional sanity (good-outcome fires score higher) | PASS | recomputed 21d +0.0070, 63d +0.0027 |
| 16 | Shadow column ONLY — no board reorder, no user-visible surface | PASS | diff touches no board/site/template files; `board_wiring=false`, `user_visible=false` |
| 17 | Forward ledger carries incumbent_rank_score + kernel_rank_score + fwd returns + proxy flags | PASS | ledger 49,939×17; `incumbent_rank_score` 49,939 non-null (from `weight`); survivor_bias all False |
| 18 | Article-2 flip criterion fields: n_floor=300, perm p<0.10, Wilson LB>0, N_PERM=5000, kill=24mo | PASS | present in build_meta.article2_flip_criterion |
| 19 | 63d terminal state column choice | PASS | `state_15_126` is the only 63d terminal-state column in the artifact; base rate 0.3709 matches |
| 20 | Per-row Massive-source confirmation | PASS (see ADVISORY-2) | `price_source == 'massive'` for all 49,939 fires (verified); script prints it as a hardcoded stamp rather than deriving it |

---

## Independent recomputation detail

Recomputed 5 parent-level cell posteriors at 21d from raw replay (episode-collapse → shrink toward grandparent (which shrinks toward global base rate) → Wilson LB, z=1.645, n_eff+10 denom). All match the committed report/cell-table to 4 decimals:

| Cell | n_eff (mine / report) | shrunken_p | wilson_lo |
|---|---|---|---|
| ext_z:Q1 | 5,618 / 5,618 | 0.5008 | 0.4898 |
| dist_52wh:Q1 | 5,576 / 5,576 | 0.4958 | 0.4848 |
| washout:NEAR | 9,581 / 9,581 | 0.4919 | 0.4835 |
| dist_52wh:Q4 | 6,323 / 6,323 | 0.3864 | 0.3764 |
| weekly_phase:UNKNOWN | 1,210 / 1,210 | 0.5331 | 0.5096 |

Per-fire kernel_rank_score recomputed for fires {0, 12345, 49938}: matched shadow parquet to <1e-4, denominator 0.86 in every case.

---

## Findings

### BLOCKING
None.

### ADVISORY

**ADVISORY-1 — prereg-internal flip-floor inconsistency (not a build defect; flag to Fable for the evaluator wave).**
The prereg header and footer cite Fable ruling **R-P2.1 as "flip floor = 100 clusters + 2 quarters"**, while the operative body (§5.2, §5.4, §7 trial ledger, §11, plain-English §) uniformly specifies **300 episode clusters** with no "2 quarters" clause. The build's `build_meta.json` encodes `n_floor_episode_clusters: 300` and omits any "2 quarters" gate. The build correctly follows the operative body of its approved prereg, so this is not a build error. However, the R-P2.1 header text and the §5.2 body disagree on both the cluster floor (100 vs 300) and the presence of a "+2 quarters" requirement. The flip-criterion evaluator (`evaluate_kernel_rank_flip.py`) is out of scope for this build (listed as a next step), so nothing is mis-implemented yet — but Fable should reconcile R-P2.1 vs §5.2 before the evaluator is built, and the evaluator must encode whichever is canonical (and the "+2 quarters" cadence gate if it survives reconciliation).

**ADVISORY-2 — Massive-source stamp is asserted, not derived.**
The prereg §5 checklist requires "Confirms via per-row source stamp that all cell-construction rows are Massive-sourced." The script prints this as a hardcoded string (line 246: "all rows Massive-sourced ... delisted-name recall verified 100%") rather than computing it from the `price_source` column present in the replay. I verified independently that the claim is factually TRUE (`price_source == 'massive'` for all 49,939 fires), so there is no data integrity issue. Recommend a one-line derived assertion (`assert (fires.price_source == 'massive').all()`) in any future re-run so the stamp cannot silently drift if the replay is rebuilt with mixed sources.

---

## Notes for downstream

- The cell table (`kernel_rank_cells.parquet`, 94 rows) contains diagnostic cells for all 5 features including `cohort_washout_proximity` and `weekly_phase`, but the shadow SCORE correctly consumes only the 3 active features. This is correct: cells are built for the full feature set (diagnostic) while the combination respects the fallback active set.
- When P2.1b produces `concordance_check.json` with a GO verdict, the build must be re-run to add `cohort_washout_proximity` at weight 0.31 (Σw → 1.17) and set `proxy_sourced=True` on those cells. The report documents this next step correctly.
- The `state_15_126` naming (126-bar lookback for the 63d verdict) is the only 63d terminal-state column in the artifact and is used correctly; there is no alternative 63-lookback column to confuse it with.
