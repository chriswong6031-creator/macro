# P3 Kernel-Rank Shadow — Build Report

**Study:** P3_KERNEL_RANK_SHADOW
**Program:** Entry Intelligence (EI)
**PREREG:** `research/entry_intel/P3_KERNEL_RANK_PREREG.md` (APPROVED, Fable 2026-07-05)
**Build date:** 2026-07-05
**Author:** Sonnet subagent under Fable orchestration
**Status:** SHADOW_ACTIVE — no board wiring, no user-visible surface (Article 2 / R6)

---

## In plain English

We have five features that P1 showed correlate with whether a stock works out well after the signal fires. This build combined them into a single data-driven score — the **kernel rank** — and logged it alongside every historical board fire without changing what anyone sees.

The process: for each combination of feature value, market regime, and time horizon, we estimated the probability of a good outcome (stock cushioned or lifted cleanly) using a conservative statistical approach (Bayesian shrinkage toward the parent cell mean, penalizing thin cells). Three features contributed to a weighted average score, with more weight given to features that showed stronger effects in Phase 1. That score is now saved beside every historical signal.

The concordance gate for `cohort_washout_proximity` (the washout proximity feature) is not yet resolved — no `concordance_check.json` artifact was present at build time. Per the pre-registered fallback rule, that feature is omitted from this build; the three remaining features use weights summing to 0.86. When the concordance GO artifact is produced by the P2.1b runner, the build should be re-run to include the fourth feature.

The score's predictions are logged in the forward ledger. Every three months, once 300 independent episode clusters have accrued with verdicts, we check: does the new score predict good outcomes better than the current formula? If yes with the required statistical threshold — the flip criterion fires and Fable reviews. Nothing visible changes until that happens.

---

## 1. Preamble

| Item | Value |
|------|-------|
| PREREG | `P3_KERNEL_RANK_PREREG.md` (APPROVED 2026-07-05) |
| Memo citation | P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments |
| Replay artifact | `data/replay/replay_boarded.parquet` |
| Replay MD5 | `906175f9eb8caa351ed6d7d5c56265d3` (matches expected) |
| Replay shape | 961,656 rows × 66 cols |
| Total fires (all) | 57,640 |
| **Verdict-grade fires (primary)** | **49,939** |
| Episode clusters | 22,295 |
| Horizon-censored fires (pre-excluded) | 7,701 |
| Stamped rows excluded | 0 (all survivor_bias=False) |
| Effective verdict window | 2022-06-30 → 2025-12-29 |
| Pre-2021 rows | 0 (none in artifact) |
| good_21d base rate | 0.4394 |
| good_63d base rate | 0.3709 |

**Proxy-source status per feature dimension:**

| Feature | Proxy-sourced | Status in this build |
|---------|--------------|---------------------|
| `dist_52wh` | No (Massive-sourced direct) | Included |
| `cohort_washout_proximity` | YES — 100% proxy-sourced (P1.1 REVIEW A1) | **OMITTED** — concordance_check.json absent |
| `ext_z` | No | Included |
| `ext_atr` | No | Included |
| `weekly_phase` | No | Included as conditioning dimension (weight=0) |

---

## 2. Feature bucket breakpoints

Breakpoints computed on the 49,939 verdict-grade fires at run start (pre-registered; no search).

| Feature | Q25 | Q50 | Q75 |
|---------|-----|-----|-----|
| `dist_52wh` (via `dist_to_52wh`) | −0.2779 | −0.1644 | −0.0701 |
| `ext_z` | −1.0500 | −0.2600 | 0.7200 |
| `ext_atr` | −4.6930 | −0.7640 | 4.2920 |

| Feature | Buckets |
|---------|---------|
| `cohort_washout_proximity` | NEAR (True; 22,965 fires), NOT_NEAR (False; 26,974 fires) |
| `weekly_phase` | BASING, BEAR_RECOVERING, TURNING, RISING, ROLLING, FALLING, UNKNOWN |

---

## 3. Cell table summary

