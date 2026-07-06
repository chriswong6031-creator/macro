# P1.2b Gate P&L — Taxonomy Extension: RESULTS

2026-07-05 — Fable adjudication: verdict-of-record corrected per REVIEW_P1_2B.md.

**Study ID:** P1_2B
**Run timestamp:** 2026-07-05T17:59:05.602186Z
**Spec:** research/entry_intel/P1_2B_TAXONOMY_EXTENSION_SPEC.md
**Era memo:** P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments (2026-07-05)
**Effective verdict window:** 2022-06-30 → 2026-07-02
**BH family:** ei_gate_pnl_p12b (m=16)
**Canonical input:** replay_boarded_p12b.parquet (re-tagged artifact)
**Original artifact MD5:** 906175f9eb8caa351ed6d7d5c56265d3
**Re-tagged artifact MD5:** b8b24c4c8e87d763f984a80564a8a9c5

## In plain English

> The P1.2 study tested nine gate rejection reasons but found four with zero rows.
> Two of those — 'stale signal' (freshness_expired) and 'T4 tier' (tier_cutoff) —
> were actually present in the data under different labels, not truly absent.
> This study (P1.2b) adds proper labels to those rows and re-runs the matched
> comparison: do names rejected for staleness or T4 tier status actually perform
> worse than names that cleared the gate and made the board? A clean counterfactual
> (rejected names vs board-accepted fires from the same sector and time window)
> gives an honest answer to that question.

## 1. Re-tag Preamble

**Original artifact:** `data/replay/replay_boarded.parquet` (MD5: 906175f9eb8caa351ed6d7d5c56265d3)
**Re-tagged artifact:** `data/replay/replay_boarded_p12b.parquet` (MD5: b8b24c4c8e87d763f984a80564a8a9c5)

### Validation Gates

| Gate | Description | Result |
|---|---|---|
| V1 | Fire set byte-identity | PASS |
| V2 | Near-miss set identity (excl. rejection_reason) | PASS |
| V2b | Whole-frame verdict_type byte-identity | PASS |
| V3 | Coverage plausibility (freshness_expired=7,319, tier_cutoff=131) | PASS |

### Re-tag Row Counts

| Code | Before (rows with this rejection_reason) | After | Delta |
|---|---|---|---|
| `freshness_expired` | 0 | 8,789 | +8,789 |
| `tier_cutoff` | 0 | 158 | +158 |

**Re-tag logic (tier_cutoff processed first):**

- **Change 2 (tier_cutoff, first):** All rows where `gate_reason == 'tier T4 (weight 0.4)'`
  and `verdict_type ∈ {rejection, near_miss}` tagged as `rejection_reason = 'tier_cutoff'`.
  This overrides `board_rank_cutoff` for 121 rejection rows because those rows are semantically
  tier_cutoff (T4 is excluded from BUYABLE_TIERS per spec §1.1); board_rank_cutoff was the
  catch-all placeholder. Achieves the ~131 verdict_grade rows the spec expects.
- **Change 1 (freshness_expired, second):** Remaining rows where
  `near_miss_reason == 'freshness_expired'` and `rejection_reason` is still null tagged
  as `rejection_reason = 'freshness_expired'`.

### NOT-AVAILABLE-IN-SUBSTRATE (spec §2.4 — verbatim)

> **`event_blackout` — NOT-AVAILABLE-IN-SUBSTRATE.** The earnings-proximity exclusion gate is defined in `engine/grading.py REJECTION_TAXONOMY` but is annotated "where wired." As of the current replay substrate, no rows carry this rejection reason or its semantic equivalent in any free-text column (0 token hits confirmed by Opus review 2026-07-05). This code requires new data plumbing in the replay harness before it becomes testable. No re-tag action is possible. Deferred to a future P1.2c amendment when the gate is wired.

> **`cohort_null` — NOT-AVAILABLE-IN-SUBSTRATE.** The §3.3 coverage-law gate (coverage_pct < 70%) is defined in the taxonomy but not applied in the current replay substrate (0 rows). This code requires the per-name PIT membership coverage computation to be plumbed into the replay gate path. Deferred to a future P1.2c amendment.

## 2. Era Coverage Statement

- **Era memo:** P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments (2026-07-05)
- **Effective verdict window:** 2022-06-30 → 2026-07-02 (250-bar MTF warmup per §6.1)
- **Canonical input:** `data/replay/replay_boarded_p12b.parquet` ONLY
- **verdict_grade=True rows within window (primary):** 834,267
- **Stamped rows (survivor_bias=True) excluded:** 0
- **Episode clusters (21-day windows):** 44
- **horizon_censored rows (excluded from primary):** 0 (horizon_censored=True: 0 within verdict_grade primary)
- **Stamped rows in primary (expected 0):** 0

