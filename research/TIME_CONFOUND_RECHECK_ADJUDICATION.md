# Time-Confound Re-Check Adjudication — Rulings RC-RUL-1..5

**Date:** 2026-07-07
**Adjudicator:** Fable (main loop)
**Authority chain:** DT-W1a (research/dannytrades/DT_W1_RESULTS.md) → Ruling DT-R14 → research/TIME_CONFOUND_EXPOSURE_AUDIT.md (#1755) → re-check evidence PRs #1850 / #1855 / #1864 / #1866 (+ OTA-RC-2, pending at time of writing).
**Discipline:** every re-check froze events/cohorts/thresholds and changed inference machinery only, passed a mandatory reproduction gate against the shipped numbers before running new inference, and shipped labeled "adjudication pending." This document is the adjudication.

> **In plain English:** we re-measured five sets of shipped results with the clock controlled. Outcome: one production-relevant promotion warrant is withdrawn (the anti-chase hard-gate evidence was the calendar, not the signal), one compound promotion candidate loses its gauntlet pass (A9), and three things we expected to weaken actually survived the harder test (the member-transmission chip, A15/A17-modern, and the P3 secondary — which got *stronger*). The healthcare null stands on repaired machinery. Nothing here was decided by re-running until we liked the answer: every re-check had one pre-specified design, and the internal positive controls confirmed the machinery can still detect real effects (T02 survived at −9.66pp).

---

## RC-RUL-1 — Entry Intelligence P1.3 / F3 anti-chase (EI-RC-1, PR #1866)

**Evidence** (`research/entry_intel/p1_runs/P1_3_TC_RECHECK/RESULTS.md`; reproduction gate exact to 0.000% on all five trials; within-month label-permutation null clean; +2pp injection detected):

| Trial | Shipped delta (pp) | Time-controlled delta (pp) | 95% CI | exact p | BH q (m=5) |
|---|---|---|---|---|---|
| T02 F1 dead-money 21d | −13.19 | **−9.66** | [−11.61, −8.05] | 0.0000 | 0.0000 |
| T09 F1 RW stop 63d | −4.55 | +0.01 | [−3.08, +3.26] | 0.53 | 0.66 |
| T18 F2 RW cushion 21d | +0.15 | +0.42 | [−0.58, +1.35] | 0.19 | 0.48 |
| T21 F3 HG stop 21d | −0.43 | +0.82 | [−2.69, +4.45] | 0.66 | 0.66 |
| T24 F3 HG stop 63d | −5.00 | +0.04 | [−3.66, +3.27] | 0.52 | 0.66 |

**Rulings:**

1. **The P1.3 evidentiary designation "F3 anti-chase SHIPS-AS-HARD-GATE" is WITHDRAWN.** Both F3 trials (T24, T21) collapse to zero on the within-month-demeaned, month-block basis — the shipped stop-rate deltas were calendar composition, exactly the half-concentration signature the audit flagged (T24 half1 −8.75 / half2 −1.55). No production rollback is required: the implementation was shadow-first per Article 2 (P2.1a; `antichase_shadow_ledger.parquet`), so no money-path change ever rested on the confounded CI.
2. **P2.1a flip terms tightened:** the R-P2.1 floors (100 blocked episode-clusters + 2 quarters) remain necessary but are no longer sufficient — any future flip decision must ALSO include a DT-R14-compliant read (within-period demeaning + calendar-block resampling) of the accumulated shadow-ledger data. P1.3 no longer supplies a standing in-sample warrant; the forward ledger must earn the flip on its own.
3. **T02 (F1 dead-money) is REAFFIRMED on the time-controlled basis** (−9.66pp, CI excluding zero, BH 0.000) — the one P1.3 effect that was real all along. Its status is unchanged (future clade note; F1 gate remains rejected on fire-cost grounds, which are mechanical and unaffected).
4. **The P2.1b F1 rank-weight KILL stands, with corrected rationale:** the original T09 promotion evidence is now shown to have been time-confounded (+0.01pp TC), so the kill no longer rests solely on the proxy→production sign reversal — the promotion evidence never existed on a compliant ruler.
5. Consequential (no action): P2.5's six shadow configs inherited the same episode-permutation machinery; they remain shadow-quarantined with their in-sample perm_p now formally discounted — the forward ledger arbitrates, as already ruled.

## RC-RUL-2 — Oracle W2 member-transmission (OTA-RC-1, PR #1855)

**Evidence** (`research/oracle_asymmetry/W2_TC_RECHECK.md`; reproduction exact): 35 windows collapse into **9 macro-episodes** (gap ≤10 td). Episode-cluster 90% CIs: ΔWR21 [0.0399, 0.1901] (shipped window-cluster [0.0537, 0.1757]); Δmean_ret21 [0.0107, 0.0493]. Period-matched R3 baseline: Δ=0.1051, CI [0.0207, 0.1692]. All lower bounds remain above zero.

**Ruling: the CONFIRMED / display-with-edge verdict STANDS.** The audit's expected downgrade (CONFIRMED→PARTIAL) did not materialize: the deltas survive the coarser, honest clustering unit and the corrected holdout baseline, with narrowed margins. Caveats attached: (a) 7 in-arm episodes is a thin resampling base — the CI is honest but fragile; (b) the episode-joint placebo was not built (the shipped window-level placebo remains operative); it is an optional accrual item, not a blocker; (c) the §5 forward ledger remains the decisive arbiter, unchanged.

## RC-RUL-3 — Oracle compound gauntlet & P3 secondary (ORC-RC-1, PR #1864)

**Evidence** (`research/ORACLE_COMPOUND_TC_RECHECK.md`; reproduction exact): circular time-shift placebo (preserves inter-onset spacing/clustering; 2000 draws) vs shipped independent-draw placebo:

| Compound | Shipped G3 p | Time-shift p | G3 under time-null |
|---|---|---|---|
| A15 (full) | 0.0000 | 0.0095 | holds |
| A9 (full) | 0.0000 | **0.1390** | **does not hold** |
| A17 (full) | 0.0000 | 0.1050 | does not hold (read already superseded) |
| A17 (modern, n=73) | 0.0000 | 0.0130 | holds |

P3 secondary `ep_in_onset_21d` under calendar-month block bootstrap (142 months): CI [+0.15%, +1.11%], p=0.0045 — **stronger** than the shipped detection-order-block read (p=0.0075).

**Rulings:**

1. **A15 gauntlet PASS is REAFFIRMED** under the time-preserving null (p=0.0095). The research-factory paper pipeline built on A15 is unaffected.
2. **A9's gauntlet PASS is WITHDRAWN.** Its G3 evidence does not survive a null that preserves temporal clustering (p=0.139). A9 reverts to `screened` evidence status only (its registry status never advanced, so no registry edit is needed); it is no longer a promotion candidate absent fresh out-of-time evidence. The gauntlet R1 document carries the amendment banner.
3. **A17: the modern-regime read (the operative verdict since the 2026-07-04 correction) STANDS** (p=0.013), with its existing n=73 caveat. The full-history read — already superseded — is additionally confirmed non-robust under the time-null (p=0.105); it must not be revived.
4. **`ep_in_onset_21d` may now be cited** — with the month-block CI, which supersedes the detection-order block read. The audit's precondition ("re-express before citing") is satisfied, and the effect strengthened under the compliant ruler.
5. **Standing instruction:** future compound-gauntlet rounds use the circular time-shift placebo (now in `scripts/research/oracle_compound_tc_recheck.py`) as the G3 null, not independent index draws.

## RC-RUL-4 — Healthcare R-1 construction divergence (HC-RC-1, PR #1850)

**Evidence** (`research/CONSTRUCTION_DIVERGENCE_R1_TC_RECHECK.md`; reproduction gate pass; CD-1/CD-2/CD-3 repaired — 419 real ±7d cross-sector co-firing blocks, block-cluster bootstrap): DD21 pooled +0.27% CI [−0.26, +0.83] (null, unchanged); DD63 pooled +0.85% CI [−0.07, +1.84], p=0.072 (marginal, includes zero); DD63 stress-stratified null in BOTH strata (stress p=0.774, calm p=0.103). DD63 tail (p10): div −12.35 [−15.88, −10.28] vs con −15.12 [−16.75, −13.22] — non-overlapping cohort CIs, no CI on the difference.

**Ruling: the R-1 "null held" LOCK is REAFFIRMED — now on repaired machinery.** The audit's false-null concern is resolved: with real calendar-block inference, no clear masked effect emerges (the pooled DD63 marginal does not survive stratification). Consequential rulings: (a) `scripts/study_construction_divergence_tc.py` is the **mandatory apparatus** for any future R-1 verdict batch — the original script's inference path (CD-1/2/3 defects) is retired for inferential use, retained as historical record; (b) the DD63 tail asymmetry (divergent cohort's p10 genuinely shallower) is logged as a **descriptive watch item** for the accrual — if a future batch tests it, the test must be pre-registered on the repaired apparatus with a quantile-difference bootstrap.

## RC-RUL-5 — SEQ_TLT_RELIEF_WASHOUT (OTA-RC-2)

Re-check dispatched 2026-07-07 (episode-cluster CIs on the gauntlet legs + time-shift Leg-6 placebo). Ruling to be appended when the evidence lands. Until then the audit's HIGH exposure rating stands and the signal remains at registry status `screened` (display ceiling), as shipped.

---

## Scoreboard (audit prediction vs adjudicated outcome)

| Re-check | Audit flip expectation | Outcome |
|---|---|---|
| EI-RC-1 (F3 gate warrant) | HIGH flip risk | **Flipped — warrant withdrawn** (T24/T21 → 0) |
| EI-RC-1 (T02 control) | expected to survive | Survived (−9.66pp, q=0.000) |
| OTA-RC-1 (W2 CONFIRMED) | MEDIUM, → PARTIAL | **Stood** — margins narrowed, LBs > 0 |
| ORC-RC-1 (A15) | MEDIUM | Stood (p=0.0095) |
| ORC-RC-1 (A9) | MEDIUM | **Flipped — PASS withdrawn** (p=0.139) |
| ORC-RC-1 (A17-modern) | MEDIUM-HIGH | Stood (p=0.013, n=73 caveat) |
| ORC-RC-1 (P3 secondary) | exposed | Stood and **strengthened** (p=0.0045) |
| HC-RC-1 (R-1 false-null) | LOW-MED masked effect | No masked effect — lock reaffirmed |

Two flips, five survivals, one strengthening — the audit's ranking was directionally right (its #1 item flipped; the survivals were all in the MEDIUM band), and the re-check pattern (frozen events, inference-only, reproduction gates, positive controls) held everywhere. DT-R14 is confirmed as load-bearing beyond the DannyTrades family.

## File actions shipped with this adjudication

- Superseding banner on `research/entry_intel/p1_runs/P1_3/RESULTS.md`; log entry + flip-term tightening note in `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` and `research/entry_intel/P2_1A_ANTICHASE_GATE_PREREG.md`.
- Re-check note appended to `research/oracle_asymmetry/W2_FORMAL_RESULTS.md`.
- Amendment banner on `research/ORACLE_COMPOUND_GAUNTLET_R1.md` (A9 withdrawal, A17 scope, A15 reaffirmation, time-shift placebo law).
- Re-check note on `research/CONSTRUCTION_DIVERGENCE_R1_DESCRIPTIVE.md`.
- `research/TIME_CONFOUND_EXPOSURE_AUDIT.md` §7 statuses resolved + §9 resolution postscript.