| Metric | Value |
|--------|-------|
| Total cells built | 94 |
| THIN cells (n_eff < 25) | 0 |
| Cells falling back to parent | 0 |
| Horizons | {21d, 63d} |

All cells have adequate n_eff. No THIN fallback required in this historical build. This is expected: with 22,295 episode clusters across just 5 features × 4 buckets × 2 regimes × 2 horizons, all cells have well above 25 episode clusters.

### Top 10 cells by wilson_lo at 21d (parent level)

| Feature | Bucket | n_eff | shrunken_p | wilson_lo |
|---------|--------|-------|-----------|-----------|
| weekly_phase | UNKNOWN | 1,210 | 0.5331 | 0.5096 |
| ext_z | Q1 | 5,618 | 0.5008 | 0.4898 |
| dist_52wh | Q1 | 5,576 | 0.4958 | 0.4848 |
| cohort_washout_proximity | NEAR | 9,581 | 0.4919 | 0.4835 |
| ext_atr | Q2 | 6,225 | 0.4731 | 0.4627 |
| dist_52wh | Q2 | 5,903 | 0.4682 | 0.4575 |
| weekly_phase | BEAR_RECOVERING | 11,633 | 0.4552 | 0.4476 |
| ext_atr | Q1 | 5,660 | 0.4574 | 0.4465 |
| ext_z | Q2 | 6,431 | 0.4424 | 0.4322 |
| ext_atr | Q3 | 6,505 | 0.4254 | 0.4153 |

### Bottom 10 cells by wilson_lo at 21d (parent level)

| Feature | Bucket | n_eff | shrunken_p | wilson_lo |
|---------|--------|-------|-----------|-----------|
| dist_52wh | Q4 | 6,323 | 0.3864 | 0.3764 |
| weekly_phase | BASING | 128 | 0.4228 | 0.3536 |
| weekly_phase | FALLING | 282 | 0.3779 | 0.3312 |
| weekly_phase | ROLLING | 933 | 0.3546 | 0.3289 |
| weekly_phase | TURNING | 61 | 0.3570 | 0.2634 |

### Wilson_lo distribution

| Horizon | Mean | Std | Min | Max |
|---------|------|-----|-----|-----|
| 21d | 0.4101 | 0.0621 | 0.2532 | 0.5104 |
| 63d | 0.3469 | 0.0339 | 0.2711 | 0.4103 |

**Directional sanity check:** the score correctly separates outcomes in the expected direction.

| Horizon | Mean score (good outcome) | Mean score (bad outcome) | Difference |
|---------|--------------------------|--------------------------|------------|
| 21d | 0.4314 | 0.4244 | +0.0070 |
| 63d | 0.3604 | 0.3577 | +0.0027 |

The positive difference confirms the kernel-rank score ranks good-outcome fires higher. The effect is small (as expected for a conservative Wilson lower bound on historical in-sample cells) — the prospective ledger is the proper evaluation surface.

---

## 4. Combination weight confirmation

**Concordance GO: False** — `concordance_check.json` absent at build time.

Active features in this build: `{dist_52wh, ext_z, ext_atr}` (washout omitted per pre-registered fallback).

| Feature | |ρ_21d| weight | Active |
|---------|-------------|--------|
| `dist_52wh` | 0.34 | Yes |
| `cohort_washout_proximity` | 0.31 | **No (concordance absent)** |
| `ext_z` | 0.28 | Yes |
| `ext_atr` | 0.24 | Yes |
| `weekly_phase` | 0.00 (categorical) | Conditioning dimension only |

Combination denominator: **Σwᵢ = 0.86** (fallback, per PREREG §3.5).

When `concordance_check.json` with a GO verdict is produced by the P2.1b runner, re-run this build to include `cohort_washout_proximity` at weight 0.31 (Σwᵢ = 1.17).

---

## 5. Leak audit