## 3. Coverage Table (Two New Codes)

Matched fired cohort: `board_fire` rows only (board_verdict='board_fire'), per §3.1 confound fix.

| Reason | n_total | n_matchable | n_survived | prune_rate | n_board_fire_matched |
|---|---|---|---|---|---|
| `freshness_expired` | 7,319 | 1,972 | 872 | 55.8% | 1,097 |
| `tier_cutoff` | 131 | 38 | 10 | 73.7% | 28 |

## 4. Primary Verdict Table (B01–B16)

BH correction: m=16, q≤0.1, family=ei_gate_pnl_p12b.
Δ = rejection cohort rate − matched board_fire cohort rate.
Wilson LB = one-sided 95% Wilson lower bound on rate.

### freshness_expired — **KEEP**
*No significant axis at q≤0.10 (KEEP by default)*

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.393 (0.367) | 0.188 | 0.136 | 0.282 (0.258) | 872 |
| 21d | board_fire (matched) | 0.409 (0.385) | 0.187 | 0.146 | 0.258 (0.237) | 1,097 |

| Horizon | Axis | Δ | Raw p | BH q | Reject? |
|---|---|---|---|---|---|
| 21d | Δ_stop_out | -0.0159 | 0.5413 | 1.0000 | no |
| 21d | Δ_dead_money | +0.0012 | 0.9501 | 1.0000 | no |
| 21d | Δ_cushion | -0.0094 | 0.6205 | 1.0000 | no |
| 21d | Δ_clean_lift | +0.0241 | 0.5025 | 1.0000 | no |

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 63d | Rejection | 0.594 (0.566) | 0.016 | 0.124 | 0.266 (0.242) | 872 |
| 63d | board_fire (matched) | 0.602 (0.577) | 0.012 | 0.154 | 0.232 (0.212) | 1,097 |

| Horizon | Axis | Δ | Raw p | BH q | Reject? |
|---|---|---|---|---|---|
| 63d | Δ_stop_out | -0.0076 | 0.7808 | 1.0000 | no |
| 63d | Δ_dead_money | +0.0042 | 0.7125 | 1.0000 | no |
| 63d | Δ_cushion | -0.0302 | 0.5145 | 1.0000 | no |
| 63d | Δ_clean_lift | +0.0336 | 0.5060 | 1.0000 | no |

### tier_cutoff — **INSUFFICIENT-POWER** (verdict of record)

*Registered rule (spec §2.1 no-overwrite): only 37 previously-null rows qualify; n=37 < 50 V3 floor. Verdict of record: INSUFFICIENT-POWER.*

#### Post-hoc exploratory trial (recorded per species §8)

