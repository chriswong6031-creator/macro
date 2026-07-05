# P1.5 Continuation Partition — CONFORMANCE REVIEW (Opus reviewer)

**FINAL VERDICT: DEVIATIONS — one BLOCKING mis-specification of the primary partition axis.**

The runner's headline ("AMBIGUOUS / PREREG-GAP blocker") is **not conformant**. The reported
"gap case" is an artifact of substituting the wrong tier column for the PREREG-registered
partition. Under the PREREG-literal column, the study lands on a clean, registered branch
(**H-MISLABEL**), and there is **no decision-table gap**. The blocker to Fable should be
withdrawn and the study re-run on the correct column.

---

## BLOCKING findings

### B1 — Primary partition uses the wrong tier column (`tier_cascade` instead of `align_tier`)

**This is the finding that inverts the verdict.**

- PREREG §1 registers the consumed column as **`tier` (PRIME/ARMED/APPROACHING)`** and §3/§9
  define both primary arms by tier *value*: `tier == 'ARMED'` and `tier == 'PRIME'`.
- The replay parquet carries a column whose values are literally `{APPROACHING, ARMED, PRIME}`:
  **`align_tier`**. This is the canonical alignment-tier column — sibling study **P1.1**
  (`run_P1_1_SEPARABILITY.py` L202, L842, L1126) explicitly treats `align_tier` as *the*
  alignment tier, with the fixed ordinal `APPROACHING=0, ARMED=1, PRIME=2`.
- The runner instead partitions on **`tier_cascade`** (values `T1/T2/T3`) with a silent,
  undocumented remap `T1→PRIME`, `T2→ARMED`. `tier_cascade` is the confluence-tier cascade
  byte (a different construct; P0_1_PIT_AUDIT §fire-classification), **not** the alignment tier.
- The two columns do **not** map cleanly. Recomputed crosstab on verdict-grade fires:

  | tier_cascade \ align_tier | APPROACHING | ARMED | PRIME |
  |---|---|---|---|
  | **T1** | 1075 | 620 | 3625 |
  | **T2** | 2100 | 883 | 1745 |
  | **T3** | 991 | 249 | 78 |

  T1 contains 620 ARMED + 1075 APPROACHING rows; T2 contains 1745 PRIME rows. The remap is
  simply wrong.

**Impact — it flips the decision branch:**

| Partition column | T1 Δ (ARMED-cont − PRIME) | Stop-out Δ | Materiality (≥5pp) | PREREG branch |
|---|---|---|---|---|
| `tier_cascade` (runner) | **−5.49pp** | +0.60pp | material | none → "GAP / AMBIGUOUS" |
| `align_tier` (PREREG-literal) | **−2.79pp** | +1.06pp | **immaterial** | **H-MISLABEL** (\|Δ\|<5pp) |

Under the correct column: Δ=−0.0279 (recomputed, boot p≈0.05), \|Δ\|=2.79pp < 5pp → the PREREG
§6 H-MISLABEL row (`|Δ| < 5pp`) governs cleanly. **There is no decision-table gap.** The
"unspecified branch" the runner escalated to Fable exists only because the −5.49pp figure comes
from a mis-specified partition.

K1 is still satisfied on the correct column (ARMED-continuation = **1,322** episodes ≥ 100 floor),
so the study remains executable — it does not collapse to INSUFFICIENT-POWER; it simply resolves
to H-MISLABEL.

**Required remediation:** re-run T1–T5 with arms defined on `align_tier ∈ {ARMED, PRIME}` per
PREREG §3/§9. If the program intends `tier_cascade` as the tier column, that is a PREREG
amendment for Fable to make explicitly — it cannot be introduced silently by the runner, and
the current PREREG text does not support it.

---

## ADVISORY findings

### A2 — Stated effective window end-date is inconsistent with the data
Preamble/`results.json` state the window as **2022-06-30 → 2026-07-02**, but the actual last
fire `signal_date` is **2025-12-29** (recomputed), and the sign-stability grid in RESULTS.md
itself prints "Window: 2022-06-30 → 2025-12-29". The `2026-07-02` end is the replay-data
boundary (memo §6.1), not the fire boundary; fires stop ~6 months earlier because the 21-day
forward horizon must fit. Not a computational error, but the two dates should be reconciled
(state both: data window vs last-graded-fire window) to avoid implying fires exist through
2026-07-02.

### A3 — `board_rank_unresolved` not surfaced descriptively
Memo §6.3 and §APPROVAL clause 4 require `board_rank_unresolved` rows to receive descriptive
treatment. The study neither reports the count of such rows among its fire arms nor states they
were left untouched. Since P1.5 does not issue keep/demote/flip verdicts this is low-severity,
but the descriptive line is a checklist item and is absent.

### A4 — MAE column proxy is undocumented in the leak-audit
The script computes `mae_21d` from `fwd_mdd_21` (max drawdown), which is a reasonable proxy for
MAE, but the PREREG §1 names `fwd_mae_21d`. The substitution is silent. Secondary/context only
(never verdict), so advisory — but the mapping should be stamped.

---

## Per-check results

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Trial-grid adherence (m=5, all registered, none unregistered as primary) | **FAIL (BLOCKING)** | All 5 trial *labels* match the grid and m=5 is honored, but the primary **partition axis is mis-specified** (`tier_cascade` vs registered `align_tier`), which is a spec violation of the trial definition itself (B1). |
| 2 | Era/stamp discipline (verdict_grade filter, stamps excluded, window stated) | **PASS** | verdict_grade=True + fire filter correct; 0 stamped rows (all Massive-sourced 2022+); horizon_censored=0; effective window cited. Minor date inconsistency A2. |
| 3 | Independent recompute (≥3 headline numbers, flag mismatch >1%) | **PASS (numbers), but they reproduce a wrong-column result** | Recomputed independently: armed_cont P=0.27897, PRIME P=0.33384, Δ=−0.05487, stop-diff=+0.00597, T4 Δ=−0.0676, BH q=[0,.308,.8184,.308→ordered], census 10521/5838 & 15145/7312 — **all match to <0.01%**. The arithmetic is faithful; the *inputs* are wrong (B1). |
| 4 | BH family (m=5, pooling, sign-stability halves) | **PASS** | BH m=5 reproduces exactly (T1 q≈0, T2/T5 q=0.308, T3 q=0.818, T4 q≈0). Halves executed at midpoint 2024-03-30 as registered. |
| 5 | n-floors (episode-clustered, INSUFFICIENT-POWER where unmet) | **PASS** | K1 floor honored (arm episodes ≥100 under both columns). No borrowing from stamped rows. |
| 6 | Honesty surface (verdict-first, plain-English box, stamps, board_rank_unresolved) | **PARTIAL** | RESULTS.md leads with verdict; plain-English box present; mandatory stamp text present. But `board_rank_unresolved` descriptive line absent (A3) and proxy-column substitutions undocumented (A4). |

---

## Recompute log (independent, against `data/replay/replay_boarded.parquet`)

Reproduced to <0.01% (`tier_cascade` reading — matches runner):
- ARMED-continuation: n=10,521, episodes=5,838, P(clean8_21)=0.27897 ✓
- PRIME: n=15,145, episodes=7,312, P(clean8_21)=0.33384 ✓
- T1 Δ = −0.05487 ✓ ; stop-out Δ = +0.00597 ✓ ; DEAD_MONEY 0.1969 vs 0.1618 ✓
- T4 Δ = −0.0676 (above_200 True 0.25319 vs False 0.32079) ✓
- BH q-values = [0, 0.308, 0.8184, 0, 0.308] ✓
- Survivor census: 0 stamped / 961,656 unstamped ✓ ; verdict-grade fires 49,939 ✓

Divergent (correct `align_tier` reading — the PREREG-registered column):
- ARMED-continuation: n=1,752, episodes=1,322, P=0.30651
- PRIME: n=5,448, episodes=3,846, P=0.33443
- **T1 Δ = −0.02793** (boot p≈0.049), stop-out Δ=+0.0106, halves −0.0146 / −0.0539, per-name
  majority 410/642=0.639 → **H-MISLABEL**, no gap.

Window: last fire signal_date = 2025-12-29 (not 2026-07-02, see A2).

---

## Bottom line for the Fable orchestrator

The runner's "PREREG decision-table gap → blocker" is **not a real gap**. It is produced by
partitioning on `tier_cascade` (T1/T2/T3, the confluence cascade) instead of the PREREG-registered
`align_tier` (PRIME/ARMED/APPROACHING, per §3/§9 and sibling study P1.1). On the correct column
the differential is −2.79pp — below the 5pp materiality bar — and PREREG §6 resolves it as
**H-MISLABEL** with no ambiguity. Recommended action: reject the blocker, direct a re-run on
`align_tier`, and expect an H-MISLABEL verdict (relabel into an explicit continuation lane; no
gate change, no rank change). The T4 sub-partition finding (below-200 continuation fires grade
better) should be re-checked on the corrected arm before any ruling, as it too was computed on
the `tier_cascade`-defined ARMED-continuation population.