1. **Fill rule:** entry = first close strictly after `signal_date`. Inherited from replay grader (PIT-stamped by P0.1). Not re-estimated.
2. **Feature freeze:** all features read from `replay_boarded.parquet` at the row's `signal_date` (PIT-stamped by P0.1 design contract). No feature computed from future data.
3. **No feedback from outcomes:** no feature is a transformation of `state_8_21` or `state_15_126`. All features are pre-signal attributes logged at signal time.
4. **Era boundary:** primary window 2022-06-30 → 2025-12-29 (v1.1 Amendment 1, 250-bar MTF warmup). Actual effective window in this build: 2022-06-30 → 2025-12-29.
5. **Proxy-sourced dimensions:** `cohort_washout_proximity` is OMITTED in this build (concordance GO absent). No proxy-sourced feature contributes to the score.
6. **Wilson CI denominator:** `n_eff_effective = n_eff + K_SHRINK`. Matches the pooled_edges construction in `engine/pooling.py` / `kernel.py`. No denominator mixing.
7. **THIN cells:** all cells above the 25 episode-cluster floor. No THIN fallback was triggered in this build.

---

## 6. Shadow artifact outputs (R9 — not git-committed)

| Artifact | Path | Schema |
|----------|------|--------|
| Shadow parquet | `data/replay/kernel_rank_shadow.parquet` | 49,939 rows × 21 cols |
| Cell table | `data/signal_archive/kernel_rank_cells.parquet` | 94 rows × 17 cols |
| Forward ledger | `data/signal_archive/kernel_rank_ledger.parquet` | 49,939 rows × 17 cols |
| Build metadata | `research/entry_intel/p3_runs/build_meta.json` | — |

**Shadow artifact columns (key):**
- `signal_date`, `ticker`, `episode_id`, `survivor_bias`
- `kernel_rank_score_21d`, `kernel_rank_source_cell_21d`, `kernel_rank_proxy_flags_21d`
- `kernel_rank_score_63d`, `kernel_rank_source_cell_63d`, `kernel_rank_proxy_flags_63d`
- `fwd_ret_21`, `fwd_ret_63`, `good_21d`, `good_63d`
- `concordance_go`, `weights_sum`, `active_features`, `K_SHRINK`, `WILSON_Z`

---

## 7. Article 2 flip criterion (pre-registered)

The shadow period has begun. The flip criterion is evaluated quarterly once the forward ledger has ≥ 300 independent episode clusters with non-null `good_21d` outcomes.

**Flip criterion (all three must hold simultaneously):**
1. `n_episode_clusters ≥ 300` (prospective forward ledger)
2. Permutation p (one-sided, kernel_rank vs incumbent on good_21d) < 0.10
3. Wilson lower bound on the difference (top-quartile kernel good rate minus top-quartile incumbent good rate) > 0.0

**Flip does NOT auto-apply.** Fable reviews and approves (or declines) any board sort order change.

**Kill criterion:** if the flip criterion has not fired within 24 months of the first forward-ledger row, the kernel-rank design is retired and the incumbent formula remains in place.

---

## 8. Next steps

1. **P2.1b concordance gate:** produce `research/entry_intel/p1_runs/P1_3/concordance_check.json` with a GO verdict (≥ 90% concordance on overlapping names between proxy and production COILED/S1 values). Then re-run `build_kernel_rank_shadow.py` to include `cohort_washout_proximity` (Σwᵢ = 1.17).
2. **Nightly runner:** wire the shadow score computation into the nightly board pipeline to append prospective rows to `data/signal_archive/kernel_rank_ledger.parquet` as each day's fires come in.
3. **Quarterly evaluation:** implement `evaluate_kernel_rank_flip.py` to run the §5 flip criterion check. First evaluation: ~63 trading days after first prospective row.
4. **Flip criterion approval:** alert Fable when the flip criterion fires. Do NOT auto-apply board changes.

---

*Build report produced by `research/entry_intel/p3_runs/build_kernel_rank_shadow.py` | 2026-07-05.*
*This document is a factual record of the build outputs. The PREREG is never edited to accommodate observed outcomes.*