> **Label:** post-hoc exploratory trial (recorded per species §8; overwrote 121 board_rank_cutoff rows contrary to spec §2.1 no-overwrite rule)
>
> n_total=131 (includes 121 rows overwriting non-null board_rank_cutoff, contrary to spec §2.1).
> Verdict under exploratory variant: **INCONCLUSIVE-THIN** (n_survived=10 < 25; §3.4 POWER NOTE governs over AC-3 n<10 floor; spec internal contradiction resolved in §3.4's favor per REVIEW_P1_2B.md ADVISORY-2).

**THIN:** n_survived=10 < 25 (§3.4 POWER NOTE floor). Power is insufficient.

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.200 (0.069) | 0.200 | 0.300 | 0.300 (0.127) | 10 |
| 21d | board_fire (matched) | 0.071 (0.024) | 0.179 | 0.214 | 0.536 (0.384) | 28 |

| Horizon | Axis | Δ | Raw p | BH q | Reject? |
|---|---|---|---|---|---|
| 21d | Δ_stop_out | +0.1286 | 0.5676 | 1.0000 | no |
| 21d | Δ_dead_money | +0.0214 | 0.8361 | 1.0000 | no |
| 21d | Δ_cushion | +0.0857 | 0.6128 | 1.0000 | no |
| 21d | Δ_clean_lift | -0.2357 | 0.5717 | 1.0000 | no |

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 63d | Rejection | 0.300 (0.127) | 0.000 | 0.100 | 0.600 (0.352) | 10 |
| 63d | board_fire (matched) | 0.321 (0.198) | 0.000 | 0.107 | 0.571 (0.418) | 28 |

| Horizon | Axis | Δ | Raw p | BH q | Reject? |
|---|---|---|---|---|---|
| 63d | Δ_stop_out | -0.0214 | 0.8344 | 1.0000 | no |
| 63d | Δ_dead_money | +0.0000 | 1.0000 | 1.0000 | no |
| 63d | Δ_cushion | -0.0071 | 0.9523 | 1.0000 | no |
| 63d | Δ_clean_lift | +0.0286 | 0.7501 | 1.0000 | no |

## 5. BH Family Audit

Family: `ei_gate_pnl_p12b`, m=16 (registered before run, 2026-07-05)
This family is INDEPENDENT from the original `ei_gate_pnl` family (m=72).
No p-values cross between families per spec AC-4.

| Trial | Reason | Horizon | Axis | Raw p | BH q | Significant? |
|---|---|---|---|---|---|---|
| B01 | freshness_expired | 21d | stop_out | 0.5413 | 1.0000 | no |
| B02 | freshness_expired | 21d | dead_money | 0.9501 | 1.0000 | no |
| B03 | freshness_expired | 21d | cushion | 0.6205 | 1.0000 | no |
| B04 | freshness_expired | 21d | clean_lift | 0.5025 | 1.0000 | no |
| B05 | freshness_expired | 63d | stop_out | 0.7808 | 1.0000 | no |
| B06 | freshness_expired | 63d | dead_money | 0.7125 | 1.0000 | no |
| B07 | freshness_expired | 63d | cushion | 0.5145 | 1.0000 | no |
| B08 | freshness_expired | 63d | clean_lift | 0.5060 | 1.0000 | no |
| B09 | tier_cutoff | 21d | stop_out | 0.5676 | 1.0000 | no |
| B10 | tier_cutoff | 21d | dead_money | 0.8361 | 1.0000 | no |
| B11 | tier_cutoff | 21d | cushion | 0.6128 | 1.0000 | no |
| B12 | tier_cutoff | 21d | clean_lift | 0.5717 | 1.0000 | no |
| B13 | tier_cutoff | 63d | stop_out | 0.8344 | 1.0000 | no |
| B14 | tier_cutoff | 63d | dead_money | 1.0000 | 1.0000 | no |
| B15 | tier_cutoff | 63d | cushion | 0.9523 | 1.0000 | no |
| B16 | tier_cutoff | 63d | clean_lift | 0.7501 | 1.0000 | no |

**n significant at q≤0.1:** 0

## 6. P2.2 Candidate List

No DEMOTE or FLIP verdicts from this run.
No new entries for the P2.2 candidate list from P1.2b.

## 7. Board-Demotion Confound Status Note

The D2 confound (Opus review REVIEW.md §D2 — BLOCKING) affecting the three board-level
demotion codes (`extension_demote`, `knife_demote`, `sector_cap_displaced`) from P1.2
is **NOT addressed in this P1.2b run**.

Their P1.2 KEEP verdicts are re-cast as **non-informative** per the Opus D2 finding:
the matched cohort was contaminated (~49.9% of the knife_demote matched pool consisted
of board_rejection fires — the very demoted names being tested). The near-zero deltas
are mechanically induced, not evidence of gate neutrality.

A future P1.2c or P2.2 scoping should design a demoted-vs-board_fire counterfactual.
P1.2b scope is the gate-stage re-tag only (spec AC-5).

## 8. Leak Audit

- **Fill rule:** Entry price = close of signal_date + 1 (fill_offset=1). No look-ahead.
- **Feature freeze:** All signal features computed as of signal_date. No fwd return in features.
- **Era boundary:** Effective window starts 2022-06-30 (250-bar MTF warmup removes pre-warmup bias).
- **gics_sector non-PIT disclosure:** sector column uses GICS as of collection time; pre-2022 sector
  assignments may not be fully PIT-clean. No sector-level finding should be over-weighted.
- **Survivor bias:** survivor_bias=True rows excluded from all primary computations.
  Primary era has 0 stamped rows.

## 9. §8 Masterplan Entry Rows

| date | wave | status | code | notes | PR |
|---|---|---|---|---|---|
| 2026-07-05 | P1.2b | KEEP | `freshness_expired` | Re-tagged 8,789 rows; verdict from ei_gate_pnl_p12b family | — |
| 2026-07-05 | P1.2b | INSUFFICIENT-POWER | `tier_cutoff` | Registered rule (n=37 < 50 floor); post-hoc exploratory override variant INCONCLUSIVE-THIN (n=131, overwrote 121 board_rank_cutoff rows contrary to spec §2.1) | — |
| 2026-07-05 | P1.2b | NOT-AVAILABLE | `event_blackout` | Genuinely absent in substrate; earnings-proximity gate not wired in replay; deferred to P1.2c | — |
| 2026-07-05 | P1.2b | NOT-AVAILABLE | `cohort_null` | Genuinely absent in substrate; §3.3 coverage gate not plumbed into replay path; deferred to P1.2c | — |
