# P1.3 Trio Ablation — RESULTS (v2, ROUND 2 — defect-corrected re-run)

> **SUPERSEDED IN PART (2026-07-07, RC-RUL-1 — research/TIME_CONFOUND_RECHECK_ADJUDICATION.md).**
> The EI-RC-1 re-check (`P1_3_TC_RECHECK/RESULTS.md`, PR #1866) re-ran this study's
> inference under within-month demeaning + month-block bootstrap (events frozen,
> reproduction exact). T24 and T21 — the entire F3 "SHIPS-AS-HARD-GATE" evidence —
> collapse to zero (T24: −5.00pp → +0.04pp, CI [−3.66, +3.27]); T09 (F1-RW) likewise
> (+0.01pp). **The F3 hard-gate designation is WITHDRAWN; anti-chase remains
> shadow-only (P2.1a), and the flip now additionally requires a DT-R14-compliant
> read of the forward ledger.** T02 (F1 dead-money) is REAFFIRMED time-controlled
> (−9.66pp, CI [−11.61, −8.05], BH q=0.000). The episode-permutation machinery below
> is retained as historical record; it is not a compliant primary ruler (DT-R14).

**WHOLE-STUDY VERDICT: PARTIAL SURVIVORS — the trio is NOT closed.**

| Factor | Verdict | Ships as | Gate rejected (§6.2)? |
|---|---|---|---|
| **F1 — cohort-washout proximity** | **GATE-REJECT + SHIPS-AS-RANK-WEIGHT** | rank weight only | YES (gate blocks 54.0% of board) |
| **F2 — RS-inflection (Q2∪Q3)** | **SHIPS-AS-RANK-WEIGHT** | rank weight only | YES (gate blocks 48.5%; HG stats also fail) |
| **F3 — anti-chase (ext_z≤2.0)** | **SHIPS-AS-HARD-GATE** | hard gate (4.6% impact) | no |

**This overturns the round-1 headline.** Round 1 reported "TRIO CLOSED, 0/30 survive." That verdict rested on a statistically invalid p-value (see the Round-1 Defect section below) and is retracted. Under a valid episode-clustered test, **22 of 30 trials survive BH at q≤0.10** and **all three factors earn a promotion path** to P2.1 (shadow-first per R6): F1 and F2 as rank weights, F3 as a hard gate.

**Study:** P1.3 Trio Ablation | **Round:** 2 (defect-corrected re-run) | **Date:** 2026-07-05
**PREREG:** research/entry_intel/P1_3_TRIO_ABLATION_PREREG.md (APPROVED, Fable 2026-07-05)
**Memo:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments
**Replay MD5:** `906175f9eb8caa351ed6d7d5c56265d3` | **Primary test:** episode-level label-permutation Mann-Whitney U (N_PERM=5,000, two-sided, Phipson–Smyth +1 smoothing)

---

## In plain English

> We tested three candidate filters for the live board: is the stock near a forced-seller **washout** (F1), is its relative strength **inflecting but not extended** (F2), and is it **not already price-extended** (F3, "anti-chase"). For each we asked two questions — would *blocking* fires that fail the filter have helped (hard gate), and would merely *ranking them lower* have helped (rank weight)? We ran all 30 registered tests on the same 49,939 production-trigger fires from mid-2022 to end-2025, correcting for multiple testing.
>
> **The honest bottom line: all three filters carry real signal — but the two strongest ones (washout, RS-inflection) would each cut roughly half the board if used as a hard block, which is too blunt. So they earn a place as a *tilt* (rank weight), not a gate. Anti-chase (F3) blocks only ~5% of the board and reduces stop-outs, so it earns the right to act as a hard gate.**
>
> Important nuance on washout (F1): near-washout fires have **much lower dead-money** (−13pp at 21d) and **lower stop-outs at 63 days** (−5pp), but at 21 days they actually stop out slightly *more* (+2.4pp) and have fewer clean cushions. The signal is real and net-favorable over the longer horizon, which is why it ships as a rank tilt rather than a hard block.
>
> **Round-1 correction:** the previous run concluded "none of the three work." That conclusion came from a broken statistic that returned a coin-flip p-value (~0.50) for every test regardless of the truth. This re-run fixes the statistic and reverses the conclusion.

---

## Round-1 defect and fix

**The defect (reviewer-reproduced; see `REVIEW.md`).** Round-1's `episode_bootstrap_mwu` resampled episodes **from within each observed group** (group A resampled from A, B from B), then compared `|boot_U − null_center|` against `|obs_U − null_center|` with `null_center = n_a·n_b/2`. A within-group resample produces bootstrap-U values centered on the **observed** U, not on the null U. So `boot_dev` centered on `obs_dev` and `P(boot_dev ≥ obs_dev) ≈ 0.50` **for every trial, by construction** — independent of the true effect size. The round-1 "0/30 survive, min BH-adj p = 0.53" headline was an artifact of a mis-specified null, not evidence of a null effect. The parametric MWU (T01: p ≈ 9e-128) diverged from the bootstrap p (≈0.50) by 128 orders of magnitude and was never sanity-checked.

**The fix (this run).** The primary p-value is now an **episode-level label-permutation null**. Group assignment (would-pass vs would-block for HG; moved-up vs not for RW) is treated as a per-episode attribute; we **shuffle the group label across whole episodes** (holding the A/B episode counts fixed), recompute the pooled-row Mann-Whitney U under each of N=5,000 permutations, and take the two-sided p as the fraction of permutation `|U − E[U]|` ≥ the observed `|U − E[U]|`. This centers the null correctly at `E[U] = n_a·n_b/2` and respects within-episode correlation (whole episodes move together under the null). A **sanity gate** now HALTS the run if the parametric p and permutation p diverge by the round-1 defect signature (perm_p ≈ 0.5 while param_p ≪ 1e-6); it did not trip.

**Why permutation, not CR1 (P1.1's choice).** The registered §5.1 statistic here is a **two-group Mann-Whitney U on forward returns**, a rank statistic on a heavy-tailed, tied variable. Label permutation is the exact finite-sample null of that U statistic and needs no distributional or linearity assumption; episode-level shuffling supplies the clustering correction directly. P1.1's CR1 sandwich is the right tool for its Spearman/OLS rank-correlation design, but would require re-casting the two-group comparison as a regression; permutation is the more faithful implementation of the U-test intent registered in §5.1. Both were offered by the reviewer as acceptable; permutation is chosen and justified here.

---

## Calibration (mandatory controls — run BEFORE the grid)

Both controls **PASS**. The corrected statistic has correct size under the null and detects a known effect.

**(1) Negative control** — apply the test to episode-permuted labels on real data, ×200 independent draws:

| Metric | Value | Expectation | Pass |
|---|---|---|---|
| Rejection rate @ α=0.05 | **0.035** | ≈0.05 | ✓ (well-controlled; not inflated) |
| p-value mean / median | 0.488 / 0.495 | ≈0.50 | ✓ |
| KS-uniformity D / p | 0.081 / 0.140 | large p ⇒ uniform | ✓ (p=0.14, consistent with U(0,1)) |

The p-value distribution is uniform and the false-positive rate is at/below nominal (3.5% observed vs 5% nominal on n=200 — within sampling noise, slightly conservative). This is exactly the behavior the round-1 statistic **appeared** to have (p≈0.5) but for the wrong reason — round-1 gave p≈0.5 even for true effects; here p≈0.5 **only** under the null.

**(2) Positive control** — inject a synthetic episode-level effect into a copied frame (shift group-A forward returns +0.05, lifting their 21d liftoff rate by **+19.7pp**):

| Metric | Value | Expectation | Pass |
|---|---|---|---|
| Permutation p | **2.00e-04** | ≪ 0.05 | ✓ |
| Parametric p | 0.00e+00 | ≪ 0.05 | ✓ |
| Rank-biserial r | -0.2969 | non-zero | ✓ |

The injected effect is detected at the permutation floor (p ≈ 2e-4), confirming the test has power against a real episode-level shift. **Calibration overall: PASS.**

---

## Preamble / population census

| Item | Value |
|---|---|
| Replay artifact | `data/replay/replay_boarded.parquet` |
| Replay MD5 | `906175f9eb8caa351ed6d7d5c56265d3` |
| Replay shape | 961,656 rows × 66 cols |
| Total fires (all) | 57,640 |
| **Verdict-grade fires (primary)** | **49,939** |
| Episode clusters (unique) | 22,295 |
| Horizon-censored fires (pre-excluded) | 7,701 |
| Stamped rows excluded | 0 (all survivor_bias=False) |
| Effective verdict window | 2022-06-30 → 2025-12-29 |
| washout_proximity True / False | 22,965 / 26,974 |
| rs_sector_quartile null (excluded from F2) | 3,828 |
| ext_z > 2.0 (F3 would-block) | 2,299 |
| Both-halves split midpoint | 2024-04-04 (H1 n=23,984, H2 n=25,955) |
| tier_frac (RW sizing check) | 0.0238 (RW bonus +0.10 ≈ one tier) |

**Column-name mapping (PREREG → replay):** `cohort_washout_proximity`→`washout_proximity` (bool), `rs_vs_sector_quartile`→`rs_sector_quartile` (1–4 float), `fwd_21d`→`fwd_ret_21`, `fwd_63d`→`fwd_ret_63`, `episode_cluster_id`→`episode_id` (TICKER_YYYY-WNN), `survivor_bias_stamp`→`survivor_bias`.

**SURVIVOR-BIAS STAMP (§2.3):** survivor-biased panel: 0% of member-months lack price history for the 2022–2026 verdict era; all rows Massive-sourced (survivor_bias=False); delisted-name recall verified 100% (17/17 probe). Results are VERDICT-GRADE. **PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE:** 0 rows (not applicable in this artifact).

**§5 conformance checklist:** [x] cites memo v1.0 + §6 v1.1; [x] window 2022-06-30→2025-12-29 (250-bar warmup); [x] verdict-grade on survivor_bias=False only; [x] Massive-sourced confirmed; [x] pre-2021 rows: none; [x] horizon_censored pre-excluded (7,701); [x] stamp text printed; [x] n-floor (25 clusters) honored — smallest would-block cell (F3, 1,270 clusters) well above floor.

---

## Full trial results table (30 trials)

perm_p = episode label-permutation two-sided p (primary, feeds BH). param_p = parametric MWU (secondary diagnostic). r = rank-biserial on forward returns. Δ = terminal-state incidence delta (would-pass − would-block for HG; moved-up − rest for RW), in pp. Note: perm_p / param_p / r are on the **forward-return distribution** and are therefore shared across the terminal states within one (factor, mode, horizon) cell (per §5.1 — the test is on continuous forward returns, not the discretized state); Δ and its favorability are the per-terminal-state descriptive statistic.

| ID | Fac | Mode | Hz | Terminal | n_A | ep_A | n_B | ep_B | Δpp | Fav | perm_p | param_p | BH_p | BH_ok | r | Sign | Thin |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | F1 | HG | 21d | STOPPED | 22,965 | 9,581 | 26,974 | 12,764 | +2.41 | N | 0.0002 | 8.68e-128 | 0.0006 | YES | -0.1247 | Y | OK |
| T02 | F1 | HG | 21d | DEAD_MONEY | 22,965 | 9,581 | 26,974 | 12,764 | -13.19 | Y | 0.0002 | 8.68e-128 | 0.0006 | YES | -0.1247 | Y | OK |
| T03 | F1 | HG | 21d | CUSHIONED | 22,965 | 9,581 | 26,974 | 12,764 | -4.10 | N | 0.0002 | 8.68e-128 | 0.0006 | YES | -0.1247 | Y | OK |
| T04 | F1 | HG | 63d | STOPPED | 22,965 | 9,581 | 26,974 | 12,764 | -5.21 | Y | 0.0002 | 1.90e-79 | 0.0006 | YES | -0.0978 | Y | OK |
| T05 | F1 | HG | 63d | DEAD_MONEY | 22,965 | 9,581 | 26,974 | 12,764 | -0.13 | Y | 0.0002 | 1.90e-79 | 0.0006 | YES | -0.0978 | Y | OK |
| T06 | F1 | HG | 63d | CUSHIONED | 22,965 | 9,581 | 26,974 | 12,764 | -2.15 | N | 0.0002 | 1.90e-79 | 0.0006 | YES | -0.0978 | Y | OK |
| T07 | F1 | RW | 21d | STOPPED | 20,698 | 8,910 | 29,241 | 14,106 | +2.58 | N | 0.0002 | 4.40e-96 | 0.0006 | YES | -0.1091 | Y | OK |
| T08 | F1 | RW | 21d | CUSHIONED | 20,698 | 8,910 | 29,241 | 14,106 | -3.62 | N | 0.0002 | 4.40e-96 | 0.0006 | YES | -0.1091 | Y | OK |
| T09 | F1 | RW | 63d | STOPPED | 20,698 | 8,910 | 29,241 | 14,106 | -4.55 | Y | 0.0002 | 8.57e-58 | 0.0006 | YES | -0.0840 | Y | OK |
| T10 | F1 | RW | 63d | CUSHIONED | 20,698 | 8,910 | 29,241 | 14,106 | -1.79 | N | 0.0002 | 8.57e-58 | 0.0006 | YES | -0.0840 | Y | OK |
| T11 | F2 | HG | 21d | STOPPED | 23,733 | 11,544 | 22,378 | 10,791 | +1.19 | N | 0.1766 | 3.03e-02 | 0.1962 | no | +0.0117 | Y | OK |
| T12 | F2 | HG | 21d | DEAD_MONEY | 23,733 | 11,544 | 22,378 | 10,791 | -0.43 | Y | 0.1766 | 3.03e-02 | 0.1962 | no | +0.0117 | N | OK |
| T13 | F2 | HG | 21d | CUSHIONED | 23,733 | 11,544 | 22,378 | 10,791 | -0.48 | N | 0.1766 | 3.03e-02 | 0.1962 | no | +0.0117 | Y | OK |
| T14 | F2 | HG | 63d | STOPPED | 23,733 | 11,544 | 22,378 | 10,791 | +1.89 | N | 0.2372 | 4.84e-02 | 0.2372 | no | +0.0106 | Y | OK |
| T15 | F2 | HG | 63d | DEAD_MONEY | 23,733 | 11,544 | 22,378 | 10,791 | -0.11 | Y | 0.2372 | 4.84e-02 | 0.2372 | no | +0.0106 | Y | OK |
| T16 | F2 | HG | 63d | CUSHIONED | 23,733 | 11,544 | 22,378 | 10,791 | +0.06 | Y | 0.2372 | 4.84e-02 | 0.2372 | no | +0.0106 | N | OK |
| T17 | F2 | RW | 21d | STOPPED | 21,696 | 10,753 | 28,243 | 13,691 | -0.96 | Y | 0.0684 | 2.70e-03 | 0.0933 | YES | -0.0156 | Y | OK |
| T18 | F2 | RW | 21d | CUSHIONED | 21,696 | 10,753 | 28,243 | 13,691 | +0.15 | Y | 0.0684 | 2.70e-03 | 0.0933 | YES | -0.0156 | Y | OK |
| T19 | F2 | RW | 63d | STOPPED | 21,696 | 10,753 | 28,243 | 13,691 | -0.04 | Y | 0.0426 | 5.55e-04 | 0.0752 | YES | -0.0180 | N | OK |
| T20 | F2 | RW | 63d | CUSHIONED | 21,696 | 10,753 | 28,243 | 13,691 | +0.68 | Y | 0.0426 | 5.55e-04 | 0.0752 | YES | -0.0180 | Y | OK |
| T21 | F3 | HG | 21d | STOPPED | 47,640 | 21,368 | 2,299 | 1,270 | -0.43 | Y | 0.0026 | 6.87e-07 | 0.0060 | YES | -0.0612 | Y | OK |
| T22 | F3 | HG | 21d | DEAD_MONEY | 47,640 | 21,368 | 2,299 | 1,270 | -3.63 | Y | 0.0026 | 6.87e-07 | 0.0060 | YES | -0.0612 | Y | OK |
| T23 | F3 | HG | 21d | CUSHIONED | 47,640 | 21,368 | 2,299 | 1,270 | -0.97 | N | 0.0026 | 6.87e-07 | 0.0060 | YES | -0.0612 | Y | OK |
| T24 | F3 | HG | 63d | STOPPED | 47,640 | 21,368 | 2,299 | 1,270 | -5.00 | Y | 0.0648 | 2.10e-03 | 0.0933 | YES | -0.0379 | Y | OK |
| T25 | F3 | HG | 63d | DEAD_MONEY | 47,640 | 21,368 | 2,299 | 1,270 | +0.09 | N | 0.0648 | 2.10e-03 | 0.0933 | YES | -0.0379 | Y | OK |
| T26 | F3 | HG | 63d | CUSHIONED | 47,640 | 21,368 | 2,299 | 1,270 | -0.23 | N | 0.0648 | 2.10e-03 | 0.0933 | YES | -0.0379 | N | OK |
| T27 | F3 | RW | 21d | STOPPED | 23,489 | 11,149 | 26,450 | 13,140 | +0.10 | N | 0.0176 | 7.68e-05 | 0.0352 | YES | -0.0205 | N | OK |
| T28 | F3 | RW | 21d | CUSHIONED | 23,489 | 11,149 | 26,450 | 13,140 | +0.06 | Y | 0.0176 | 7.68e-05 | 0.0352 | YES | -0.0205 | N | OK |
| T29 | F3 | RW | 63d | STOPPED | 23,489 | 11,149 | 26,450 | 13,140 | -1.70 | Y | 0.1284 | 8.64e-03 | 0.1605 | no | -0.0136 | N | OK |
| T30 | F3 | RW | 63d | CUSHIONED | 23,489 | 11,149 | 26,450 | 13,140 | +0.30 | Y | 0.1284 | 8.64e-03 | 0.1605 | no | -0.0136 | N | OK |

**BH family:** m=30, q≤0.10, standard step-up with monotonicity. **n_survive = 22/30; min BH-adj p = 0.0006.**

---

## Fire-rate impact table (R7 additive-lanes law — mandatory)

| Factor | Mode | n_fires_total | n_would_block | gate_impact_% | clusters_blocked | >40%? | GATE-REJECT (§6.2)? |
|---|---|---|---|---|---|---|---|
| F1 | HG | 49,939 | 26,974 | 54.0% | 12,764 | YES | YES |
| F2 | HG | 46,111 | 22,378 | 48.5% | 10,791 | YES | YES |
| F3 | HG | 49,939 | 2,299 | 4.6% | 1,270 | no | no |
| F1 | RW | 49,939 | 0 | 0.0% | 0 | no | no |
| F2 | RW | 49,939 | 0 | 0.0% | 0 | no | no |
| F3 | RW | 49,939 | 0 | 0.0% | 0 | no | no |

F1 and F2 hard gates each eliminate ~half the board; both are **GATE-REJECTED under §6.2** (impact >40% and 21d stop-out delta does not survive favorable). F3's gate eliminates only 4.6% and is allowed.

---

## Both-halves sign-stability table

Split at 2024-04-04 (H1 n=23,984, H2 n=25,955). Sign-stable = terminal-state delta has the same sign in both halves.

| ID | Fac | Mode | Hz | Terminal | H1 Δpp | H2 Δpp | Sign-stable |
|---|---|---|---|---|---|---|---|
| T01 | F1 | HG | 21d | STOPPED | +1.48 | +4.20 | YES |
| T02 | F1 | HG | 21d | DEAD_MONEY | -14.00 | -12.29 | YES |
| T03 | F1 | HG | 21d | CUSHIONED | -4.78 | -3.42 | YES |
| T04 | F1 | HG | 63d | STOPPED | -8.54 | -1.31 | YES |
| T05 | F1 | HG | 63d | DEAD_MONEY | -0.14 | -0.11 | YES |
| T06 | F1 | HG | 63d | CUSHIONED | -1.31 | -3.00 | YES |
| T07 | F1 | RW | 21d | STOPPED | +1.41 | +4.49 | YES |
| T08 | F1 | RW | 21d | CUSHIONED | -3.81 | -3.40 | YES |
| T09 | F1 | RW | 63d | STOPPED | -7.81 | -0.78 | YES |
| T10 | F1 | RW | 63d | CUSHIONED | -0.84 | -2.75 | YES |
| T11 | F2 | HG | 21d | STOPPED | +0.69 | +1.30 | YES |
| T12 | F2 | HG | 21d | DEAD_MONEY | -1.33 | +0.30 | NO |
| T13 | F2 | HG | 21d | CUSHIONED | -0.39 | -0.59 | YES |
| T14 | F2 | HG | 63d | STOPPED | +1.21 | +2.23 | YES |
| T15 | F2 | HG | 63d | DEAD_MONEY | -0.14 | -0.08 | YES |
| T16 | F2 | HG | 63d | CUSHIONED | -0.10 | +0.23 | NO |
| T17 | F2 | RW | 21d | STOPPED | -1.95 | -0.29 | YES |
| T18 | F2 | RW | 21d | CUSHIONED | +0.20 | +0.10 | YES |
| T19 | F2 | RW | 63d | STOPPED | -1.02 | +0.66 | NO |
| T20 | F2 | RW | 63d | CUSHIONED | +0.62 | +0.76 | YES |
| T21 | F3 | HG | 21d | STOPPED | -0.87 | -0.55 | YES |
| T22 | F3 | HG | 21d | DEAD_MONEY | -3.76 | -3.66 | YES |
| T23 | F3 | HG | 21d | CUSHIONED | -1.39 | -0.57 | YES |
| T24 | F3 | HG | 63d | STOPPED | -8.75 | -1.55 | YES |
| T25 | F3 | HG | 63d | DEAD_MONEY | +0.07 | +0.10 | YES |
| T26 | F3 | HG | 63d | CUSHIONED | -0.94 | +0.55 | NO |
| T27 | F3 | RW | 21d | STOPPED | -1.33 | +1.34 | NO |
| T28 | F3 | RW | 21d | CUSHIONED | +0.55 | -0.40 | NO |
| T29 | F3 | RW | 63d | STOPPED | -4.10 | +0.46 | NO |
| T30 | F3 | RW | 63d | CUSHIONED | +0.98 | -0.33 | NO |

---

## Verdict per factor (PREREG §6, checked in order)

### F1 — cohort-washout proximity → **GATE-REJECT + SHIPS-AS-RANK-WEIGHT**
- **§6.1 NO-GO?** No. HG 63d stop-out (T04) Δ=−5.21pp favorable, BH-adj p=0.0006 survives, sign-stable. Not both-fail.
- **§6.2 GATE-REJECT?** **Yes.** Gate impact 54.0% > 40% AND 21d stop-out (T01) is unfavorable (+2.41pp). The hard-gate design is rejected regardless of BH.
- **§6.3 SHIP?** Rank weight ships: RW 63d stop-out (T09) Δ=−4.55pp favorable, BH-survive, sign-stable, n_clusters well above floor. Ships as **rank weight only** (per §6.2 clause: a GATE-REJECT factor may still proceed as RW if Mode-B survives).
- **Signal shape:** strong at 63d and on dead-money (T02: −13.19pp dead-money at 21d, favorable, survives) but adverse on 21d stop-out — a horizon-dependent, net-favorable-longer-horizon effect. Correct role is a tilt, not a block.

### F2 — RS-inflection (Q2∪Q3) → **SHIPS-AS-RANK-WEIGHT**
- **§6.1 NO-GO?** No. RW cushioned (T18, 21d) favorable, BH-adj p=0.0933 survives, sign-stable → clears the NO-GO both-fail test on the Mode-B cushioned leg.
- **§6.2 GATE-REJECT?** Gate impact 48.5% > 40% and HG 21d stop-out does not survive → the **hard gate is rejected** on fire-rate; moreover the HG statistics themselves are null (T11/T14 stop-out BH-adj p ≈ 0.20–0.24, not significant). No viable gate.
- **§6.3 SHIP?** Rank weight ships: T18 (21d cushioned) and T20 (63d cushioned) favorable, BH-survive, sign-stable. Ships as **rank weight only.**
- **Signal shape:** genuinely weak (|r| ≈ 0.01–0.02) — the non-monotone Q2∪Q3 recode carries only a faint tilt. It clears the bar as an RW tilt but is the weakest of the three; shadow-testing should watch effect size closely.

### F3 — anti-chase (ext_z ≤ 2.0) → **SHIPS-AS-HARD-GATE**
- **§6.1 NO-GO?** No. HG 21d stop-out (T21) Δ=−0.43pp favorable, BH-adj p=0.0060 survives, sign-stable.
- **§6.2 GATE-REJECT?** No. Gate impact 4.6% < 40% — the gate is allowed.
- **§6.3 SHIP?** HG ships: T21 (21d stop) and T24 (63d stop, Δ=−5.00pp favorable, BH-survive, sign-stable). Also strong on dead-money (T22: −3.63pp favorable). Ships as **hard gate** (impact well under 40%). RW does NOT ship (T27/T28/T29/T30 sign-stability fails).
- **Signal shape:** small but clean stop-out and dead-money reduction; because it touches only the extended ~5% tail it is a low-cost gate.

---

## Whole-study verdict

**PARTIAL SURVIVORS — trio NOT closed.** All three factors earn a promotion path to P2.1 (shadow-first, R6):
- **F1 → rank weight** (hard gate rejected on fire-rate).
- **F2 → rank weight** (hard gate rejected; weakest effect — monitor).
- **F3 → hard gate** (4.6% impact; the one factor with a viable gate design).

Registry §8 transitions: F1 `validation_status: phase0_passed (RW)`; F2 `validation_status: phase0_passed (RW)`; F3 `validation_status: phase0_passed (HG)`. **None registered as `falsified`** — the round-1 `falsified` proposal is withdrawn.

---

## Context appendices (not verdict-grade; not BH-corrected)

**Appendix A — sector concentration of would-block subgroups (Mode-A):** printed to console log (`_v2_run.log`); no single sector dominates the F3 (anti-chase) would-block set, so the gate is not a disguised sector bet. F1/F2 would-block sets are ~half the board and broadly distributed.

**Appendix B — PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE:** 0 stamped rows in this artifact; not applicable.

**Appendix C — Weekly-trigger bottom backtest (R3): HYPOTHESIS — DIFFERENT TRIGGER — NOT VALIDATION.** The prior n=315 (quality=82.1, 64.1% durable, weekly trigger) suggested all three factors were directionally positive. The current production-trigger result **agrees directionally** for F1 (long-horizon) and F3, and is **much weaker** for F2. Per R3 this agreement is transparency only and is NOT used as confirmatory evidence.

---

## Leak audit

1. **Fill rule:** next-bar (entry = first close strictly after signal_date, per P0.1 contract). Confirmed uniform +1 offset in round-1 recompute; population identical here (same MD5).
2. **Feature freeze (PIT):** ext_z, rs_sector_quartile, washout_proximity read as frozen signal-time values from the replay; no feature recomputed.
3. **Era boundary:** 2022-06-30 → 2025-12-29 (effective; 250-bar MTF warmup consumes the nominal 2021-07-06 start). All verdict_grade rows inside window.
4. **Sector-map non-PIT disclosure:** rs_sector_quartile uses current-GICS snapshot (928-label map, 92% fill on fires); 3,828 null-RS fires excluded from F2 only.
5. **Survivor bias:** all rows survivor_bias=False (Massive-sourced, 100% delisted recall); 0 stamped rows.
6. **Episode-label purity (permutation validity):** group membership is per-episode for most episodes; a minority span both groups (F1_HG 50, F2_HG 1,729, F3_HG 343, RW 721–2,149 of 22,295). The permutation resamples at the episode level (whole episode → one drawn label via its first-seen row), which is conservative and clustering-valid. This does not bias the null center; it slightly coarsens the clustered unit, if anything widening (not shrinking) the null.

---

## Statistical-method note

- **Primary test:** episode-level label-permutation Mann-Whitney U on forward returns, N_PERM=5,000, two-sided via `|U − E[U]|`, Phipson–Smyth +1 smoothing (p ≥ 1/5001 ≈ 2.0e-4).
- **Effect size:** rank-biserial r = 1 − 2U/(n_a·n_b).
- **BH:** m=30 simultaneous, q≤0.10, monotone step-up.
- **Sign stability:** terminal-state delta sign agreement across the two chronological halves.
- **n-floor:** 25 episode clusters; no cell borrowed; no INSUFFICIENT-POWER cell in this grid.
- **Sanity gate:** HALT on param/perm divergence of the round-1 defect signature — did NOT trip.

*Round-1 files preserved as `run_P1_3_v1_bounced.py`, `RESULTS_v1_bounced.md`, `results_v1_bounced.json`. This report is the round-2 record of the registered trials with the defect corrected; the PREREG is immutable and unedited.*
